# ad-server/backend/workers/ads_jobs.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/workers/ads_jobs.py)

MongoDB 예산 검증·통계를300초 주기로 실행하고 실패 후 다음 주기 재시도·안전한 상태·종료를 관리합니다. 구성 작업은 policy 하나이며 외부 로그 전달은 없습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
refresh_policy()
class AdsJob
AdsJob.__post_init__(self)
configured_jobs()
_stamp()
class AdsJobRunner
AdsJobRunner.__init__(self, job)
AdsJobRunner.snapshot(self)
AdsJobRunner.run_once(self)
AdsJobRunner.watch(self, stop)
class AdsWorkerGroup
AdsWorkerGroup.__init__(self, jobs)
AdsWorkerGroup.snapshot(self)
AdsWorkerGroup.run_once(self)
AdsWorkerGroup.start(self)
AdsWorkerGroup.stop(self, timeout=10)
```
