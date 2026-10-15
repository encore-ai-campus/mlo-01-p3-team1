import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from pymongo import MongoClient
from pymongo.uri_parser import parse_uri

MANIFEST_PATH = Path(__file__).with_name("schemas") / "management_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def local_client() -> MongoClient:
    """개발 점검 명령 전용. 운영/공유 MongoDB 접근을 허용하지 않습니다."""
    uri = settings.ADS_MONGODB_URI
    if not uri:
        raise CommandError("ADS_MONGODB_URI를 설정하세요.")
    parsed = parse_uri(uri)
    if any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in parsed["nodelist"]):
        raise CommandError("개발 점검 명령은 로컬 MongoDB만 지원합니다.")
    if not settings.ADS_MONGODB_DATABASE.endswith("_dev"):
        raise CommandError("개발 점검 DB 이름은 _dev로 끝나야 합니다.")
    return MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)


def require_primary(client: MongoClient) -> dict:
    hello = client.admin.command("hello")
    if hello.get("setName") != "ads-rs" or not hello.get("isWritablePrimary"):
        raise CommandError("ads-rs primary가 필요합니다. standalone은 지원하지 않습니다.")
    return hello
