# YouTube 수집 자료 공유와 로컬 보관

- 작성일: 2026-10-19
- 수정일: 2026-10-19
- 담당/범위: B 통합 인계 / U-01·URL 검수 기록의 공유 정리
- 기준: `feature/ad-logic`의 `18ad173`, 최신 `develop`의 `3fa0093`을 이력 병합한 뒤 정리

## 공유 범위와 당시 상태

사용자 결정에 따라 기존 미커밋 333개 중 27개를 공유합니다. 구성은 분석 폴더의 README/집계/무결성/100곡 검수 기록 25개, 개발 라우팅과 음악 인계 색인 2개입니다. `.gitignore`, 이 안내와 새 탭 재생 라우팅은 정리를 설명하는 추가 파일입니다. 앱 소스·광고 로직·수령 음악 계약 원문은 변경하지 않습니다.

수집 README와 JSON의 미검수/미등록·승인 수는 각 회차의 과거 기록입니다. `verification.json`·`live-api-readback.json`의 외부 승인147곡은 2026-10-16 스냅샷입니다. 이후 로컬 등록은 누적75,186매핑/62,175곡·외부 승인153곡이며, [후속 반영 라우팅](../YouTube_새탭_연속재생_변경_라우팅.md)의5절과 [적용 결과](../../acceptance/assets/youtube-collected-import-20261018.json)를 따릅니다. 수집 상태를 재생 승인으로 올리거나 과거 집계를 현재 값으로 덮어쓰지 않습니다.

100곡 CSV는 `track_id,video_url,match_score,album_match,native_elapsed_seconds,reviewed_at`의 **검수 기록 내보내기**입니다. `expected_revision`이 없어 현행 등록 API는 `CSV_HEADERS_INVALID`로 거절합니다. 이전 revision=0 등록 입력의 원본은 로컬 백업에 남고 원본 SHA256은 `original_registration_csv.sha256`, 공유 CSV 해시는 `csv_sha256`에 구분합니다. 다른 환경에서는 최신 revision을 조회해 후보 입력을 별도로 작성하고 재생 검수·승인을 별도로 수행해야 합니다.

공유 검수 JSON은 곡 식별·제공된 앨범/길이·판정 점수/한계·근거 URL·실제로 기록된 짧은 시간 진행을 보존합니다. 전체 음악 점수 특성·설명 발췌·raw DOM·탭 ID·중복 메모는 제외했습니다. 96곡의 KR 메타데이터 확인과4곡의 null, 앨범 미확인·판본 차이와 두 점수 정정은 그대로입니다. 전곡 청취·물리 음향·현재 생존/지역 제공·iframe 승인을 증명하지 않습니다.

## 로컬 원본과 해시

나머지306개는 총233,833,101바이트이며 **같은 원래 경로에 보존**합니다. 8개 디렉터리의 산출물을 `.gitignore`로 제외하고 공유 파일만 예외로 허용합니다. 이 규칙은 이 폴더에서 새로 생기는 수집 중간 파일에도 적용되며 다른 분석 폴더에는 적용하지 않습니다. 수정 전 목록/크기/SHA256과 공유27개 원본 백업은 `.local-preview-logs/publish-url-records-20261019/inventory.json` 및 그 폴더의 `originals/`에 있습니다. 이는 이 PC의 로컬 백업 경로이며 GitHub 링크가 아닙니다.

기존 JSON의 `files`·`source_candidate_snapshots`·`baseline_files_preserved_sha256`·`csv_sha256`/`txt_sha256`은 **해당 회차 원본의 해시**입니다. 수집 집계와 출처 무결성 JSON은 바이트 그대로 공유하므로 상호 해시도 유지합니다. 100곡 정제 자료만 V2 스키마와 원본/공유 해시를 명시했습니다. `source_archive_path`·검증 명령·`local_evidence_artifact`도 당시 로컬 근거를 가리키며 새 clone에서 실행 가능하다는 뜻이 아닙니다.

로컬 CSV/TXT/JSONL·큐·검색 근거306개와 별도 원천 메타데이터/도구, Git 제외 SQLite/접근 코드는 이번 푸시에 포함하지 않습니다. 다른 PC에서 동일 데이터를 사용하려면 담당자가 별도로 합의한 자료 전달 경로에서 원본과 SHA256을 함께 전달해야 합니다. 저장소 clone만으로 후보/승인 DB가 복제되지 않습니다. 공유 인증·운영 저장소·AWS 발행과 전체 후보의 원곡/버전·실제 재생 검수는 남은 연결입니다.

## 디렉터리별 인계

로컬 자료를 향하던 문서 링크는 아래 해당 디렉터리의 보관 안내로 연결하고 원래 파일명을 함께 표기합니다. 상세 파일명·SHA256은 로컬 inventory와 공유 집계 JSON에서 조회합니다.

<a id="youtube_mapping_100_20261016"></a>

### youtube_mapping_100_20261016

- 로컬 원본: `analysis/youtube_mapping_100_20261016/`의 23개, 1,121,229바이트.
- 공유: [README.md](../../../analysis/youtube_mapping_100_20261016/README.md)
- 공유: [final-100-reviewed.json](../../../analysis/youtube_mapping_100_20261016/final-100-reviewed.json)
- 공유: [live-api-readback.json](../../../analysis/youtube_mapping_100_20261016/live-api-readback.json)
- 공유: [verification.json](../../../analysis/youtube_mapping_100_20261016/verification.json)
- 공유: [youtube-additional-100-mappings.csv](../../../analysis/youtube_mapping_100_20261016/youtube-additional-100-mappings.csv)

<a id="youtube_urls_1000_20261018"></a>

### youtube_urls_1000_20261018

- 로컬 원본: `analysis/youtube_urls_1000_20261018/`의 14개, 2,729,064바이트.
- 공유: [collection-summary.json](../../../analysis/youtube_urls_1000_20261018/collection-summary.json)

<a id="youtube_urls_continue_20261018"></a>

### youtube_urls_continue_20261018

- 로컬 원본: `analysis/youtube_urls_continue_20261018/`의 59개, 24,562,407바이트.
- 공유: [README.md](../../../analysis/youtube_urls_continue_20261018/README.md)
- 공유: [collection-rule-boundaries.json](../../../analysis/youtube_urls_continue_20261018/collection-rule-boundaries.json)
- 공유: [collection-summary.json](../../../analysis/youtube_urls_continue_20261018/collection-summary.json)
- 공유: [source-integrity-verification.json](../../../analysis/youtube_urls_continue_20261018/source-integrity-verification.json)

<a id="youtube_urls_followup_20261018"></a>

### youtube_urls_followup_20261018

- 로컬 원본: `analysis/youtube_urls_followup_20261018/`의 60개, 19,129,006바이트.
- 공유: [README.md](../../../analysis/youtube_urls_followup_20261018/README.md)
- 공유: [collection-summary.json](../../../analysis/youtube_urls_followup_20261018/collection-summary.json)
- 공유: [source-integrity-verification.json](../../../analysis/youtube_urls_followup_20261018/source-integrity-verification.json)

<a id="youtube_urls_next_20261018"></a>

### youtube_urls_next_20261018

- 로컬 원본: `analysis/youtube_urls_next_20261018/`의 63개, 30,237,474바이트.
- 공유: [README.md](../../../analysis/youtube_urls_next_20261018/README.md)
- 공유: [collection-summary.json](../../../analysis/youtube_urls_next_20261018/collection-summary.json)
- 공유: [source-integrity-verification.json](../../../analysis/youtube_urls_next_20261018/source-integrity-verification.json)

<a id="youtube_urls_remaining_20261018"></a>

### youtube_urls_remaining_20261018

- 로컬 원본: `analysis/youtube_urls_remaining_20261018/`의 16개, 89,542,497바이트.
- 공유: [README.md](../../../analysis/youtube_urls_remaining_20261018/README.md)
- 공유: [collection-summary.json](../../../analysis/youtube_urls_remaining_20261018/collection-summary.json)
- 공유: [source-integrity-verification.json](../../../analysis/youtube_urls_remaining_20261018/source-integrity-verification.json)

<a id="youtube_urls_residual_20261018"></a>

### youtube_urls_residual_20261018

- 로컬 원본: `analysis/youtube_urls_residual_20261018/`의 19개, 41,100,351바이트.
- 공유: [README.md](../../../analysis/youtube_urls_residual_20261018/README.md)
- 공유: [collection-summary.json](../../../analysis/youtube_urls_residual_20261018/collection-summary.json)
- 공유: [source-integrity-verification.json](../../../analysis/youtube_urls_residual_20261018/source-integrity-verification.json)

<a id="youtube_urls_tail_20261018"></a>

### youtube_urls_tail_20261018

- 로컬 원본: `analysis/youtube_urls_tail_20261018/`의 52개, 25,411,073바이트.
- 공유: [README.md](../../../analysis/youtube_urls_tail_20261018/README.md)
- 공유: [collection-summary.json](../../../analysis/youtube_urls_tail_20261018/collection-summary.json)
- 공유: [source-integrity-verification.json](../../../analysis/youtube_urls_tail_20261018/source-integrity-verification.json)
