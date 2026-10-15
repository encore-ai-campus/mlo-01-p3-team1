# 광고 저장 경계

관리 업무 저장은 `ads_mongo.py`, 공개 저장은 이를 확장한 `ads_public_mongo.py`,
로컬 점검 명령은 `domains/ads/mongo.py`로 분리합니다. 설정된 광고 replica set의 primary에서
관리 세 컬렉션과 공개 순환·배달·이벤트·반복 창·예상 원장 다섯 컬렉션을 사용합니다.
광고와 감사/멱등 기록은 같은 MongoDB 트랜잭션에 저장하며 PostgreSQL과 교차 트랜잭션을 만들지 않습니다.
무변경 수정도 트랜잭션 내부의 실제 쓰기/복원으로 동시 수정을 검사하며 최종 version/updated_at은 유지합니다.
이 과정의 쓰기 비용·운영 부하는 별도 측정 대상입니다.

공개 배달은 순환 상태와 함께 저장합니다. 측정은 최초 응답·delivery 내부 claim·반복 창·
예상 원장·event 내부 pending 로그를 한 트랜잭션으로 확정합니다. version/revision과 고유키
경합은 새 snapshot에서 다시 검사하며 재전송은 저장된 최초 응답을 반환합니다.
소재 수정·수명·예산 운영 정책과 공유 guest 원본은 저장소가 임의로 결정하지 않습니다.
[공개 인계](../../../docs/development/ads/공개_선정과_측정_로직_인계.md)를 따릅니다.
