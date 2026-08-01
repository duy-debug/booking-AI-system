"""Typed failures raised by the HTTP booking gateway."""


class BookingGatewayInfrastructureError(Exception):
    """Base error for failures at the POS HTTP boundary."""


class POSConnectionError(BookingGatewayInfrastructureError):
    """Raised when the POS cannot be reached."""


class POSTimeoutError(BookingGatewayInfrastructureError):
    """Raised when a POS request exceeds its configured timeout."""


class POSRequestMappingError(BookingGatewayInfrastructureError):
    """Raised when an application request cannot be represented by POS."""


class POSResponseMappingError(BookingGatewayInfrastructureError):
    """Raised when a successful POS response violates its declared schema."""


class POSContractNotConfiguredError(BookingGatewayInfrastructureError):
    """Raised when no verified POS contract exists for an operation."""


class POSHTTPError(BookingGatewayInfrastructureError):
    """Base error for a non-success POS HTTP response."""

    def __init__(
        self,
        *,
        operation: str,
        status_code: int,
        code: str | None,
    ) -> None:
        message = f"POS operation {operation!r} failed with HTTP {status_code}"
        if code is not None:
            message = f"{message} ({code})"
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code
        self.code = code


class POSAuthenticationError(POSHTTPError):
    """Raised when POS rejects request authentication."""


class POSAuthorizationError(POSHTTPError):
    """Raised when POS denies access to an operation."""


class POSNotFoundError(POSHTTPError):
    """Raised when a requested POS resource does not exist."""


class POSValidationError(POSHTTPError):
    """Raised when POS rejects request data as invalid."""


class POSConflictError(POSHTTPError):
    """Raised when POS reports a conflicting operation."""


class POSTemporaryError(POSHTTPError):
    """Raised for rate limiting or temporary POS server failures."""


class POSUnexpectedStatusError(POSHTTPError):
    """Raised for an undocumented POS HTTP status."""
