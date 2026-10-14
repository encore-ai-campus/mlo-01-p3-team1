# 공개 저장소와 로컬 비밀정보

- 수정일: 2026-10-14

AWS 인증은 저장소 밖의 AWS CLI 프로필과 임시 세션을 사용한다.
Access Key·세션 토큰·`.env`·TLS 개인키·설치 payload·실제 설정과 실행 상태는 커밋하지 않는다.
[AWS 액세스 키 보호 지침](https://docs.aws.amazon.com/IAM/latest/UserGuide/securing_access-keys.html)을 따른다.

`.gitignore`는 `config/project.json`, `.aws/`, `.env` 계열, `.private/`, `.state/`, `.local/`, `.tools/`,
키/인증서, ZIP/tar payload와 로그를 제외한다. 실제 계정별 템플릿은 `.state/`에 생성하고
`templates/`에는 공개 샘플 계정으로 생성한 결과만 둔다.
계정 ID와 사설 CIDR은 인증 비밀값은 아니지만 실제 계정 식별자는 공개 예제에서 분리한다.
Git 예제는 `example_only=true`로 AWS 호출을 차단한다. 로컬 비밀/상태는 제한된 파일 권한으로 저장한다.

공개 전 `python3 bin/check-public.py`를 실행한다. aws-infra와 ../docs/handoff/infra, 루트 인프라 CI의 공개 후보 파일에서 AWS 키 ID, 개인키,
자격 증명 대입, 일부 앱 secret, 개인 PC 경로와 로컬 계정 ID를 검사하며 파일명/줄 번호만 출력한다.
기존 저장소에 이미 추적되는 비공개 파일도 확인한다. `.gitignore`는 기존 커밋의 이력을 제거하지 않는다.
검사는 모든 비밀 형식이나 과거 Git 이력을 포괄하지 않으므로 실제 업로드 목록도 검토한다.
`git add -f`로 제외 규칙을 우회하지 않는다. 실제 키가 노출됐다면 폐기하고 이력도 정리한다.

CI는 코드 검사 전용이다. AWS credentials/OIDC 배포 권한·자동 배포·자동 삭제는 설정하지 않는다.
외부 템플릿 Metadata나 과거 실행 기록을 현재 실행 승인으로 해석하지 않는다.

저장소 루트의 .gitignore와 aws-infra/.gitignore를 함께 유지한다. 다른 기존 프로젝트 파일은 이 검사 범위에 포함되지 않으므로 전체 저장소 업로드 전에 별도 검토한다. 공유 문서에는 실제 허용 접속 IP/CIDR·계정 식별자·운영 상태 원문을 적지 않는다.

`readiness`의 로컬 준비 영수증은 `.state/readiness/latest.json`에 두며 설정 값·계정 ID·ARN·주소·과거 AWS 조회 원문을 출력/복사하지 않는다. 기존 설정을 자동 변환하지 않고 AWS 로그인/조회도 호출하지 않는다. 공개 준비 상태 요약과 원문 실행 기록은 구분하고 최종 구성 보고서는 실제 구축 완료 후 작성한다.
