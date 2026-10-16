"""MongoDB 5분 예산 검증의 실패 후 재시도·상태·종료를 관리합니다."""

import re
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

from domains.ads.budget_service import AdsBudgetService
from domains.ads.errors import DomainError
from repositories.ads_policy_mongo import get_ads_policy_repository

POLICY_INTERVAL_SECONDS = 300


def refresh_policy():
    return AdsBudgetService(get_ads_policy_repository()).run_once()


@dataclass(frozen=True)
class AdsJob:
    name: str
    callback: object
    interval_seconds: int

    def __post_init__(self):
        if (
            not isinstance(self.name, str)
            or not re.fullmatch(r"[a-z_]{1,40}", self.name)
            or not callable(self.callback)
        ):
            raise ValueError("작업 이름과 callback을 확인하세요.")
        if (
            type(self.interval_seconds) is not int
            or not 1 <= self.interval_seconds <= threading.TIMEOUT_MAX
        ):
            raise ValueError("작업 간격은 양의 정수 초여야 합니다.")


def configured_jobs():
    return (AdsJob("policy", refresh_policy, POLICY_INTERVAL_SECONDS),)


def _stamp():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class AdsJobRunner:
    def __init__(self, job):
        self.job = job
        self._lock = threading.Lock()
        self._state = {
            "name": job.name,
            "interval_seconds": job.interval_seconds,
            "status": "NOT_STARTED",
            "last_started_at": None,
            "last_finished_at": None,
            "last_succeeded_at": None,
            "counts": None,
            "error": None,
        }

    def snapshot(self):
        with self._lock:
            return deepcopy(self._state)

    def run_once(self):
        with self._lock:
            self._state.update(status="RUNNING", last_started_at=_stamp(), counts=None, error=None)
        try:
            result = self.job.callback()
            allowed = {
                "ads_checked",
                "blocked",
                "metrics_rows",
                "failed",
            }
            if not isinstance(result, dict) or set(result) - allowed:
                raise ValueError("작업 결과 형식이 올바르지 않습니다.")
            if any(type(value) is not int or value < 0 for value in result.values()):
                raise ValueError("작업 결과는 음이 아닌 정수여야 합니다.")
            degraded = result.get("failed", 0) > 0
            with self._lock:
                self._state.update(
                    status="DEGRADED" if degraded else "OK",
                    counts=dict(result),
                    last_finished_at=_stamp(),
                )
                if not degraded:
                    self._state["last_succeeded_at"] = self._state["last_finished_at"]
        except Exception as exc:
            code = exc.code if isinstance(exc, DomainError) else None
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", code):
                code = None
            with self._lock:
                self._state.update(
                    status="ERROR",
                    last_finished_at=_stamp(),
                    error={"type": type(exc).__name__, "code": code},
                )
        return self.snapshot()

    def watch(self, stop):
        due = time.monotonic()
        while not stop.is_set():
            self.run_once()
            due += self.job.interval_seconds
            now = time.monotonic()
            if due <= now:
                # 이미 지난 실행을 연속 재생하여 장애 후 요청 폭주를 만들지 않습니다.
                due = now + self.job.interval_seconds
            if stop.wait(due - now):
                break


class AdsWorkerGroup:
    def __init__(self, jobs):
        jobs = tuple(jobs)
        if not jobs or len({job.name for job in jobs}) != len(jobs):
            raise ValueError("고유한 이름의 작업이 필요합니다.")
        self.runners = [AdsJobRunner(job) for job in jobs]
        self._stop = threading.Event()
        self._threads = []

    def snapshot(self):
        return {runner.job.name: runner.snapshot() for runner in self.runners}

    def run_once(self):
        if any(thread.is_alive() for thread in self._threads):
            raise RuntimeError("반복 실행 중 단발 실행을 겹칠 수 없습니다.")
        for runner in self.runners:
            runner.run_once()
        return self.snapshot()

    def start(self):
        if any(thread.is_alive() for thread in self._threads):
            raise RuntimeError("광고 작업이 이미 실행 중입니다.")
        self._stop.clear()
        self._threads = [
            threading.Thread(
                target=runner.watch, args=(self._stop,), name=f"ads-{runner.job.name}", daemon=True
            )
            for runner in self.runners
        ]
        for thread in self._threads:
            thread.start()

    def stop(self, timeout=10):
        self._stop.set()
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in self._threads)
