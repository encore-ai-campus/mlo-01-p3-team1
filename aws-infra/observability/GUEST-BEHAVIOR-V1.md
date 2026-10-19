# 비회원 행동 분석 · Kibana v1

작성일·수정일: 2026-10-19 (KST). **사용자 추가 승인 후 AWS 배포 및 실데이터 검증 완료.** 아래의 배포 준비 절차·안전성 설명은 최초 로컬 인계 기준이며 실제 적용 결과는 마지막 절을 따릅니다.

## 목적과 소유권
- 기존 `music-operations-v1`, `dashboard_v2.py`, 기존 `ops-mlo-*` 인덱스는 변경하지 않습니다.
- 신규 Kibana ID: `music-guest-behavior-v1`. 신규 시각화: `music-guest-v1-*` (27개 패널).
- 비회원이며 로그인 사용자별 분석이 아닙니다. 익명 개별 방문자 수, 실제 재생 수, 체류 시간은 제공하지 않습니다.
- 기존 v2 남색 헤더 / KPI 6개 / 청록·파랑·빨강·주황 / Vega 및 48컬럼 구조를 재사용합니다.

## 데이터 출처와 해석
- 원본: PostgreSQL Django `FeedbackEvent` (타입과 생성 시각, payload의 지정된 컬럼만)
- 현재 값: `FeedbackState` (곡 좋아요/싫어요, 선곡표 1~5 별점), `Family.excluded` (현재 제외 목록)
- 상태: `Outbox` 및 `Projection` (전송 대기/적용 누적)
- 추천 분류: `Playlist.job.method` (RULE_BASED/GEMINI_RECONFIGURE)
- 태그·날씨: 반응 시점의 snapshot에서 승인된 스칼라/짧은 문자열/분류 태그만 추출. 스냅샷 전체를 ES에 내보내지 않습니다.
- `is_test=False`만 수집, owner_id, family_id, 원본 track_id/playlist_id, 쿠키, 세션, 원본 JSON 제외.
- **이벤트 흐름**: 동일 곡을 여러 차례 좋아요/싫어요 하면 여러 이벤트로 계산됩니다.
- **현재 값 카드**: 현행 최종 피드백 상태를 기반으로 하며 상단 기간/KQL과 독립됩니다.
- **별점 이벤트 분포**: 선곡표의 평가 변경을 중복 포함하며 '현재 별점 분포'가 아닙니다.
- 장르/테마는 다중 태그라 합계가 이벤트 수와 다를 수 있습니다.
- 곡 이름 기준 TOP 차트는 동명곡이 합쳐질 수 있습니다. 개별 곡을 구분하려면 `track_key` 필터를 사용합니다.
- 시계열·별점·추천 방식 차트의 세로 Y축 제목은 제거하고, 가로 부제와 툴팁에 지표 단위를 남깁니다. 범주 라벨은 수평 표시합니다.
- 현행 제외곡 수는 가족별 현재 제외 목록의 합계이고, 동일 음악이 여러 가족에서 제외되면 중복으로 계산합니다.

## 구현 파일
- `guest_behavior_export.py`: Django ORM 읽기 전용, 타임스탬프+ID 커서, ES bulk 전송 후 커서 기록, 최신 상태 단일 문서 교체.
- `guest_behavior_elastic_plan.py`: 전용 인덱스 템플릿 및 최소 권한 역할 **적용 계획만 출력**, 자동 실행하지 않음.
- `dashboard_guest_v1.py`: 신규 Saved Object 정의, 중복 소유권 보호, dry-run.
- 운영지표 v2/기존 수집기/데이터베이스 마이그레이션 파일은 수정하지 않았습니다.

## 권장 배포 준비 순서 (아직 실행하지 않음)
1. 배포 앱의 PostgreSQL 실제 테이블/인덱스/이벤트 종류·현재 건수 확인. `common_feedbackevent`, `common_feedbackstate`, `recommendation_family` 및 외래키 확인.
2. PostgreSQL에서 **SELECT 전용 별도 계정** 사용. 앱과 동일 환경에서 Django로 접근하는 대신 최소 테이블 SELECT 권한만 가진 DSN/계정을 지급하고 실제 읽기 전용 연결 검증.
3. `guest_behavior_elastic_plan.py` 출력을 검토 후 전용 매핑/권한을 ES에 구축. 전용 writer 계정에만 `analytics-mlo-guest-*` 쓰기 허용; Kibana viewer에는 해당 인덱스 읽기 권한 부여.
4. Control A/B 중 **하나의 활성 호스트**에 exporter timer(1분)를 설치. 동시 실행 차단, 커서 파일 접근제어(0600), 전용 ES TLS CA/인증을 설정. HTTPS와 인증서 이름 검증을 비활성화하지 않음.
5. exporter `--dry-run`으로 이벤트/현재 상태 건수를 비교하고, 실제 전송 후 Kibana Discover에서 `analytics-mlo-guest-events-*`, `analytics-mlo-guest-summary-v1` 수집 확인.
6. Kibana Saved Object 신규 ID 충돌 유무 확인 후 최초 게시. `dashboard_guest_v1.publish(client, private_state_path, dry_run=True)`로 계획 확인 후 배포 모드 사용. 기존 운영 대시보드에는 어떠한 갱신도 하지 않음.
7. 기준 시점별 SQL 수와 ES 수, 재시작/중복/부분실패/비시험 필터를 검증하고 실데이터 없는 경우 '데이터 없음' 표시를 확인.

## 안전성과 한계
- **자동 운영 배포 경로 없음**: 사용자가 현 환경의 안전한 배포를 요청하기 전까지 CLI, 스크립트 또는 템플릿을 실행하여 리소스를 변경하지 마세요.
- 커서 증분 수집은 최초 30일(설정 가능 1~90일)의 이벤트만 초기 수집합니다. 과거 전수 이력은 별도 백필 정책이 필요합니다.
- 1회 실행 최대 20개 배치, 배치당 최대 1,000건으로 제한. 트래픽 급증 시 처리 지연 확인 필요.
- 현재 상태는 최대 100,000행을 조회하고 초과 시 실패하여 누락된 숫자로 표시하지 않습니다.
- 해당 예제는 read replica / DB 부하 / 권한·샤드 정책 검토 전 대용량 운영 트래픽용으로 간주하지 마세요.
- summary의 중첩 top list는 분석 상세의 확장 용도로만 저장; 현재 v1 차트는 이벤트 인덱스를 사용합니다.
- 임의 사용자의 유일 방문, 재생 완료, 좋아요가 없는 이용자 등의 모수는 측정하지 않습니다.
- Kibana 상단 시간 필터는 events 패널에만 적용하고, KPI 현행 카드에는 적용하지 않습니다. 서로 다른 단위가 섞이지 않도록 패널 제목에 명시합니다.


## AWS 적용 결과 — 2026-10-19

- 별도 대시보드 `music-guest-behavior-v1`를 게시했습니다. 기존 운영 관제 대시보드와 시각화의 속성·참조 지문이 동일한 것을 확인했습니다.
- Control A 한 대에서 `music-guest-analytics.timer`가 분당 실행됩니다. 전용 OS 사용자와 잠금·0600 커서를 사용하며 기존 앱·추천 작업자를 재시작하지 않았습니다.
- PostgreSQL은 전용 계정 `music_guest_analytics`에 대상 8개 테이블의 필요한 컬럼 SELECT만 허용했습니다. Control A 한 대의 TLS/SCRAM 연결만 추가했습니다. 쓰기·owner_id·Catalog.tracks 조회가 불가능한 것을 검증했습니다.
- ES writer는 신규 `analytics-mlo-guest-*`에만 접근합니다. 기존 `ops_admin`의 비밀번호·기존 역할은 보존하고 분석 읽기 역할을 추가했습니다. 웹 앱 관리자 계정과 Kibana 계정은 별개입니다.
- Data View: `Music guest behavior events`, `Music guest current state`.
- 검증 시 비시험 원본 이벤트127건 중 이 대시보드 대상49건이 SQL/ES에서 일치했습니다. 시험 문서0건, 현재 좋아요19/싫어요16/별점4건·평균4.75/제외곡2/Outbox대기0/투영127건입니다. 값은 이용에 따라 갱신됩니다.
- 22개 실제 ES 집계 쿼리, 로컬 unittest7개가 통과했습니다. 재실행에서 신규 이벤트0건·커서 유지와 ES 중복 없음, 브라우저27패널 로딩 및 실제 카드/차트 표시를 확인했습니다.
- 실행·권한·설치 영수증과 체크포인트는 Git 제외 `.state/operations/guest-behavior-20261019/`, 비밀값은 `.private/guest-analytics/<세대>/`에 보관합니다.
- 공개 경로는 기존 HTTPS `/ops/app/dashboards#/view/music-guest-behavior-v1`입니다. Kibana 로그인이 필요하며 익명 공개 대시보드로 바꾸지 않았습니다.

중지는 Control A에서 `systemctl stop music-guest-analytics.timer`와 실행 중인 `music-guest-analytics.service`만 대상으로 합니다. 커서·원본·분석 인덱스를 삭제하지 않습니다. 읽기 계정/ES 역할 회수는 영향 확인 후 별도 운영 작업으로 진행합니다.
