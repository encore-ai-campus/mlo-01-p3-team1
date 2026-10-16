"""확정된 광고 보관 기간의 읽기 점검 명령입니다. --apply/삭제 모드는 없습니다."""

import json

from django.core.management.base import BaseCommand, CommandError
from pymongo import timeout

from repositories.ads_policy_mongo import get_ads_policy_repository
from workers.ads_retention import inspect_retention


class Command(BaseCommand):
    help = "광고 보관 기산점·기간 도래·참조를 읽기만 합니다. 기간 도래는 삭제 허용이 아닙니다."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if type(options["limit"]) is not int or not 1 <= options["limit"] <= 1000:
            raise CommandError("limit는1~1000 정수여야 합니다.")
        try:
            with timeout(10):
                repository = get_ads_policy_repository()
                report = inspect_retention(
                    repository.database, is_test=repository.is_test, limit=options["limit"]
                )
        except Exception as exc:
            raise CommandError(f"MongoDB 보관 점검 실패: {type(exc).__name__}") from None
        self.stdout.write(json.dumps(report, ensure_ascii=False))
        if report["status"] != "REVIEW_READY":
            raise CommandError("보관 기산점이 없거나 잘못된 표본 자료를 확인하세요.")
