# 광고 저장 경계

업무 저장은 `ads_mongo.py`, 로컬 점검 명령은 `domains/ads/mongo.py`로 분리합니다.
업무 어댑터는 설정된 광고 replica set의 primary에서 세 컬렉션을 사용합니다.
광고와 감사/멱등 기록은 같은 MongoDB 트랜잭션에 저장하며 PostgreSQL과 교차 트랜잭션을 만들지 않습니다.
무변경 수정도 트랜잭션 내부의 실제 쓰기/복원으로 동시 수정을 검사하며 최종 version/updated_at은 유지합니다.
이 과정의 쓰기 비용·운영 부하는 별도 측정 대상입니다.
