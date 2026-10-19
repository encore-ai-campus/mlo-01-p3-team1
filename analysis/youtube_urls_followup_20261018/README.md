# 잔여 25,318곡 YouTube URL 추가 수집 — 2026-10-18

- 문서 정리일: 2026-10-19

> 아래 결과와 미등록/미검수 설명은 해당 수집·검수 회차 당시의 기록입니다. 공유 파일·로컬 원본·후속 등록 상태는 [보관 및 인계 안내](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md)에서 구분합니다.

이번 회차 최종 내보내기입니다. **추가 1,008곡 / 고유 영상 URL 1,008개 / 곡·영상 조합 1,008개**, **미수집 24,310곡**입니다. 전체 수집 완료 여부는 `collection_complete=false`입니다.

기존 **61,167곡·68,284개 영상 ID**를 제외했으며 기존 곡·영상과의 중복은 각각 0개입니다. 누적 **62,175곡** + 미수집 **24,310곡** = GENERAL 86,485곡입니다. 후보 상태는 모두 `URL_COLLECTED_UNREVIEWED`입니다. 음악·동일 녹음/버전·URL 생존·한국 재생·iframe·청취 검수, 승인·레지스트리/대시보드 등록은 하지 않았습니다.

| 파일 | 내용 |
|---|---|
| [곡·영상 CSV · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/youtube-followup-new-candidates.csv`) | 1,008개 조합, 원래 곡 정보와 실제 발견 제목·검색어·원천 기록 |
| [URL TXT · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/youtube-followup-new-urls.txt`) | 고유 신규 영상 URL 1,008개 |
| [미수집 목록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/remaining-uncollected.csv`) | 24,310곡과 이번·누적 검색/재시도 상태 |
| [선정·제외 기준 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/selection.json`)·[고정 입력 큐 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/continuation-queue.csv`) | 부모 입력 해시와 기존 곡·영상 ID |
| [집계·해시](./collection-summary.json) | 실제 수집 수, 출처별 집계·입출력 SHA256, 전체 수집 완료 여부 |
| [출처·내보내기 대조](./source-integrity-verification.json) | 실제 발견/원천 행과 최종 CSV/TXT·미수집 분할 대조. 음악 검수가 아님 |
| [출처 간 중복 제외 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/final-source-overlap.json`) | 웹·메타데이터 사이의 곡·영상 ID 중복 제외 |
| [이전 파일 보존 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/prior-files-preservation.json`) | 이전 산출물과 수령 음악 README 보존 |

부모는 [이전 미수집 목록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/remaining-uncollected.csv`)이며 SHA256은 `d37e1fbabd883b1f1dc5832cf366de9619614134e782e2441b58942992fa14fa`입니다. 이번 큐 SHA256은 `1aa4a36beb381952aefe62694f245058db15b192396ab61fcc52f1e9342404c0`입니다. 부모 위치와 누적 검색 여부를 보존한 별도 큐이므로 두 해시가 다릅니다. 기존 파일은 수정하지 않았습니다.

| 대표 출처 | 곡 | 고유 영상 | 조합 |
|---|---:|---:|---:|
| PUBLIC_YOUNIVERSE_TITLE_DURATION_URL_COLLECTION | 14 | 14 | 14 |
| WEB_SEARCH_RULE_CANDIDATE | 994 | 994 | 994 |

이번 개별 검색은 **2,092곡**, 정상 완료 **2,092곡**입니다. 미수집 중 검색 제한/오류 재시도 대상은 **0곡**입니다. 검색 완료와 URL 확보는 별도이며, 정상 검색 결과 없음은 영상 부재 확정이 아닙니다. 기존에 검색한 곡과 이번 검색·미시도 상태를 `search_attempted_cumulative`·`search_completed_cumulative` 및 이번 이력 필드로 구분합니다.

공개 웹 검색은 실제 영상 URL·검색 결과 제목·검색어·수집 조건을 `auto-search-candidates.jsonl`·`auto-search-evidence.jsonl`·`auto-search/batch-*-discoveries.jsonl`·`*-attempts.jsonl`에 보존합니다. 수집 대상 제목의 전체 단어 순서와 검색 결과에 나타난 주 아티스트 전체 이름을 요구하고, 명시된 공동 아티스트 괄호 크레딧과 제한된 표시 단어만 처리합니다. 주 아티스트가 제목 대신 결과 문맥에 나타난 경우와 공동 아티스트 미확인의 한계는 `match_basis`에 남깁니다. 별칭·번역·동일 녹음을 승인하지 않았습니다. 최초 12곡은 문자열 site 조건으로 실제 검색했으나 수집 후보가 없었고, 마지막에 도메인 필터로 다시 검색해 발견 이력을 별도 묶음에 보존했습니다. 선택된 URL은 `youtube.com`·`youtu.be` 도메인 필터 검색에서 얻었습니다. 곡 수는 고유 곡 기준이므로 같은 곡의 추가 검색 요청을 중복 가산하지 않습니다. 비공식 YouTube 검색 API나 로그인 정보를 사용하지 않았습니다.

추가 메타데이터 출처는 Manoel Horta Ribeiro·Robert West(EPFL)의 [YouNiverse v1.1](https://zenodo.org/records/4650046), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)입니다. 원천을 선택·정규화해 URL 후보와 출처 필드를 추출했습니다. 이전 6GiB prefix의 SHA256을 확인해 별도 위치로 복사한 뒤 정상 HTTP 206 Range로 이어받았습니다. 전송의 조기 EOF 후 한 번 정상 이어받았으며, 전송 속도 저하로 받은 범위를 보존하고 다운로드 세션을 종료했습니다. 실제 보존한 영상 **메타데이터** 파일 `yt_metadata_en.jsonl.gz`는 **6,753,768,064바이트**, 완전하게 읽힌 JSONL은 **36,302,124행**입니다. 요청한 8GiB 수신 완료로 표시하지 않습니다. 전체 13,636,127,630바이트와 공식 전체 MD5는 미확인이고 `source_file_checksum_complete=False`·`PARTIAL_SOURCE_FILE_CHECKSUM_NOT_VERIFIED`를 유지합니다. 음원·영상 파일은 받지 않았습니다.

메타데이터 기본 후보는 전체 제목/버전과 전체 아티스트 이름이 명시된 `artist - song` 또는 역순 표기, 길이 차 3초 이내 또는 `min(30초,max(15초,원곡 길이 10%))` 이내 조건을 사용합니다. 늘어난 길이 차는 미확인 상태로 남깁니다. 채널 보조 후보는 영상 제목·버전과 전체 대상 아티스트 이름에 맞는 채널 `name_cc`를 조인하며, Topic/VEVO 끝 표시만 처리합니다. 채널 파일은 전체 공식 MD5를 확인했지만 영상 메타데이터의 전체 체크섬 확인을 뜻하지 않습니다. [영상 수집 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/youniverse-summary.json`)·[채널 수집 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/youniverse-channel-summary.json`)에 0건을 포함한 실제 결과를 남겼습니다. 원천 작성 시점과 현재 시점의 차이에 따른 URL 생존·재생 여부는 후속 검수 대상입니다.

수집 흐름은 부모 입력/기존 ID 고정 → 서로 다른 곡의 공개 검색과 공개 메타데이터 처리 → 기존·이번 곡/영상 중복 제외 → CSV/TXT·미수집 큐 저장 → 원천·발견 기록과 최종 파일 대조입니다. CSV의 `raw_collection_record_json`·`additional_evidence_json`과 실제 원천 행 번호를 보존합니다. 서비스 코드·추천 수식·날씨 후보·불변 결과·DB/레지스트리·대시보드·수령 원문은 변경하지 않았습니다. 커밋·푸시·PR·배포·계정 변경도 하지 않았습니다. 남은 곡의 수집과 음악/재생 검수·등록은 후속입니다. [담당 변경 라우팅](../../docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md)을 함께 확인합니다.
