# backend/recommendation/models.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-19
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/recommendation/models.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

Catalog.save가 신규 카탈로그와 DB 자동 증가 CatalogPublication을 같은 트랜잭션/DB alias에 기록합니다. 기존 카탈로그 갱신은 새 순번을 만들지 않습니다. Job/Playlist는 당시 카탈로그 FK와 snapshot을 유지합니다.

## AST 시그니처

```python
uid()
class OwnerLock(models.Model)
class Catalog(models.Model)
Catalog.save(self, *args, **kwargs)
class CatalogPublication(models.Model)
class Family(models.Model)
class Job(models.Model)
class Playlist(models.Model)
class DemoFeedback(models.Model)
class Idempotency(models.Model)
class PendingEvent(models.Model)
class YoutubeTrackRevision(models.Model)
class YoutubeMapping(models.Model)
class YoutubeReviewAudit(models.Model)
```

```python
class DispatchControl(models.Model)
```

## 2026-10-19 추천 분산 실행 연결

이번 큐·worker·provider 예약·설정/검증 변경은 별도 `docs/development/추천_분산처리_변경_라우팅.md`와 `docs/runbook/추천_분산처리_인프라_인계.md`에서 관리합니다. 기존 담당 기록과 수령 원문은 보존합니다.

## 운영 DB YouTube 검수 이력 보존 (2026-10-19)

운영에 이미 적용된 `0006_youtubereviewaudit_youtubetrackrevision_and_more`의 테이블을 삭제·재생성하지 않습니다. 신규 `0006_distributed_dispatch`와 동등한 마이그레이션 leaf를 `0007_merge_youtube_dispatch`로 결합해 기존 적용 이력을 보존합니다. 검수된 YoutubeTrackRevision·YoutubeMapping·YoutubeReviewAudit와 신규 DispatchControl은 공존하며, YouTube 운영 연결은 기존 PostgreSQL을 계속 사용합니다.
