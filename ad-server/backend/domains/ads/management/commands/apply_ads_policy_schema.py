import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from domains.ads.mongo import local_client, require_primary

POLICY_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "schemas" / "policy_manifest.json"


def load_policy_manifest():
    return json.loads(POLICY_MANIFEST_PATH.read_text(encoding="utf-8"))


class Command(BaseCommand):
    help = "광고 예산·일일 집계 두 컬렉션을 점검합니다. --apply는 로컬 _dev DB만 허용합니다."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        manifest = load_policy_manifest()
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
                        database[name].create_index(
                            [(key, order) for key, order in index["keys"]],
                            name=index["name"],
                            unique=index.get("unique", False),
                        )
                self.stdout.write(self.style.SUCCESS("로컬 광고 예산·집계 스키마 적용 완료"))
        except PyMongoError as error:
            raise CommandError(f"MongoDB 스키마 적용 실패: {type(error).__name__}") from None
