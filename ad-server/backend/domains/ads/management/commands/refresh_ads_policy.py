"""광고 예산 검증·통계 배치를 한 번 또는 명시적인 반복 모드로 실행합니다."""

import time

from django.core.management.base import BaseCommand, CommandError

from domains.ads.budget_service import AdsBudgetService
from domains.ads.errors import DomainError
from repositories.ads_policy_mongo import get_ads_policy_repository

REFRESH_INTERVAL_SECONDS = 300


class Command(BaseCommand):
    help = "광고 예산 검증·통계를 한 번 갱신합니다. --watch는 300초 간격으로 반복합니다."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")

    def handle(self, *args, **options):
        watch = options["watch"]
        if watch:
            self.stdout.write("광고 정책 검증을 300초마다 반복합니다. Ctrl+C로 종료하세요.")
        try:
            service = AdsBudgetService(get_ads_policy_repository())
            next_due = time.monotonic()
            while True:
                counts = service.run_once()
                self.stdout.write(
                    "광고 정책 갱신: "
                    + ", ".join(f"{name}={count}" for name, count in counts.items())
                )
                if not watch:
                    break
                next_due += REFRESH_INTERVAL_SECONDS
                now = time.monotonic()
                if next_due < now:
                    next_due = now
                time.sleep(max(0, next_due - now))
        except KeyboardInterrupt:
            self.stdout.write("광고 정책 검증 반복을 종료했습니다.")
        except (DomainError, ValueError) as error:
            raise CommandError(str(error)) from None
