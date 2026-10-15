# backend/domains/ads/management/commands/run_ads_dev.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../backend/domains/ads/management/commands/run_ads_dev.py)

공통 DB migration 적용 전 로컬 광고 API를 확인할 WSGI 개발 서버 명령입니다. `--port` 입력은 기본 8000의 정수이며 DEBUG와 1~65535를 검사하고 127.0.0.1에만 서버를 엽니다. Ctrl+C로 종료합니다.

Django 설정·미들웨어·URL 구성을 로딩합니다. health/schema 외의 관리 요청도 등록돼 있으나 공유 ADMIN 어댑터·CSRF 없이 허용하지 않습니다. 공통 migration은 이 명령에서 검사/적용하지 않습니다. 공개 배포용 서버나 관리자 UI를 제공하지 않습니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
