"""설정·MongoDB 스키마·내장 광고 로그의 읽기 전용 점검. 운영 수용 시험은 아닙니다."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.utils.module_loading import import_string
from pymongo import timeout

from api.ads_public_auth import load_public_policy
from domains.ads.public_service import AdsPublicService
from domains.ads.validation import utc_datetime, utc_string
from repositories.ads_policy_mongo import get_ads_policy_repository
from workers.ads_logs import inspect_logs

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "domains" / "ads" / "schemas"


def _callable_setting(name):
    value = getattr(settings, name, "")
    try:
        return callable(import_string(value)) if isinstance(value, str) and value else False
    except Exception:
        return False


def check_configuration():
    checks = {
        "mongo_uri_present": isinstance(settings.ADS_MONGODB_URI, str)
        and bool(settings.ADS_MONGODB_URI.strip()),
        "mongo_database_present": isinstance(settings.ADS_MONGODB_DATABASE, str)
        and bool(settings.ADS_MONGODB_DATABASE.strip()),
        "test_mode_valid": type(settings.ADS_IS_TEST) is bool,
        "admin_adapter_loadable": _callable_setting("ADS_ADMIN_AUTHORIZER"),
        "guest_adapter_loadable": _callable_setting("ADS_GUEST_CONTEXT_PROVIDER"),
    }
    try:
        AdsPublicService(
            SimpleNamespace(is_test=settings.ADS_IS_TEST),
            policy=load_public_policy(),
            signing_key=settings.ADS_DELIVERY_SIGNING_KEY,
            public_base_url=settings.ADS_PUBLIC_BASE_URL,
            is_test=settings.ADS_IS_TEST,
        )
        checks["public_policy_settings_valid"] = True
    except Exception:
        checks["public_policy_settings_valid"] = False
    return checks


def expected_collections():
    combined = {}
    for filename in ("management_manifest.json", "public_manifest.json", "policy_manifest.json"):
        combined.update(
            json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))["collections"]
        )
    return combined


def schema_issues(database):
    expected = expected_collections()
    actual = {
        item["name"]: item
        for item in database.list_collections(filter={"name": {"$in": list(expected)}})
    }
    issues = []
    for name, definition in expected.items():
        if name not in actual:
            issues.append({"collection": name, "code": "MISSING_COLLECTION"})
            continue
        options = actual[name].get("options", {})
        if (
            options.get("validator") != definition["validator"]
            or options.get("validationLevel", "strict") != "strict"
            or options.get("validationAction", "error") != "error"
        ):
            issues.append({"collection": name, "code": "VALIDATOR_MISMATCH"})
        indexes = database[name].index_information()
        for index in definition["indexes"]:
            stored = indexes.get(index["name"])
            if (
                stored is None
                or list(stored["key"]) != [tuple(pair) for pair in index["keys"]]
                or bool(stored.get("unique", False)) != bool(index.get("unique", False))
                or stored.get("partialFilterExpression") != index.get("partialFilterExpression")
                or stored.get("sparse", False)
                or stored.get("collation", {}).get("locale", "simple") != "simple"
            ):
                issues.append(
                    {"collection": name, "code": "INDEX_MISMATCH", "index": index["name"]}
                )
        if any("expireAfterSeconds" in index for index in indexes.values()):
            issues.append({"collection": name, "code": "UNEXPECTED_TTL"})
    return issues


def inspect_runtime(*, check_database=False, repository=None, now=None):
    now = utc_datetime(now or datetime.now(UTC))
    checks = check_configuration()
    report = {
        "scope": "CONFIG_AND_MONGODB_ONLY",
        "checked_at": utc_string(now),
        "is_test": settings.ADS_IS_TEST,
        "configuration": checks,
        "database": {"status": "NOT_CHECKED"},
        "shared_authentication_verified": False,
        "log_storage": "MONGODB",
    }
    if check_database:
        try:
            with timeout(10):
                repository = repository or get_ads_policy_repository()
                database = repository.database  # 기존 어댑터가 replica set primary를 확인합니다.
                issues = schema_issues(database)
                logs = inspect_logs(database, is_test=repository.is_test)
                invalid_logs = any(
                    row["missing_required"] or row["sample_invalid"] for row in logs.values()
                )
                report["database"] = {
                    "status": "CHECKS_PASSED" if not issues and not invalid_logs else "MISMATCH",
                    "schema_issues": issues,
                    "logs": logs,
                }
        except Exception as exc:
            report["database"] = {"status": "ERROR", "error_type": type(exc).__name__}
    report["status"] = (
        "CHECKS_PASSED"
        if all(checks.values()) and report["database"]["status"] == "CHECKS_PASSED"
        else "INCOMPLETE"
    )
    return report
