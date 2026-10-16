"""광고 MongoDB 로그 조회 진입점입니다. 외부 전달이나 자료 변경은 하지 않습니다."""

import json

from django.core.management.base import BaseCommand, CommandError
from pymongo import timeout

from repositories.ads_policy_mongo import get_ads_policy_repository
from workers.ads_logs import inspect_logs


class Command(BaseCommand):
    help = "MongoDB 광고 로그 건수와 제한된 표본의 hash를 읽기 전용으로 확인합니다."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("limit는 1~100이어야 합니다.")
        try:
            with timeout(10):
                repository = get_ads_policy_repository()
                report = inspect_logs(
                    repository.database, is_test=repository.is_test, limit=options["limit"]
                )
        except Exception as exc:
            raise CommandError(f"MongoDB 로그 점검 실패: {type(exc).__name__}") from None
        self.stdout.write(json.dumps(report, ensure_ascii=False))
        if any(row["missing_required"] or row["sample_invalid"] for row in report.values()):
            raise CommandError("광고 로그 누락 또는 표본 hash 오류를 확인하세요.")
