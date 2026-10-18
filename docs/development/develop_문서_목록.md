# develop 문서 목록

- 작성자: Codex — 파일 수령 작업
- 작성일: 2026-10-16
- 수정일: 2026-10-16
- 기준: `origin/develop@b4499c5bf641ef84122f8fee99e3a6d04bdd8ef3`

위 develop 커밋의 추적 Markdown 143개입니다. 보관본·초안·구현 기록도 포함하므로 목록에 있다는 사실만으로 현행 정책이나 구현 완료를 뜻하지 않습니다. 현행 기준은 [AGENTS.md](../../AGENTS.md)와 각 문서의 상태·최신 결정에 따라 구분합니다.

현재 develop에는 weather 코드도 PR #7로 반영돼 있습니다. 로컬 정리 후 실제 코드 경로는 [통합 변경 라우팅](./통합_폴더_정리_변경_라우팅.md)을 따릅니다. 이전 weather 브랜치에서는 코드만 수령했습니다. 별도 수령 원문 6개와 비교/연결 대기는 [날씨 코드 수령과 연결 라우팅](./%EB%82%A0%EC%94%A8_%EC%BD%94%EB%93%9C_%EC%88%98%EB%A0%B9%EA%B3%BC_%EC%97%B0%EA%B2%B0_%EB%9D%BC%EC%9A%B0%ED%8C%85.md)을 확인합니다. 새 원문·목록·라우팅은 아래 develop 원본 목록에 포함하지 않습니다.

## 저장소 루트

- [AGENTS.md](../../AGENTS.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [README.md](../../README.md)

## ad-server

- [README.md](../../ad-server/README.md)

## ad-server/backend

- [README.md](../../ad-server/backend/README.md)

## ad-server/backend/presentation/ads

- [README.md](../../ad-server/backend/presentation/ads/README.md)

## ad-server/backend/repositories

- [README.md](../../ad-server/backend/repositories/README.md)

## ad-server/backend/workers

- [README.md](../../ad-server/backend/workers/README.md)

## ad-server/config/environments/ads

- [README.md](../../ad-server/config/environments/ads/README.md)

## docs/acceptance

- [C_로컬_검증_20261015.md](../../docs/acceptance/C_%EB%A1%9C%EC%BB%AC_%EA%B2%80%EC%A6%9D_20261015.md)
- [광고_개발_준비_검증.md](../../docs/acceptance/%EA%B4%91%EA%B3%A0_%EA%B0%9C%EB%B0%9C_%EC%A4%80%EB%B9%84_%EA%B2%80%EC%A6%9D.md)

## docs/backend-routing

- [README.md](../../docs/backend-routing/README.md)

## docs/backend-routing/files/ad-server/backend

- [manage.py.md](../../docs/backend-routing/files/ad-server/backend/manage.py.md)
- [sandbox.py.md](../../docs/backend-routing/files/ad-server/backend/sandbox.py.md)

## docs/backend-routing/files/ad-server/backend/api

- [__init__.py.md](../../docs/backend-routing/files/ad-server/backend/api/__init__.py.md)
- [ads.py.md](../../docs/backend-routing/files/ad-server/backend/api/ads.py.md)
- [ads_auth.py.md](../../docs/backend-routing/files/ad-server/backend/api/ads_auth.py.md)
- [ads_public.py.md](../../docs/backend-routing/files/ad-server/backend/api/ads_public.py.md)
- [ads_public_auth.py.md](../../docs/backend-routing/files/ad-server/backend/api/ads_public_auth.py.md)
- [ads_public_serializers.py.md](../../docs/backend-routing/files/ad-server/backend/api/ads_public_serializers.py.md)
- [ads_sandbox.py.md](../../docs/backend-routing/files/ad-server/backend/api/ads_sandbox.py.md)
- [ads_serializers.py.md](../../docs/backend-routing/files/ad-server/backend/api/ads_serializers.py.md)
- [health.py.md](../../docs/backend-routing/files/ad-server/backend/api/health.py.md)

## docs/backend-routing/files/ad-server/backend/config

- [__init__.py.md](../../docs/backend-routing/files/ad-server/backend/config/__init__.py.md)
- [sandbox_settings.py.md](../../docs/backend-routing/files/ad-server/backend/config/sandbox_settings.py.md)
- [sandbox_urls.py.md](../../docs/backend-routing/files/ad-server/backend/config/sandbox_urls.py.md)
- [settings.py.md](../../docs/backend-routing/files/ad-server/backend/config/settings.py.md)
- [urls.py.md](../../docs/backend-routing/files/ad-server/backend/config/urls.py.md)
- [wsgi.py.md](../../docs/backend-routing/files/ad-server/backend/config/wsgi.py.md)

## docs/backend-routing/files/ad-server/backend/domains

- [__init__.py.md](../../docs/backend-routing/files/ad-server/backend/domains/__init__.py.md)

## docs/backend-routing/files/ad-server/backend/domains/ads

- [__init__.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/__init__.py.md)
- [apps.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/apps.py.md)
- [budget_service.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/budget_service.py.md)
- [delivery_policy.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/delivery_policy.py.md)
- [errors.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/errors.py.md)
- [measurement.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/measurement.py.md)
- [mongo.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/mongo.py.md)
- [public_policy.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/public_policy.py.md)
- [public_schema.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/public_schema.py.md)
- [public_service.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/public_service.py.md)
- [runtime_policy.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/runtime_policy.py.md)
- [sandbox_runtime.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/sandbox_runtime.py.md)
- [selection.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/selection.py.md)
- [service.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/service.py.md)
- [validation.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/validation.py.md)

## docs/backend-routing/files/ad-server/backend/domains/ads/management

- [__init__.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/__init__.py.md)

## docs/backend-routing/files/ad-server/backend/domains/ads/management/commands

- [__init__.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/__init__.py.md)
- [apply_ads_policy_schema.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/apply_ads_policy_schema.py.md)
- [apply_ads_public_schema.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/apply_ads_public_schema.py.md)
- [apply_ads_schema.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/apply_ads_schema.py.md)
- [check_ads_database.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/check_ads_database.py.md)
- [check_ads_logs.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/check_ads_logs.py.md)
- [check_ads_retention.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/check_ads_retention.py.md)
- [check_ads_runtime.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/check_ads_runtime.py.md)
- [refresh_ads_policy.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/refresh_ads_policy.py.md)
- [run_ads_dev.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/run_ads_dev.py.md)
- [run_ads_sandbox.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/run_ads_sandbox.py.md)
- [run_ads_workers.py.md](../../docs/backend-routing/files/ad-server/backend/domains/ads/management/commands/run_ads_workers.py.md)

## docs/backend-routing/files/ad-server/backend/repositories

- [__init__.py.md](../../docs/backend-routing/files/ad-server/backend/repositories/__init__.py.md)
- [ads_mongo.py.md](../../docs/backend-routing/files/ad-server/backend/repositories/ads_mongo.py.md)
- [ads_policy_mongo.py.md](../../docs/backend-routing/files/ad-server/backend/repositories/ads_policy_mongo.py.md)
- [ads_public_mongo.py.md](../../docs/backend-routing/files/ad-server/backend/repositories/ads_public_mongo.py.md)

## docs/backend-routing/files/ad-server/backend/tests

- [__init__.py.md](../../docs/backend-routing/files/ad-server/backend/tests/__init__.py.md)
- [policy_fixtures.py.md](../../docs/backend-routing/files/ad-server/backend/tests/policy_fixtures.py.md)
- [public_fixtures.py.md](../../docs/backend-routing/files/ad-server/backend/tests/public_fixtures.py.md)
- [test_ads_api.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_api.py.md)
- [test_ads_budget_service.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_budget_service.py.md)
- [test_ads_delivery_policy.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_delivery_policy.py.md)
- [test_ads_domain.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_domain.py.md)
- [test_ads_jobs.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_jobs.py.md)
- [test_ads_logs.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_logs.py.md)
- [test_ads_measurement.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_measurement.py.md)
- [test_ads_mongo_integration.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_mongo_integration.py.md)
- [test_ads_policy_api.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_policy_api.py.md)
- [test_ads_policy_mongo_integration.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_policy_mongo_integration.py.md)
- [test_ads_policy_repository.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_policy_repository.py.md)
- [test_ads_public_api.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_public_api.py.md)
- [test_ads_public_mongo_integration.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_public_mongo_integration.py.md)
- [test_ads_public_repository.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_public_repository.py.md)
- [test_ads_public_service.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_public_service.py.md)
- [test_ads_repository.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_repository.py.md)
- [test_ads_repository_configuration.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_repository_configuration.py.md)
- [test_ads_retention.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_retention.py.md)
- [test_ads_runtime_check.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_runtime_check.py.md)
- [test_ads_runtime_policy.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_runtime_policy.py.md)
- [test_ads_sandbox.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_sandbox.py.md)
- [test_ads_selection.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_selection.py.md)
- [test_ads_worker_shutdown.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_worker_shutdown.py.md)
- [test_ads_workers_mongo_integration.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_ads_workers_mongo_integration.py.md)
- [test_scaffold.py.md](../../docs/backend-routing/files/ad-server/backend/tests/test_scaffold.py.md)

## docs/backend-routing/files/ad-server/backend/workers

- [ads_jobs.py.md](../../docs/backend-routing/files/ad-server/backend/workers/ads_jobs.py.md)
- [ads_logs.py.md](../../docs/backend-routing/files/ad-server/backend/workers/ads_logs.py.md)
- [ads_retention.py.md](../../docs/backend-routing/files/ad-server/backend/workers/ads_retention.py.md)
- [ads_runtime_check.py.md](../../docs/backend-routing/files/ad-server/backend/workers/ads_runtime_check.py.md)

## docs/development

- [C_코드초안_정리기준과_작업라우팅.md](../../docs/development/C_%EC%BD%94%EB%93%9C%EC%B4%88%EC%95%88_%EC%A0%95%EB%A6%AC%EA%B8%B0%EC%A4%80%EA%B3%BC_%EC%9E%91%EC%97%85%EB%9D%BC%EC%9A%B0%ED%8C%85.md)

## docs/development/ads

- [MongoDB_광고_로그_저장_계약.md](../../docs/development/ads/MongoDB_%EA%B4%91%EA%B3%A0_%EB%A1%9C%EA%B7%B8_%EC%A0%80%EC%9E%A5_%EA%B3%84%EC%95%BD.md)
- [공개_선정과_측정_로직_인계.md](../../docs/development/ads/%EA%B3%B5%EA%B0%9C_%EC%84%A0%EC%A0%95%EA%B3%BC_%EC%B8%A1%EC%A0%95_%EB%A1%9C%EC%A7%81_%EC%9D%B8%EA%B3%84.md)
- [광고_남은_작업과_연결_계획.md](../../docs/development/ads/%EA%B4%91%EA%B3%A0_%EB%82%A8%EC%9D%80_%EC%9E%91%EC%97%85%EA%B3%BC_%EC%97%B0%EA%B2%B0_%EA%B3%84%ED%9A%8D.md)
- [광고_데이터와_로직_설계.md](../../docs/development/ads/%EA%B4%91%EA%B3%A0_%EB%8D%B0%EC%9D%B4%ED%84%B0%EC%99%80_%EB%A1%9C%EC%A7%81_%EC%84%A4%EA%B3%84.md)
- [광고_로컬_화면과_프레젠테이션_수정_가이드.md](../../docs/development/ads/%EA%B4%91%EA%B3%A0_%EB%A1%9C%EC%BB%AC_%ED%99%94%EB%A9%B4%EA%B3%BC_%ED%94%84%EB%A0%88%EC%A0%A0%ED%85%8C%EC%9D%B4%EC%85%98_%EC%88%98%EC%A0%95_%EA%B0%80%EC%9D%B4%EB%93%9C.md)
- [광고_미정_정책_결정_가이드.md](../../docs/development/ads/%EA%B4%91%EA%B3%A0_%EB%AF%B8%EC%A0%95_%EC%A0%95%EC%B1%85_%EA%B2%B0%EC%A0%95_%EA%B0%80%EC%9D%B4%EB%93%9C.md)
- [임시_광고_관리_도구.md](../../docs/development/ads/%EC%9E%84%EC%8B%9C_%EA%B4%91%EA%B3%A0_%EA%B4%80%EB%A6%AC_%EB%8F%84%EA%B5%AC.md)

## docs/handoff/ads

- [01_광고_화면_API와_측정_계약.md](../../docs/handoff/ads/01_%EA%B4%91%EA%B3%A0_%ED%99%94%EB%A9%B4_API%EC%99%80_%EC%B8%A1%EC%A0%95_%EA%B3%84%EC%95%BD.md)
- [02_광고_MongoDB_저장과_로그_연결.md](../../docs/handoff/ads/02_%EA%B4%91%EA%B3%A0_MongoDB_%EC%A0%80%EC%9E%A5%EA%B3%BC_%EB%A1%9C%EA%B7%B8_%EC%97%B0%EA%B2%B0.md)
- [03_광고_인프라와_검증_인계.md](../../docs/handoff/ads/03_%EA%B4%91%EA%B3%A0_%EC%9D%B8%ED%94%84%EB%9D%BC%EC%99%80_%EA%B2%80%EC%A6%9D_%EC%9D%B8%EA%B3%84.md)
- [04_광고_관리_간소화_인수인계서.md](../../docs/handoff/ads/04_%EA%B4%91%EA%B3%A0_%EA%B4%80%EB%A6%AC_%EA%B0%84%EC%86%8C%ED%99%94_%EC%9D%B8%EC%88%98%EC%9D%B8%EA%B3%84%EC%84%9C.md)
- [05_광고_간소화_통합과_추가_인계.md](../../docs/handoff/ads/05_%EA%B4%91%EA%B3%A0_%EA%B0%84%EC%86%8C%ED%99%94_%ED%86%B5%ED%95%A9%EA%B3%BC_%EC%B6%94%EA%B0%80_%EC%9D%B8%EA%B3%84.md)
- [06_4차_광고_업종매칭_확장_가이드.md](../../docs/handoff/ads/06_4%EC%B0%A8_%EA%B4%91%EA%B3%A0_%EC%97%85%EC%A2%85%EB%A7%A4%EC%B9%AD_%ED%99%95%EC%9E%A5_%EA%B0%80%EC%9D%B4%EB%93%9C.md)
- [README.md](../../docs/handoff/ads/README.md)

## docs/handoff/infra

- [AWS_인프라_구축_계획서.md](../../docs/handoff/infra/AWS_%EC%9D%B8%ED%94%84%EB%9D%BC_%EA%B5%AC%EC%B6%95_%EA%B3%84%ED%9A%8D%EC%84%9C.md)
- [README.md](../../docs/handoff/infra/README.md)
- [local infra guide.md](../../docs/handoff/infra/local%20infra%20guide.md)

## docs/handoff/music

- [README.md](../../docs/handoff/music/README.md)
- [음악_분류_컬럼_정의.md](../../docs/handoff/music/%EC%9D%8C%EC%95%85_%EB%B6%84%EB%A5%98_%EC%BB%AC%EB%9F%BC_%EC%A0%95%EC%9D%98.md)
- [음악_분류_컬럼_정의_및_변환_규칙.md](../../docs/handoff/music/%EC%9D%8C%EC%95%85_%EB%B6%84%EB%A5%98_%EC%BB%AC%EB%9F%BC_%EC%A0%95%EC%9D%98_%EB%B0%8F_%EB%B3%80%ED%99%98_%EA%B7%9C%EC%B9%99.md)
- [테마_장르_정의.md](../../docs/handoff/music/%ED%85%8C%EB%A7%88_%EC%9E%A5%EB%A5%B4_%EC%A0%95%EC%9D%98.md)
- [테이블_구조_설계.md](../../docs/handoff/music/%ED%85%8C%EC%9D%B4%EB%B8%94_%EA%B5%AC%EC%A1%B0_%EC%84%A4%EA%B3%84.md)
- [플레이리스트_생성_규칙.md](../../docs/handoff/music/%ED%94%8C%EB%A0%88%EC%9D%B4%EB%A6%AC%EC%8A%A4%ED%8A%B8_%EC%83%9D%EC%84%B1_%EA%B7%9C%EC%B9%99.md)

## docs/handoff/music/archive

- [음악_분류_컬럼_정의_16개_수동_보관.md](../../docs/handoff/music/archive/%EC%9D%8C%EC%95%85_%EB%B6%84%EB%A5%98_%EC%BB%AC%EB%9F%BC_%EC%A0%95%EC%9D%98_16%EA%B0%9C_%EC%88%98%EB%8F%99_%EB%B3%B4%EA%B4%80.md)

## docs/handoff/weather

- [01_날씨_수집과_지역매핑.md](../../docs/handoff/weather/01_%EB%82%A0%EC%94%A8_%EC%88%98%EC%A7%91%EA%B3%BC_%EC%A7%80%EC%97%AD%EB%A7%A4%ED%95%91.md)
- [02_날씨_데이터규격과_정제.md](../../docs/handoff/weather/02_%EB%82%A0%EC%94%A8_%EB%8D%B0%EC%9D%B4%ED%84%B0%EA%B7%9C%EA%B2%A9%EA%B3%BC_%EC%A0%95%EC%A0%9C.md)
- [03_날씨_저장구조.md](../../docs/handoff/weather/03_%EB%82%A0%EC%94%A8_%EC%A0%80%EC%9E%A5%EA%B5%AC%EC%A1%B0.md)
- [04_API호출과_RDB적재시험.md](../../docs/handoff/weather/04_API%ED%98%B8%EC%B6%9C%EA%B3%BC_RDB%EC%A0%81%EC%9E%AC%EC%8B%9C%ED%97%98.md)
- [05_날씨분류와_계절기준.md](../../docs/handoff/weather/05_%EB%82%A0%EC%94%A8%EB%B6%84%EB%A5%98%EC%99%80_%EA%B3%84%EC%A0%88%EA%B8%B0%EC%A4%80.md)

## docs/product

- [3차_공통_개발_계약과_검증_기준.md](../../docs/product/3%EC%B0%A8_%EA%B3%B5%ED%86%B5_%EA%B0%9C%EB%B0%9C_%EA%B3%84%EC%95%BD%EA%B3%BC_%EA%B2%80%EC%A6%9D_%EA%B8%B0%EC%A4%80.md)
- [3차_광고_운영_회의_결정사항_목록.md](../../docs/product/3%EC%B0%A8_%EA%B4%91%EA%B3%A0_%EC%9A%B4%EC%98%81_%ED%9A%8C%EC%9D%98_%EA%B2%B0%EC%A0%95%EC%82%AC%ED%95%AD_%EB%AA%A9%EB%A1%9D.md)
- [3차_구현_결정과_익명문맥_원문보관_가이드.md](../../docs/product/3%EC%B0%A8_%EA%B5%AC%ED%98%84_%EA%B2%B0%EC%A0%95%EA%B3%BC_%EC%9D%B5%EB%AA%85%EB%AC%B8%EB%A7%A5_%EC%9B%90%EB%AC%B8%EB%B3%B4%EA%B4%80_%EA%B0%80%EC%9D%B4%EB%93%9C.md)
- [3차_사용자_확인과_담당자_인계_목록.md](../../docs/product/3%EC%B0%A8_%EC%82%AC%EC%9A%A9%EC%9E%90_%ED%99%95%EC%9D%B8%EA%B3%BC_%EB%8B%B4%EB%8B%B9%EC%9E%90_%EC%9D%B8%EA%B3%84_%EB%AA%A9%EB%A1%9D.md)
- [3차_음악_정책_통합_계약.md](../../docs/product/3%EC%B0%A8_%EC%9D%8C%EC%95%85_%EC%A0%95%EC%B1%85_%ED%86%B5%ED%95%A9_%EA%B3%84%EC%95%BD.md)
- [3차_저장소_경계와_발행_계약.md](../../docs/product/3%EC%B0%A8_%EC%A0%80%EC%9E%A5%EC%86%8C_%EA%B2%BD%EA%B3%84%EC%99%80_%EB%B0%9C%ED%96%89_%EA%B3%84%EC%95%BD.md)
- [날씨_기반_음악_추천_로직_설계_흐름과_검증_계획.md](../../docs/product/%EB%82%A0%EC%94%A8_%EA%B8%B0%EB%B0%98_%EC%9D%8C%EC%95%85_%EC%B6%94%EC%B2%9C_%EB%A1%9C%EC%A7%81_%EC%84%A4%EA%B3%84_%ED%9D%90%EB%A6%84%EA%B3%BC_%EA%B2%80%EC%A6%9D_%EA%B3%84%ED%9A%8D.md)
- [카페_음악_서비스_3차_Gemini_API_추천_설계.md](../../docs/product/%EC%B9%B4%ED%8E%98_%EC%9D%8C%EC%95%85_%EC%84%9C%EB%B9%84%EC%8A%A4_3%EC%B0%A8_Gemini_API_%EC%B6%94%EC%B2%9C_%EC%84%A4%EA%B3%84.md)
- [카페_음악_서비스_구현_설계도.md](../../docs/product/%EC%B9%B4%ED%8E%98_%EC%9D%8C%EC%95%85_%EC%84%9C%EB%B9%84%EC%8A%A4_%EA%B5%AC%ED%98%84_%EC%84%A4%EA%B3%84%EB%8F%84.md)
- [카페_음악_서비스_기능_및_사용자_흐름_정리.md](../../docs/product/%EC%B9%B4%ED%8E%98_%EC%9D%8C%EC%95%85_%EC%84%9C%EB%B9%84%EC%8A%A4_%EA%B8%B0%EB%8A%A5_%EB%B0%8F_%EC%82%AC%EC%9A%A9%EC%9E%90_%ED%9D%90%EB%A6%84_%EC%A0%95%EB%A6%AC.md)
- [카페_음악_추천_서비스_3차_구현_태스크.md](../../docs/product/%EC%B9%B4%ED%8E%98_%EC%9D%8C%EC%95%85_%EC%B6%94%EC%B2%9C_%EC%84%9C%EB%B9%84%EC%8A%A4_3%EC%B0%A8_%EA%B5%AC%ED%98%84_%ED%83%9C%EC%8A%A4%ED%81%AC.md)
- [카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md](../../docs/product/%EC%B9%B4%ED%8E%98_%EC%9D%8C%EC%95%85_%EC%B6%94%EC%B2%9C_%EC%84%9C%EB%B9%84%EC%8A%A4_3%EC%B0%A8_%EC%BB%AC%EB%9F%BC_%EA%B8%B0%EB%B0%98_%EC%B6%94%EC%B2%9C_%EB%A1%9C%EC%A7%81_%EA%B0%80%EC%9D%B4%EB%93%9C.md)

## docs/product/archive

- [규칙_기반_추천_설계_보관.md](../../docs/product/archive/%EA%B7%9C%EC%B9%99_%EA%B8%B0%EB%B0%98_%EC%B6%94%EC%B2%9C_%EC%84%A4%EA%B3%84_%EB%B3%B4%EA%B4%80.md)
- [날씨_기반_음악_추천_로직_설계_흐름과_검증_계획.md](../../docs/product/archive/%EB%82%A0%EC%94%A8_%EA%B8%B0%EB%B0%98_%EC%9D%8C%EC%95%85_%EC%B6%94%EC%B2%9C_%EB%A1%9C%EC%A7%81_%EC%84%A4%EA%B3%84_%ED%9D%90%EB%A6%84%EA%B3%BC_%EA%B2%80%EC%A6%9D_%EA%B3%84%ED%9A%8D.md)
- [자동_시간_단축_25퍼센트_정책_보관.md](../../docs/product/archive/%EC%9E%90%EB%8F%99_%EC%8B%9C%EA%B0%84_%EB%8B%A8%EC%B6%95_25%ED%8D%BC%EC%84%BC%ED%8A%B8_%EC%A0%95%EC%B1%85_%EB%B3%B4%EA%B4%80.md)
- [카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md](../../docs/product/archive/%EC%B9%B4%ED%8E%98_%EC%9D%8C%EC%95%85_%EC%B6%94%EC%B2%9C_%EC%84%9C%EB%B9%84%EC%8A%A4_3%EC%B0%A8_%EC%BB%AC%EB%9F%BC_%EA%B8%B0%EB%B0%98_%EC%B6%94%EC%B2%9C_%EB%A1%9C%EC%A7%81_%EA%B0%80%EC%9D%B4%EB%93%9C.md)

## docs/runbook

- [C_구현과_연결_인계.md](../../docs/runbook/C_%EA%B5%AC%ED%98%84%EA%B3%BC_%EC%97%B0%EA%B2%B0_%EC%9D%B8%EA%B3%84.md)
- [광고_보관_점검과_배치_종료.md](../../docs/runbook/%EA%B4%91%EA%B3%A0_%EB%B3%B4%EA%B4%80_%EC%A0%90%EA%B2%80%EA%B3%BC_%EB%B0%B0%EC%B9%98_%EC%A2%85%EB%A3%8C.md)
- [광고_서버_개발_준비.md](../../docs/runbook/%EA%B4%91%EA%B3%A0_%EC%84%9C%EB%B2%84_%EA%B0%9C%EB%B0%9C_%EC%A4%80%EB%B9%84.md)

## develop 계약·고정 자료 JSON

문서에 연결되는 계약/예시 자료입니다.

- [3차_공통_API_이벤트.schema.json](../../docs/contracts/3%EC%B0%A8_%EA%B3%B5%ED%86%B5_API_%EC%9D%B4%EB%B2%A4%ED%8A%B8.schema.json)
- [3차_공통_계약_예시.json](../../docs/fixtures/3%EC%B0%A8_%EA%B3%B5%ED%86%B5_%EA%B3%84%EC%95%BD_%EC%98%88%EC%8B%9C.json)
