class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class SemanticRequestError(AppError):
    status_code = 422
    code = "semantic_error"


class InternalServiceError(AppError):
    status_code = 500
    code = "internal_error"
