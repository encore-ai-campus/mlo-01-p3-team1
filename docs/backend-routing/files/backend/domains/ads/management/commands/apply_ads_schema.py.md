# backend/domains/ads/management/commands/apply_ads_schema.py

- 작성일: 2026-10-15
- 역할: 광고 관리 3컬렉션의 validator/index를 미리 보고 로컬 개발 DB에 적용합니다.

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```

`add_arguments`는 `--apply` 플래그를 추가합니다. `handle`은 manifest를 읽어 컬렉션별 validator/index 개수를 출력합니다. 기본 실행은 DB 접속이나 변경 없이 종료합니다.

`--apply` 입력 시 `local_client`와 `require_primary`로 loopback·`_dev` DB·`ads-rs` primary를 확인한 뒤 기존 컬렉션은 `collMod`, 없는 컬렉션은 생성하고 index를 설정합니다. 검증은 `strict`/`error`로 적용합니다. 출력은 적용 완료 메시지이며 PyMongo 실패는 예외 타입만 담은 `CommandError`로 변환합니다.

스키마 적용은 여러 컬렉션에 걸친 원자적 트랜잭션이 아닙니다. 실패하면 일부 적용 가능성을 확인하고 재실행해야 합니다. 업무 데이터 생성·CRUD·공유 DB 적용은 이 명령의 범위에 포함하지 않습니다.
