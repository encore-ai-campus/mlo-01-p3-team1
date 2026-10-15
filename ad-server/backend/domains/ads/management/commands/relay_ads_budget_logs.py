"""예산 검증 상태의 로그만 전달하며 예산 판정이나 사용량을 재계산하지 않습니다."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from domains.ads.errors import DomainError
from repositories.ads_policy_mongo import get_ads_policy_repository
from workers.ads_log_relay import AdsLogRelay, get_log_sink


def run_configured_budget_relay(limit=20):
    sink = get_log_sink()
    repository = get_ads_policy_repository()
    worker = AdsLogRelay(
        repository.database["ad_budget_states"],
        sink,
        is_test=repository.is_test,
        claim_seconds=getattr(settings, "ADS_LOG_RELAY_CLAIM_SECONDS", 30),
        retry_seconds=getattr(settings, "ADS_LOG_RELAY_RETRY_SECONDS", 30),
    )
    return worker.run_once(limit)


class Command(BaseCommand):
    help = "광고 예산 검증 로그를 공통 PostgreSQL sink로 한 batch 전달합니다."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        try:
            counts = run_configured_budget_relay(options["limit"])
        except (DomainError, ValueError) as error:
            raise CommandError(str(error)) from None
        self.stdout.write(
            "광고 예산 로그 전달: " + ", ".join(f"{name}={count}" for name, count in counts.items())
        )
