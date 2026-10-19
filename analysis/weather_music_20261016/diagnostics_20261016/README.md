# 날씨 음악 V2 통계 진단 재현 안내

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- 진단 버전: `WEATHER_DIAGNOSTICS_20261016_V1`
- 기준 공식: `WEATHER_SCORE_PROPOSAL_20261016_V2`
- 상태: `DESCRIPTIVE_DIAGNOSTICS_NOT_LISTENING_VALIDATION`

[기존 산출식](../../../docs/product/proposals/날씨별_음악_점수_산출식_기획안_20261016.md)과 [통계·LLM 추가 기획](../../../docs/product/proposals/날씨별_음악_통계진단과_LLM_데이터_보완_추가기획_20261016.md)을 함께 읽습니다. 청취 정답·회귀 학습·LLM 호출·과금·운영 반영은 없습니다. 기존 원본·V2 정책·후보·180분 CSV는 보존합니다.

## 핵심 결과

- 원본 114,000행/89,741고유곡과 유효 61,931곡을 구분했습니다. 기존 V2 분모를 그대로 재현했습니다.
- 유효 e/a/v 평균은 .669854/.282835/.487547입니다. acousticness≤.01은24.88%이며 전자음향 등의 정상 특성일 수 있습니다.
- 유효곡 energy–acousticness Pearson −.723632/Spearman −.693572입니다. e/a/v/mode의 VIF2.2448/2.1884/1.0702/1.0164는 중복 진단이며 날씨 계수를 학습한 결과가 아닙니다.
- IQR/MAD 검토 표시는53,691곡–특성 쌍/37,922고유곡(61.23%)입니다. 자동 삭제·교정0건입니다. 전역 기준이 클래식·뉴에이지 등 정상 장르 특성을 대량 표시할 수 있습니다.
- 구름낌76점10,566곡+80점7,758곡=50.07%입니다. 점수의 평탄 영역과 동점 집중은 세밀한 순위의 한계이며 청취 품질 지표가 아닙니다.
- 총81개 OAT 시나리오입니다. 기준1+하한4+core2+가중치40+h30+곡선4입니다. 전체 조합 분석이나 신뢰구간이 아닙니다.
- 하한74/75/76은 전곡 커버,77은8,823곡·80은10,570곡이 미매칭입니다. 현행75점은 유지합니다.
- 가중치·h 상대±10%, core15/25, 네 감점 곡선에서는 전곡 커버가 유지됐습니다. SUPPORT c80/하한75이면 mode 정규화 비중≤6.25%가 필요합니다. 현재5%, 이번 변형의 최저 내부점수75.6219입니다.
- 모든 시나리오에서 상위200의 ID집합과 기존180분 예시의 적격성이 유지됐습니다. 모두100점 평탄 영역이므로 음악 품질의 안정성 증거가 아닙니다.
- sqrt(.5)의 눈3곡만±1e−8 합격 경계가 미해결입니다. 눈 후보12,201~12,204곡으로 표시하고 전체 커버의 수치 상하한은61,931곡입니다. 다른 곡선의 미해결 합격 경계는0건입니다.
- 39,414곡이 하나 이상 시나리오에서 통과 날씨가 바뀌었습니다. 실험 종류·개수에 의존하는 검토 우선순위이며 오류율·실패율·불안정 확률이 아닙니다.

## 파일과 근거

| 파일 | 용도 |
|---|---|
| [baseline_manifest.json](baseline_manifest.json) | 기존14개 정책/소스/요약/후보/예시 해시와 크기 |
| [baseline_proposal.source.txt](baseline_proposal.source.txt) | 문서 보완 전 V2 기획안 원문. 원래 상대 경로를 현재 링크로 해석하지 않음 |
| [profile_analysis.py](profile_analysis.py) · [profile_summary.json](profile_summary.json) | 분포·평균순위 Spearman·Pearson·VIF·조건수·풀/장르/speed/동점·IQR/MAD |
| [profile_feature_distribution.csv](profile_feature_distribution.csv) | 원본/유효 분모별 분위수·평균·표준편차·왜도·경계 비율 |
| [profile_pearson.csv](profile_pearson.csv) · [profile_spearman.csv](profile_spearman.csv) · [profile_vif.csv](profile_vif.csv) | 상관과 입력 중복 진단 |
| [profile_pool_score_ties.csv](profile_pool_score_ties.csv) · [profile_pool_features.csv](profile_pool_features.csv) | 날씨/패턴별 정확 점수 집중·입력 분포 |
| [profile_pool_genres.csv](profile_pool_genres.csv) · [profile_pool_speeds.csv](profile_pool_speeds.csv) | 다중 장르/상호배타 speed 분포 |
| [profile_review_flags.csv](profile_review_flags.csv) · [profile_review_criteria.csv](profile_review_criteria.csv) · [profile_review_flags_by_genre.csv](profile_review_flags_by_genre.csv) | 검토 대상과 실제 임계값·장르 맥락. 오류 확정값 아님 |
| [sensitivity_analysis.py](sensitivity_analysis.py) · [sensitivity_summary.json](sensitivity_summary.json) |81개 시나리오 정의·후보 변화·수치 경계·커버 증명·순위/기존 예시 검사 |
| [sensitivity_scenarios.csv](sensitivity_scenarios.csv) · [sensitivity_scenario_overview.csv](sensitivity_scenario_overview.csv) |405개 날씨×시나리오 비교와81개 전체 커버 요약 |
| [pertrack_sensitivity_flags.csv](pertrack_sensitivity_flags.csv) |61,931곡별 통과 변화 횟수·핵심 통과 대표점수의75점 거리 |
| [build_review_sample.py](build_review_sample.py) · [review_sample_summary.json](review_sample_summary.json) · [llm_review_sample.csv](llm_review_sample.csv) | 미래 보완 검토 표본500개와 선정/출처/미전송 검증 |
| [validate_diagnostics.py](validate_diagnostics.py) · [verification.json](verification.json) | 원본에서 통계·플래그·역상관행렬 VIF·하한77/80 전곡 Fraction을 별도 재계산하고 전체 산출물 대조 |
| [build_diagnostics_notebook.py](build_diagnostics_notebook.py) · [weather_diagnostics.ipynb](weather_diagnostics.ipynb) | 재현 노트북·실행 코드5셀·표·그림4개 |

원본 SHA-256: `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`. 기준 정책 SHA-256: `def75d6885d04464b58bcb60b8148482ecb394de23151e4b4830f25f15626622`. 각 요약과 검증 파일에 입력 해시를 보존합니다. 문서/README의 이번 보완과 기준 점수·CSV의 불변을 구분합니다.

## 재현

Python3.14·pandas3.0.3·NumPy·Matplotlib 환경에서 저장소 루트에서 순서대로 실행합니다. 대부분의 진단 스크립트는 ../summary.json의 원본 경로를 읽고, 표본 생성 스크립트는 코드의 SOURCE 고정 경로를 사용합니다. 현재는 모두 같은 Downloads 원본을 참조합니다. 다른 PC에서는 같은 해시의 CSV를 확보한 뒤 각 입력 경로 설정을 확인해야 합니다. 경로용 CLI 옵션은 구현하지 않았으며 기준 summary를 원본 데이터 수정에 사용하지 않습니다.

```powershell
python -B analysis/weather_music_20261016/diagnostics_20261016/profile_analysis.py
python -B analysis/weather_music_20261016/diagnostics_20261016/sensitivity_analysis.py
python -B analysis/weather_music_20261016/diagnostics_20261016/build_review_sample.py
python -B analysis/weather_music_20261016/diagnostics_20261016/validate_diagnostics.py
python -B analysis/weather_music_20261016/diagnostics_20261016/build_diagnostics_notebook.py
```

각 스크립트는 자기 진단 산출물만 다시 씁니다. profile은 pandas 평균순위 후 Pearson으로 Spearman을 계산해 SciPy에 의존하지 않습니다. baseline은 Fraction, 선형 시나리오의 하한/core 근접 행은 Fraction으로 재검사합니다. power2 제곱·완전제곱 sqrt·0/100 성분 경계는 정확 재검사하며 남은 sqrt/exp는 수치 경계 구간으로 표시합니다. 순위 진단은 시나리오 근삿값을10자리로 정규화한 뒤 ID 동점을 사용하며 합격 판정 전 반올림은 하지 않습니다.

노트북 생성기는 nbformat/nbclient가 없는 환경에서 표준 JSON 셀 구조·ID·코드 컴파일을 확인하고5개 코드 셀을 위에서 아래로 직접 실행해 출력과4개 PNG를 저장합니다. 표준 Jupyter nbformat 패키지 검사는 미실행입니다. 노트북 및 저장 그림의 가독성·축/분모·값을 직접 확인했습니다.

## 미래 LLM 검토 표본

500곡=민감도150+특성 순회 IQR/MAD100+모든 날씨 PRIMARY 미합격 SUPPORT 전용100+균형 비교150입니다. 중복0이며 비교군에18장르/4speed/5날씨/10대표패턴이 포함됩니다. 비교군을 오류가 전혀 없는 정답군이라고 취급하지 않습니다. 이 표본은 전곡 오류율 추정용 무작위 표본이 아닙니다.

원본 사실 문자열은 그대로 보존하고 LLM 제안·날씨 y·모델은 빈칸입니다. 상태는 REVIEW_TARGET_ONLY/NOT_SENT입니다.500곡은 검토 표본 수이며 실제 요청량/예산 승인이 아닙니다. CSV의 기준 날씨·점수·패턴은 사람이 진단을 확인할 정보이고 그대로 API payload로 보내는 파일이 아닙니다. 입력 사실·허용 필드·출처를 별도 조립하며 현재 W/통과 날씨를 정답으로 강요하지 않습니다. LLM이 없는 음향값·길이·ID를 만들거나 자동 approved로 바꾸는 절차는 없습니다.

## 그림

- [원본과 유효곡 분포](feature_distributions.png): 집단별 분모·특성별 세로축 범위 구분.
- [입력 특성 상관](feature_correlations.png): 유효곡 Pearson, 실제 날씨 정답과의 상관 아님.
- [동점 집중](score_tie_concentration.png): 날씨별 후보 안의 비율, 날씨 간 합산 금지.
- [하한별 후보/미매칭](threshold_sensitivity.png): OAT 하한, 숫자 간 실제 간격.
- [곡선 Jaccard 보조 요약](sensitivity_overview.png): 기준 후보와의 겹침, 품질 우열 아님.
