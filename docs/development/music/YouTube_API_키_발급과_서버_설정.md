# YouTube 자동 영상 검색 API 키 발급과 서버 설정

- 작성일/수정일: 2026-10-16
- 대상: 현재 로컬 Django 추천 API 담당자·사용자
- 상태: 키 등록 전입니다. 사용자가 아직 키가 없음을 확인했고 발급·설정 방법을 요청했습니다. 아래 명령은 안내이며 실제 키 등록·Google Cloud 설정 변경은 수행하지 않았습니다.

## 역할 구분

추천은 기존 규칙과 전체 GENERAL 카탈로그로 계산합니다. 중앙 iframe은 YouTube IFrame Player API로 재생하며 이 자체에는 API 키나 LLM이 필요하지 않습니다. 이미 저장된 영상 ID도 바로 재생 후보로 사용할 수 있습니다. 새 곡/삽입 제한 영상의 대안을 자동으로 찾을 때 서버가 YouTube Data API v3의 search.list·videos.list를 호출합니다. 이 검색에 아래 서버 API 키를 사용합니다.

Google 계정 아이디·비밀번호를 우리 서비스의 POST 요청으로 받아 iframe에 로그인시키지 않습니다. 공개 영상 검색 API 키와 사용자의 YouTube 로그인은 별개입니다. 계정에 재생목록을 저장하는 등 사용자 권한이 필요한 기능은 Google 공식 화면의 OAuth를 별도로 연결해야 하며, OAuth 토큰이 iframe의 Premium/광고 제거를 보장하지 않습니다. 현재 비밀번호 수집·OAuth·계정 저장은 추가하지 않았습니다. [Google OAuth 정책](https://developers.google.com/identity/protocols/oauth2/policies)·[YouTube 인증 안내](https://developers.google.com/youtube/data/guides/authentication).

## 발급

1. [Google Cloud Console](https://console.cloud.google.com/)에 본인 Google 계정으로 로그인합니다.
2. 프로젝트 선택 메뉴에서 사용할 개발 프로젝트를 선택하거나 새로 만듭니다.
3. **API 및 서비스 → 라이브러리**에서 **YouTube Data API v3**를 찾아 사용 설정합니다.
4. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → API 키**를 선택합니다. 공개 영상 검색용이므로 OAuth 클라이언트 ID와 구분합니다.
5. 생성한 키의 **API 제한사항**을 **YouTube Data API v3**로 지정합니다. 서버 호출용 키이므로 웹사이트 Referer 제한용 프런트 키로 만들지 않습니다. 서버의 고정 송신 IP를 확인할 수 있는 환경에서는 해당 IP의 애플리케이션 제한도 설정합니다.
6. 프로젝트의 YouTube API 할당량 화면에서 실제 허용 검색량을 확인합니다. 현재 공식 안내는 기본 search.list100회/일과 다른 API의 별도 할당량을 설명하지만 실제 프로젝트 설정을 기준으로 운영합니다.

[공식 시작 안내](https://developers.google.com/youtube/data/getting-started)·[인증 정보 발급](https://developers.google.com/youtube/registering_an_application)·[키 제한 설정](https://docs.cloud.google.com/api-keys/docs/add-restrictions-api-keys)을 따릅니다. 새 프로젝트의 약관·권한·설정은 본인이 확인합니다. 키 값은 채팅·Git·프런트 코드에 넣지 않습니다.

## Windows PowerShell에서 서버에 전달

현재 백엔드는 `.env`를 자동으로 읽지 않습니다. [예시 설정](../../../backend/.env.example)은 항목 안내입니다. API를 실행할 PowerShell에서 실제 키를 숨김 입력하고 같은 터미널에서 실행합니다.

```powershell
Set-Location -LiteralPath 'C:\MLO01-01\Chapter3,4 mission'
$youtubeKeyInput = Read-Host 'YouTube Data API 키' -AsSecureString
$env:YOUTUBE_DATA_API_KEY = [System.Net.NetworkCredential]::new('', $youtubeKeyInput).Password
Remove-Variable youtubeKeyInput
$env:C_LOCAL_DEMO = '1'
& '.\.venv\Scripts\python.exe' -m backend.manage runserver 127.0.0.1:8011 --noreload
```

기존8011 API가 실행 중이면 해당 API를 종료한 다음 이 명령으로 재시작합니다. 현재 Codex가 실행한 로컬 프로세스를 사용 중이라면 중복 실행하지 않고 담당자와 재시작을 조율합니다. 프런트5174·추천 작업자는 그대로 유지할 수 있습니다. 검색은 API 프로세스에서 수행합니다. 키를 임의 파일에 저장하거나 `.env.example`의 빈 항목에 실제 값으로 덮어쓰지 않습니다.

이 환경변수는 해당 PowerShell과 자식 프로세스에 전달됩니다. 다른 창·이미 실행 중인 API에 자동 적용되지 않습니다. API 키 교체/제한 변경 후에는 API를 다시 시작합니다. AWS 이전 시에는 INF의 서버 비밀 설정에 같은 환경변수를 주입하며 브라우저의 VITE_ 변수로 전달하지 않습니다.

## 동작 확인

1. 같은 PC의 Chrome에서 **http://127.0.0.1:5174/** 를 엽니다.
2. 지역·취향을 선택하고 **선곡표 받기**를 누릅니다.
3. 중앙 **음악 재생** 영역이 해당 목록의 현재 곡 영상을 자동으로 찾고 재생을 시도합니다. 브라우저가 자동 재생을 막으면 **재생**을 한 번 누릅니다.
4. 현재 곡이 끝나면 다음 곡으로 진행합니다. 삽입 불가100/101/150은 같은 원곡의 대안 후보를 시도하고, 소진하면 사유를 남긴 뒤 다음 곡으로 진행합니다. 미매핑곡의 검색 연결이 준비되지 않았으면 그 위치에서 안내하고 보류합니다.

API_KEY_MISSING은 키 등록/프로세스 재시작을, API_AUTH_FAILED는 API 사용 설정·키 제한을, 할당량/호출 제한은 프로젝트 할당량과 앱 보호 설정을 확인합니다. 실제 오류 응답에 키나 외부 URL을 반사하지 않습니다. API 검색 후보는 자동 매칭 CANDIDATE이며 수동 원곡 검수·Gold 승인과 다릅니다.

앱의 기본 보호값은 소유자당 분6회 검색·프로세스당 UTC일80회 검색·후보6시간 캐시입니다. 이는 프로젝트의 공식 할당량이 아니라 이번 구현의 보호 설정입니다. 기본 LocMem 캐시는 API 프로세스별이므로 재시작/다중 프로세스 전체의 운영 한도를 보장하지 않습니다. 운영 연결 시 공유 캐시/할당량 관리가 별도 필요합니다.

삽입 제한을 API 키나 로그인으로 해제하지 않습니다. 오류153은 페이지 출처/Referer 식별 문제로, 브라우저 자동 재생 보류는 클릭 대기로 구분합니다. 두 상태를 원곡 미존재나 LLM 필요로 바꾸지 않습니다. [공식 IFrame API](https://developers.google.com/youtube/iframe_api_reference)·[현재 연결 가이드](./YouTube_로컬_재생_기획과_구현_가이드.md)를 함께 확인합니다.
