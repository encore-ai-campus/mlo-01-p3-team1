import time
from django.core.management.base import BaseCommand
from backend.recommendation.worker import run_one


class Command(BaseCommand):
    help = 'Run the C recommendation worker; PostgreSQL required for multiple workers.'
    def add_arguments(self,parser): parser.add_argument('--once',action='store_true')
    def handle(self,*args,**options):
        while True:
            processed=run_one()
            if options['once']: return
            if not processed: time.sleep(1)
