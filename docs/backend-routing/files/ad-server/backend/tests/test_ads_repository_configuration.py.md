# ad-server/backend/tests/test_ads_repository_configuration.py

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_repository_configuration.py)

관리·공개·정책 세 저장소의 연결 계약을 같은 입력별 공통 시험으로 검증합니다.
각 저장소에 `is_test=True/False`를 적용해 전용 어댑터 타입·동일 설정의 client 재사용·
원본 private URI·primary 옵션·환경 전달을 확인합니다. URI 누락은 모든 팩토리에서
드라이버 생성 전에 거부해야 합니다. 각 시험 전후 팩토리 캐시를 비웁니다.

기존6개 메서드를2개로 합쳤으며 세 연결 경로를 각각 `subTest`로 실행합니다.
MagicMock을 사용하므로 실제 MongoDB 접속·원자성 검증을 대체하지 않습니다.

## AST 시그니처

```python
class AdsRepositoryConfigurationTests(SimpleTestCase)
AdsRepositoryConfigurationTests.setUp(self)
AdsRepositoryConfigurationTests.test_private_primary_factories_reuse_clients_and_preserve_environment(self)
AdsRepositoryConfigurationTests.test_missing_uri_is_rejected_by_each_factory_before_driver_creation(self)
```
