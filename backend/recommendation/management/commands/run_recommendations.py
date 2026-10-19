import time
import logging
import os
import re
import signal
import socket
import threading
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections, connection
from backend.recommendation.dispatch import configuration
from backend.recommendation.errors import DomainError
from backend.recommendation.worker import run_one, warm_current_catalog


class Command(BaseCommand):
    help = 'Run the C recommendation worker; PostgreSQL required for multiple workers.'
    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true')
        parser.add_argument('--queue', choices=['rule', 'gemini', 'all'], default=settings.RECOMMENDATION_QUEUE)
        parser.add_argument('--worker-id', default=settings.RECOMMENDATION_WORKER_ID)

    def handle(self,*args,**options):
        invalid = [key for key, valid in configuration().items() if not valid]
        if invalid: raise CommandError('invalid_worker_settings: ' + ','.join(invalid))
        if not settings.LOCAL_DEMO and connection.vendor != 'postgresql':
            raise CommandError('PostgreSQL is required outside single-worker local demo mode')
        if options['queue'] == 'gemini' and not settings.GEMINI_ENABLED:
            raise CommandError('Gemini is disabled; do not start a dedicated Gemini worker')
        if options['queue'] in ('gemini', 'all') and settings.GEMINI_ENABLED:
            budget = os.environ.get('GEMINI_MAX_OUTPUT_TOKENS', '')
            if not os.environ.get('GEMINI_API_KEY') or not budget.isdecimal() or int(budget) <= 0:
                raise CommandError('Gemini worker requires a private API key and positive output token budget')
        worker_id = options['worker_id'] or f'{socket.gethostname()}:{os.getpid()}:{options["queue"]}'
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', worker_id):
            raise CommandError('worker_id must contain 1-160 ASCII letters, digits or _.:-')
        stopped = threading.Event()
        previous = {}
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, lambda *_: stopped.set())
        logger = logging.getLogger('recommendation.worker')
        next_warm = 0
        logger.info('recommendation_worker_start worker_id=%s queue=%s', worker_id, options['queue'])
        try:
            while not stopped.is_set():
                close_old_connections()
                try:
                    if not options['once'] and time.monotonic() >= next_warm:
                        next_warm = time.monotonic() + 5
                        try: warm_current_catalog()
                        except DomainError as exc:
                            logger.warning('recommendation_warmup_failed code=%s', exc.code)
                    if stopped.is_set(): break
                    processed = run_one(options['queue'], worker_id)
                except Exception as exc:
                    if options['once']: raise
                    # Connection/provider exceptions can contain credentials or request bodies.
                    logger.error('recommendation_worker_error worker_id=%s type=%s', worker_id, type(exc).__name__)
                    if isinstance(exc, DatabaseError): close_old_connections()
                    processed = False
                if options['once']: return
                if not processed: stopped.wait(settings.RECOMMENDATION_WORKER_IDLE_SECONDS)
        finally:
            for signum, handler in previous.items(): signal.signal(signum, handler)
            close_old_connections()
            logger.info('recommendation_worker_stopped worker_id=%s', worker_id)
