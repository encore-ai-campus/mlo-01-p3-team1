"""5분 정책 작업의 재시도 가능한 반복 실행 진입점입니다."""

import json
import signal
import threading

from django.core.management.base import BaseCommand, CommandError

from workers.ads_jobs import AdsWorkerGroup, configured_jobs


class Command(BaseCommand):
    help = "MongoDB 예산 검증·통계를 실행합니다. --watch는 실패 후에도 다음 주기를 시도합니다."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")

    def handle(self, *args, **options):
        group = AdsWorkerGroup(configured_jobs())
        if not options["watch"]:
            result = group.run_once()
            self.stdout.write(json.dumps(result, ensure_ascii=False))
            if any(value["status"] != "OK" for value in result.values()):
                raise CommandError(
                    "일부 광고 작업이 실패/대기 상태입니다. 위 상태 코드를 확인하세요."
                )
            return
        self.stdout.write("MongoDB 예산 검증·통계 300초 작업 시작. Ctrl+C로 종료하세요.")
        self.watch(group)
        self.stdout.write("광고 반복 작업을 종료했습니다.")

    def watch(self, group):
        stop = threading.Event()
        previous_handler = None
        manages_signals = threading.current_thread() is threading.main_thread()

        def request_stop(signum, frame):
            stop.set()

        if manages_signals:
            previous_handler = signal.signal(signal.SIGTERM, request_stop)
        try:
            try:
                group.start()
                # 시작/초기 오류 상태를 첫30초 출력까지 숨기지 않습니다.
                self.stdout.write(json.dumps(group.snapshot(), ensure_ascii=False))
                while not stop.wait(30):
                    self.stdout.write(json.dumps(group.snapshot(), ensure_ascii=False))
            except KeyboardInterrupt:
                pass
            finally:
                if not group.stop():
                    raise CommandError(
                        "종료 대기 중 정책 작업이 남았습니다. 다음 실행에서 저장 결과를 확인하세요."
                    )
        finally:
            if manages_signals:
                signal.signal(signal.SIGTERM, previous_handler)
