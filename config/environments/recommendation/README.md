# 추천 요청 분산 실행 설정

- 작성일/수정일: 2026-10-19
- 현재 Django ASGI API와 추천 워커의 배포 검토용 예시입니다. 파일을 두는 것만으로 서버에 적용되지 않습니다.
- [인프라 인계·적용/복구/수용 절차](../../../docs/runbook/추천_분산처리_인프라_인계.md)
- [기준 문서→코드→검증 변경 라우팅](../../../docs/development/추천_분산처리_변경_라우팅.md)

| 파일 | 전달 위치·용도 |
|---|---|
| `shared.env.example` | A/B 각각 `/etc/music-cluster/control/recommendation.env`. 큐/lease/호출 한도는 동일, API_BIND_HOST는 호스트별 사설 IP |
| `control-a-rule.env.example` | A의 `recommendation-rule-1.env` |
| `control-b-rule.env.example` | B의 `recommendation-rule-1.env` |
| `control-b-gemini.env.example` | B의 `recommendation-gemini-1.env`. 실제 키는 이 비공개 파일에만 주입 |
| `music-recommendation@.service` | 작업 종류별 독립 프로세스. instance=`rule-1` 또는 `gemini-1` |
| `music-recommendation-api.service` | 초기 Django ASGI/Uvicorn API 호스트당1프로세스, 8000, 사설 bind |

실제 환경 파일은 root:control/0640으로 인계합니다. 기존 `database.env/application.env`와 같은 PostgreSQL·인증·날씨/피드백 어댑터가 필요합니다. 원문 DB 파일의 이름이 다르면 PG 설정 이름과 unit 참조를 함께 맞춥니다. 코드·migration·한도는 양쪽 호스트에서 같아야 하며 구 워커와 혼합 실행하지 않습니다.

프로세스 메모리/CPU·작업/호출 한도·프로세스 개수는 초기 검증 예시입니다. Linux systemd 실기동·실제 카탈로그 부하·ALB/HTTPS/SSO·운영 장애 승계는 인계 문서의 남은 검증입니다. 실제 서버 설치·활성화·AWS 변경은 이번 작업에서 수행하지 않았습니다.
