# backend/recommendation/service.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/recommendation/service.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

기존 소유·멱등·계열 잠금과 부모 카탈로그 고정을 유지합니다. current_catalog는 READY/is_test 범위와 로컬 고정 재생 subset 제외 후 publication.id 내림차순을 사용합니다. 동일 시각·시계 역행에도 새 추천/사전 로딩이 등록 순서를 공유합니다.

## AST 시그니처

```python
event(kind, family, request_id, payload)
owned(model, owner, pk, lock=False)
busy(family)
mutate(owner, scope, key, data, operation)
current_catalog()
catalog()
enqueue(family, request_id, parent=None, weather_refresh=False)
refresh_weather(owner, playlist_id, key, data, request_id)
basic(owner, key, data, request_id)
exclusions(owner, family_id, key=None, data=None, request_id='')
regenerate(owner, playlist_id, key, data, request_id)
approve(owner, playlist_id, key, data, request_id)
```
