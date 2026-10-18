from django.core.management.base import BaseCommand
from backend.common.events import ingest
from backend.common.models import StreamRecord


class Command(BaseCommand):
    help='보관된 PostgreSQL 원본으로 멱등 재처리합니다. 원본 ID/offset을 변경하지 않습니다.'

    def handle(self,*args,**options):
        count=0
        for raw in StreamRecord.objects.order_by('received_at').iterator(chunk_size=100):
            ingest(raw.envelope,raw.pk);count+=1
        self.stdout.write(f'replayed_records={count}')
