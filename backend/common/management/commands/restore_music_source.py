from django.core.management.base import BaseCommand,CommandError
from backend.common.models import MusicSource
from backend.common.music_archive import restore
from backend.recommendation.errors import DomainError


class Command(BaseCommand):
    help='등록한 음악 원본의 S3 version을 새 로컬 파일로 복원하고 해시 검증합니다.'

    def add_arguments(self,parser):
        parser.add_argument('sha256');parser.add_argument('target')

    def handle(self,*args,**options):
        source=MusicSource.objects.filter(pk=options['sha256']).first()
        if source is None:raise CommandError('music_source_not_found')
        try:restore(source.archive,options['target'])
        except DomainError as error:raise CommandError(error.code) from None
        self.stdout.write('music_source_restored_and_verified')
