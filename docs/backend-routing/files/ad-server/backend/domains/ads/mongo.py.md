# ad-server/backend/domains/ads/mongo.py

- 작성일: 2026-10-15
- 역할: 관리 명령용 manifest 로딩과 로컬 MongoDB 연결 조건을 공통으로 검사합니다.

```python
load_manifest() -> dict
local_client() -> MongoClient
require_primary(client: MongoClient) -> dict
```

- `load_manifest`: `schemas/management_manifest.json`의 UTF-8 JSON을 읽어 dict를 반환합니다.
- `local_client`: 설정의 광고 MongoDB URI와 DB명을 검사하고 timezone-aware `MongoClient`를 반환합니다. URI가 없거나 loopback 이외의 호스트, `_dev`로 끝나지 않는 DB명은 `CommandError`로 차단합니다. 이 클라이언트는 운영 연결 어댑터가 아닌 로컬 점검 전용입니다.
- `require_primary`: 입력 클라이언트로 `hello`를 실행하여 `ads-rs`의 쓰기 가능한 primary인지 검사하고 응답 dict를 반환합니다. standalone이나 다른 replica set은 `CommandError`로 차단합니다.

`apply_ads_schema`와 `check_ads_database`가 이 함수들을 사용합니다. 접속 실패의 PyMongo 오류는 각 명령에서 처리합니다.
