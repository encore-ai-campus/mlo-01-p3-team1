# 잔여 31,708곡 YouTube URL 계속 수집 — 2026-10-18

- 문서 정리일: 2026-10-19

> 아래 결과와 미등록/미검수 설명은 해당 수집·검수 회차 당시의 기록입니다. 공유 파일·로컬 원본·후속 등록 상태는 [보관 및 인계 안내](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md)에서 구분합니다.

이번 회차의 내보내기 스냅샷입니다. **전체 31,708곡의 수집은 아직 완료되지 않았습니다.**

- 이번 추가 후보: **2,637곡 / 고유 신규 영상 URL 2,632개 / 고유 곡·영상 조합 2,715개**입니다.
- 이전 수집 54,777곡·61,933개 영상 ID를 제외했습니다. 기존 곡·영상과의 중복은 각각 0개입니다.
- 누적 후보 확보 곡은 **57,414곡**이며, **29,071곡이 미수집**입니다. 전체 GENERAL 86,485곡과 합계가 일치합니다.
- 모든 신규 후보는 `URL_COLLECTED_UNREVIEWED`입니다. 원곡·버전·생존·한국 재생·iframe·실제 재생 검수, 승인·레지스트리·대시보드 등록은 수행하지 않았습니다.

| 파일 | 내용 |
|---|---|
| [URL TXT · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/youtube-tail-new-urls.txt`) | 이번 회차의 새 영상 URL 2,632개를 영상 ID로 중복 제거한 목록입니다. |
| [곡·영상 CSV · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/youtube-tail-new-candidates.csv`) | 2,715개 후보 조합과 원천·검색어·발견 제목·원본 행·표기 보완·후속 검토 필드입니다. |
| [미수집 목록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/remaining-uncollected.csv`) | 29,071곡의 후속 수집 대상과 검색 시도·완료·재시도 상태입니다. |
| [집계·해시](./collection-summary.json) | 입력·제외 기준, 원천별 개수, 파일 SHA256, 이전 산출물 보존과 전체 수집 미완료 상태입니다. |
| [선정·제외 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/selection.json`) | 카탈로그 버전·해시, 기존 곡/영상 ID 집합입니다. |
| [수집 무결성 확인](./source-integrity-verification.json) | 출처 연결·중복·집계·내보내기 검사입니다. 음악/재생 검수와 다릅니다. |

CSV는 곡·영상 **조합**이며 같은 영상이 서로 다른 곡 ID 후보로 발견된 경우가 있습니다. TXT는 영상 URL을 한 번만 수록합니다. `shared_video_candidate_count`로 공유 여부를 확인하며, 이 연결을 서로 다른 곡의 원음원으로 승인하지 않습니다. 원천 간 같은 조합은 합치고 추가 근거는 `additional_evidence_json`에 보존합니다. `raw_collection_record_json`에는 원천별 수집 필드를 보존합니다.

수집 흐름은 이전 미수집 CSV와 기존 ID 집합 고정 → 원천 대조/개별 검색 → 기존 곡·영상 제외 → 곡·영상 조합 통합 → TXT/CSV 내보내기 → 재조회입니다. 개별 검색은 1,917곡에서 시도했고, 정상 검색을 완료한 곡은 1,910곡입니다. 미수집 중 7곡은 제한/오류로 재시도가 필요합니다. 검색했으나 새 URL을 못 얻은 곡을 영상 없음으로 확정하지 않습니다. 앞선 검색 실패와 이번 미시도를 구분합니다.

| 수집 출처 | 곡 | 고유 영상 | 조합 |
|---|---:|---:|---:|
| WEB_SEARCH_URL_COLLECTION | 990 | 990 | 990 |
| PUBLIC_METADATA_TAIL_EXPLICIT_CREDIT_URL_COLLECTION | 792 | 761 | 806 |
| PUBLIC_METADATA_LATIN_DIACRITIC_URL_CANDIDATE | 691 | 678 | 713 |
| WEB_SEARCH_RULE_CANDIDATE | 150 | 150 | 150 |
| PUBLIC_YOUNIVERSE_TITLE_DURATION_URL_COLLECTION | 11 | 10 | 11 |
| PUBLIC_METADATA_LATIN_DIACRITIC_DURATION_URL_CANDIDATE | 36 | 36 | 38 |
| PUBLIC_METADATA_SAME_YEAR_REMASTER_ORDER_URL_CANDIDATE | 7 | 7 | 7 |

각 출처의 곡/영상은 출처 사이에서 겹칠 수 있으므로 위 표의 단순 합은 전체 고유 개수와 다를 수 있습니다.

원천과 후보 조건:

- LAION e.V., [LAION-DISCO-12M](https://huggingface.co/datasets/laion/LAION-DISCO-12M/tree/6e7bf3758a77301e46a715af894fefd79bb1da53), revision `6e7bf3758a77301e46a715af894fefd79bb1da53`, Apache 2.0. 고정 5파일 12,320,916행의 메타데이터를 대조했습니다. 완전한 참여자 이름을 명시한 피처링/리믹스 크레딧, 같은 전체 제목 반복 등의 표기 보완을 후보로 분리했습니다. 명시되지 않은 참여자를 추정하거나 버전명을 일반 삭제하지 않았습니다. [수집·원천 행 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/laion-tail-summary.json`).
- LAION의 별도 라틴 악센트 후보는 라틴 기본 문자 뒤 U+0300~U+036F 결합 기호만 보완하고 **전체 제목 단어 순서·전체 아티스트 집합·길이 차 3초 이내**를 적용했습니다. 악센트가 다른 이름이 동일인임을 확정하지 않았으며 `latin_diacritic_normalization_requires_review`가 남습니다. [수집 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/laion-latin-diacritic-summary.json`)·[독립 원천 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/laion-latin-diacritic-integrity.json`).
- LAION의 동일 연도 리마스터 후보는 양쪽에 명시된 같은 연도와 remaster/remastered 표식을 유지한 채 말미 표기의 순서 차이만 보완했습니다. 전체 아티스트와 나머지 제목, 길이 차 3초 이내를 요구했고 연도 없는 버전·다른 연도·원곡과 결합하지 않았습니다. [수집 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/laion-remaster-order-summary.json`)·[원천 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/laion-remaster-order-integrity.json`).
- 라틴 악센트 조건을 유지한 별도 길이 차 후보는 3초 초과~`min(30초, max(15초, 원곡 길이의 10%))` 이내만 추가 선별했습니다. 엄격 3초 후보와 파일을 분리하고 `duration_difference_requires_review`를 남겼습니다. [수집 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/laion-latin-duration-summary.json`)·[원천 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/laion-latin-duration-integrity.json`).
- Manoel Horta Ribeiro와 Robert West(EPFL), [YouNiverse v1.1](https://zenodo.org/records/4650046), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 메타데이터에서 제목·완전한 아티스트 표기·길이로 URL 후보만 선별했습니다. **원천 전체 13,636,127,630바이트 중 앞부분 130,023,424바이트만 보존**했으며, 완전한 698,522개 JSONL 행을 읽었습니다. 전체 파일 다운로드·MD5 확인은 미완료입니다. 보존된 prefix SHA256과 실제 후보 행만 재확인했고, `PARTIAL_SOURCE_FILE_CHECKSUM_NOT_VERIFIED`를 유지합니다. [부분 원천 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/youniverse-summary.json`)·[prefix/후보 행 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/youniverse-prefix-integrity.json`). 변환은 대상 선별·필드 추출·URL 정규화이며 저작자·라이선스·원본 링크를 보존했습니다.
- 개별 공개 웹 검색은 실제 발견된 영상 URL·제목·검색어·출처를 `web-part*-evidence.jsonl`, `web-extra-evidence.jsonl` 및 `auto-search-evidence.jsonl`에 저장했습니다. 일부 자동/개별 후보는 제목·아티스트 전처리와 공동 크레딧 미확인 한계를 `match_basis`에 기록했습니다. 나머지 행은 발견 근거와 공통 미검수 상태를 보존하며, 빈 `match_basis`를 추가 확인 완료로 해석하지 않습니다. 자동 수집의 원발견 행·검색 시도는 `auto-search/batch-*-discoveries.jsonl` 및 `*-attempts.jsonl`에 남습니다. 검색 제목과 발견 근거는 곡의 원음원·한국 재생 보증이 아닙니다. 잘못된 형식의 미선택 검색 결과 URL은 근거 로그에 보존하되 최종 후보에 포함하지 않았습니다.

공개 원천의 `source_record_index`는 LAION에서 파일 내 0부터, YouNiverse에서 JSONL 행 1부터입니다. 자료 작성 시점과 수집 시점이 달라 URL이 사라졌을 수 있으며 별도 생존 확인은 하지 않았습니다. 길이 차가 3초를 넘는 앞선 명시 크레딧/YouNiverse 후보는 별도 차이 필드로 남겼습니다.

서비스 코드·추천 산출식·점수·날씨 후보·불변 결과·운영 저장소는 변경하지 않았습니다. 이전 수집 결과는 해시로 보존을 확인했고 새 자료만 이 폴더에 분리했습니다. 사용자 요청에 따라 커밋·푸시·배포·계정 변경도 수행하지 않았습니다. 변경 연결과 후속 인계는 [담당 라우팅 문서](../../docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md)를 따릅니다.
