"""관리 스키마와 분리한 공개 광고 상태의 로컬 점검용 manifest 진입점."""

import json
from pathlib import Path

PUBLIC_MANIFEST_PATH = Path(__file__).with_name("schemas") / "public_manifest.json"


def load_public_manifest() -> dict:
    return json.loads(PUBLIC_MANIFEST_PATH.read_text(encoding="utf-8"))
