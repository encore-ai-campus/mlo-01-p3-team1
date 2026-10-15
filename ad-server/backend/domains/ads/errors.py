class DomainError(Exception):
    """광고 도메인 오류를 공통 HTTP 오류 형식에 연결합니다."""

    def __init__(self, code, message, http_status, fields=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.fields = fields
        self.status = http_status
        self.details = fields


class ValidationError(DomainError):
    def __init__(self, message="광고 입력을 확인해 주세요.", fields=None):
        super().__init__("VALIDATION_ERROR", message, 422, fields)


class NotFound(DomainError):
    def __init__(self, message="광고 자료를 찾을 수 없습니다."):
        super().__init__("NOT_FOUND", message, 404)


class VersionConflict(DomainError):
    def __init__(self, message="최신 광고를 확인하고 다시 저장해 주세요.", fields=None):
        super().__init__("VERSION_CONFLICT", message, 409, fields)


class IdempotencyConflict(DomainError):
    def __init__(self, message="같은 멱등키에 다른 요청을 사용할 수 없습니다."):
        super().__init__("IDEMPOTENCY_CONFLICT", message, 409)


class DatabaseUnavailable(DomainError):
    def __init__(self, message="광고 저장소에 연결할 수 없습니다."):
        super().__init__("DATABASE_UNAVAILABLE", message, 503)


AdsError = DomainError
