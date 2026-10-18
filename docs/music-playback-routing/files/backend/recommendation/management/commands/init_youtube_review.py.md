# backend/recommendation/management/commands/init_youtube_review.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: API 키 없는 YouTube 등록·검수 백엔드 / 통합팀
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: `backend/recommendation/management/commands/init_youtube_review.py`
- 통합 근거: docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md

## 기준 → 실행 → 저장

로컬 검수 도구의 실행 준비 명령입니다. C_LOCAL_DEMO=1에서만 실행하며 registry.initialize_access_code로 Git 제외 접근코드 파일을 준비합니다. --rotate는 이전 접근코드를 대체합니다. stdout은 is_test·파일 경로·secret_printed=false만 출력하고 코드값은 출력하지 않습니다.

--seed-legacy는 service.catalog의 최신 일반 음악 카탈로그에서 기존 영상 ID를 읽어 registry.seed_legacy_mappings로 전달합니다. 기존 VERIFIED 표기는 승계하지 않고 CANDIDATE/LEGACY_REVIEW_PENDING으로만 추가하며 이미 검수/차단된 매핑과 음악 카탈로그·원문은 보존합니다.

```powershell
$env:C_LOCAL_DEMO='1'
.\.venv\Scripts\python.exe -X utf8 -m backend.manage init_youtube_review --seed-legacy
```

--seed-native-reviewed는 별도 명시 선택입니다. 기존 원곡 메타데이터와 native 큐 검수 근거를 엄격히 대조한 경우만 native_verified=true/source=LEGACY_NATIVE_METADATA_REVIEW를 보존하며 iframe 상태는 변경하지 않습니다. 이전 47곡 모두의 PLAYING·완청을 주장하지 않으며 표준 길이 허용을 초과한 영상은 자동 예외 승인하지 않습니다. 운영자 native-block 철회는 다시 seed해도 복구하지 않습니다.

이 명령은 영상 검색·재생을 하지 않습니다. iframe 실제 재검수와 신규 외부 영상 승인은 별도 화면 관측·운영자 확인이 필요합니다. 코드 생성·비출력·회전·운영 거절·기존 자료의 native 전용 승계는 격리 시험으로 검증했습니다.

## AST 시그니처

검사기 `.local-preview-logs/keyless-routing-audit.json`의 python_files[].symbols를 그대로 기록합니다.

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
