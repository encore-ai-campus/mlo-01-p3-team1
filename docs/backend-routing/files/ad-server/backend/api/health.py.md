# ad-server/backend/api/health.py

- 작성일: 2026-10-15
- 역할: DB 연결 없이 API 프로세스의 응답과 OpenAPI 응답 형식을 확인합니다.

```python
class HealthResponseSerializer(serializers.Serializer)
class HealthView(APIView)
HealthView.get(self, request)
```

`HealthResponseSerializer`는 `status`, `service`, `database_checked` 응답 필드를 정의합니다. `HealthView.get`은 GET 요청을 받아 `status="ok"`, `service="ads-api"`, `database_checked=False`를 반환합니다. DB를 조회하지 않으며 인증 없이 호출할 수 있습니다.

`config/urls.py`의 `/api/health`에 연결됩니다. `extend_schema`가 응답 serializer와 `development` 태그를 OpenAPI에 연결합니다. 이 응답은 DB·광고 업무 기능의 정상 여부를 보장하지 않습니다.
