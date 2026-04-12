"""AI integration layer."""

from .gateway import AiGateway
from .core import (
    AiConnectorError,
    AiResult,
    AiTimeoutError,
    AuthError,
    DEFAULT_PROFILE_NAMES,
    NetworkError,
    NoFallbackConfiguredError,
    ProfileName,
    ProfileNotFoundError,
    ProviderError,
    ProviderNotFoundError,
    ProviderTemporaryError,
    RateLimitError,
    RetryableAiError,
)
from .settings import AISettings, get_ai_settings
from .service import AIIntegrationService, build_ai_integration_service


__all__ = [
    "AiGateway",
    "AiResult",
    "ProfileName",
    "DEFAULT_PROFILE_NAMES",
    "AiConnectorError",
    "RetryableAiError",
    "AuthError",
    "RateLimitError",
    "AiTimeoutError",
    "NetworkError",
    "ProviderTemporaryError",
    "ProviderError",
    "ProfileNotFoundError",
    "ProviderNotFoundError",
    "NoFallbackConfiguredError",
    "AISettings",
    "get_ai_settings",
    "AIIntegrationService",
    "build_ai_integration_service",
]
