# 운영 YouTube 검수 DB · 추천 분산 마이그레이션 호환성

- 기준: 2026-10-19, 최신 develop의 추천 분산 처리 통합
- 목적: 운영에 이미 적용된 YouTube 검수 이력과 신규 추천 작업 큐를 함께 유지

## 보존 계약

운영 PostgreSQL에는 이미 `recommendation.0006_youtubereviewaudit_youtubetrackrevision_and_more`가 적용되어 있습니다. 이 마이그레이션의 `youtube_mapping`, `youtube_review_audit`, `youtube_track_revision`은 실제 검수 데이터가 들어 있는 기존 테이블입니다. **삭제·초기화·재생성·역적용하거나 테스트 데이터로 덮어쓰지 않습니다.**

공개 develop의 `0006_distributed_dispatch`는 신규 Job 필드·DispatchControl을 추가하는 별도 additive 마이그레이션입니다. 서로 독립적인 두 `0006`을 모두 유지하고 `0007_merge_youtube_dispatch`가 양쪽에 의존하게 구성합니다. 이미 각자의 `0006`을 적용한 환경에서도 기존 migration 이름을 바꾸거나 fake 처리하지 않습니다.

공유 YouTube 검수 데이터 읽기·쓰기에는 배포 중인 기존 PostgreSQL 어댑터를 사용하며, 비운영 로컬 리뷰는 계속 로컬 SQLite를 사용합니다. 기존 검수자 식별·revision 충돌 검사·원자적 커밋 계약을 유지합니다.

## 배포 안전 확인

1. 동일한 소스 및 잠금 의존성을 Control A/B에 준비하며 실제 운영 DB에 적용하기 전 마이그레이션 계획을 검토합니다.
2. PostgreSQL 사용자 데이터의 **새 시점 백업**을 별도 암호·접근 제어 영역에 만들고 복원 목록을 검증합니다. 백업을 공개 Git, 공개 객체 저장소, 채팅에 업로드하지 않습니다.
3. 기존 추천 워커 drain 후 새 분산 워커로 전환하며 신·구 워커를 혼합하지 않습니다. 날씨 Driver·피드백·광고·MongoDB·Kafka offset/checkpoint는 재생성하지 않습니다.
4. 적용 전후 YouTube 세 테이블 건수, 실제 video ID 검수 상태, 추천 Job·카탈로그, SSO·Django health 및 두 ALB target을 읽기 전용으로 비교합니다.
5. `migrate --plan`에서 `0006_distributed_dispatch`와 `0007_merge_youtube_dispatch` 이외에 삭제/변환 동작이 나타나면 운영 반영을 보류합니다. `common.0006` 및 기존 음악 마이그레이션도 별도로 확인합니다.

## 검사

`python -m backend.manage makemigrations --check --dry-run` 및 `python scripts/check_routing.py`를 실행합니다. PostgreSQL CI의 `backend.recommendation.tests.test_shared_youtube_database`로 기존 공유 DB 계약과 모델 테이블명을 확인합니다.

> 운영 배포는 코드 커밋과 별개이며, 해당 작업의 AWS 적용 영수증·버전·서비스 health가 모두 일치할 때에만 완료로 기록합니다.
