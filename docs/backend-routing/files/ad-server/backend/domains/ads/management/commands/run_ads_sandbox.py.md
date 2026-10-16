# ad-server/backend/domains/ads/management/commands/run_ads_sandbox.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/run_ads_sandbox.py)

`sandbox.py`로 호출하는 전용 개발 명령입니다. `config.sandbox_settings`만 허용하고 sandbox/test DB/loopback URI·primary를 확인한 뒤 관리3·공개5·정책2 manifest를 로컬 DB에 적용합니다. 실행별 접근 코드는 Git에서 제외한 저장소 루트 `.local/ads-sandbox/access.txt`에 씁니다.

`--port`는 기본8001·1~65535이며 HTTP 서버를 `127.0.0.1`에만 엽니다. `--start-mongo`를 명시하면 `--mongod` 또는 PATH/로컬 도구의 실행 파일을 사용합니다. 이미 응답하는 MongoDB는 소유/초기화하지 않고 사용 가능한 primary 검사를 진행합니다. 새 프로세스는 전용 자료 경로·loopback·ads-rs와 Windows 숨김 옵션으로 시작하고 준비 실패 또는 종료 시 직접 시작한 프로세스만 정리합니다.

`start_worker`의 최초 검증 후300초 작업과 WSGI 서버를 실행하며 Ctrl+C/finally에서 worker를 중단합니다. `QuietHandler`는 query proof가 기본 access log에 남지 않도록 요청 로그를 출력하지 않습니다. 계정/공유 PostgreSQL·AWS·운영 서버 기동 명령이 아닙니다.

명령의 스키마 적용은 세 manifest의 순차 적용이며 전체 DDL의 단일 트랜잭션이라고 설명하지 않습니다. 기동 출력과 예외에는 실제 접속 URI·접근 코드 본문을 노출하지 않습니다.

## AST 시그니처

```python
class QuietHandler(WSGIRequestHandler)
QuietHandler.log_message(self, format, *args)
class LocalServer(ThreadingMixIn, WSGIServer)
start_mongo(executable, state_dir)
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
