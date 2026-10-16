# 음악 분석 자료의 Git 공유와 재현

- 작성일/수정일: 2026-10-16
- 범위: 현재까지 작업의 `feature/ad-logic` 커밋·푸시를 위한 산출물 경계
- 기준: [Git 협업 방침](../CONTRIBUTING.md)의 큰 실데이터·실행 로그 제외 원칙

코드·정책·집계/비교 요약·manifest·작은 3시간 예시·그림/노트북·YouTube 매핑과 선별 검증 증거를 공유합니다. 전곡 후보/판정/검토 CSV 약176MiB는 `.gitignore`로 제외하고 로컬 파일은 보존합니다. DB·접근 코드·환경 실값·실행 로그·생성된 AST 감사 JSON도 공유하지 않습니다. 음악 수령 원문과 기존 로컬 작업은 덮어쓰거나 삭제하지 않습니다.

| 자료 | 공유 범위 |
|---|---|
| [V2 분석](weather_music_20261016/README.md) | 산출 코드·현재 정책·V1 비교 입력·요약·3시간 예시를 포함. 전곡 `pools/*.csv`는 로컬 생성 |
| [시즌·행사 스크린](weather_music_20261016/general/README.md) | 정책·summary/manifest·검증·3시간 예시를 포함. `occasion_decisions.csv`, `occasion_review.csv`, `pools/*.csv`는 로컬 생성 |
| [통계 진단](weather_music_20261016/diagnostics_20261016/README.md) | 재현 코드·집계표·요약·그림·노트북을 포함. 곡별 플래그2개와 LLM 검토 표본 CSV는 로컬 생성 |
| [YouTube47 매핑](youtube_mapping_20261016/README.md) | 공개 메타데이터의 매핑·버전·관측 증거를 포함. Google 계정·API 키·로컬 운영자 코드는 포함하지 않음 |

위 안내에서 로컬 생성 파일의 이름/경로는 생성 후 사용할 위치입니다. GitHub에 모든 전곡 CSV가 동봉됐다는 뜻이 아닙니다. 과거 manifest는 당시 관측 해시이며 재실행 시점/입력 경로를 포함한 새 manifest·검증 결과와 구분합니다.

## 원본과 전곡 자료 재생성 순서

저장소에 이미 추적된 `docs/handoff/music/spotify_dataset.csv`의 Git blob 또는 동일 SHA-256 원본을 사용합니다. 기대 해시는 `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`입니다. Windows checkout은 줄바꿈 변환으로 작업 파일의 바이트 해시가 달라질 수 있어 아래에서 Git blob을 별도 Git 제외 입력에 복사합니다. 수령 원문 파일은 수정하지 않습니다. 분석 당시 환경은 Python3.14·pandas3.0.3·NumPy이며 진단 그림에는 Matplotlib도 필요합니다. 분석 의존성은 Django 서비스 실행 환경과 구분합니다.

`analyze.py`는 원래 PC의 Downloads 경로를 기본값으로 가진 보존 코드이며 `--source` 옵션이 없습니다. 다른 PC에서는 아래처럼 실행 모듈의 입력만 지정할 수 있습니다. 저장소 루트에서 수행합니다.

```powershell
@'
from pathlib import Path
import hashlib
import runpy
import subprocess
source = Path('.local-preview-logs/source/spotify_dataset.csv').resolve()
source.parent.mkdir(parents=True, exist_ok=True)
source.write_bytes(subprocess.check_output(['git', 'show', 'HEAD:docs/handoff/music/spotify_dataset.csv']))
assert hashlib.sha256(source.read_bytes()).hexdigest() == 'b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd'
module = runpy.run_path('analysis/weather_music_20261016/analyze.py', run_name='weather_analysis_rebuild')
module['main'].__globals__['SOURCE'] = source
module['main']()
'@ | python -

python -m music_playback build --source .local-preview-logs/source/spotify_dataset.csv --analysis-dir analysis/weather_music_20261016
python -m music_playback verify --source .local-preview-logs/source/spotify_dataset.csv --analysis-dir analysis/weather_music_20261016
```

순서는 V2 전곡 풀 생성 → 시즌 스크린·일반 풀/판정 생성 → 검증입니다. `music_playback build`만 먼저 실행하면 원래 풀/요약이 없어 실패할 수 있습니다. 생성 스크립트는 자기 분석 산출물을 다시 쓰므로 필요한 기존 분석 결과는 먼저 별도 보관합니다. 절대경로·시각 등이 달라지면 summary/manifest 바이트 해시도 달라질 수 있으며 기존 검증 기록을 새 실행의 검증으로 사용하지 않습니다.

진단의 곡별 플래그·표본이 필요하면 위 V2 생성 후 통계 진단 README 순서를 따릅니다. 그 README에 표시된 입력 경로도 해당 PC 원본과 맞춰 확인해야 합니다.

그 다음 로컬 Django의 일반 카탈로그를 적재할 수 있습니다.

```powershell
$env:C_LOCAL_DEMO='1'
$env:YOUTUBE_PLAYBACK_MODE='KEYLESS'
.\.venv\Scripts\python.exe -m backend.manage seed_csv_preview .local-preview-logs/source/spotify_dataset.csv --youtube-mappings analysis/youtube_mapping_20261016/mapping-47-verified-v1.json
.\.venv\Scripts\python.exe -m backend.manage init_youtube_review --seed-legacy --seed-native-reviewed
```

로컬 DB migration/작업자/프런트 기동은 [YouTube 운영 가이드](../docs/development/music/YouTube_로컬_재생_기획과_구현_가이드.md)와 [C 실행 인계](../docs/runbook/C_구현과_연결_인계.md)를 따릅니다. 과거47곡 native 검수 승계는 iframe 자동 승인이 아니며, 이후 수동 URL 등록·검수 내용은 Git 제외 레지스트리에 따로 보관합니다.
