# ad-server/backend/config/sandbox_settings.py

- 작성일: 2026-10-15
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/config/sandbox_settings.py)

기존 `config.settings`·`.env`와 독립적인 로컬 광고 확인 도구 설정입니다. import 시 새로운 Django 서명키·접근 코드·실행 instance·delivery 서명키를 생성하며 실제 값은 문서에 기록하지 않습니다.

`IS_ADS_SANDBOX=True`, `ADS_IS_TEST=True`, DB명 `ads_sandbox_dev`를 고정하고 `config.sandbox_urls`의 전용 경로·middleware와 ADMIN/guest provider를 사용합니다. 공유 Django 업무 DB 대신 dummy backend를 사용하며 광고 로그는 MongoDB에 원자 저장합니다.

연결 URI만 `ADS_SANDBOX_MONGODB_URI` 환경변수로 지정할 수 있으며 기본은 loopback27019의 `ads-rs`입니다. 실제 실행 guard에서 모든 노드의 loopback과 테스트 DB를 재검사합니다. Django DEBUG는 False이고 쿠키/CSRF는 로컬 HTTP 전용 이름과 Strict 정책입니다. 본 서비스의 운영 HTTPS·공유 계정 규정을 변경하지 않습니다.

대입/import로 구성된 설정 파일이며 AST 클래스·함수 심볼은 없습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python

```

## 2026-10-16 로컬 화면 연결

로컬 화면 변경을 즉시 확인하도록 filesystem.Loader를 사용합니다. 템플릿 캐시를 추가하지 않으며 일반 서비스 설정은 변경하지 않습니다.
