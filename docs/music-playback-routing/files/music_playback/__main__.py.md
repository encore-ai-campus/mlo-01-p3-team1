# music_playback/__main__.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [music_playback/__main__.py](../../../../music_playback/__main__.py)
- 범위/목적: build/verify 명령 진입점

## 기준과 입력

--source/--analysis-dir/--output을 읽고 build에만 --overrides를 받습니다.

[최신 ON/OFF 후보 계약](../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

build는 후보 생성, verify는 저장된 자료 재대조를 호출하고 결과 JSON을 출력합니다.

작업자는 저장소 루트에서 python -m music_playback 명령으로 실행합니다. FastAPI 운영 API나 기존 Django 코드를 변경하지 않습니다.

근거: [연결 문서/검증 자료](../../../development/음악_시즌필터_변경_라우팅.md). [정본 차이·남은 연결](../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `main`: function, 소스 10행

```python
main()
```
