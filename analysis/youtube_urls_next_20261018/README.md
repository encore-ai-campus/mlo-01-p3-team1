# 잔여 29,071곡 YouTube URL 계속 수집 — 2026-10-18

- 문서 정리일: 2026-10-19

> 아래 결과와 미등록/미검수 설명은 해당 수집·검수 회차 당시의 기록입니다. 공유 파일·로컬 원본·후속 등록 상태는 [보관 및 인계 안내](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md)에서 구분합니다.

이번 회차 내보내기 스냅샷입니다. **전체 29,071곡 수집은 아직 완료되지 않았습니다.**

- 이번 추가: **2,438곡 / 고유 신규 영상 URL 2,404개 / 곡·영상 조합 2,523개**입니다.
- 기존 57,414곡·64,565개 영상 ID를 제외했으며 기존 곡·영상과의 중복은 각각 0개입니다.
- 누적 확보는 **59,852곡**, 미수집은 **26,633곡**입니다. 합계는 GENERAL 86,485곡입니다.
- 전부 `URL_COLLECTED_UNREVIEWED`입니다. 원곡/버전·생존·한국 재생·iframe·실제 재생 검수, 승인·레지스트리·대시보드 등록은 하지 않았습니다.

| 파일 | 내용 |
|---|---|
| [URL TXT · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/youtube-next-new-urls.txt`) | 영상 ID로 중복 제거한 이번 신규 URL 2,404개 |
| [곡·영상 CSV · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/youtube-next-new-candidates.csv`) | 2,523개 조합과 실제 원천/검색어/발견 제목/후속 검토 필드 |
| [미수집 목록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/remaining-uncollected.csv`) | 26,633곡과 이번·누적 검색/재시도 상태 |
| [집계·해시](./collection-summary.json) | 원천별 집계, 보존·내보내기 SHA256, 전체 수집 미완료 상태 |
| [선정·제외 기준 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/selection.json`) | 카탈로그 버전·이전 입력 해시·기존 곡/영상 ID 집합 |
| [수집 무결성 확인](./source-integrity-verification.json) | 실제 출처·중복·집계·내보내기 대조. 음악/재생 검수와 별개 |
| [이전 파일 보존 확인 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/prior-files-preservation.json`) | 이전 수집 자료·수령 음악 README의 별도 보존 스냅샷 대조 |

이전 입력은 `youtube_urls_tail_20261018/remaining-uncollected.csv`이며 SHA256은 `4436a6611bcb01384f201487944e7fda969852845f0ca82ed5570f0eb6151f58`입니다. 이번 [작업 큐 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/continuation-queue.csv`)는 이전 검색 상태를 보존하고 continuation 위치·상태 컬럼을 추가했으므로 SHA256이 `3c14e05d29b0dcffe03b13aa8162273c4efd979a48ecbb841dcc0695a7c77304`로 다릅니다. 이전 산출물은 변경하지 않았습니다.

CSV는 곡·영상 조합입니다. 같은 영상이 서로 다른 곡 ID의 후보로 발견된 경우 `shared_video_candidate_count`를 남기고, TXT에는 한 번만 수록했습니다. 공유 연결을 서로 다른 곡의 원음원으로 승인하지 않습니다. 같은 조합의 추가 출처는 `additional_evidence_json`, 원천별 필드는 `raw_collection_record_json`에 보존합니다.

| 수집 출처 | 곡 | 고유 영상 | 조합 |
|---|---:|---:|---:|
| PUBLIC_YOUNIVERSE_TITLE_DURATION_URL_COLLECTION | 274 | 274 | 274 |
| PUBLIC_METADATA_ALBUM_TARGET_ARTIST_SUBSET_URL_CANDIDATE | 108 | 108 | 108 |
| PUBLIC_METADATA_PRIMARY_ARTIST_MISSING_CREDITS_URL_CANDIDATE | 819 | 795 | 899 |
| PUBLIC_METADATA_ORTHOGRAPHIC_FULLTITLE_URL_CANDIDATE | 65 | 65 | 66 |
| PUBLIC_YOUNIVERSE_CHANNEL_TITLE_DURATION_URL_COLLECTION | 64 | 64 | 64 |
| WEB_SEARCH_URL_COLLECTION | 803 | 803 | 803 |
| PUBLIC_METADATA_ORTHOGRAPHIC_CREDIT_URL_CANDIDATE | 103 | 90 | 104 |
| WEB_SEARCH_RULE_CANDIDATE | 203 | 203 | 203 |
| PUBLIC_METADATA_COMPLETE_COMPACT_TITLE_ARTISTS_ALBUM_URL_CANDIDATE | 2 | 2 | 2 |

위 표는 같은 조합을 병합한 뒤의 대표 출처별 집계입니다. 추가 출처는 원본 후보와 `additional_evidence_json`에 남습니다. 출처 사이에 같은 곡/영상이 있을 수 있어 표의 단순 합은 전체 고유 개수와 다를 수 있습니다.

수집 흐름은 입력/기존 ID 고정 → 공개 메타데이터 대조·곡별 공개 검색 → 기존 곡/영상 제외 → 조합 통합 → TXT/CSV 내보내기·재조회입니다. 이번 개별 검색 시도는 1,848곡, 정상 완료는 1,841곡이며 미수집 중 7곡은 제한/오류 재시도가 필요합니다. 앞선 실패·이번 미시도·현재 재시도를 구분합니다. 정상 검색을 완료하면 이전 재시도 상태를 해제하며, 검색 결과 없음은 영상이 존재하지 않는다는 판정이 아닙니다.

원천과 후보 조건:

- LAION e.V., [LAION-DISCO-12M](https://huggingface.co/datasets/laion/LAION-DISCO-12M/tree/6e7bf3758a77301e46a715af894fefd79bb1da53), revision `6e7bf3758a77301e46a715af894fefd79bb1da53`, Apache 2.0. 고정 5파일 12,320,916행을 대조했습니다. 라틴 결합 악센트와 명시 문자 `ø/ł/đ/ð/þ/æ/œ`, `&→and`만 보완하고 제목/버전/연도·완전한 아티스트 이름을 유지했습니다. 완전한 이름으로 입증된 feat/리믹스 크레딧과 전체 제목 반복 조건은 별도 기록합니다. 추정 별칭·번역·일반 버전 삭제를 적용하지 않았습니다. 표기 보완은 동일인/동일곡 확정이 아니며 `orthographic_normalization_requires_review`가 남습니다. 길이 차는 `min(30초,max(15초,원곡 길이의 10%))` 이내이며 3초 초과는 추가 검토 표시가 있습니다. [명시 크레딧/반복 수집 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-orthographic-summary.json`)·[원천 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-orthographic-integrity.json`), [전체 제목 수집 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-orthographic-fulltitle-summary.json`)·[원천 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-orthographic-fulltitle-integrity.json`).
- LAION의 별도 **공동 크레딧 누락 후보**는 전체 제목/버전·주 아티스트의 완전한 이름·길이 차 3초 이내를 요구합니다. 원천 아티스트 집합이 대상 집합의 진부분집합일 때만 포함하고 서로 다른 추가 아티스트가 있는 행은 제외합니다. 빠진 공동 아티스트는 추정하거나 확인 완료로 처리하지 않으며 `missing_source_artist_credits`·`coartist_identity_review_required`를 보존합니다. 이 후보는 위의 전체 아티스트 일치 후보와 분리합니다. [수집 조건 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-primary-missing-credits-summary.json`)·[원천 행/규칙 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-primary-missing-credits-integrity.json`).
- LAION의 별도 **앨범·참여자 부분집합 후보**는 전체 제목/버전과 **전체 앨범명**까지 같고 길이 차 3초 이내인 경우에만 수집합니다. 원천의 모든 아티스트가 대상 곡 참여자에 포함되어야 하지만 주 아티스트가 원천 크레딧에 없을 수 있습니다. `primary_artist_credit_review_required`·`coartist_identity_review_required`, 누락된 이름과 실제 원천 이름을 보존합니다. 주 아티스트 일치 후보로 설명하거나 승인하지 않습니다. [수집 조건 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-album-artist-subset-summary.json`)·[원천 행/규칙 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-album-artist-subset-integrity.json`).
- LAION의 별도 **공백 경계 차이 후보**는 명시 표기 보완 뒤 전체 제목과 모든 아티스트의 문자/숫자가 빠짐없이 같고 공백 경계만 다른 경우입니다. 전체 앨범 단어순서 일치와 길이 차 3초 이내를 추가 요구하며 `word_boundary_normalization_requires_review`를 남깁니다. 이름의 경계가 달라도 동일인이라고 확정하지 않습니다. [수집 조건 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-compact-album-summary.json`)·[원천 행/규칙 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/laion-compact-album-integrity.json`).
- Manoel Horta Ribeiro·Robert West(EPFL), [YouNiverse v1.1](https://zenodo.org/records/4650046), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 영상 메타데이터 전체 13,636,127,630바이트 중 **prefix 4,294,967,296바이트**, 완전한 JSONL 23,109,761행을 처리했습니다. 전체 영상 파일의 다운로드·공식 MD5 확인은 미완료이며 `PARTIAL_SOURCE_FILE_CHECKSUM_NOT_VERIFIED`를 유지합니다. 실제 저장 prefix의 SHA256·후보 행만 대조했습니다. [부분 원천 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/youniverse-summary.json`)·[prefix/행 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/youniverse-prefix-integrity.json`).
- YouNiverse 채널 보조 자료 `df_channels_en.tsv.gz`는 전체 5,960,728바이트와 공식 MD5를 확인했습니다. 영상 channel_id와 원천 채널 행을 조인하고 전체 제목/버전 및 **모든 대상 아티스트 이름**이 채널 표시명과 일치하는 후보만 별도 수집했습니다. 끝의 ` - Topic`/`VEVO` 보완을 기록하고 임의 별칭을 추정하지 않았습니다. 채널 이름은 공식 계정·아티스트·원음원 승인 근거가 아니며 `channel_identity_review_required`를 유지합니다. 채널 전체 파일 검증과 영상 부분 파일 상태를 구분합니다. [채널 수집 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/youniverse-channel-summary.json`)·[행 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/youniverse-channel-integrity.json`).
- 공개 웹 검색의 실제 영상 URL·제목·검색어·출처는 `web-part*-evidence.jsonl`·`auto-search-evidence.jsonl`에 보존했습니다. 자동 검색 원발견과 시도는 `auto-search/batch-*-discoveries.jsonl`·`*-attempts.jsonl`에 남습니다. 일부 후보는 주 아티스트만 확인한 한계와 표기 보완을 `match_basis`에 기록합니다. 빈 basis도 검수 완료를 뜻하지 않습니다. 명확히 다른 제목/표시 버전은 수집에서 제외하지만 곡을 청취하거나 원음원으로 승인하지 않았습니다.

원천 행은 LAION에서 파일 내 0부터, YouNiverse 영상 JSONL·채널 데이터 행에서 1부터입니다. 원천 작성 시점과 현재 시점이 달라 URL이 사라졌을 수 있으며 생존 확인은 하지 않았습니다. 제목이 기호 `△`뿐인 1곡은 이 단어 기반 대조에서 비교할 수 없어 미수집으로 남겨두었습니다. 곡 자체를 무효로 판정하지 않았습니다. 원천 변환은 대상 선별·명시 표기 보완·필드 추출·URL 정규화이며 저작자·원천 링크·라이선스를 보존합니다.

원천별 raw record의 `latin_diacritic_*` 차이 필드는 이번 명시 라틴 문자/결합 기호/접속사 보완 전후의 차이를 나타내며, 차이가 단순 악센트에만 한정된다는 판정은 아닙니다. 적용 규칙과 실제 표기는 각 행에 보존되어 있습니다.

여기서 주 아티스트는 `artists_name`을 `;`로 나눈 첫 번째 이름을 뜻합니다. 별도 보컬·권리 주체 분류를 생성하지 않았습니다.

서비스 코드·추천 수식/점수·날씨 후보·불변 결과·승인 147곡·운영 레지스트리·대시보드는 변경하지 않았습니다. 수령 원문도 수정하지 않았습니다. 커밋·푸시·PR·배포·계정 변경은 하지 않았습니다. 후속 수집과 음악/재생 검수·등록은 별도 작업입니다. [담당 변경 라우팅](../../docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md).
