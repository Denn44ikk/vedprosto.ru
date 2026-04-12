from __future__ import annotations


class TelegramIntegrationError(RuntimeError):
    """Base error for Telegram integration helpers."""


class BotApiUnavailableError(TelegramIntegrationError):
    """Raised when aiogram is unavailable."""


class PersonalApiUnavailableError(TelegramIntegrationError):
    """Raised when telethon is unavailable."""


class PersonalTransportError(TelegramIntegrationError):
    """Raised for generic personal account transport failures."""


class PersonalSessionUnauthorizedError(PersonalTransportError):
    """Raised when a personal Telegram session is invalid or unauthorized."""


class PersonalPeerResolveError(PersonalTransportError):
    """Raised when a target peer cannot be resolved."""


class PersonalFloodWaitError(PersonalTransportError):
    """Raised when Telegram requests a flood-wait pause."""
