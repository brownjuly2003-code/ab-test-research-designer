class ApiError(Exception):
    def __init__(
        self,
        detail: str,
        *,
        error_code: str,
        status_code: int = 400,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.error_code = error_code
        self.status_code = status_code
        self.headers = headers or {}
