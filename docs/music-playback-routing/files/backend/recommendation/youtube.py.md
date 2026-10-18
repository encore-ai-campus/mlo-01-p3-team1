# backend/recommendation/youtube.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 음악 데이터·기존 대시보드 CSV 추천 연결
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/youtube.py](../../../../../backend/recommendation/youtube.py)

## 기준과 공급·소비

외부 YouTube 이동용 검증 원곡 매핑 snapshot 로더입니다. 선택 YOUTUBE_MAPPING_V1 파일 중 VERIFIED만 원곡 ID/곡명/아티스트/앨범/ms·11자 ID·영상 길이·검수자/근거/시각을 검사합니다. BLOCKED_EMBED/후보는 승격하지 않고 입력 파일을 변경하지 않습니다.

seed 명령이 optional video ID/VERIFIED 상태와 허용된 증빙 필드·파일 SHA를 당시 Catalog row에 복사합니다. 외부 이동/임베드 가능성 자체를 재생 검증한 것으로 주장하지 않습니다.

[정책→코드→실행·미실행 연결](../../../../development/음악_시즌필터_변경_라우팅.md)의 후속 절과 [YouTube 이동 기획](../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 함께 읽습니다. 수령 원문·원본18개/원본CSV·기존Spotify play_url은 보존합니다.

## 검증

루트 .venv Python3.12.13에서 C_LOCAL_DEMO=1로 backend.music/backend.recommendation.tests 전체57건 통과. 메모리 시험 DB만 사용하며 외부 YouTube 호출·계정·운영DB 변경은 수행하지 않았습니다. source/schema 불일치는 저장 전에 실패하고 기존 결과를 보존합니다.

## AST 시그니처

검사기의 구조화 symbols 값을 그대로 기록합니다.

```python
load_verified_youtube_mappings(path, tracks)
```
