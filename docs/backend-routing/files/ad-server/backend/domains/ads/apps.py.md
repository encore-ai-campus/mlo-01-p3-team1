# ad-server/backend/domains/ads/apps.py

- 작성일: 2026-10-15
- 역할: 광고 도메인을 Django 앱으로 등록합니다.

```python
class AdsConfig(AppConfig)
```

`name="domains.ads"`와 기본 자동 필드 타입을 정의합니다. `config/settings.py`의 `INSTALLED_APPS`에 연결되어 Django가 광고 관리 명령을 검색할 수 있게 합니다. MongoDB 컬렉션을 Django ORM 모델로 변환하지 않습니다.
