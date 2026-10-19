import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from workers.ads_runtime_check import check_configuration


class Command(BaseCommand):
    help='외부 접속 없이 광고 설정만 점검합니다. 저장소/인증 연결 완료로 표시하지 않습니다.'
    requires_system_checks=[]
    requires_migrations_checks=False
    def handle(self,*args,**options):
        checks=check_configuration()
        checks['shared_url_present']=bool(settings.ADS_COMMON_API_URL)
        checks['shared_secret_present']=bool(settings.ADS_INTERNAL_SECRET)
        self.stdout.write(json.dumps({'configuration':checks,'connections_verified':False}))
        if not all(checks.values()):raise CommandError('ads_configuration_incomplete')
