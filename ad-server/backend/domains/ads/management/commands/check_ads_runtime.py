import json

from django.core.management.base import BaseCommand, CommandError

from workers.ads_runtime_check import inspect_runtime


class Command(BaseCommand):
    help = "광고 설정을 점검합니다. --database는 MongoDB 스키마/로그 대기 현황을 읽기만 합니다."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--database", action="store_true")

    def handle(self, *args, **options):
        report = inspect_runtime(check_database=options["database"])
        self.stdout.write(json.dumps(report, ensure_ascii=False))
        if report["status"] != "CHECKS_PASSED":
            raise CommandError("광고 연결의 미확인/누락 항목이 있습니다. JSON 상태를 확인하세요.")
