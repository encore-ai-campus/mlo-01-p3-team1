# 잔여 26,633곡 YouTube URL 계속 수집 — 2026-10-18

- 문서 정리일: 2026-10-19

> 아래 결과와 미등록/미검수 설명은 해당 수집·검수 회차 당시의 기록입니다. 공유 파일·로컬 원본·후속 등록 상태는 [보관 및 인계 안내](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md)에서 구분합니다.

이번 회차의 최종 내보내기 스냅샷입니다. 전체 대상 중 **25,318곡은 아직 미수집**입니다.

- 이번 추가: **1,315곡 / 고유 신규 영상 URL 1,315개 / 곡·영상 조합 1,315개**입니다.
- 기존 **59,852곡·66,969개 영상 ID**를 제외했으며 기존 곡·영상과의 중복은 각각 0개입니다.
- 누적 **61,167곡** + 미수집 **25,318곡** = GENERAL 86,485곡입니다.
- 전부 `URL_COLLECTED_UNREVIEWED`입니다. 음악/동일 원음원·현재 URL 생존·한국 재생·iframe·실제 재생 검수, 승인·대시보드 등록은 수행하지 않았습니다.

| 파일 | 내용 |
|---|---|
| [URL TXT · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/youtube-continue-new-urls.txt`) | 영상 ID로 중복 제거한 이번 신규 URL 1,315개 |
| [곡·영상 CSV · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/youtube-continue-new-candidates.csv`) | 1,315개 조합과 실제 원천/검색어/발견 제목/추후 검토 필요 표시 |
| [미수집 목록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/remaining-uncollected.csv`) | 25,318곡, 이번·누적 검색 및 재시도 상태 |
| [집계·해시](./collection-summary.json) | 원천별 집계·입출력 SHA256·전체 수집 완료 여부 |
| [선정·제외 기준 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/selection.json`) | 카탈로그 버전·부모 입력 해시·기존 곡/영상 ID |
| [작업 큐 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/continuation-queue.csv`) | 부모 검색 이력을 보존한 26,633곡의 고정 입력 |
| [출처·내보내기 대조](./source-integrity-verification.json) | 실제 원천 행·검색 증거·중복·합계·최종 파일 해시 확인 |
| [수집 규칙 경계 시험](./collection-rule-boundaries.json) | 서로 다른 리마스터/다른 버전·아티스트·앨범·길이·불완전 괄호 등 합성 조건 확인. 음악 검수가 아님 |
| [이전 파일 보존 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/prior-files-preservation.json`) | 앞선 수집 산출물과 수령 음악 README의 보존 확인 |

부모 입력은 [이전 미수집 목록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/remaining-uncollected.csv`)이며 SHA256은 `53e5e3bf6f708e6840eeae5228cd52fcc4c526a044f395b5e63c2808b80b6921`입니다. 이번 큐의 SHA256은 `78232641f92f5772d2459e946b04acf305b10d2aefc87674a391f57cab60ee6e`입니다. 부모 위치는 `parent_continuation_position`에 보존하고 새 위치·누적 검색 이력 필드를 추가했기 때문에 두 해시가 다릅니다. 앞선 파일은 변경하지 않았습니다. 입력 카탈로그는 `spotify-preview-b202fa49909b-general-c2478b153aa8-yt-39c5056603a0`입니다.

CSV는 곡·영상 조합이며 TXT는 고유 영상 목록입니다. 같은 영상이 여러 곡 ID의 후보일 수 있어 `shared_video_candidate_count`를 보존합니다. 이를 여러 곡의 동일 원음원으로 승인하지 않습니다. 동일 조합의 추가 출처는 `additional_evidence_json`, 실제 원천별 필드는 `raw_collection_record_json`에 남깁니다. 검색 결과 URL이나 임의 생성 ID를 영상 URL 개수에 포함하지 않습니다.

| 대표 수집 출처 | 곡 | 고유 영상 | 조합 |
|---|---:|---:|---:|
| PUBLIC_YOUNIVERSE_TITLE_DURATION_URL_COLLECTION | 123 | 123 | 123 |
| PUBLIC_METADATA_UNLABELLED_REMASTER_VERSION_URL_CANDIDATE | 36 | 36 | 36 |
| PUBLIC_METADATA_PRIMARY_ARTIST_ALBUM_MISSING_CREDITS_EXTENDED_DURATION_URL_CANDIDATE | 7 | 7 | 7 |
| WEB_SEARCH_URL_COLLECTION | 914 | 914 | 914 |
| PUBLIC_YOUNIVERSE_CHANNEL_TITLE_DURATION_URL_COLLECTION | 9 | 9 | 9 |
| WEB_SEARCH_RULE_CANDIDATE | 226 | 226 | 226 |

표는 조합 병합 후 대표 출처 기준입니다. 여러 출처에서 같은 곡/영상이 발견될 수 있으므로 출처별 고유 곡·영상의 합은 전체 고유 수와 다를 수 있습니다.

수집 흐름은 이전 입력·기존 ID 고정 → 공개 원천 대조와 서로 다른 곡의 공개 검색 → 기존 곡/영상 제외 → 출처별 후보 통합 → CSV/TXT·미수집 큐 내보내기 → 실제 원천/검색 증거와 재조회입니다. 이번 개별 검색 시도는 2,188곡, 정상 완료는 2,188곡이며 미수집 중 0곡은 검색 제한/오류 재시도가 필요합니다. 검색 직전 이미 확보되어 건너뛴 곡을 실제 검색 시도로 계산하지 않습니다.

부모의 `search_attempted_cumulative`·`search_completed_cumulative`를 이전 이력으로 보존합니다. 실제 정상 검색이 완료되면 이전 재시도 상태를 해제하고, 현재 실패·이전 정상 검색·개별 검색 미시도를 구분합니다. 정상 검색 결과 없음은 영상 부재 확정이 아닙니다.

출처와 후보 조건:

- LAION e.V., [LAION-DISCO-12M](https://huggingface.co/datasets/laion/LAION-DISCO-12M/tree/6e7bf3758a77301e46a715af894fefd79bb1da53), 고정 revision `6e7bf3758a77301e46a715af894fefd79bb1da53`, Apache 2.0. 기존 캐시의 고정 5파일 12,320,916행을 대조했습니다. 이번 추가 lane은 전체 제목/버전·전체 앨범명·주 아티스트의 완전한 이름이 같고, 원천의 아티스트 집합이 대상의 진부분집합인 후보입니다. 길이 차는 **3초 초과, `min(30초,max(15초,원곡 길이의 10%))` 이내**입니다. 라틴 결합 기호와 명시 문자 `ø/ł/đ/ð/þ/æ/œ`, `&→and`를 보완하며 제목/버전/연도 단어를 삭제하거나 별칭을 추정하지 않습니다. 누락 공동 크레딧과 길이 차는 `missing_source_artist_credits`·`coartist_identity_review_required`·`duration_difference_requires_review`에 보존합니다. 동일 곡·원음원 확정이 아닙니다. [수집 조건 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/laion-primary-album-duration-summary.json`)·[실제 Parquet 행/규칙 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/laion-primary-album-duration-integrity.json`).
- LAION의 별도 **리마스터 표기 한쪽 누락 후보**는 제목 끝의 ` - 2009 Remaster`·`(Remastered 2009)` 같은 제한된 remaster/연도 표기가 한쪽에만 없고, 나머지 전체 제목·전체 아티스트 집합·전체 앨범명·길이 차 3초 이내가 맞는 경우입니다. 양쪽 모두 리마스터 표시가 있거나 live/acoustic/remix 등 다른 버전 표시는 제거하지 않습니다. `version_metadata_status=ONE_SIDE_TERMINAL_REMASTER_LABEL_MISSING_UNCONFIRMED`·`version_identity_review_required=True`·`original_recording_verified=False`와 실제 양쪽 라벨을 보존합니다. **동일 버전 미확인 URL 후보**이며 전체 제목 일치 후보와 구분합니다. [수집 조건 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/laion-unlabelled-remaster-summary.json`)·[실제 행/규칙 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/laion-unlabelled-remaster-integrity.json`).
- Manoel Horta Ribeiro·Robert West(EPFL), [YouNiverse v1.1](https://zenodo.org/records/4650046), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 기존 4GiB 캐시를 새 위치로 복사하여 동일 SHA256을 확인하고 정상 HTTP 206 Range 응답으로 수신 범위를 확장했습니다. 실제 저장한 **6,442,450,944바이트 prefix**의 완전한 JSONL **34,718,688행**을 처리했습니다. 전체 영상 메타데이터 파일 `yt_metadata_en.jsonl.gz` 13,636,127,630바이트의 다운로드와 공식 MD5 확인은 미완료이며 `PARTIAL_SOURCE_FILE_CHECKSUM_NOT_VERIFIED`를 유지합니다. 제목에 명시된 전체 아티스트 이름·제목/버전과 길이 조건을 대조하며 길이 차가 큰 후보에는 별도 표시를 남깁니다. [수집 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/youniverse-summary.json`)·[prefix/실제 후보 행 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/youniverse-prefix-integrity.json`).
- YouNiverse 채널 보조 자료 `df_channels_en.tsv.gz`는 전체 5,960,728바이트와 공식 MD5를 확인했습니다. 영상의 channel_id를 원천 채널 행과 조인하고, **전체 곡명·버전은 영상 `title`과**, **모든 대상 아티스트 이름은 채널 `name_cc`와** 맞는 후보만 별도로 수집합니다. 끝의 ` - Topic`/`VEVO` 보완을 기록하며 별칭을 추정하지 않습니다. 채널 이름 일치는 아티스트·공식 계정·동일 원음원 승인이 아니며 `channel_identity_review_required`를 유지합니다. 채널 전체 파일 확인과 영상 메타데이터 파일의 부분 prefix 상태를 구분합니다. [채널 수집 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/youniverse-channel-summary.json`)·[영상/채널 행 대조 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/youniverse-channel-integrity.json`).
- 공개 웹 검색은 실제 영상 URL·제목·검색어·출처를 `web-part*-evidence.jsonl`·`auto-search-evidence.jsonl`에 보존합니다. 자동 검색의 원발견·시도는 `auto-search/batch-*-discoveries.jsonl`·`*-attempts.jsonl`에 남습니다. 모든 공동 아티스트를 확인하지 않고 주 아티스트 이름만 대조한 경우 그 한계를 `match_basis`에 명시합니다. 명백히 다른 제목/표시 버전은 수집에서 제외하지만 청취·동일 녹음 승인은 수행하지 않았습니다.

여기서 주 아티스트는 원본 `artists_name`을 `;`로 나눈 첫 이름입니다. 별도 보컬·권리 주체 분류를 만들지 않았습니다. LAION 행 번호는 파일 내 0부터, YouNiverse 영상 JSONL·채널 데이터 행은 1부터입니다. 원천의 작성 시점과 현재 시점은 다르므로 URL이 삭제되었을 가능성은 별도 생존 검수로 확인해야 합니다. 표기·누락 크레딧·길이 차는 추후 검토 자료이며 검수 통과로 취급하지 않습니다.

검증은 원천/검색 증거·고정 입력·최종 파일의 수집 무결성 대조입니다. 원천 변경은 대상 선별·명시 표기 보완·필드 추출·URL 정규화이며 저작자·원천 링크·라이선스를 보존했습니다. 서비스 코드·추천 수식/점수·날씨 후보·불변 결과·운영 레지스트리·대시보드·수령 원문은 변경하지 않았습니다. 커밋·푸시·PR·배포·계정 변경은 수행하지 않았습니다. 남은 곡의 추가 수집과 음악/재생 검수·등록은 후속입니다. [담당 변경 라우팅](../../docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md).
