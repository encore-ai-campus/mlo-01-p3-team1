# 광고 MongoDB 로컬 개발 환경

- 작성일: 2026-10-15
- 용도: 광고 백엔드의 MongoDB 트랜잭션·스키마·연결을 검증하는 개발 PC 전용 환경
- 저장 구조: `ads`, `ad_assets`, `ad_admin_changes`의 정의·적용은 광고 백엔드에서 담당합니다.

MongoDB 8.0 단일 멤버 replica set `ads-rs`를 사용합니다. 광고 상태와 감사·멱등 기록을 함께 저장하는 트랜잭션을 개발하기 위한 구성입니다. 단일 멤버이므로 장애 시 복제본 전환이나 고가용성을 제공하지 않습니다.

관리자 화면은 다른 담당자가 구현하며 이 폴더는 DB 환경만 제공합니다. 계정·세션·로그의 기준 저장소는 공통 PostgreSQL입니다. 광고 DB에 사용자 원본이나 별도 관리자 계정을 복제하지 않습니다.

## 준비와 실행

Docker Desktop의 Linux containers 엔진과 Docker Compose가 필요합니다. 저장소 루트에서 PowerShell로 실행합니다. 다른 MongoDB가 이미 `27017`을 사용하면 먼저 사용 대상을 확인하십시오. 포트·replica set 구성을 임의 변경하지 않습니다.

```powershell
docker compose -f ad-server/config/environments/ads/docker-compose.yml config --quiet
docker compose -f ad-server/config/environments/ads/docker-compose.yml up -d
docker compose -f ad-server/config/environments/ads/docker-compose.yml wait mongo-init
docker compose -f ad-server/config/environments/ads/docker-compose.yml up -d --wait --wait-timeout 120 mongo
docker compose -f ad-server/config/environments/ads/docker-compose.yml ps -a
```

`mongo-init`는 한 번 실행한 뒤 정상 종료합니다. `wait mongo-init`의 종료 코드가 0인지 확인한 뒤 다음 명령으로 MongoDB의 primary 상태를 확인합니다. 초기화는 기존 이름과 단일 멤버 주소를 검사하고, 일치하면 재사용합니다. 다른 replica set 이름·멤버 구성이 발견되면 오류로 종료하며 강제 재설정이나 데이터 삭제를 하지 않습니다. `mongo`의 지속 healthcheck는 ping뿐 아니라 `ads-rs`의 쓰기 가능한 primary인지 검사합니다.

```powershell
docker compose -f ad-server/config/environments/ads/docker-compose.yml logs mongo-init
docker compose -f ad-server/config/environments/ads/docker-compose.yml exec mongo mongosh "mongodb://127.0.0.1:27017/admin?directConnection=true" --quiet --eval "JSON.stringify(db.hello())"
```

후속 작업의 실제 명령·환경값은 광고 백엔드 개발 안내를 따릅니다. 여기서는 컬렉션을 미리 만들거나 Django 공통 DB 마이그레이션을 실행하지 않습니다.

## Django/PyMongo 연결

호스트 PC에서 실행하는 광고 백엔드의 로컬 설정은 다음과 같습니다. DB명 `advertising_dev`는 개발 DB이며 실제 팀/AWS 환경의 DB명은 별도로 맞춥니다.

```text
ADS_MONGODB_URI=mongodb://127.0.0.1:27017/?replicaSet=ads-rs&directConnection=true
ADS_MONGODB_DATABASE=advertising_dev
```

replica set 멤버 주소는 `localhost:27017`입니다. 초기화 서비스는 `mongo`의 네트워크를 공유하므로 컨테이너 안에서도 이 주소가 MongoDB 자신을 가리킵니다. 네이티브 Django/PyMongo는 호스트의 loopback에 공개한 포트로 연결합니다. `directConnection=true`는 로컬 Docker 환경의 단일 공개 엔드포인트에 직접 연결하기 위한 옵션입니다. 별도 API 컨테이너를 만들 경우 그 컨테이너의 `localhost`는 API 자신이므로 이 URI를 그대로 복사하지 말고 네트워크와 연결 주소를 조율해야 합니다.

## 보관과 운영 경계

`mongo-data` named volume에 DB 파일을 보관합니다. 아래 명령은 컨테이너와 네트워크만 종료하며 volume은 남깁니다.

```powershell
docker compose -f ad-server/config/environments/ads/docker-compose.yml down
```

호스트 공개 포트는 `127.0.0.1:27017`로 제한했습니다. 로컬 실습 편의를 위해 DB 인증을 생략했으므로 외부 IP에 포트를 공개하거나 이 설정을 AWS 배포 파일로 사용하지 않습니다. AWS 프라이빗 서브넷의 인증·TLS·권한·replica set 구성·백업·복구는 INF의 환경 인계와 별도로 검증합니다.

공식 Linux 이미지 `mongo:8.0.34-noble`의 patch/OS 태그와 registry의 다중 아키텍처 manifest digest `sha256:0dc2511c4261bffa84f5af2c7df2aae148c0bea68d9b0aacd85c3d7be07e0583`를 함께 고정했습니다. 공식 이미지 목록과 registry manifest에서 Linux amd64/arm64 지원을 확인했습니다. 태그가 재발행되어도 동일 digest의 이미지를 사용하며, 이미지 변경 시 버전과 digest를 함께 검증·갱신합니다. 로컬 개발 버전 선택은 INF의 전체 운영 버전 확정을 뜻하지 않습니다.

## 확인 근거

- [MongoDB replica set 구성과 primary 확인](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [PyMongo의 Docker replica set 직접 연결](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/connect/connection-targets/)
- [Docker Compose의 서비스 의존성과 네트워크](https://docs.docker.com/reference/compose-file/services/)
- [Docker 공식 MongoDB 이미지·태그 목록](https://github.com/docker-library/official-images/blob/master/library/mongo)
