# 나머지 YouTube URL 수집 — 2026-10-18

- 문서 정리일: 2026-10-19

> 아래 결과와 미등록/미검수 설명은 해당 수집·검수 회차 당시의 기록입니다. 공유 파일·로컬 원본·후속 등록 상태는 [보관 및 인계 안내](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md)에서 구분합니다.

- 대상: 서비스 GENERAL 카탈로그 86,485곡에서 기존 147곡과 앞서 수집한 1,000곡을 제외한 85,338곡입니다.
- 이번 신규 영상 후보: **43,167곡 / 고유 URL 48,744개 / 고유 곡·영상 조합 53,544개**입니다.
- 기존 영상 재사용 후보 326개 조합을 포함하면 URL 후보가 있는 곡은 43,220곡입니다. **아직 미수집 42,118곡이 남아 있습니다.**
- 모든 후보는 `URL_COLLECTED_UNREVIEWED`입니다. 원곡·버전 검수, URL 생존·한국 재생·iframe 확인, 서비스 등록은 수행하지 않았습니다.

| 파일 | 내용 |
|---|---|
| [URL TXT · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/youtube-remaining-unique-urls.txt`) | 이번에 확보한 신규 고유 영상 URL 48,744개. 이전에 확보한 영상 URL은 제외했습니다. |
| [곡·영상 CSV · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/youtube-remaining-url-candidates.csv`) | 53,544개 곡·영상 후보 조합. 여러 후보가 있는 곡과 여러 곡 ID에서 공유하는 영상이 있어 TXT와 행 수가 다릅니다. |
| [기존 영상 재사용 후보 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/existing-url-reuse-candidates.csv`) | 기존 영상 ID를 다른 곡 ID에 연결하는 미검수 후보 326개 조합. 신규 URL 수에 포함하지 않습니다. |
| [미수집 목록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/remaining-uncollected.csv`) | 아직 후보를 확보하지 못한 42,118곡. `PENDING_ADDITIONAL_SOURCE_SEARCH`이며 URL은 빈 값입니다. |
| [수집 집계](./collection-summary.json) | 개수·중복·원천별 입력·내보내기 재조회·파일 SHA256과 전체 수집 미완료 상태입니다. |
| [출처 무결성 검사](./source-integrity-verification.json) | 수집 자료의 원천 행 연결과 파일 집계 검사입니다. 청취·재생 검수를 뜻하지 않습니다. |

Spotify ID 정확 일치 또는 제목·전체 아티스트·길이 차이 3초 이내를 사용했습니다. 명시적인 피처링 괄호는 기재된 이름이 아티스트 집합에 포함되는 경우에만 별도로 대조했습니다. 라이브·리믹스·리마스터 같은 버전 표시는 제거하지 않았습니다. TIMJ는 Spotify ID·제목·단일 아티스트를 대조했으며 원천에 재생시간이 없습니다. 원본의 Spotify ID도 당시 추정값이므로 별도 출처로 표시합니다.

`candidate_rank`는 출처와 정렬 기준에 따른 후보 순서이며 승인 점수가 아닙니다. `cross_track_title_artist_collision=true`인 영상은 서로 다른 곡명·아티스트에 연결된 이력이 있어 후속 검토가 필요합니다. 원천별 JSONL은 복수 후보와 출처 기록을 보존하며 실제 추천·영상 레지스트리는 변경하지 않았습니다.

출처와 자료 라이선스:

- Salvatore Rastelli, [Spotify and Youtube](https://www.kaggle.com/datasets/salvatorerastelli/spotify-and-youtube), 버전 2, CC0. Spotify ID 정확 조인과 별도 엄격 메타데이터 조인을 적용했습니다. [원본 기록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/kaggle-source-summary.json`)·[추가 조인 기록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/kaggle-metadata-summary.json`).
- LAION e.V., [LAION-DISCO-12M](https://huggingface.co/datasets/laion/LAION-DISCO-12M), revision `6e7bf3758a77301e46a715af894fefd79bb1da53`, Apache 2.0. 5개 파일의 12,320,916행을 대조하고 필요한 URL·곡 메타데이터만 추출했습니다. [원본 기록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/laion-source-summary.json`)·[피처링 표기 보완 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/laion-credit-summary.json`).
- This Is My Jam; Andreas Jansson, Colin Raffel, Tillman Weyde, [This Is My Jam Data Dump](https://archive.org/details/thisismyjam-datadump), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). 2011–2015년 원천에서 곡·URL 필드만 추출·정규화·대상 곡에 조인했습니다. 사용자 계정·댓글 등은 산출물에 포함하지 않았습니다. [원본·변환 기록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/timj-source-summary.json`).
