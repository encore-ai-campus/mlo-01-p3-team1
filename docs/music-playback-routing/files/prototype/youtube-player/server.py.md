# prototype/youtube-player/server.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [prototype/youtube-player/server.py](../../../../../prototype/youtube-player/server.py)
- 범위/목적: loopback 전용 플레이어·큐/영상 매핑 로컬 HTTP 서버

## 기준과 입력

PlaylistStore가 general/examples CSV와 별도 mapping 파일을 읽습니다. SearchProvider는 설정된 서버 키가 있을 때만 공식 YouTube Data API를 호출하며 키 없이도 수동 검증 매핑 경로를 제공합니다.

[최신 ON/OFF 후보 계약](../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

/api/config·/api/playlists·/api/playlists/{WEATHER}·/api/youtube/search와 /api/mappings/import를 제공합니다. GENERAL+검증된 영상 매핑만 재생 가능한 큐로 표시하며 원래 CSV 열과 source/queue/mapping 버전을 보존합니다.

web 플레이어가 API 응답을 소비합니다. loopback Host/Origin/nonce·정적 파일 허용 목록·매핑 배치 원자성/낡은 revision 충돌을 적용합니다. Premium·로그인·실제 음성 출력을 자동으로 검증했다고 표시하지 않습니다.

근거: [연결 문서/검증 자료](../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md). [정본 차이·남은 연결](../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `utc_now`: function, 소스 30행
- `digest`: function, 소스 34행
- `InputError`: class, 소스 38행 / base ValueError
- `ConflictError`: class, 소스 42행 / base InputError
- `PlaylistStore`: class, 소스 46행
- `PlaylistStore.__init__`: method, 소스 47행
- `PlaylistStore.source`: method, 소스 52행
- `PlaylistStore.mappings`: method, 소스 75행
- `PlaylistStore.known_tracks`: method, 소스 91행
- `PlaylistStore.validate_mapping`: method, 소스 103행 / decorator staticmethod
- `PlaylistStore.import_mappings`: method, 소스 140행
- `PlaylistStore.playlist`: method, 소스 166행
- `PlaylistStore.listing`: method, 소스 187행
- `iso_duration`: function, 소스 198행
- `SearchProvider`: class, 소스 206행
- `SearchProvider.__init__`: method, 소스 208행
- `SearchProvider.request`: method, 소스 215행
- `SearchProvider.search`: method, 소스 224행
- `LocalServer`: class, 소스 255행 / base ThreadingHTTPServer
- `LocalServer.__init__`: method, 소스 258행
- `Handler`: class, 소스 264행 / base BaseHTTPRequestHandler
- `Handler.log_message`: method, 소스 267행
- `Handler.local_origin`: method, 소스 270행
- `Handler.headers_for`: method, 소스 280행
- `Handler.send_json`: method, 소스 291행
- `Handler.protected`: method, 소스 296행
- `Handler.do_GET`: method, 소스 302행
- `Handler.do_POST`: method, 소스 337행
- `main`: function, 소스 358행

```python
utc_now() -> str
digest(value: object) -> str
class InputError(ValueError)
class ConflictError(InputError)
class PlaylistStore
PlaylistStore.__init__(self, data_dir: Path, mapping_file: Path)
PlaylistStore.source(self, weather: str) -> tuple[list[dict], str]
PlaylistStore.mappings(self) -> tuple[dict[str, dict], str]
PlaylistStore.known_tracks(self) -> dict[str, dict]
PlaylistStore.validate_mapping(record: dict, source: dict) -> dict
PlaylistStore.import_mappings(self, payload: dict) -> dict
PlaylistStore.playlist(self, weather: str) -> dict
PlaylistStore.listing(self) -> dict
iso_duration(value: str) -> float
class SearchProvider
SearchProvider.__init__(self, api_key: str | None)
SearchProvider.request(self, endpoint: str, parameters: dict) -> dict
SearchProvider.search(self, source: dict) -> dict
class LocalServer(ThreadingHTTPServer)
LocalServer.__init__(self, port: int, store: PlaylistStore, search: SearchProvider)
class Handler(BaseHTTPRequestHandler)
Handler.log_message(self, format: str, *args: object) -> None
Handler.local_origin(self) -> str | None
Handler.headers_for(self, status: int, kind: str, length: int) -> None
Handler.send_json(self, status: int, payload: object) -> None
Handler.protected(self, *, read: bool=False) -> bool
Handler.do_GET(self) -> None
Handler.do_POST(self) -> None
main() -> None
```
