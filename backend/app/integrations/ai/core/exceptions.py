class AiConnectorError(Exception):
    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.status_code = status_code


class RetryableAiError(AiConnectorError):
    pass


class AuthError(AiConnectorError):
    pass


class RateLimitError(RetryableAiError):
    pass


class AiTimeoutError(RetryableAiError):
    pass


class NetworkError(RetryableAiError):
    pass


class ProviderTemporaryError(RetryableAiError):
    pass


class ProviderError(AiConnectorError):
    pass


class ProfileNotFoundError(AiConnectorError):
    def __init__(self, message: str):
        super().__init__(message)


class ProviderNotFoundError(AiConnectorError):
    def __init__(self, message: str):
        super().__init__(message)


class NoFallbackConfiguredError(AiConnectorError):
    def __init__(self, message: str):
        super().__init__(message)
