"""SDK error model. Two distinct failure modes:

- :class:`GoableAPIError`     -- the API returned a non-2xx response. Maps the
                                  canonical flat error envelope
                                  ``{ error, message?, issues?, detail? }``.
- :class:`GoableNetworkError` -- the request never produced an HTTP response
                                  (DNS, connection, abort/timeout, JSON parse).

Mirrors ``/home/user/sdk/src/errors.ts`` 1:1 (camelCase -> snake_case).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol


class ZodIssueLike(dict[str, Any]):
    """A single Zod validation issue, as returned on a 422 VALIDATION_ERROR.

    Kept as a permissive ``dict`` subclass (mirrors the TS `[k: string]: unknown`
    index signature) rather than a strict model, since the shape is
    Zod-internal and not part of the stable wire contract.
    """


class RateLimit(dict[str, Any]):
    """Rate-limit snapshot parsed from ``X-RateLimit-*`` response headers.

    Present when the server sent them (currently the ``score`` +
    ``recommend-spot`` endpoints; omitted on unlimited Scale plans).

    Keys: ``limit``, ``remaining``, ``reset`` (all ``int``).
    """


class HeaderBag(Protocol):
    """A minimal read-only header bag (an httpx.Headers-like object)."""

    def get(self, name: str) -> str | None: ...


class GoableAPIError(Exception):
    """Raised when the API returns a non-2xx response.

    Attributes:
        status: HTTP status code.
        code: Machine-readable code from the ``error`` field (e.g. "PAYMENT_REQUIRED").
        message: Human-readable message, when the server sent one.
        issues: Zod validation issues, present on 422 VALIDATION_ERROR responses.
        detail: Free-form extra context (e.g. plan info, quote id).
        retry_after_seconds: Seconds to wait before retrying, from the
            ``Retry-After`` header. Set on a 429; ``None`` when the header is
            absent or unparseable.
        rate_limit: Rate-limit snapshot from ``X-RateLimit-*`` headers, when
            the response carried them.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str | None = None,
        *,
        issues: list[ZodIssueLike] | None = None,
        detail: dict[str, Any] | None = None,
        retry_after_seconds: int | None = None,
        rate_limit: RateLimit | None = None,
    ) -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message
        self.issues = issues
        self.detail = detail
        self.retry_after_seconds = retry_after_seconds
        self.rate_limit = rate_limit

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{type(self).__name__}(status={self.status!r}, code={self.code!r}, message={self.message!r})"


class DriftActiveError(GoableAPIError):
    """Raised on a ``422 DRIFT_ACTIVE`` from ``POST /v1/underwriting/policy/bind``.

    The resolved cell has an open warning/critical L9 drift event, so the bind
    is refused (a watch-level event is a soft ``driftAdvisories`` on success,
    not an error). Subclasses :class:`GoableAPIError`, so existing
    ``isinstance(err, GoableAPIError)`` / ``err.code == "DRIFT_ACTIVE"`` checks
    keep working.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str | None = None,
        *,
        issues: list[ZodIssueLike] | None = None,
        detail: dict[str, Any] | None = None,
        retry_after_seconds: int | None = None,
        rate_limit: RateLimit | None = None,
    ) -> None:
        super().__init__(
            status,
            code,
            message,
            issues=issues,
            detail=detail,
            retry_after_seconds=retry_after_seconds,
            rate_limit=rate_limit,
        )
        raw = (detail or {}).get("openDriftEvents")
        self.open_drift_events: list[dict[str, Any]] = raw if isinstance(raw, list) else []


class GoableNetworkError(Exception):
    """Raised when the request never produced an HTTP response.

    Attributes:
        kind: ``"timeout"`` when the request was aborted by the configured
            timeout, ``"network"`` for connection failures, ``"parse"`` when
            the response body could not be read/decoded.
        cause: The underlying exception, when available.
    """

    def __init__(
        self,
        message: str,
        kind: Literal["timeout", "network", "parse"],
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.__cause__ = cause


def _int_header(headers: HeaderBag | None, name: str) -> int | None:
    """Parse an integer header, returning None when absent or non-numeric."""
    if headers is None:
        return None
    v = headers.get(name)
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            return None
    return n


def to_api_error(status: int, body: Any, headers: HeaderBag | None = None) -> GoableAPIError:
    """Map a parsed error body + status into a GoableAPIError.

    Tolerant of a non-conforming body (falls back to the status code as the
    error code). When ``headers`` are supplied, surfaces ``Retry-After`` (as
    ``retry_after_seconds``) and the ``X-RateLimit-*`` snapshot on the
    resulting error.
    """
    b: dict[str, Any] = body if isinstance(body, dict) else {}

    raw_code = b.get("error")
    code: str = raw_code if isinstance(raw_code, str) else f"HTTP_{status}"

    raw_message = b.get("message")
    message: str | None = raw_message if isinstance(raw_message, str) else None

    raw_issues = b.get("issues")
    issues: list[ZodIssueLike] | None = raw_issues if isinstance(raw_issues, list) else None

    raw_detail = b.get("detail")
    detail: dict[str, Any] | None = raw_detail if isinstance(raw_detail, dict) else None

    retry_after_seconds = _int_header(headers, "Retry-After")

    rate_limit: RateLimit | None = None
    limit = _int_header(headers, "X-RateLimit-Limit")
    remaining = _int_header(headers, "X-RateLimit-Remaining")
    reset = _int_header(headers, "X-RateLimit-Reset")
    if limit is not None and remaining is not None and reset is not None:
        rate_limit = RateLimit(limit=limit, remaining=remaining, reset=reset)

    # Specialise the one error the SDK models with its own class. Stays a
    # GoableAPIError subclass, so generic catch sites are unaffected.
    if code == "DRIFT_ACTIVE":
        return DriftActiveError(
            status,
            code,
            message,
            issues=issues,
            detail=detail,
            retry_after_seconds=retry_after_seconds,
            rate_limit=rate_limit,
        )
    return GoableAPIError(
        status,
        code,
        message,
        issues=issues,
        detail=detail,
        retry_after_seconds=retry_after_seconds,
        rate_limit=rate_limit,
    )
