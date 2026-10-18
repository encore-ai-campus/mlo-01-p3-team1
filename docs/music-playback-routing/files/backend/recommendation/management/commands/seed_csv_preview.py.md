# backend/recommendation/management/commands/seed_csv_preview.py 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-18
- 담당: 음악 데이터·기존 대시보드 CSV 추천 연결
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/management/commands/seed_csv_preview.py](../../../../../../../backend/recommendation/management/commands/seed_csv_preview.py)

## 기준과 공급·소비

기존 사용자 대시보드 로컬 CSV 프리뷰 적재 연결입니다. 원본 CSV와 --general-dir의 불변 판정을 검사하고 GENERAL만 새 Catalog 버전으로 적재합니다. --youtube-mappings가 있으면 검증 영상 snapshot만 추가하고 원래 Spotify play_url은 유지합니다.

기존 service/worker/API가 Catalog JSON을 그대로 소비합니다. is_test/preview_only·기존 결과를 보존하고 ON/OFF의 공통 적격 경계를 적용합니다. 공유DB/migration/API 스키마를 변경하지 않습니다.

[정책→코드→실행·미실행 연결](../../../../../../development/음악_시즌필터_변경_라우팅.md)의 후속 절과 [YouTube 이동 기획](../../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 함께 읽습니다. 수령 원문·원본18개/원본CSV·기존Spotify play_url은 보존합니다.

## 검증

루트 .venv Python3.12.13에서 C_LOCAL_DEMO=1로 backend.music/backend.recommendation.tests 전체61건 통과. 메모리 시험 DB만 사용하며 외부 YouTube 호출·계정·운영DB 변경은 수행하지 않았습니다. source/schema 불일치는 저장 전에 실패하고 기존 결과를 보존합니다.

## AST 시그니처

검사기의 구조화 symbols 값을 그대로 기록합니다.

```python
load_playback_selection(path, source_sha256, general_rows)
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```

명시 재생 선택 후속: --playback-selection은 GENERAL 원본의 고유 ID와 전곡 VERIFIED 매핑을 검사하고 선택파일 SHA/버전/입력순서를 새 test Catalog에 보존합니다. 기존 worker 정렬·기존 Catalog·운영 경계는 유지합니다. 의미 검증4건 추가 후 백엔드 전체61건이 통과했습니다.

## 2026-10-18 develop 동기화 보완

GENERAL 판정·선택 목록·영상 snapshot 검증을 유지한 채 precompute_scores를 적용합니다. source_sha256와 충돌 track 수를 응답하며 점수 캐시가 추가된 버전은 -scores-v3으로 분리해 기존 카탈로그를 덮어쓰지 않습니다.

기준 develop `8bdad88`·기존 feature/ad-logic `0a0cc82`의 대조와 실제 재검증은 [통합 기록](../../../../../../development/feature_전체_동기화_변경_라우팅_20261018.md)을 따릅니다.
