# ad-server/backend/config/wsgi.py

- 작성일: 2026-10-15
- 역할: WSGI 서버가 사용할 Django `application` 객체를 초기화합니다.
- 정의된 클래스·함수: 없음. 모듈 수준에서 Django WSGI 앱을 로딩합니다.

`DJANGO_SETTINGS_MODULE`이 없으면 `config.settings`를 지정합니다. 광고 개발 준비 명령의 WSGI 앱과 같은 설정을 사용하며 DB 점검을 직접 수행하지 않습니다.
