import time
from django.conf import settings
from django.core.management.base import BaseCommand
from backend.recommendation.worker import run_one, warm_current_catalog


class Command(BaseCommand):
    help = 'Run the C recommendation worker; PostgreSQL required for multiple workers.'
    def add_arguments(self,parser): parser.add_argument('--once',action='store_true')
    def handle(self,*args,**options):
        next_warm = 0
        while True:
            if not options['once'] and time.monotonic() >= next_warm:
                warm_current_catalog()
                next_warm = time.monotonic() + 5
            processed=run_one()
            if options['once']: return
            if not processed: time.sleep(settings.RECOMMENDATION_WORKER_IDLE_SECONDS)
