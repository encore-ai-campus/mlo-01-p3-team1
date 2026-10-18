# 잔여 42,118곡 URL 추가 수집 — 2026-10-18

- 문서 정리일: 2026-10-19

> 아래 결과와 미등록/미검수 설명은 해당 수집·검수 회차 당시의 기록입니다. 공유 파일·로컬 원본·후속 등록 상태는 [보관 및 인계 안내](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md)에서 구분합니다.

이번 수집에서 **10,410곡 / 고유 신규 영상 URL 12,040개 / 곡·영상 후보 조합 13,266개**를 확보했습니다. **아직 미수집 31,708곡이 남아 있습니다.** 기존 수집의 곡 44,367개·영상 ID 49,893개는 제외 기준으로 고정했으며, 이번 결과와의 중복은 0입니다. 이 숫자는 후보 수집 현황이며 서비스 승인 곡 수가 아닙니다.

| 파일 | 내용 |
|---|---|
| [신규 URL TXT · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/youtube-residual-new-urls.txt`) | 기존 수집분에 없는 고유 영상 URL 12,040개. URL만 한 줄씩 저장했습니다. |
| [곡별 후보 CSV · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/youtube-residual-new-candidates.csv`) | 고유 곡·영상 조합 13,266개. 한 곡의 복수 영상과 여러 Spotify ID가 공유하는 영상이 있어 TXT와 행 수가 다릅니다. |
| [최신 미수집 목록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/remaining-uncollected.csv`) | 후보를 추가 확보하지 못한 31,708곡. URL은 비워 두고 `PENDING_ADDITIONAL_SOURCE_SEARCH`로 유지했습니다. |
| [집계·해시](./collection-summary.json) | 기존 수집분 제외·URL 중복·전체 카탈로그 합계·내보내기 재조회 결과입니다. |
| [출처 무결성 확인](./source-integrity-verification.json) | 원천 행과 URL·곡 필드, 검색 근거, 최종 산출물의 개수·중복을 확인한 기록입니다. |
| [개별 검색 진행 기록 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/web-part1-progress.json`) | 첫 검색 입력 115곡의 시도와 제외 사유를 기록했습니다. 이후 개별 검색은 아직 진행하지 않았습니다. |

모든 결과는 `URL_COLLECTED_UNREVIEWED`입니다. 음악의 동일 녹음·버전, 현재 URL 생존, 한국 재생, iframe, 실제 재생은 검수하지 않았고 대시보드·영상 레지스트리에도 등록하지 않았습니다. 기존 CSV·TXT와 이전 미수집 목록은 덮어쓰지 않았습니다.

이번에는 원문을 보존하면서 다음 수집 조건을 구분했습니다. 공개 자료 전체 대조와 일부 곡의 개별 검색을 수행했으며 전체 곡의 개별 검색 완료를 뜻하지 않습니다.

- LAION: 곡명의 단어 순서와 전체 아티스트를 유지한 구두점 동치, 원천 제목에 명시된 참여 아티스트의 별도 근거, 재생시간 차이 표시를 적용했습니다. 버전 단어를 삭제하거나 다른 버전을 같은 녹음으로 승인하지 않았습니다.
- 길이 차이가 3초를 초과하는 1,087개 조합은 별도 `duration_difference_requires_review=true`로 표시했습니다. 허용 범위는 최대 30초이며 기준과 원문 길이는 원천 요약·각 행에 남겼습니다.
- 공백·구분자만 다른 전체 문자 순서와 전체 아티스트 집합을 대조한 추가 177개 조합은 `word_boundary_normalization_requires_review=true`입니다. 짧은 식별자 위험 11개 조합도 별도 표시했습니다.
- TIMJ는 단일 아티스트·전체 제목의 엄격 동치와 제한된 유니코드 문장부호 동치만 적용했습니다. 원천 Spotify ID가 다르거나 없는 경우, 재생시간이 제공되지 않은 사실을 그대로 남겼습니다.
- Kaggle 길이는 Spotify 곡 메타데이터이며 YouTube 영상 길이가 아닙니다. `source_duration_origin`에 이를 표시했습니다.
- 개별 검색은 실제 검색 결과의 영상 URL·제목·검색어·출처를 보존했습니다. 검색 URL이나 추측한 영상 ID는 수집 결과에 포함하지 않았습니다.

출처와 자료 라이선스:

- LAION e.V., [LAION-DISCO-12M](https://huggingface.co/datasets/laion/LAION-DISCO-12M), revision `6e7bf3758a77301e46a715af894fefd79bb1da53`, Apache 2.0. 12,320,916행을 다시 대조하고 필요한 메타데이터만 추출·정규화했습니다. [수집 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/laion-residual-summary.json`)·[공백·구분자 보완 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/laion-compact-summary.json`).
- This Is My Jam; Andreas Jansson, Colin Raffel, Tillman Weyde, [This Is My Jam Data Dump](https://archive.org/details/thisismyjam-datadump), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), 2011–2015년 기록. 곡·영상 필드만 추출·정규화·대조했으며 사용자 계정·댓글은 산출물에 복사하지 않았습니다. [수집 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/timj-residual-summary.json`).
- Salvatore Rastelli, [Spotify and Youtube](https://www.kaggle.com/datasets/salvatorerastelli/spotify-and-youtube), 버전 2, CC0. 기존 원본을 재사용했습니다. [수집 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/kaggle-residual-summary.json`).
- WaveGenAI, [youtube-cc-by-music](https://huggingface.co/datasets/WaveGenAI/youtube-cc-by-music), revision `d3cb1a062720085f8ed0be0d9964c3645680aa51`, 메타데이터 MIT 표기. 영상 제목·게시 채널·URL만 대조했고 설명·음원 파일은 산출물에 포함하지 않았습니다. [수집 요약 · 로컬 보관](../../docs/development/music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/wavegen-residual-summary.json`).
