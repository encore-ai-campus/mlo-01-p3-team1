# 매장 문맥 MCP 구현·연결 안내

| 항목 | 내용 |
|---|---|
| 담당·범위 | 오재석 / 4차 선택 확장: 매장·주변 장소·날씨 문맥 제공 |
| 작성·수정일 | 2026-11-04 |
| 작업 브랜치 | `feature/mood-mcp` |
| 기준 브랜치·커밋 | `feature/weather` · `a8a2467e4421c7b1b331a71a947e7eb4a5f92289` |
| 분기 기준 | 사용자의 feature 기준 작업 지시 적용 |
| 작업 번호 | 별도 배정 전. 기존 날씨 작업 번호로 대체하지 않음 |
| 현재 상태 | MCP 서버·클라이언트 및 추천 조건 정합성 구현, 로컬 44개 검증 통과. 실제 LLM·서비스 연결 및 추천 튜닝 대기 |

## 1. 목적과 적용 범위

점주 설정, 주변 장소 종류, 유효한 날씨를 LLM에 전달하는 읽기 전용 MCP 구현. 기존에는 이 자료를 함께 조회하는 MCP 경로가 없었으며, 이번 변경으로 동일 매장 기준의 조회 결과와 출처·누락 상태를 수집하는 연결 경로 추가.

기존 기본 추천, 날씨 ON/OFF 점수, 음악 후보 자격, 176~184분 검증은 기존 추천 모듈의 책임. MCP는 추천 조건을 제안할 자료를 제공하며, 곡 선정·재생·결과 저장을 수행하지 않음. 일반 추천의 필수 입력이나 로그인 조건도 변경하지 않음.

주변 장소 정보는 카카오 카테고리 검색 결과. 매출·유동 인구·고객 취향·지역의 분위기를 확인한 상권 분석 자료가 아님. 인테리어·선호 분위기는 점주 설정, 주변 업종 분포는 관측 자료, 음악 분위기 제안은 LLM의 추론으로 구분.

## 2. 기준 문서와 코드 연결

아래 문서는 기준 커밋 `a8a2467`에서 확인한 버전. 수령 문서와 제품 정책은 보존하고 이번 선택 확장의 구현·연결 상태를 이 문서에서 관리.

| 기준 | 반영 위치·내용 |
|---|---|
| [서비스 기능 및 사용자 흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md) | 공개 기본 추천을 유지하고 별도 매장 문맥 경로 추가 |
| [구현 설계도](../product/카페_음악_서비스_구현_설계도.md) | 기존 웹 API와 분리된 로컬 stdio 프로세스. 사용자 인증 연결은 미구현 |
| [추천 로직 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md) | 점수·후보·시간 정책 유지. LLM 응답의 최종 음악 검증은 기존 모듈에 연결 필요 |
| [구현 범위·완료 기준](../product/카페_음악_추천_서비스_3차_구현_태스크.md) | 4차 선택 확장으로 분리. 기존 작업의 완료 상태·선행 관계 변경 없음 |
| 기존 [날씨 조회](../../pipeline/weather/es_latest.py)·[유효성 재평가](../../pipeline/weather/service_view.py) | `get_weather_context`에서 같은 조회·판정 재사용. 조회 시각 기준 만료와 대상 시간별 유효성 반환 |

## 3. 파일별 변경

모든 경로는 저장소 루트 기준. MCP 코드·설정·검증·이 문서를 추가하고 자동 검사 설정을 보완. 기존 음악 추천·날씨 파이프라인·저장 구조는 그대로 사용.

| 경로 | 주요 함수·변경 내용 |
|---|---|
| `backend/store_context/__init__.py` | 매장 문맥 패키지 |
| `backend/store_context/server.py` | `create_server`, `main`: 공식 SDK 도구 등록·stdio 실행. 반경 입력의 문자열·실수·불리언 변환을 허용하지 않음 |
| `backend/store_context/service.py` | `ContextService`, `load_service`: 허용 매장 확인, 프로필·장소·날씨 응답 구성 |
| `backend/store_context/kakao.py` | `KakaoPlaces.search`: 카테고리 검색·페이지 제한·중복 제거·거리 및 응답 검증 |
| `backend/store_context/client.py` | `collect_context`, `model_input`, `request_conditions`, `read_local_server`: 출처·시간대·자료 용도 검증, LLM 응답 시간 제한·오류 정리, 제안 검증 |
| `backend/store_context/proposal.py` | `response_schema`, `validate_proposal`: 기존 `recommendation.inputs.options`와 `policy`의 선택 코드 재사용. 다른 매장·알 수 없는 조건·사용 불가 출처·곡 ID 제안 거절 |
| `backend/store_context/requirements.txt` | MCP 프로세스 전용 의존성 `mcp==1.30.0` |
| `config/examples/store-context.example.json` | 가상 매장·점주·권한·위치·선호 설정 예시 |
| `tests/test_store_context.py` | 조회·권한·부분 결과·만료·오류 단위 검증 |
| `tests/test_store_context_client.py` | 동일 매장·응답 규격·시간 제한·LLM 전달 검증 |
| `tests/test_store_context_mcp.py` | 공식 SDK의 실제 자식 프로세스 stdio 통신 검증 |
| `.github/workflows/application-tests.yml` | 광고 검사 커널 호환 조치, MongoDB 실패 로그, 공식 SDK를 설치하는 별도 MCP 검사 |

## 4. 도구와 응답 규격

| 도구 | 입력 | 제공 자료 |
|---|---|---|
| `get_store_profile` | `store_id` | 매장 위치·인테리어·선호 분위기·사용 목적·제외 조건·설정 버전 |
| `get_neighborhood_context` | `store_id`, `radius_m=500` | 반경 내 업종별 검색 건수·관측 건수·거리·검색 완결 여부 |
| `get_weather_context` | `store_id`, 선택 `target_time` | 기존 날씨 값·출처·예보 대상별 유효성·누락/만료 상태 |

도구는 `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=true`로 등록. 주석 값 외에 실제 구현도 읽기 전용이며 DB 변경·임의 URL·SQL 실행 기능 없음. MCP 초기화·도구 목록·호출·구조화 응답은 고정 버전 SDK로 처리. `schema_version=1`은 자체 응답 규격 버전이며 MCP 프로토콜 버전과 별개.

공통 응답: `schema_version`, `store_id`, `status`, `data`, `provenance`, `warnings`, `data_trust`. 출처에는 `source`, `queried_at`, `source_as_of`를 포함하며 확인할 수 없는 원천 기준 시각은 `null`.

| 상태 | 의미·사용 조건 |
|---|---|
| `ok` | 해당 도구의 정상 조회 결과 |
| `empty` | 주변 장소 조회를 완료했으나 검색 결과 없음 |
| `partial` | 페이지 한도·일부 조회 실패·만료 등으로 자료 일부만 사용 가능 |
| `unavailable` | 설정 누락·조회 실패·격자 불일치 등으로 자료 사용 불가 |

주변 장소의 기본 카테고리는 카페·문화시설·학교·지하철역·관광명소. 반경 50~2,000m, 카테고리당 최대 3페이지, 요청당 시간 제한 5초. 부분 결과는 전체 건수로 단정하지 않고 `observed_count`를 제공. 비율은 모든 카테고리 조회가 완료된 경우에만 산출. 외부 장소명·주소·전화번호는 모델 문맥에서 제외.

날씨는 `usable=true`인 예보와 `observation_usable=true`인 실황만 조건 제안에 사용. `missing_targets`, `invalid_type_targets`, `stale_targets`, `observation_stale` 경고를 함께 확인. 전체 상태가 부분 조회라는 이유로 모든 예보를 유효하게 취급하지 않음. `target_time`은 시간대가 있는 ISO 8601 시각이며 기존 현재 추천 구간 안의 예보 대상 시각만 조회 가능. `ready`는 조회한 예보 구간의 준비 상태이며 실황 유효성과 별개.

존재하지 않는 매장과 권한 없는 매장은 같은 `store_access_denied` 오류. 잘못된 반경·시각은 도구 오류. 호스트는 도구 오류·다른 매장의 응답·잘못된 규격·시간 초과 시 처리를 중단하고, 정상 응답 안의 원천 자료 부족은 상태와 경고를 유지.

## 5. 실행·설정

검증 환경은 Python 3.12.14, `mcp==1.30.0`. 저장소 루트에서 MCP 전용 환경의 Python으로 실행.

```text
python -m pip install -r backend/store_context/requirements.txt
python -m backend.store_context.server --config config/examples/store-context.example.json
```

서버는 stdio 연결을 기다림. 클라이언트가 서버를 시작하고 3개 도구를 호출하는 확인 명령:

```text
python -m backend.store_context.client --config config/examples/store-context.example.json --store-id example-cafe
```

설정 예시는 가상 자료. 실제 연결 시 운영자가 별도 비공개 설정 파일에 `principal_id`, `allowed_store_ids`, 각 매장의 `owner_id`, 좌표·날씨 격자·설정 버전·수정 시각·선호 항목을 입력. 도구 호출자가 신원·좌표·설정 파일 경로를 임의로 바꾸는 구조가 아님. 현재 권한 검사는 신뢰된 로컬 앱 설정 기준이며 서비스의 로그인 사용자 인증을 대체하지 않음.

| 환경 변수 | 사용처 |
|---|---|
| `KAKAO_REST_API_KEY` | 카카오 Local 카테고리 조회 |
| `ES_URL`, `WEATHER_INDEX` | 기존 날씨 Elasticsearch 조회 |
| `ES_USERNAME`, `ES_PASSWORD`, `ES_CA_CERT` | 기존 Elasticsearch 인증·TLS 설정 |

키·접속 정보·실제 매장 파일은 저장소에 포함하지 않음. 키나 날씨 연결 설정이 없으면 해당 자료는 `unavailable`. 예시 설정의 프로필 조회 성공만으로 외부 연결 성공을 판단하지 않음.

## 6. LLM 담당자 연결 지점

```text
LLM 호스트 → MCP 초기화 → 3개 조회 도구 → 동일 매장·응답 검증
          → 점주 요청과 자료를 분리해 모델에 전달 → 추천 조건 제안
          → 기존 음악 모듈의 후보 선정·정책 검증 [연결 대기]
```

초기화된 MCP `ClientSession`과 비동기 모델 호출 함수 `generate(payload)`를 `request_conditions(session, generate, store_id, owner_request)`에 전달. 모델 호출 함수는 호스트 담당자가 구현. 전달 항목은 `instruction`, `owner_request`, `store_context`, `response_schema`. 모델 API가 지원하는 구조화 출력 설정에 `response_schema`를 연결하고 결과는 Python 딕셔너리로 반환. 문맥 수집의 기본 제한은 20초, 모델 호출은 별도 30초이며 두 값을 호스트에서 지정 가능. 잘못된 점주 요청·모델 설정은 조회 전에 거절.

모델 응답의 필수 항목과 허용 범위:

| 항목 | 조건 |
|---|---|
| `schema_version` | 정수 `1` |
| `store_id` | 조회한 매장과 일치 |
| `option_version` | 기존 추천 `policy.OPTIONS`와 일치 |
| `conditions` | `vocal_option`, `tempo_preference`, `selected_theme_codes`, `selected_genre_codes` 중 제안할 항목만 포함. 기존 선택 코드·정규화 재사용 |
| `rationale` | 비어 있지 않은 2,000자 이하 설명 |
| `source_refs` | 조회된 매장·주변 장소·사용 가능한 날씨 도구의 이름. 중복·알 수 없는 출처·사용 불가 자료 참조 거절 |

형식·매장·코드·출처 참조를 검증한 뒤 `proposal`, `context`, `condition_contract_validated=True`, `catalog_selection_verified=False` 반환. 모델 오류 메시지는 `model_request_failed`, 시간 초과는 `model_request_timeout`으로 정리. 출처 참조 검증은 해당 자료를 조회했고 사용 가능한지 확인하는 범위이며 설명의 사실성이나 추천 품질을 증명하지 않음.

기존 `recommendation.provider.propose`는 적격 음악 후보를 받아 `track_ids`를 제안하는 별도 계약. 이번 MCP의 `conditions`를 그 함수의 곡 목록 응답으로 직접 전달하지 않음. 점주 확인·현재 선택 조건과의 조정·추천 요청 연결은 호스트 어댑터에서 구현해야 함. 날씨 ON/OFF·제외 곡·지역·점수/시간 정책은 모델 제안에 포함할 수 없으며 곡 선정·최종 검증은 기존 추천 모듈의 책임.

호스트의 stdio 실행 설정에는 MCP 전용 Python 경로, 서버 모듈과 `--config` 인수, 저장소 루트 작업 폴더, 필요한 환경 변수를 지정. 현재 제공 범위는 로컬 프로세스 연결이며 공유 HTTP 서비스·다중 사용자 인증은 별도 구현 대상.

## 7. 검증과 남은 연결

2026-11-04 정합성 보완 후 실행 결과: 44개 모두 통과, 건너뛴 검사 0개. 기존 날씨·설정 파일 52개는 기준 `feature/weather`와 일치 확인. MCP는 공식 SDK 1.30.0의 Python 3.12 환경에서 확인.

```text
python -m unittest tests.test_store_context tests.test_store_context_client tests.test_store_context_mcp -q
```

| 검증 | 확인 범위 |
|---|---|
| 조회·권한 20개 | 본인/타인/없는 매장, 허용 목록, 반경·좌표, 중복·페이지 한도, 부분 실패, 실황·예보별 유효성, 설정 버전의 불리언/실수 거절 |
| 클라이언트 21개 | 출처·시각·매장 일치, 기존 추천 코드와 정규화 호환, 곡 ID·정책 덮어쓰기·사용 불가 출처 거절, 잘못된 요청 선차단, 모델 시간 초과·오류 정리 |
| 실제 stdio 3개 | 초기화·도구 목록·3개 도구 호출, 권한·반경 타입 거절, 예시 설정 기동, 부분/불가 상태 전달, 실제 MCP 세션 뒤 잘못된 모델 응답 거절 |

SDK 미설치 환경은 stdio 3개를 건너뜀. 이번 자동 검사에는 SDK 전용 설치·`pip check`·위 전체 검증을 수행하는 `mcp` 작업을 추가해 기존 공통 검사에서 SDK 시험이 누락되는 문제를 보완. 외부 장소·날씨는 고정 자료 또는 빈 접속 설정으로 검증하며 실제 유료 LLM 호출은 포함하지 않음.

남은 항목은 실제 카카오·Elasticsearch 연결, 로그인 사용자와 매장 권한 연계, 실제 LLM 어댑터, 점주 조건 확인과 음악 후보 선정 연결, 추천 품질 평가·튜닝. 검색 캐시·응답 지연도 실측 전이며 현재 기본 5개 카테고리에서 최대 15회 순차 요청. 실제 조회 시간이 문맥 수집 제한을 넘으면 중단됨. 조회 후 곡 선정 시점의 날씨 유효성은 기존 추천 검증을 다시 거쳐야 함.

튜닝 시 동일 매장·동일 요청에서 문맥 사용 전후의 적합성, 근거 없는 추론, 누락 자료 처리, 응답 시간·비용을 비교할 계획. 아직 평가 결과나 성능 개선 수치를 확보한 상태는 아님.

## 8. 자동 검사 기동 실패 진단

11월 3일 `feature/weather` 2회와 11월 4일 `feature/mood-mcp` 1회 모두 광고용 임시 MongoDB 기동 단계에서 실패. 광고 테스트 본문은 미실행이며 다른 3개 검사는 통과. 10월 18일 성공 시점과 검사 설정은 같고 MongoDB 이미지·GitHub 실행 환경은 변경된 상태.

진단 커밋 `89c7321`의 [실행 기록](https://github.com/encore-ai-campus/mlo-01-p3-team1/actions/runs/41750542127)에서 종료 코드 1, `OOMKilled=false`, MongoDB fatal ID `12257600` 확인. MongoDB의 Linux 커널 버전 검사 때문에 기동 중 종료됨. GitHub 실행 환경의 Ubuntu 커널 표기와 MongoDB의 호환 판정 문제는 [runner-images #15005](https://github.com/actions/runner-images/issues/15005), [SERVER-131779](https://jira.mongodb.org/browse/SERVER-131779)에 보고된 현상과 일치.

공식 실행 환경 담당자가 제시한 임시 조치에 따라 광고 검사만 `ubuntu-22.04`에서 실행. MongoDB 8.0과 기존 광고 검사는 유지하고 시작 시 커널 버전, 실패 시 컨테이너 상태·종료 코드·최근 로그를 출력. 수정 커밋 `aa4d7cc`의 [실행 기록](https://github.com/encore-ai-campus/mlo-01-p3-team1/actions/runs/41750966968)에서 기존 검사 4개 모두 통과. MongoDB 수정 릴리스로 전환할 때는 해당 호환 문제 해결과 기존 광고 검증을 확인한 뒤 실행 환경을 재검토.
