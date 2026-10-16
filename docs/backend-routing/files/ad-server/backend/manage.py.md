# ad-server/backend/manage.py

- 작성일: 2026-10-15
- 역할: CLI 인수를 Django 관리 명령으로 전달하는 실행 진입점입니다.

```python
main() -> None
```

입력은 `sys.argv`, 출력은 각 관리 명령의 실행 결과입니다. `DJANGO_SETTINGS_MODULE`이 없으면 `config.settings`를 지정합니다. 광고 스키마/DB 점검과 테스트 명령이 이 진입점을 사용합니다.
