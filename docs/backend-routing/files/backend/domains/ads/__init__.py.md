# backend/domains/ads/__init__.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 역할: 광고 도메인을 Python 패키지로 구성합니다.
- 정의된 클래스·함수: 없음.

Django 앱 등록은 `apps.py`, 첫 관리 단계의 업무 처리는 `service.py`, 입력 검증은 `validation.py`, 오류는 `errors.py`에 있습니다. 실제 저장 어댑터는 `backend/repositories/ads_mongo.py`와 연결합니다. 로컬 점검 연결은 `mongo.py`, 스키마 정의는 `schemas/management_manifest.json`에 있습니다.
