# 날씨 4차 보완 및 매장 문맥 MCP 구현 기록

작성·수정: 2026-11-03 / 담당: 날씨·MCP 구현 지원(Codex)

구현·검증 기준: `encore-ai-campus/mlo-01-p3-team1`의 main, `f94f2f2021824eb7a0a686a2991759ed98d98a9e`.
반영 브랜치: `feature/weather`, 출발 커밋 `757edbcc6c969a7d90ed4170878a2075e51102df`.
두 기준의 날씨 실행 코드·관련 기존 검증 파일 일치 확인 후 이번 변경 17개 파일만 추가. main의 다른 기능 변경은 포함하지 않음. Git 반영과 운영 배포는 별도이며 운영 서비스는 미반영.

## 1. 기준과 적용 범위

사용자 요청: 날씨 4차 보완 구현 및 부가 기능인 MCP 연결 코드 작성.

| 기준 자료 | 이번 적용 |
|---|---|
| [사용자 흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md), [구현 설계도](../product/카페_음악_서비스_구현_설계도.md) | 기존 공개 추천·로그인 흐름 유지. MCP는 별도 로컬 연결 모듈 |
| [추천 기준](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md), [구현 범위](../product/카페_음악_추천_서비스_3차_구현_태스크.md) | 기존 음악 후보·제외·점수·재설정 정책 유지. MCP 출력은 추천 조건의 참고 근거 |
| [날씨 데이터 규격](../handoff/weather/02_날씨_데이터규격과_정제.md), [저장 구조](../handoff/weather/03_날씨_저장구조.md) | 시각·업무 키·정제 상태 재사용. 수령 문서 원문 보존 |
| 바탕화면 `4차 시작전 구현.md`(2026-10-19) | 재정제·장애 검증 취지 적용. MongoDB 중심 경로는 현재 코드의 ES 직접 저장 경로로 재확인 |

저장소 문서는 모두 위 기준 커밋의 자료. 문서의 과거 MongoDB·별도 ES 발행 설명을 현재 실행 경로의 증거로 사용하지 않음.

현재 코드 경로: `pipeline/weather/run_collector.py` → Kafka → `pipeline/weather/spark_job.py` → `es_latest.write_grid()` → Elasticsearch → `backend/weather/queries.py`.
이 경로는 소스 기준이며 실제 배포 구성은 별도 확인 필요.

## 2. 날씨 보완

| 기존 한계 | 구현 | 검증·제한 |
|---|---|---|
| 수집 성공 로그만으로 예정 요청의 누락 여부 판단 불가 | [quality_report.py](../../pipeline/weather/quality_report.py)의 `build_report`: 독립된 예정 요청 목록과 실제 로그 비교. 누락·실패·지연·대기 및 재시도 집계 | 고유 요청 성공률과 시도 성공률 분리. 전체 입력이라는 명시가 없거나 입력 오류가 있으면 불완전 상태 |
| 과거 입력의 정제 결과를 운영 저장소와 분리해 비교하는 실행 경로 부재 | [replay.py](../../pipeline/weather/replay.py)의 `replay_records`·`compare_rows`: 기존 `normalize_event` 재사용, 기간·격자 선택, 업무 값 비교 | 새 JSONL·보고서 파일만 생성. 운영 저장·Kafka offset·체크포인트 변경 없음 |
| 재정제 결과의 중복·누락·값 상태·시각을 일괄 확인하는 검사 부족 | [history_validation.py](../../pipeline/weather/history_validation.py)의 `analyze_history`: 메모리 SQLite SELECT 기반 검사 | 디스크 DB·스키마 생성 없음. 예상 업무 키 목록이 없으면 누락 미판정 |
| 저장 응답 유실·일부 격자 실패 후 재실행 근거 부족 | [test_weather_recovery.py](../../tests/test_weather_recovery.py): 실제 `es_latest.write_grid`와 모의 저장 전송 계층 결합 | 저장 직후 응답 유실, 일부 저장, 충돌, 구자료 재전달 확인. 실제 Kafka·Spark 프로세스 복구 증거와 구분 |

이력 업무 키는 `source, kind, nx, ny, category, issued_at, target_at`.
같은 발표의 재수집은 최신 수신 값으로 정리하고 발표 시각이 다른 자료는 각각 유지. 같은 수신 시각에 서로 다른 값이 있으면 임의 선택하지 않고 오류 처리.

재정제 입력은 내보낸 공통 이벤트 또는 `{topic, partition, offset, event}` JSONL. 원본 HTTP 응답에서 이미 유실된 내용은 복원 불가. 입력·매핑·정제 구현 해시와 제공된 offset 범위를 보고서에 기록하며, offset 범위만으로 전체 수집이 완전하다고 판정하지 않음.

현재 Kafka 보존 설정의 기본값은 168시간이나 실제 운영 보존 기간·남은 입력은 미확인. 이번 구현에 장기 이력 저장소나 자동 내보내기 기능은 포함하지 않음.

기존 최신 값 upsert·동시 갱신 보호·회차 완전성·만료 판정·재시도·모니터링은 유지. 이미 구현된 기능을 중복 개발하지 않음.

## 3. 매장 문맥 MCP

연결 순서: 조장님 LLM 호스트 → [client.py](../../backend/store_context/client.py) → 공식 MCP stdio 세션 → [server.py](../../backend/store_context/server.py) → [service.py](../../backend/store_context/service.py) → 점주 설정 / 카카오 장소 검색 / 기존 ES 날씨.

| 도구 | 입력 | 제공 내용 |
|---|---|---|
| `get_store_profile` | `store_id` | 점주가 지정한 인테리어·선호 분위기·이용 목적·제외 조건, 설정 버전 |
| `get_neighborhood_context` | `store_id`, `radius_m` | 검색 범위 내 업종별 확인 건수·가장 가까운 거리·조회 완전성 |
| `get_weather_context` | `store_id`, 선택 `target_time` | 기존 추천 구간 예보·관측, 시각별 `usable`, 누락·만료·유형 오류 대상 |

반환 공통 필드: `schema_version`, `store_id`, `status`, `data`, `provenance`, `warnings`, `data_trust`.
상태는 `ok / empty / partial / unavailable`. 조회 실패를 장소 0곳이나 정상 날씨로 대체하지 않음. 업종 조회가 불완전하면 `count=null`, 확인한 수는 `observed_count`로 구분. 전체 검색이 완료되지 않으면 비율 미제공.

장소 조회는 [카카오 Local 공식 카테고리 API](https://developers.kakao.com/docs/ko/local/dev-guide#search-by-category) 사용. 구현 범위는 기본 500m, 허용 50~2000m, 업종별 최대 3페이지·페이지당 15건. 기본 업종은 카페·문화시설·학교·지하철역·관광명소. 최대 15회 요청이며 공급자 제한·누락·오류는 부분 조회로 표시. 음식점은 설정에서 추가 가능.

장소 분포는 검색 결과이며 전체 상권 통계·방문객 취향·유동 인구를 뜻하지 않음. 지역명만으로 분위기를 단정하지 않음. 장소명·주소·전화번호 등 외부 자유문구는 LLM 입력에서 제외. 인테리어는 점주 설정이며 사진 자동 분석은 포함하지 않음.

`request_conditions(session, generate, store_id, owner_request)`가 세 도구 결과를 검증하고 호스트의 비동기 `generate(payload)` 함수로 전달. `payload`는 고정 지침·점주 요청·조회 자료를 분리. 호스트가 소유한 LLM API 연결을 이 함수에 주입하는 방식. 반환된 `proposal`은 추천 조건 제안이며 `catalog_selection_verified=False`. 기존 음악 모듈이 후보·제외·카탈로그·최종 결과를 검증해야 함.

보안·소유 경계:

- 신뢰된 서버 설정의 `principal_id`, `allowed_store_ids`, 매장의 `owner_id`를 함께 확인. 도구 인자로 사용자 신원·임의 좌표·URL·SQL을 받지 않음.
- 현재 연결은 신뢰된 로컬 호스트의 stdio 전용. 다중 사용자 웹 인증 기능은 아님. 웹 연결 시 서버에서 확인한 로그인 사용자와 매장 소유를 연결하는 어댑터 필요.
- 날씨 반환 격자가 설정과 다르면 차단. 조회 시 만료를 다시 계산하고 예보별 사용 가능 여부 제공.
- 외부 검색·점주 문구를 실행 지시로 취급하지 않도록 입력 분리. 이 조치만으로 실제 LLM의 지시 무시·오추천이 방지됐다고 확정하지 않음.

## 4. 실행·연결 조건

명령 실행 위치는 위 작업 폴더. `python`은 해당 모듈을 실행할 Python 환경을 뜻함.

```text
python -m pipeline.weather.quality_report --expected expected-requests.jsonl --logs collection.jsonl --now 2026-11-03T12:40:00+09:00 --output quality.json
python -m pipeline.weather.replay replay --input events.jsonl --mapping mapping.json --time-field target_at --start 2026-11-03T00:00:00+09:00 --end 2026-11-04T00:00:00+09:00 --output normalized.jsonl --report replay-report.json
python -m pipeline.weather.replay compare --before before.jsonl --after normalized.jsonl --report comparison.json
python -m pipeline.weather.history_validation --input normalized.jsonl --expected expected-history.jsonl --late-after-seconds 1200 --output history-quality.json
```

입력 파일명은 사용자가 확보한 자료의 경로로 대체. `expected-requests.jsonl`은 `{request_id, due_at}` 형식이며 성공 로그에서 역산하지 않음. `expected-history.jsonl`은 검사 대상의 위 7개 업무 키. 시각에는 시간대 필수. 품질 보고의 `--complete-window`는 예정 목록과 로그가 검사 기간 전체를 포함할 때만 추가. 기존 출력 파일 덮어쓰기 금지.

MCP 의존성: [requirements.txt](../../backend/store_context/requirements.txt)의 공식 SDK `mcp==1.30.0`. 사용자 설치 승인 후 아래 전용 환경에 설치 완료. 기존 프로젝트 환경에 설치하지 않음.

검증 환경: 별도 가상환경의 Python 3.12.14, MCP 1.30.0. 아래 MCP 명령의 `python`은 MCP 의존성을 설치한 환경 사용. `pip check` 결과 의존성 충돌 없음.

다른 개발 환경에서는 기존 패키지와 분리한 가상환경에 `python -m pip install -r backend/store_context/requirements.txt`로 설치. 명령은 저장소 루트에서 실행하며 LLM 호스트가 서버를 시작할 때도 같은 Python과 작업 경로 지정.

```text
python -m backend.store_context.server --config config/examples/store-context.example.json
python -m backend.store_context.client --config config/examples/store-context.example.json --store-id example-cafe --radius-m 500
```

첫 명령은 LLM 호스트가 시작하는 stdio 서버. 둘째 명령은 서버를 자식 프로세스로 실행해 조회 자료를 받는 클라이언트. [설정 예시](../../config/examples/store-context.example.json)는 가상 매장 자료이며 실제 매장·소유자·좌표·격자로 교체 필요.

필요 설정: `KAKAO_REST_API_KEY`, `ES_URL`, `WEATHER_INDEX`; 기존 ES 구성에 따라 `ES_USERNAME`, `ES_PASSWORD`, `ES_CA_CERT`. 키 값·접속 비밀번호를 설정 예시나 문서에 저장하지 않음. 키·ES 설정이 없으면 해당 자료는 `unavailable`로 반환. 전용 환경에서 서버 실행·실제 통신 확인 완료.

클라이언트 기본 도구 호출 제한은 20초. 느린 공급자·많은 페이지로 초과하면 호출 실패로 종료. 호스트 연결 함수의 `timeout_seconds`로 제한 조정 가능. 이 기본값의 실서비스 응답시간 적합성은 실제 연결 시험 대상.

## 5. 실제 검증 결과

| 범위 | 실행 결과 |
|---|---|
| 수집 품질·재정제·저장 장애 모의 검증 | `tests.test_weather_phase4`, `tests.test_weather_recovery`: 17개 통과 |
| SQL 이력 검사·시간대·상태·큰 임계값 | `tests.test_weather_history_validation`: 14개 통과 |
| MCP 조회 서비스·장소 실패/0건·소유·날씨 격자/만료 | `tests.test_store_context`: 19개 통과 |
| 클라이언트·호스트 경계·실제 서비스 함수 연결 | `tests.test_store_context_client`: 10개 통과 |
| 기존 날씨 ES·환경·폴더·Kafka 설정 회귀 | `tests.test_weather_es`, `tests.test_weather_environment`, `tests.test_weather_layout`, `tests.test_kafka_config`: 14개 통과 |
| 실제 공식 SDK stdio 교환·도구 호출·호스트 전달 | `tests.test_store_context_mcp`: 3개 통과, 건너뛴 검사 없음 |

합계 77개 통과. 서로 다른 검증 실행 결과를 합산한 고유 검사 수이며 전체 저장소 시험 결과가 아님. 설치 전 건너뛴 MCP 검사를 실행했고 설정 파일 기동·부분 실패 전달 검사 2개 추가.

기준 커밋의 기존 파일 1,075개는 SHA-256 비교 결과 변경·삭제 없음. 이번 소스·검증·설정 예시·기록 17개 파일 추가. 이 문서의 로컬 참조 링크 및 실행 명령의 인자 확인 완료.

실행 명령은 `python -m unittest <위 표의 모듈 이름> -q` 형식. 기존 환경 Python 3.13과 번들 Python 3.12 사용. 일부 파일 시험은 제한 환경의 임시폴더 접근 권한 오류로 실패한 뒤 허용된 로컬 실행으로 통과. 애플리케이션 결함과 환경 오류를 구분.

MCP 실제 통신 시험은 전용 환경에서 다음 명령으로 실행:

```text
python -X utf8 -m unittest tests.test_store_context_mcp -v
```

실제 서버·클라이언트 프로세스 간 MCP 초기화, 도구 목록·입력 규격, 세 도구 호출, 타 매장·반경 초과 차단, 호스트 함수 전달 검증. `server --config` 및 `read_local_server()` 경로도 예시 설정으로 실행. 키 없는 장소 조회·만료 날씨의 `unavailable/partial/usable=False`가 실제 통신과 호스트 경계를 통과해 유지됨을 확인.

카카오·ES는 고정 자료 또는 설정 없음으로 처리하고 LLM은 시험용 호스트 함수 사용. 외부 API·유료 LLM 호출 없음. 최초 제한 실행은 Windows 프로세스 간 통신 권한 오류로 실패했으며, 허용된 로컬 실행에서 3개 모두 통과(7.200초). 설치 과정의 임시폴더 권한 오류도 전용 환경을 대상으로 해결.

추가 교차검토: 실제 재정제 출력의 정제 상태 8종을 SQL 검사에 전달하여 업무 키·시각·상태 계약 일치 확인. MCP의 다른 격자 혼입·시간대별 만료 표시 누락을 발견해 수정 후 회귀 통과.

## 6. 남은 연결

1. 실제 매장 설정·읽기 권한이 있는 ES·카카오 설정으로 조회 확인. 외부 호출 비용·쿼터 조건 확인 후 실행.
2. 조장님 LLM 호스트의 인증된 매장 식별·`generate` 함수 연결, 실제 응답과 기존 음악 모듈 검증.
3. 보존된 Kafka 입력 범위·내보내기 경로 확보 및 실제 로그로 품질 보고·재정제 실행.
4. 격리된 Kafka·Spark·ES 환경에서 프로세스 종료·동일 체크포인트 재개 검증.
5. feature/weather 변경의 팀 리뷰 및 통합 브랜치 반영 후 배포·실서비스 확인.

현재 결과는 로컬 구현과 해당 검증 범위까지. 실제 음악 추천·실서비스 연결·운영 장애 복구 완료로 간주하지 않음.
