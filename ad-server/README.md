# 광고 서버

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 브랜치: `feature/ad-logic`

광고 서버 코드와 실행 환경 설정을 이 폴더에 모읍니다.

```text
ad-server/
├─ backend/                  Django/DRF API·광고 로직·MongoDB 저장·테스트
└─ config/
   └─ environments/ads/      로컬 MongoDB replica set·Compose 설정
```

설치·실행은 [backend 안내](./backend/README.md), DB 환경은
[MongoDB 환경 안내](./config/environments/ads/README.md)를 따릅니다.
기획·라우팅·실행/검증 문서는 저장소 루트의 `docs/`에 유지합니다.

- [코드·API 라우팅](../docs/backend-routing/README.md)
- [광고 데이터와 로직](../docs/development/ads/광고_데이터와_로직_설계.md)
- [실행·인계](../docs/runbook/광고_서버_개발_준비.md)
- [검증 결과](../docs/acceptance/광고_개발_준비_검증.md)

관리 API의 세 컬렉션을 유지하고, 공개 상태에는 순환·배달·측정·반복 창·예상 원장 다섯 컬렉션을 추가했습니다.
`GET /api/ads`, `POST /api/ad-events`, `GET /api/ad-deliveries/{delivery_id}/image`를 제공하며
MongoDB 트랜잭션으로 광고 잠금·배달/순환 또는 판정/claim/반복/원장을 함께 저장합니다.
정책 `ad_budget_states`·`ad_daily_metrics` 두 개를 더해 합계10개이며5분 예산/통계·소진 로그 코드를 연결했습니다. 관리자 화면·태그/업종 매칭은 구현하지 않습니다.

공개 HTTP·선정·측정 판정과 저장 어댑터도 backend에 두었습니다.
[공개 선정·측정 인계](../docs/development/ads/공개_선정과_측정_로직_인계.md)에
구현 범위와 남은 운영 연결을 기록했습니다. `ADS_GUEST_CONTEXT_PROVIDER`,
`ADS_PUBLIC_POLICY_PROVIDER`, `ADS_DELIVERY_SIGNING_KEY`, `ADS_PUBLIC_BASE_URL`이 필요하며
미설정이면 공개 경로는 503으로 차단합니다. 이미지 읽기는 guest 발급 없이 배달 proof를 확인합니다.
정책 callback은 MongoDB 트랜잭션 안에서 외부 I/O를 실행하지 않아야 합니다.

사용자 확정은 배달30분·표시/보고 분리·소재 변경 후 옛 배달 차단·통계/예산 모두5분입니다. 소진 확인 cutoff부터 신규/재확인/이미지를 막고 이전 유효 발생만300초 내 초과 인정합니다. 자동 종료는 소진/게시 기간이고 수동 paused는 유지합니다. 예약·최소잔여23/20은 없으며 실제 예산값은 관리API 입력, 기본값 없음입니다.

정책 provider는 `domains.ads.runtime_policy.get_public_policy`(1800초·분리마감/예산이력True·자정단축False)이며 `.env.example`에 선택 경로를 적었습니다. 상태 누락은 부적격,300초 초과 stale는503이며 캠페인 종료와 구분합니다. 기존 배달/원응답은 소급하지 않습니다. 테스트900초는 운영값이 아닙니다.

실행은 `apply_ads_policy_schema`(dry-run 기본/--apply는local `_dev`), `refresh_ads_policy`(기본1회/--watch는300초 시작간격), `relay_ads_budget_logs`입니다. 실제 watch·공유 guest/PostgreSQL·AWS·브라우저 실행은 미완료입니다.
관리·측정 로그는 각각 `relay_ads_logs`·`relay_ads_event_logs`에서 기존 `ADS_LOG_SINK`로 전달하며,
공유 guest/정책·PostgreSQL sink·브라우저·실운영 인프라 연결 완료는 별도 검증입니다.
