"""현재 프로세스의 로컬 검증 작업 상태. 운영 스케줄러·로그 sink는 아닙니다."""

import threading
import time
from datetime import UTC, datetime

from django.conf import settings
from pymongo.errors import PyMongoError
from pymongo.uri_parser import parse_uri

from domains.ads.budget_service import AdsBudgetService
from domains.ads.errors import DomainError
from repositories.ads_policy_mongo import get_ads_policy_repository

_batch_lock = threading.Lock()
_state_lock = threading.Lock()
_stop = threading.Event()
_thread = None
_state = {"last_started_at": None, "last_succeeded_at": None, "last_error": None}


def _stamp():
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def require_sandbox():
    if (
        not getattr(settings, "IS_ADS_SANDBOX", False)
        or settings.ADS_IS_TEST is not True
        or settings.ADS_MONGODB_DATABASE != "ads_sandbox_dev"
    ):
        raise DomainError("SANDBOX_LOCAL_ONLY", "로컬 시험 도구에서만 실행할 수 있습니다.", 403)
    uri = settings.ADS_MONGODB_URI
    try:
        if not uri.startswith("mongodb://"):
            raise ValueError
        parsed = parse_uri(uri)
        if any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in parsed["nodelist"]):
            raise ValueError
        if parsed["options"].get("directConnection") is not True:
            raise ValueError
    except (TypeError, ValueError, PyMongoError):
        raise DomainError("SANDBOX_LOCAL_ONLY", "로컬 MongoDB만 사용할 수 있습니다.", 403) from None


def worker_status():
    with _state_lock:
        return {
            "running": _thread is not None and _thread.is_alive(),
            "interval_seconds": 300,
            **_state,
        }


def refresh_policy():
    require_sandbox()
    if not _batch_lock.acquire(blocking=False):
        raise DomainError("SANDBOX_BUSY", "이미 검증 중입니다. 잠시 뒤 다시 확인하세요.", 409)
    try:
        with _state_lock:
            _state["last_started_at"] = _stamp()
        result = AdsBudgetService(get_ads_policy_repository()).run_once()
        with _state_lock:
            _state["last_succeeded_at"] = _stamp()
            _state["last_error"] = None
        return result
    except Exception as exc:
        # 예외 문자열·접속 URI·delivery proof는 브라우저나 로그에 반환하지 않습니다.
        with _state_lock:
            _state["last_error"] = type(exc).__name__
        raise
    finally:
        _batch_lock.release()


def _loop():
    due = time.monotonic() + 300
    while not _stop.wait(max(0, due - time.monotonic())):
        try:
            refresh_policy()
        except Exception:
            pass  # worker_status에 실패를 남기고 다음 주기에 재시도합니다.
        due += 300
        if due < time.monotonic():
            due = time.monotonic() + 300


def start_worker():
    global _thread
    require_sandbox()
    if _thread is not None and _thread.is_alive():
        return
    refresh_policy()
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="ads-sandbox-budget", daemon=True)
    _thread.start()


def stop_worker():
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=10)
