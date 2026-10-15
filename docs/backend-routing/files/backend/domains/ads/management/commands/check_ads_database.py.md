# backend/domains/ads/management/commands/check_ads_database.py

- 작성일: 2026-10-15
- 역할: 로컬 광고 MongoDB의 primary 및 세션/트랜잭션 읽기를 점검합니다.

```python
class Command(BaseCommand)
Command.handle(self, *args, **options)
```

추가 CLI 입력은 없습니다. `handle`은 `local_client`의 loopback·`_dev` 조건과 `require_primary`의 `ads-rs` 조건을 확인합니다. 세션에서 트랜잭션을 시작하고 `ads.find_one`의 `_id` 읽기를 수행한 뒤 정상 종료합니다. 결과는 primary/transaction OK 메시지이며 PyMongo 오류는 예외 타입을 담은 `CommandError`로 변환합니다.

업무 데이터 쓰기, 스키마 일치, 장애 복구나 공유/운영 환경 연결을 검증하는 명령은 아닙니다.
