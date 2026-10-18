# 일반 운영용 시즌·행사 사전 스크린 후보

- 작성일/수정일: 2026-10-16
- 상태: 원본 CSV의 곡명·앨범명과 제한된 녹음 대조 규칙을 적용한 **분석용 사전 스크린**입니다. 실제 청취 검수, 운영 READY 카탈로그, YouTube 영상 매핑·180분 스트리밍 완료를 뜻하지 않습니다.
- 행사 정책: `OCCASION_GENERAL_20261016_V1`
- 원래 날씨 점수: `WEATHER_SCORE_PROPOSAL_20261016_V2` 그대로 유지합니다.
- 원본 SHA-256: `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`

`occasion_decisions.csv`는 전체 89,741개 고유 곡의 별도 판정표입니다. `occasion_review.csv`는 REVIEW_REQUIRED/UNSCREENED를 모은 검수 대상입니다. `pools/`는 원래 날씨 풀에서 GENERAL만 남긴 전체 후보이며 `examples/`는 이 후보로 다시 조합한 목록입니다. 원래 `../pools`, `../examples`, 원본 CSV와 기존 계산 정책은 수정하지 않았습니다.

| 상태 | 의미 | 일반 후보 포함 |
|---|---|---|
| GENERAL | 검사한 메타데이터에 행사 신호 없음 또는 명시 청취 검수로 일반 확정 | 포함 |
| SEASONAL_EVENT | 명백한 행사 구절/녹음 대조 규칙 또는 명시 검수로 행사 분류 | 제외 |
| REVIEW_REQUIRED | 행사 앨범 단독, 다의적 캐럴 제목 등으로 추가 확인 필요 | 보류 |
| UNSCREENED | 필수 메타데이터 누락/충돌로 스크린 미완료 | 보류 |

GENERAL + RULE_SCREEN은 청취 검수가 아닙니다. `decision_source=APPROVED_RULE`도 버전이 고정된 초기 규칙의 판정이며 사람이 해당 음원을 모두 들었다는 뜻이 아닙니다. Snow/Winter/Holiday 단독 표현과 Billie Holiday 같은 아티스트 인명만으로 제외하거나 보류하지 않습니다. Christmas 앨범에 실린 일반곡은 자동으로 행사곡을 확정하지 않고 검수로 분리합니다. 메타데이터에 나타나지 않는 행사성은 놓칠 수 있습니다.

실행 명령:

```powershell
$env:PYTHONUTF8='1'
python -m music_playback build --source 'C:/Users/이해나/Downloads/spotify_dataset (1).csv' --analysis-dir analysis/weather_music_20261016
python -m music_playback verify --source 'C:/Users/이해나/Downloads/spotify_dataset (1).csv' --analysis-dir analysis/weather_music_20261016
python -m unittest discover -s tests -p 'test_music_*.py' -v
```

`--overrides <JSON파일>`은 명시적인 검수 레코드의 목록을 받습니다. `track_id`, `occasion_status`, `occasion_codes`, `reviewer`, `evidence`, `reviewed_at`, `source_dataset_sha256`을 기록합니다. source SHA가 현재 원본과 다르면 거부합니다. 자동 검수 승인은 하지 않습니다.

3시간 조합은 원본 정수 duration_ms로 목표 180분/허용 176~184분을 지킵니다. 정확 180분을 먼저 탐색하고 없으면 180분 초과→176분 이상 부족 순서입니다. 보류곡을 되살리거나 자동 단축하지 않습니다. 모든 선택 곡 W=100일 때만 이 점수 체계 내 품질 상한을 입증했다고 표시하며 청취 만족도나 ID 동점 최적성을 주장하지 않습니다. 비·눈 보조 예시는 원래 교집합을 사용하고 speed 4종을 허용한 로컬 초기값이며 운영 혼합 speed의 사용자 수용을 대신하지 않습니다.

수량·기존 예시 대비 제외 곡·탐색 결과는 `summary.json`, 입력/산출물 해시는 `manifest.json`, 독립 재검증은 `verification.json`을 확인합니다. YouTube의 영상 길이·광고·버퍼링으로 실제 경과시간은 CSV 합계와 다를 수 있습니다.

[코드·수령 문서·검증 연결](../../../docs/development/음악_시즌필터_변경_라우팅.md)
