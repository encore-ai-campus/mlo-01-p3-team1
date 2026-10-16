class DomainError(Exception):
    def __init__(self, code, message, status=422, details=None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.details = details or {}


def require(condition, code='VALIDATION_ERROR', message='입력값을 확인해 주세요.', status=422, **details):
    if not condition:
        raise DomainError(code, message, status, details)
