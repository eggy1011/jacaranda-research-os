from __future__ import annotations

from enum import StrEnum
from typing import Any


class ProviderError(Exception):
    """Safe, typed provider failure. Messages never include upstream payloads or credentials."""

    def __init__(
        self,
        *,
        code: str,
        provider: str | None,
        retryable: bool,
        message: str,
    ) -> None:
        self.code = code
        self.provider = provider
        self.retryable = retryable
        self.message = message
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "provider": self.provider,
            "retryable": self.retryable,
            "message": self.message,
        }


class ProviderConfigurationError(ProviderError):
    def __init__(self, provider: str, setting: str) -> None:
        super().__init__(
            code="provider_configuration_error",
            provider=provider,
            retryable=False,
            message=f"{provider} is not configured: required setting {setting} is missing",
        )


class SymbolNormalizationError(ProviderError):
    def __init__(self) -> None:
        super().__init__(
            code="invalid_symbol",
            provider=None,
            retryable=False,
            message="symbol is not a supported A-share or US equity identifier",
        )


class ProviderRoutingError(ProviderError):
    def __init__(
        self, message: str = "no provider supports the requested market and capability"
    ) -> None:
        super().__init__(
            code="provider_routing_error",
            provider=None,
            retryable=False,
            message=message,
        )


class ProviderCapabilityError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="unsupported_capability",
            provider=provider,
            retryable=False,
            message=f"{provider} does not support the requested capability",
        )


class MalformedProviderResponseError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="malformed_provider_response",
            provider=provider,
            retryable=False,
            message=f"{provider} returned data that does not match its response contract",
        )


class ProviderAuthenticationError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="provider_authentication_error",
            provider=provider,
            retryable=False,
            message=f"{provider} rejected its server-side credentials",
        )


class ProviderRateLimitError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="provider_rate_limited",
            provider=provider,
            retryable=True,
            message=f"{provider} rate limit was reached",
        )


class ProviderUnavailableError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="provider_unavailable",
            provider=provider,
            retryable=True,
            message=f"{provider} is temporarily unavailable",
        )


class ClientFailureKind(StrEnum):
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    UNAVAILABLE = "unavailable"


class ExternalClientFailure(Exception):
    """Sanitised signal emitted by an injected external client implementation."""

    def __init__(self, kind: ClientFailureKind) -> None:
        self.kind = kind
        super().__init__(kind.value)
