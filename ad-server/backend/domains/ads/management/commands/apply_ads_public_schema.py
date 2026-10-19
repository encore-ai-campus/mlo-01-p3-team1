from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from domains.ads.mongo import local_client, require_primary
from domains.ads.public_schema import load_public_manifest


class Command(BaseCommand):
    help = "공개 광고의 추가 다섯 컬렉션을 점검합니다. --apply는 로컬 _dev DB만 허용합니다."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        manifest = load_public_manifest()
        for name, definition in manifest["collections"].items():
            self.stdout.write(f"{name}: validator + {len(definition['indexes'])} indexes")
        if not options["apply"]:
            self.stdout.write("미적용: 로컬 개발 DB에 적용하려면 --apply를 사용하세요.")
            return
        try:
            with local_client() as client:
                require_primary(client)
                database = client[settings.ADS_MONGODB_DATABASE]
                existing = set(database.list_collection_names())
                for name, definition in manifest["collections"].items():
                    if name in existing:
                        database.command(
                            "collMod",
                            name,
                            validator=definition["validator"],
                            validationLevel="strict",
                            validationAction="error",
                        )
                    else:
                        database.create_collection(
                            name,
                            validator=definition["validator"],
                            validationLevel="strict",
                            validationAction="error",
                        )
                    for index in definition["indexes"]:
                        index_options = {
                            "name": index["name"],
                            "unique": index.get("unique", False),
                        }
                        if "partialFilterExpression" in index:
                            index_options["partialFilterExpression"] = index[
                                "partialFilterExpression"
                            ]
                        database[name].create_index(
                            [(key, order) for key, order in index["keys"]], **index_options
                        )
                self.stdout.write(self.style.SUCCESS("로컬 공개 광고 스키마 적용 완료"))
        except PyMongoError as exc:
            raise CommandError(f"MongoDB 스키마 적용 실패: {type(exc).__name__}") from None
