"""GoableClient -- thin typed transport over the public Goable REST API.

No caching, no business logic; one pair of private helpers
(``_request`` / ``_request_text``) powers every public method. Sync only
(built on ``httpx.Client``) for v0.1.0.

Mirrors ``/home/user/sdk/src/client.ts`` 1:1: same method names
(camelCase -> snake_case), same HTTP verbs + paths, same auth header, same
idempotency handling, same error semantics.
"""

from __future__ import annotations

import contextlib
import json as _json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote, urlencode

import httpx
from pydantic import BaseModel

from ._models import (
    ScoreMultiResponse,
    ScoreResponse,
    ScoreSeriesResponse,
    UnderwritingQuoteResponse,
    V1AuditExportGetResponse,
    V1DecisionPostResponse,
    V1HealthGetResponse,
    V1HealthReadyGetResponse,
    V1IntelligenceBriefingPostResponse,
    V1IntelligenceEdgeCasePostResponse,
    V1IntelligenceExplainPostResponse,
    V1LegalKindCurrentGetResponse,
    V1ObservationsPostResponse,
    V1ObservationsStationsGetResponse,
    V1ObservationsStationsPostResponse,
    V1ObservationsStationsStationIdPatchResponse,
    V1ObservationsStationsStationIdRecentGetResponse,
    V1OutcomesPostResponse,
    V1ProjectionsAdaptationReportPostResponse,
    V1ProjectionsPortfolioPostResponse,
    V1ProjectionsPostResponse,
    V1PublicCatalogStatsGetResponse,
    V1PublicSignupPostResponse,
    V1PublicSustainabilityIndexGetResponse,
    V1RecommendSpotPostResponse,
    V1ScoreDifficultyPostResponse,
    V1ScoreExplainCounterfactualPostResponse,
    V1ScoreHistoricalPostResponse,
    V1ScorePortfolioPostResponse,
    V1ScoreSessionIdOutcomePostResponse,
    V1TenantLlmKeyGetResponse,
    V1UnderwritingPolicyBindPostResponse,
    V1UnderwritingPolicyGetResponse,
    V1UnderwritingPolicyPolicyIdEvaluatePostResponse,
    V1UnderwritingPolicyPolicyIdGetResponse,
    V1UnderwritingPolicyPolicyIdSettlePostResponse,
    WebhookEvent,
)
from .errors import GoableNetworkError, to_api_error

DEFAULT_BASE_URL = "https://api.goable.io"
DEFAULT_TIMEOUT_S = 30.0

#: Legal document kinds accepted by ``legal_document`` (from the OpenAPI
#: path-param enum on ``GET /v1/legal/{kind}/current``).
LegalDocumentKind = Literal[
    "terms_of_service",
    "privacy_policy",
    "data_processing_agreement",
    "sla",
    "acceptable_use",
    "cookie_policy",
]

# A request body: either the matching generated pydantic model, or a plain
# JSON-serialisable mapping. Query params for GET endpoints are always a
# plain mapping (never the generated model) -- several query schemas alias a
# field to the Python keyword `from` (e.g. ``{"from": ..., "to": ...}``),
# which is far more natural to construct as a dict than to fight the
# generated model's alias-only constructor for.
RequestBody = BaseModel | Mapping[str, Any]


@dataclass(frozen=True)
class DeleteUserDataResult:
    """GDPR erasure result -- receipt headers from the 204 response.

    Not a wire schema; an SDK-specific result type (mirrors
    ``DeleteUserDataResult`` in the TS SDK's types.ts).
    """

    status: int
    #: Total rows anonymised across audit-log / behavioural model /
    #: decision_runs / recommendation_runs (the ``X-Anonymized-Rows`` header).
    anonymized_rows: int | None
    anonymized_decision_runs: int | None
    #: L10 -- count of recommendation_runs rows anonymised. Wired with
    #: migration 0030; older API deploys may return None.
    anonymized_recommendation_runs: int | None
    receipt: str | None


class WebhookDelivery(BaseModel):
    """A webhook delivery body, POSTed to a tenant's registered endpoint.

    The envelope shape is stable; ``data`` is per-event and best-effort --
    narrow it by checking ``delivery.type``. Field names mirror the deliverer
    exactly (``id`` / ``type`` / ``created``). Hand-written (not part of the
    OpenAPI request/response surface, so not codegen'd), mirroring the TS
    SDK's ``WebhookDelivery<T>`` interface.
    """

    id: str
    type: WebhookEvent
    created: str
    data: dict[str, Any]


def _serialize_body(body: RequestBody | None) -> Any:
    if body is None:
        return None
    if isinstance(body, BaseModel):
        return body.model_dump(mode="json", by_alias=True, exclude_none=True)
    return body


def _to_query(params: Mapping[str, Any] | None) -> str:
    """Serialise a query mapping into a leading-``?`` string (or "" when empty).

    Skips ``None`` values; booleans render as lowercase ``true``/``false`` to
    match JS's ``String(v)`` (mirrors ``toQuery`` in the TS SDK).
    """
    if not params:
        return ""
    pairs: list[tuple[str, str]] = []
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool):
            pairs.append((k, "true" if v else "false"))
        else:
            pairs.append((k, str(v)))
    if not pairs:
        return ""
    return "?" + urlencode(pairs)


def _idempotency_header(idempotency_key: str | None) -> dict[str, str] | None:
    """Build the optional ``Idempotency-Key`` header bag from a per-call key."""
    return {"Idempotency-Key": idempotency_key} if idempotency_key else None


def _int_header(headers: httpx.Headers, name: str) -> int | None:
    v = headers.get(name)
    if v is None:
        return None
    try:
        n = int(v)
    except ValueError:
        return None
    return n


def _safe_json(response: httpx.Response) -> Any:
    try:
        text = response.text
    except httpx.HTTPError as err:
        raise GoableNetworkError("Failed to read response body", "parse", err) from err
    if text == "":
        return None
    try:
        return _json.loads(text)
    except ValueError:
        return text


class GoableClient:
    """Sync client for the Goable API.

    Every request carries the tenant API key as ``X-Goable-Key`` (NOT
    ``Authorization: Bearer`` -- the API sits behind CloudFront with OAC,
    which hijacks the standard ``Authorization`` header for its own SigV4
    signature. The custom header sidesteps the conflict and stays untouched
    end-to-end; server-side middleware also accepts ``Authorization: Bearer``
    as a fallback for direct testing without CloudFront in the path).

    Example:
        >>> client = GoableClient(api_key="gk_...")
        >>> result = client.score({
        ...     "activity": "kitesurfing",
        ...     "location": {"lat": 43.7, "lng": 7.27},
        ... })
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | None = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
    ) -> None:
        """Construct a client.

        Args:
            api_key: Tenant API key -- sent as ``X-Goable-Key: <api_key>``.
            base_url: Base URL. Default ``https://api.goable.io``.
            timeout: Per-request timeout in seconds. Default 30. ``0`` or
                ``None`` disables the timeout.
            client: Inject a preconfigured ``httpx.Client`` (tests -- pass
                one built with ``transport=httpx.MockTransport(handler)`` to
                avoid any real network I/O). When omitted, the client owns
                and closes its own ``httpx.Client``.
        """
        if not api_key:
            raise ValueError("GoableClient requires an api_key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=_resolve_timeout(timeout))

    def close(self) -> None:
        """Close the underlying HTTP client, if this instance owns it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GoableClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ── public methods ──────────────────────────────────────────────────
    def health(self) -> V1HealthGetResponse:
        return V1HealthGetResponse.model_validate(self._request("GET", "/v1/health"))

    def health_ready(self) -> V1HealthReadyGetResponse:
        """Readiness probe (DB + skill lookup + LLM config).

        Note: a degraded/critical deployment answers 503, which surfaces
        here as a :class:`~goable_sdk.errors.GoableAPIError`.
        """
        return V1HealthReadyGetResponse.model_validate(self._request("GET", "/v1/health/ready"))

    def score(self, input: RequestBody) -> ScoreResponse:
        return ScoreResponse.model_validate(self._request("POST", "/v1/score", input))

    def score_series(self, input: RequestBody) -> ScoreSeriesResponse:
        return ScoreSeriesResponse.model_validate(self._request("POST", "/v1/score/series", input))

    def score_multi(self, input: RequestBody) -> ScoreMultiResponse:
        return ScoreMultiResponse.model_validate(self._request("POST", "/v1/score/multi", input))

    def score_historical(self, input: RequestBody) -> V1ScoreHistoricalPostResponse:
        return V1ScoreHistoricalPostResponse.model_validate(
            self._request("POST", "/v1/score/historical", input)
        )

    def score_portfolio(self, input: RequestBody) -> V1ScorePortfolioPostResponse:
        return V1ScorePortfolioPostResponse.model_validate(
            self._request("POST", "/v1/score/portfolio", input)
        )

    def explain_counterfactual(self, input: RequestBody) -> V1ScoreExplainCounterfactualPostResponse:
        return V1ScoreExplainCounterfactualPostResponse.model_validate(
            self._request("POST", "/v1/score/explain-counterfactual", input)
        )

    def decision(self, input: RequestBody) -> V1DecisionPostResponse:
        return V1DecisionPostResponse.model_validate(self._request("POST", "/v1/decision", input))

    def explain(self, input: RequestBody) -> V1IntelligenceExplainPostResponse:
        return V1IntelligenceExplainPostResponse.model_validate(
            self._request("POST", "/v1/intelligence/explain", input)
        )

    def briefing(self, input: RequestBody) -> V1IntelligenceBriefingPostResponse:
        return V1IntelligenceBriefingPostResponse.model_validate(
            self._request("POST", "/v1/intelligence/briefing", input)
        )

    def projections(self, input: RequestBody) -> V1ProjectionsPostResponse:
        return V1ProjectionsPostResponse.model_validate(self._request("POST", "/v1/projections", input))

    def quote(self, input: RequestBody) -> UnderwritingQuoteResponse:
        return UnderwritingQuoteResponse.model_validate(
            self._request("POST", "/v1/underwriting/quote", input)
        )

    def recommend_spot(self, input: RequestBody) -> V1RecommendSpotPostResponse:
        """L10 -- inverse query: given ``(activity, region, radius, window)``,
        returns top-K ranked sub-spots. Per-plan caps apply (radius
        25/50/200/1000 km, topK 5/10/20/50 across Free / Starter / Pro /
        Scale); requests above the cap return 402 PLAN_LIMIT_EXCEEDED. Pass
        ``user_pseudonym`` on Pro+ to get personalization via the L6
        cold-start blend.
        """
        return V1RecommendSpotPostResponse.model_validate(self._request("POST", "/v1/recommend-spot", input))

    def score_difficulty(self, input: RequestBody) -> V1ScoreDifficultyPostResponse:
        """L15 -- skill-conditioned difficulty grids per scoring dimension (Pro+)."""
        return V1ScoreDifficultyPostResponse.model_validate(
            self._request("POST", "/v1/score/difficulty", input)
        )

    def report_outcome(
        self,
        session_id: str,
        input: RequestBody,
        *,
        idempotency_key: str | None = None,
    ) -> V1ScoreSessionIdOutcomePostResponse:
        """Close the calibration loop: report the observed outcome of a scored
        session. Requires the ``outcomes:write`` scope. Pass
        ``idempotency_key`` so a retry after a network timeout can't record
        the same outcome twice.
        """
        return V1ScoreSessionIdOutcomePostResponse.model_validate(
            self._request(
                "POST",
                f"/v1/score/{quote(session_id, safe='')}/outcome",
                input,
                _idempotency_header(idempotency_key),
            )
        )

    def submit_outcome(self, input: RequestBody) -> V1OutcomesPostResponse:
        """Report a standalone activity outcome not tied to a scored session --
        the operator-reported behavioural signal behind the calibration +
        research datasets. Responds 202. Requires the ``outcomes:write``
        scope. For an outcome linked to a specific score, use
        :meth:`report_outcome` instead.
        """
        return V1OutcomesPostResponse.model_validate(self._request("POST", "/v1/outcomes", input))

    def edge_case(self, input: RequestBody) -> V1IntelligenceEdgeCasePostResponse:
        """LLM edge-case narrative for a marginal score."""
        return V1IntelligenceEdgeCasePostResponse.model_validate(
            self._request("POST", "/v1/intelligence/edge-case", input)
        )

    def projections_portfolio(self, input: RequestBody) -> V1ProjectionsPortfolioPostResponse:
        """T3 -- multi-spot climate-decadal projections (Scale)."""
        return V1ProjectionsPortfolioPostResponse.model_validate(
            self._request("POST", "/v1/projections/portfolio", input)
        )

    def adaptation_report(self, input: RequestBody) -> V1ProjectionsAdaptationReportPostResponse:
        """T3 -- adaptation report across months x scenarios x decades (Scale)."""
        return V1ProjectionsAdaptationReportPostResponse.model_validate(
            self._request("POST", "/v1/projections/adaptation-report", input)
        )

    # ── underwriting policy lifecycle (Scale) ───────────────────────────
    def get_quote(self, id: str) -> UnderwritingQuoteResponse:
        """Fetch a stored quote by id."""
        return UnderwritingQuoteResponse.model_validate(
            self._request("GET", f"/v1/underwriting/quote/{quote(id, safe='')}")
        )

    def bind_policy(
        self, input: RequestBody, *, idempotency_key: str | None = None
    ) -> V1UnderwritingPolicyBindPostResponse:
        """Bind a recent quote into a policy. Responds 201. A watch-level drift
        event on the resolved cell surfaces as ``driftAdvisories`` on
        success; a warning/critical event refuses the bind with
        ``422 DRIFT_ACTIVE``, raised as :class:`~goable_sdk.errors.DriftActiveError`.
        """
        return V1UnderwritingPolicyBindPostResponse.model_validate(
            self._request(
                "POST",
                "/v1/underwriting/policy/bind",
                input,
                _idempotency_header(idempotency_key),
            )
        )

    def list_policies(self, query: Mapping[str, Any] | None = None) -> V1UnderwritingPolicyGetResponse:
        """List the calling tenant's bound policies (paginated, boundAt DESC)."""
        return V1UnderwritingPolicyGetResponse.model_validate(
            self._request("GET", f"/v1/underwriting/policy{_to_query(query)}")
        )

    def get_policy(self, policy_id: str) -> V1UnderwritingPolicyPolicyIdGetResponse:
        """Fetch a single policy + its payout events."""
        return V1UnderwritingPolicyPolicyIdGetResponse.model_validate(
            self._request("GET", f"/v1/underwriting/policy/{quote(policy_id, safe='')}")
        )

    def evaluate_policy(self, policy_id: str) -> V1UnderwritingPolicyPolicyIdEvaluatePostResponse:
        """Re-evaluate a bound policy against the historical archive; inserts
        any newly detected payout events. No request body.
        """
        return V1UnderwritingPolicyPolicyIdEvaluatePostResponse.model_validate(
            self._request("POST", f"/v1/underwriting/policy/{quote(policy_id, safe='')}/evaluate")
        )

    def settle_policy(
        self, policy_id: str, input: RequestBody
    ) -> V1UnderwritingPolicyPolicyIdSettlePostResponse:
        """Settle a bound policy. PLATFORM-OPS ONLY -- requires the
        ``platform_admin`` scope (a cross-tenant underwriter operation,
        normally run by the daily settlement cron). Not a policyholder
        self-service action; tenant integrations should not call this.
        """
        return V1UnderwritingPolicyPolicyIdSettlePostResponse.model_validate(
            self._request("POST", f"/v1/underwriting/policy/{quote(policy_id, safe='')}/settle", input)
        )

    # ── observations / nowcasting (L5.3) ────────────────────────────────
    def create_station(self, input: RequestBody) -> V1ObservationsStationsPostResponse:
        """Register a tenant observation station. Responds 201."""
        return V1ObservationsStationsPostResponse.model_validate(
            self._request("POST", "/v1/observations/stations", input)
        )

    def list_stations(self) -> V1ObservationsStationsGetResponse:
        """List the calling tenant's observation stations."""
        return V1ObservationsStationsGetResponse.model_validate(
            self._request("GET", "/v1/observations/stations")
        )

    def update_station(
        self, station_id: str, input: RequestBody
    ) -> V1ObservationsStationsStationIdPatchResponse:
        """Patch a station (partial update)."""
        return V1ObservationsStationsStationIdPatchResponse.model_validate(
            self._request(
                "PATCH",
                f"/v1/observations/stations/{quote(station_id, safe='')}",
                input,
            )
        )

    def submit_observations(self, input: RequestBody) -> V1ObservationsPostResponse:
        """Push station observations into the 0-6h assimilation window (Pro+).
        Responds 202.
        """
        return V1ObservationsPostResponse.model_validate(self._request("POST", "/v1/observations", input))

    def recent_observations(
        self, station_id: str, query: Mapping[str, Any] | None = None
    ) -> V1ObservationsStationsStationIdRecentGetResponse:
        """Most-recent observations for one of the tenant's stations."""
        return V1ObservationsStationsStationIdRecentGetResponse.model_validate(
            self._request(
                "GET",
                f"/v1/observations/stations/{quote(station_id, safe='')}/recent{_to_query(query)}",
            )
        )

    # ── public / research (no-auth surfaces) ────────────────────────────
    def sustainability_index(self, query: Mapping[str, Any]) -> V1PublicSustainabilityIndexGetResponse:
        """Public Goable Sustainability Index (JSON-LD, CC BY 4.0)."""
        return V1PublicSustainabilityIndexGetResponse.model_validate(
            self._request("GET", f"/v1/public/sustainability-index{_to_query(query)}")
        )

    def verification_export(self, query: Mapping[str, Any] | None = None) -> str:
        """Public Stream F forecast-verification export. Returns the raw NDJSON
        stream as a string (one cell per line + a trailing meta line).
        """
        return self._request_text("GET", f"/v1/research/verification/export{_to_query(query)}")

    def difficulty_atlas_export(self) -> str:
        """Public L15 Difficulty Atlas export. Returns the raw NDJSON stream."""
        return self._request_text("GET", "/v1/research/difficulty-atlas/export.jsonl")

    def public_signup(self, input: RequestBody) -> V1PublicSignupPostResponse:
        """Self-service tenant signup (no auth). Always 202 on success."""
        return V1PublicSignupPostResponse.model_validate(self._request("POST", "/v1/public/signup", input))

    def catalog_stats(self) -> V1PublicCatalogStatsGetResponse:
        """Open catalogue coverage stats (no auth)."""
        return V1PublicCatalogStatsGetResponse.model_validate(
            self._request("GET", "/v1/public/catalog-stats")
        )

    def legal_document(self, kind: LegalDocumentKind) -> V1LegalKindCurrentGetResponse:
        """Fetch the current published legal document of a kind (no auth)."""
        return V1LegalKindCurrentGetResponse.model_validate(
            self._request("GET", f"/v1/legal/{quote(kind, safe='')}/current")
        )

    # ── audit / compliance ───────────────────────────────────────────────
    def audit_export(self, query: Mapping[str, Any]) -> V1AuditExportGetResponse | str:
        """Export the calling tenant's own score + outcome audit history for a
        date range. ``query["format"] == "csv"`` returns the raw CSV as a
        ``str``; the default (``"json"``) returns the parsed
        :class:`V1AuditExportGetResponse`. Offset-paginated via ``limit`` /
        ``offset``.
        """
        path = f"/v1/audit/export{_to_query(query)}"
        if query.get("format") == "csv":
            return self._request_text("GET", path)
        return V1AuditExportGetResponse.model_validate(self._request("GET", path))

    # ── LLM BYOK (bring-your-own Anthropic key) ─────────────────────────
    def set_llm_key(self, input: RequestBody) -> None:
        """Set/rotate the tenant's Anthropic API key. The server validates it
        with one cheap Anthropic call, encrypts it at rest, and never echoes
        it back. Resolves ``None`` on the 204.
        """
        self._request("PUT", "/v1/tenant/llm-key", input)

    def get_llm_key(self) -> V1TenantLlmKeyGetResponse:
        """Get the tenant's Anthropic key status (masked -- never the key itself)."""
        return V1TenantLlmKeyGetResponse.model_validate(self._request("GET", "/v1/tenant/llm-key"))

    def delete_llm_key(self) -> None:
        """Remove the tenant's Anthropic key. Resolves ``None`` on the 204."""
        self._request("DELETE", "/v1/tenant/llm-key")

    def delete_user_data(self, pseudonym: str) -> DeleteUserDataResult:
        """GDPR Art. 17 erasure. Surfaces the receipt headers from a 204."""
        res = self._raw_request("DELETE", f"/v1/decision/user-data/{quote(pseudonym, safe='')}")
        if not res.is_success:
            raise to_api_error(res.status_code, _safe_json(res), res.headers)
        return DeleteUserDataResult(
            status=res.status_code,
            anonymized_rows=_int_header(res.headers, "X-Anonymized-Rows"),
            anonymized_decision_runs=_int_header(res.headers, "X-Anonymized-Decision-Runs"),
            anonymized_recommendation_runs=_int_header(res.headers, "X-Anonymized-Recommendation-Runs"),
            receipt=res.headers.get("X-Receipt"),
        )

    # ── transport ─────────────────────────────────────────────────────────
    def _request(
        self,
        method: str,
        path: str,
        body: RequestBody | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        res = self._raw_request(method, path, body, extra_headers)
        parsed = _safe_json(res)
        if not res.is_success:
            raise to_api_error(res.status_code, parsed, res.headers)
        return parsed

    def _request_text(self, method: str, path: str) -> str:
        """Like :meth:`_request` but returns the raw response body as text --
        used for the NDJSON research streams and the ``format=csv`` audit
        export, which are not a single JSON document.
        """
        res = self._raw_request(method, path)
        try:
            text = res.text
        except httpx.HTTPError as err:
            raise GoableNetworkError("Failed to read response body", "parse", err) from err
        if not res.is_success:
            parsed: Any = text
            # non-JSON error body -- pass the raw text through to to_api_error
            with contextlib.suppress(ValueError):
                parsed = _json.loads(text)
            raise to_api_error(res.status_code, parsed, res.headers)
        return text

    def _raw_request(
        self,
        method: str,
        path: str,
        body: RequestBody | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers: dict[str, str] = {
            "X-Goable-Key": self._api_key,
            "Accept": "application/json",
        }
        content: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            content = _json.dumps(_serialize_body(body)).encode("utf-8")
        if extra_headers:
            headers.update({k: v for k, v in extra_headers.items() if v is not None})

        try:
            return self._client.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                content=content,
            )
        except httpx.TimeoutException as err:
            raise GoableNetworkError(f"Request timed out after {self._timeout}s", "timeout", err) from err
        except httpx.HTTPError as err:
            raise GoableNetworkError(f"Network request failed: {path}", "network", err) from err


def _resolve_timeout(timeout: float | None) -> httpx.Timeout:
    """``0`` or ``None`` disables the timeout (mirrors the TS SDK's
    ``timeoutMs: 0`` semantics); anything else is seconds.
    """
    if not timeout:
        return httpx.Timeout(None)
    return httpx.Timeout(timeout)
