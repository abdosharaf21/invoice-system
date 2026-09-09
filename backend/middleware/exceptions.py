"""Custom exception classes for the application."""


class AppException(Exception):
    """Base exception class for application errors.

    Attributes:
        message: Error message.
        status_code: HTTP status code.
        success: Always False for errors.
    """

    def __init__(
        self,
        message: str = "An error occurred",
        status_code: int = 400,
        code: str = "APP_ERROR",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.success = False
        self.code = code

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "status": self.status_code,
            "code": self.code,
        }


class BadRequestException(AppException):
    """Exception for bad request errors (400)."""

    def __init__(self, message: str = "Bad request") -> None:
        super().__init__(message, 400, "BAD_REQUEST")


class UnauthorizedException(AppException):
    """Exception for unauthorized errors (401)."""

    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, 401, "UNAUTHORIZED")


class ForbiddenException(AppException):
    """Exception for forbidden errors (403)."""

    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(message, 403, "FORBIDDEN")


class NotFoundException(AppException):
    """Exception for not found errors (404)."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, 404, "NOT_FOUND")


class ConflictException(AppException):
    """Exception for conflict errors (409)."""

    def __init__(self, message: str = "Resource conflict") -> None:
        super().__init__(message, 409, "CONFLICT")


class ValidationException(AppException):
    """Exception for validation errors (422)."""

    def __init__(self, message: str = "Validation failed", errors: dict = None) -> None:
        super().__init__(message, 422, "VALIDATION_ERROR")
        self.errors = errors or {}

    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.errors:
            result["errors"] = self.errors
        return result


class DatabaseException(AppException):
    """Exception for database errors (500)."""

    def __init__(self, message: str = "Database error occurred") -> None:
        super().__init__(message, 500, "DATABASE_ERROR")


class ServiceUnavailableException(AppException):
    """Exception for service unavailable errors (503)."""

    def __init__(self, message: str = "Service unavailable") -> None:
        super().__init__(message, 503, "SERVICE_UNAVAILABLE")
