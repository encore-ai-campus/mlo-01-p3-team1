# ad-server/backend/sandbox.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../ad-server/backend/sandbox.py)

독립 로컬 광고 확인 도구의 실행 진입점입니다. `DJANGO_SETTINGS_MODULE`을 `config.sandbox_settings`로 고정하고 사용자 인자를 `run_ads_sandbox` 명령에 전달합니다.

저장소 루트에서 `ad-server/backend/.venv/Scripts/python.exe ad-server/backend/sandbox.py --start-mongo`로 사용할 수 있습니다. 일반 `manage.py`·운영 설정/URLconf·기존 `.env`를 바꾸지 않습니다. 실제 DB 기동·스키마/worker·HTTP 실행과 종료는 명령 모듈이 담당합니다.

## AST 시그니처

```python
main()
```
