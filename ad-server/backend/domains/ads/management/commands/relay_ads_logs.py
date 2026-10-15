from django.core.management.base import BaseCommand, CommandError

from domains.ads.errors import DomainError
from workers.ads_log_relay import run_configured_relay


class Command(BaseCommand):
    help = "광고 관리 로그를 설정된 공통 PostgreSQL sink로 한 batch 전달합니다."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        try:
            counts = run_configured_relay(options["limit"])
        except (DomainError, ValueError) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(
            "광고 로그 전달: " + ", ".join(f"{name}={count}" for name, count in counts.items())
        )
