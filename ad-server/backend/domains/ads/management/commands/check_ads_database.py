from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from domains.ads.mongo import local_client, require_primary


class Command(BaseCommand):
    help = "로컬 광고 MongoDB primary와 실제 트랜잭션 시작/읽기/종료를 점검합니다."

    def handle(self, *args, **options):
        try:
            with local_client() as client:
                hello = require_primary(client)
                database = client[settings.ADS_MONGODB_DATABASE]
                with client.start_session() as session:
                    with session.start_transaction():
                        database.ads.find_one({}, {"_id": 1}, session=session)
                message = f"MongoDB {hello['setName']}: primary/transaction OK"
                self.stdout.write(self.style.SUCCESS(message))
        except PyMongoError as exc:
            raise CommandError(f"MongoDB 점검 실패: {type(exc).__name__}") from None
