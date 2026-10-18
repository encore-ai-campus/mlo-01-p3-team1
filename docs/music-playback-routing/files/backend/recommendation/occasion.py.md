# backend/recommendation/occasion.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 음악 데이터·기존 대시보드 CSV 추천 연결
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/occasion.py](../../../../../backend/recommendation/occasion.py)

## 기준과 공급·소비

로컬 CSV 추천용 행사 판정 snapshot 로더입니다. manifest의 원본 SHA·판정 CSV SHA·정책과 행별 상태·출처·판정 버전을 검증합니다. 빈/중복/누락/무효 판정은 실패하며 무필터 fallback은 제공하지 않습니다.

seed_csv_preview가 normalized CSV와 track_id로 연결하여 GENERAL만 새 test Catalog로 적재합니다.

[정책→코드→실행·미실행 연결](../../../../development/음악_시즌필터_변경_라우팅.md)의 후속 절과 [YouTube 이동 기획](../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 함께 읽습니다. 수령 원문·원본18개/원본CSV·기존Spotify play_url은 보존합니다.

## 검증

루트 .venv Python3.12.13에서 C_LOCAL_DEMO=1로 backend.music/backend.recommendation.tests 전체57건 통과. 메모리 시험 DB만 사용하며 외부 YouTube 호출·계정·운영DB 변경은 수행하지 않았습니다. source/schema 불일치는 저장 전에 실패하고 기존 결과를 보존합니다.

## AST 시그니처

검사기의 구조화 symbols 값을 그대로 기록합니다.

```python
load_occasion_decisions(directory, source_sha256)
```
