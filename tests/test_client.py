"""Tests for GoableClient. Mirrors ``/home/user/sdk/test/client.test.ts``.

No real network I/O: every client is built on an ``httpx.Client`` wired to an
``httpx.MockTransport``, so requests never leave the process.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from goable_sdk import (
    DriftActiveError,
    GoableAPIError,
    GoableClient,
    GoableNetworkError,
)

KEY = "test-api-key-0000000000000000000000000000"

# ── minimal-but-schema-valid fixtures ─────────────────────────────────────
# The response models are pydantic-validated (unlike the TS SDK's untyped
# `as T` cast), so routing tests that don't care about the response *shape*
# still need a body that satisfies each endpoint's *required* fields. Real
# API responses always do; these are the smallest valid instance per schema.

_SERIALISED_POLICY = {
    "id": "00000000-0000-0000-0000-000000000001",
    "tenantId": "00000000-0000-0000-0000-000000000002",
    "quoteId": "00000000-0000-0000-0000-000000000003",
    "status": "bound",
    "premiumCollection": "external",
    "coverageWindow": {"monthFrom": 6, "dayFrom": 1, "monthTo": 6, "dayTo": 30},
    "coverageYear": 2027,
    "trigger": {},
    "policyTerms": {},
    "boundAt": "2026-07-01T00:00:00Z",
    "triggeredAt": None,
    "settledAt": None,
    "expiredAt": None,
    "settlementReference": None,
}

_QUOTE_RESPONSE = {
    "policy": {
        "coverageWindow": {"monthFrom": 6, "dayFrom": 1, "monthTo": 6, "dayTo": 30},
        "trigger": {},
        "historicalYearsRange": {"from": 2015, "to": 2025},
    },
    "expectedPayouts": {"byCurrency": {}},
    "expectedPremium": {"byCurrency": {}, "loadingFactor": 1.0},
    "modelConfidence": 0.8,
    "advisoryLevel": "high_confidence",
    "issuable": True,
    "notes": [],
    "underlying": {},
}

# Keyed by "METHOD /path" (the literal request path, no query string).
_PATH_FIXTURES: dict[str, Any] = {
    "POST /v1/score/series": {"series": []},
    "POST /v1/score/multi": {"results": []},
    "POST /v1/score/difficulty": {"resolved": {"level": "sub-spot", "slug": "x"}, "dimensions": []},
    "POST /v1/underwriting/quote": _QUOTE_RESPONSE,
    "GET /v1/underwriting/quote/q-1": _QUOTE_RESPONSE,
    "POST /v1/underwriting/policy/bind": {
        "policy": _SERIALISED_POLICY,
        "quoteId": "00000000-0000-0000-0000-000000000003",
    },
    "GET /v1/underwriting/policy": {"policies": []},
    "GET /v1/underwriting/policy/pol-1": {"policy": _SERIALISED_POLICY, "events": []},
    "POST /v1/underwriting/policy/pol-1/evaluate": {
        "policy": _SERIALISED_POLICY,
        "events": [],
        "inserted": 0,
        "skipped": 0,
    },
    "POST /v1/underwriting/policy/pol-1/settle": {"policy": _SERIALISED_POLICY},
    "GET /v1/observations/stations/st-1/recent": {"observations": []},
    "GET /v1/public/sustainability-index": {
        "@context": "https://schema.org",
        "@type": "GoableSustainabilityIndex",
        "generatedAt": "2026-07-01T00:00:00Z",
        "period": {"from": "2026-01-01T00:00:00Z", "to": "2026-04-01T00:00:00Z"},
        "methodology": {
            "indexFormula": "x",
            "weights": {"carbonNeutralShare": 0.5, "electrificationShare": 0.5},
            "suppression": "k>=10",
            "notes": "",
        },
        "overall": {
            "index": 1.0,
            "totalSessions": 0,
            "carbonNeutralSessions": 0,
            "carbonPositiveSessions": 0,
            "carbonNeutralShare": 0.0,
            "zonesReleased": 0,
            "zonesSuppressed": 0,
        },
        "zones": [],
        "license": "CC BY 4.0",
        "attribution": "Goable",
    },
    "GET /v1/public/catalog-stats": {
        "computedAt": "2026-07-01T00:00:00Z",
        "catalogVersion": "2.3.4",
        "totals": {"activities": 1, "subSpots": 1, "clusters": 1, "regions": 1, "countries": 1},
        "byActivity": [],
    },
    "GET /v1/legal/terms_of_service/current": {
        "document": {
            "id": "00000000-0000-0000-0000-000000000001",
            "kind": "terms_of_service",
            "version": "1.0",
            "title": "Terms of Service",
            "body": "...",
            "contentHash": "deadbeef",
            "status": "published",
            "createdAt": "2026-01-01T00:00:00Z",
            "publishedAt": "2026-01-01T00:00:00Z",
        }
    },
    "GET /v1/tenant/llm-key": {"set": True},
}


def path_fixture_responder(request: httpx.Request) -> httpx.Response:
    """Return the fixture registered for this request's method+path, or an
    empty JSON object for endpoints whose response schema has no required
    fields (all-optional / extra=allow, per the generated models).
    """
    key = f"{request.method} {request.url.path}"
    return httpx.Response(200, json=_PATH_FIXTURES.get(key, {}))


@dataclass
class Call:
    method: str
    url: str
    headers: httpx.Headers
    body: bytes | None


@dataclass
class Recorder:
    calls: list[Call] = field(default_factory=list)


def mock_client(
    responder: Callable[[httpx.Request], httpx.Response],
    *,
    base_url: str = "https://x",
) -> tuple[GoableClient, Recorder]:
    """Build a GoableClient wired to an in-process MockTransport, recording calls."""
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        recorder.calls.append(
            Call(
                method=request.method,
                url=str(request.url),
                headers=request.headers,
                body=request.content or None,
            )
        )
        return responder(request)

    transport = httpx.MockTransport(handler)
    client = GoableClient(api_key=KEY, base_url=base_url, client=httpx.Client(transport=transport))
    return client, recorder


def json_response(
    body: Any = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def responder(_request: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status, headers=headers)
        if isinstance(body, str):
            return httpx.Response(status, content=body, headers=headers)
        return httpx.Response(status, json=body, headers=headers)

    return responder


# ── construction ─────────────────────────────────────────────────────────


class TestConstruction:
    def test_requires_an_api_key(self) -> None:
        with pytest.raises(ValueError):
            GoableClient(api_key="")

    def test_accepts_an_injected_client(self) -> None:
        client, _ = mock_client(json_response({"status": "ok"}))
        assert isinstance(client, GoableClient)
        client.close()


# ── request building ─────────────────────────────────────────────────────


class TestRequestBuilding:
    def test_score_sends_post_with_x_goable_key_and_json_body(self) -> None:
        client, rec = mock_client(
            json_response(
                {
                    "score": 82,
                    "verdict": "favorable",
                    "confidence": 0.7,
                    "breakdown": [],
                    "physics": {},
                    "alerts": [],
                    "eco": {},
                }
            ),
            base_url="https://api.example.com/",
        )
        res = client.score({"activity": "kitesurfing", "location": {"lat": 43.7, "lng": 7.27}})

        call = rec.calls[0]
        assert call.url == "https://api.example.com/v1/score"
        assert call.method == "POST"
        assert call.headers["X-Goable-Key"] == KEY
        assert "Authorization" not in call.headers
        assert call.headers["Content-Type"] == "application/json"
        assert call.body is not None
        assert json.loads(call.body) == {
            "activity": "kitesurfing",
            "location": {"lat": 43.7, "lng": 7.27},
        }
        assert res.score == 82
        assert res.verdict.value == "favorable"

    def test_trailing_slash_on_base_url_is_normalised(self) -> None:
        client, rec = mock_client(json_response({"status": "ok"}), base_url="https://api.example.com///")
        client.health()
        assert rec.calls[0].url == "https://api.example.com/v1/health"

    def test_get_health_sends_no_content_type_or_body(self) -> None:
        client, rec = mock_client(json_response({"status": "ok"}))
        client.health()
        assert rec.calls[0].method == "GET"
        assert rec.calls[0].body is None
        assert "Content-Type" not in rec.calls[0].headers

    def test_each_method_hits_its_documented_path(self) -> None:
        client, rec = mock_client(path_fixture_responder)
        client.score_series(
            {
                "activity": "a",
                "location": {"lat": 0, "lng": 0},
                "window": {"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T06:00:00Z"},
            }
        )
        client.score_multi({"activities": ["a"], "location": {"lat": 0, "lng": 0}})
        client.explain_counterfactual(
            {
                "activity": "a",
                "spot": {"lat": 0, "lng": 0},
                "window": {"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T06:00:00Z"},
            }
        )
        client.decision(
            {
                "user_pseudonym": "a" * 32,
                "activity": "a",
                "spot": {"lat": 0, "lng": 0},
                "window": {"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T06:00:00Z"},
            }
        )
        client.quote(
            {
                "spot": {"location": {"lat": 0, "lng": 0}, "activity": "a"},
                "coverageWindow": {"monthFrom": 6, "dayFrom": 1, "monthTo": 6, "dayTo": 30},
            }
        )
        paths = [c.url.replace("https://x", "") for c in rec.calls]
        assert paths == [
            "/v1/score/series",
            "/v1/score/multi",
            "/v1/score/explain-counterfactual",
            "/v1/decision",
            "/v1/underwriting/quote",
        ]


# ── full surface routing ─────────────────────────────────────────────────


class TestFullSurfaceRouting:
    def test_every_method_hits_its_documented_path_and_verb(self) -> None:
        client, rec = mock_client(path_fixture_responder)

        client.score_difficulty({"activity": "a", "location": {"lat": 0, "lng": 0}})
        client.report_outcome("sess-1", {"outcome_type": "ran"})
        client.edge_case({"activity": "a", "location": {"lat": 0, "lng": 0}})
        client.projections_portfolio(
            {"spots": [{"location": {"lat": 0, "lng": 0}, "activity": "a"}], "scenarios": ["SSP2-4.5"]}
        )
        client.adaptation_report(
            {"spots": [{"location": {"lat": 0, "lng": 0}, "activity": "a"}], "scenarios": ["SSP2-4.5"]}
        )
        client.get_quote("q-1")
        client.bind_policy({"quoteId": "q-1", "coverageYear": 2027, "premiumCollection": "external"})
        client.list_policies()
        client.get_policy("pol-1")
        client.evaluate_policy("pol-1")
        client.settle_policy("pol-1", {"settlementReference": "wire-9"})
        client.create_station({"name": "n", "point": {"lat": 0, "lng": 0}, "variables": ["wind_speed_kn"]})
        client.list_stations()
        client.update_station("st-1", {"active": False})
        client.submit_observations(
            {
                "stationId": "st-1",
                "observations": [
                    {"observedAt": "2026-07-01T00:00:00Z", "variable": "wind_speed_kn", "value": 12}
                ],
            }
        )
        client.recent_observations("st-1")
        client.sustainability_index({"from": "2026-01-01T00:00:00Z", "to": "2026-04-01T00:00:00Z"})
        client.public_signup({"displayName": "Acme", "contactEmail": "a@b.co", "acceptTerms": True})
        client.catalog_stats()

        client.health_ready()
        client.submit_outcome(
            {"occurred_at": "2026-07-01T00:00:00Z", "activity_slug": "kitesurfing", "outcome_type": "ran"}
        )
        client.legal_document("terms_of_service")
        client.get_llm_key()
        client.set_llm_key({"apiKey": "sk-ant-xxxxxxxxxxxxxxxxxxxx"})
        client.delete_llm_key()

        seen = [f"{c.method} {c.url.replace('https://x', '')}" for c in rec.calls]
        assert seen == [
            "POST /v1/score/difficulty",
            "POST /v1/score/sess-1/outcome",
            "POST /v1/intelligence/edge-case",
            "POST /v1/projections/portfolio",
            "POST /v1/projections/adaptation-report",
            "GET /v1/underwriting/quote/q-1",
            "POST /v1/underwriting/policy/bind",
            "GET /v1/underwriting/policy",
            "GET /v1/underwriting/policy/pol-1",
            "POST /v1/underwriting/policy/pol-1/evaluate",
            "POST /v1/underwriting/policy/pol-1/settle",
            "POST /v1/observations/stations",
            "GET /v1/observations/stations",
            "PATCH /v1/observations/stations/st-1",
            "POST /v1/observations",
            "GET /v1/observations/stations/st-1/recent",
            "GET /v1/public/sustainability-index?from=2026-01-01T00%3A00%3A00Z&to=2026-04-01T00%3A00%3A00Z",
            "POST /v1/public/signup",
            "GET /v1/public/catalog-stats",
            "GET /v1/health/ready",
            "POST /v1/outcomes",
            "GET /v1/legal/terms_of_service/current",
            "GET /v1/tenant/llm-key",
            "PUT /v1/tenant/llm-key",
            "DELETE /v1/tenant/llm-key",
        ]

    def test_evaluate_policy_sends_no_body(self) -> None:
        client, rec = mock_client(
            json_response({"policy": _SERIALISED_POLICY, "events": [], "inserted": 0, "skipped": 0})
        )
        client.evaluate_policy("pol-1")
        assert rec.calls[0].method == "POST"
        assert rec.calls[0].body is None
        assert "Content-Type" not in rec.calls[0].headers

    def test_query_params_are_serialised_and_url_encoded(self) -> None:
        client, rec = mock_client(path_fixture_responder)
        client.list_policies({"status": "bound", "coverageYear": 2027, "limit": 10})
        client.recent_observations("st-1", {"limit": 5})
        assert rec.calls[0].url == "https://x/v1/underwriting/policy?status=bound&coverageYear=2027&limit=10"
        assert rec.calls[1].url == "https://x/v1/observations/stations/st-1/recent?limit=5"

    def test_202_response_returns_the_parsed_body(self) -> None:
        client, _ = mock_client(json_response({"accepted": True}, status=202))
        res = client.submit_observations(
            {
                "stationId": "st-1",
                "observations": [
                    {"observedAt": "2026-07-01T00:00:00Z", "variable": "wind_speed_kn", "value": 9}
                ],
            }
        )
        assert res.model_dump(exclude_none=True) == {"accepted": True}

    def test_legal_document_url_encodes_the_kind_path_segment(self) -> None:
        client, rec = mock_client(
            json_response(
                {
                    "document": {
                        "id": "00000000-0000-0000-0000-000000000001",
                        "kind": "privacy_policy",
                        "version": "1.0",
                        "title": "Privacy Policy",
                        "body": "...",
                        "contentHash": "deadbeef",
                        "status": "published",
                        "createdAt": "2026-01-01T00:00:00Z",
                        "publishedAt": "2026-01-01T00:00:00Z",
                    }
                }
            )
        )
        client.legal_document("privacy_policy")
        assert rec.calls[0].url == "https://x/v1/legal/privacy_policy/current"

    def test_set_llm_key_sends_json_body_and_returns_none_on_204(self) -> None:
        client, rec = mock_client(json_response(status=204))
        out = client.set_llm_key({"apiKey": "sk-ant-xxxxxxxxxxxxxxxxxxxx"})
        assert rec.calls[0].method == "PUT"
        assert rec.calls[0].headers["Content-Type"] == "application/json"
        assert rec.calls[0].body is not None
        assert json.loads(rec.calls[0].body) == {"apiKey": "sk-ant-xxxxxxxxxxxxxxxxxxxx"}
        assert out is None

    def test_delete_llm_key_sends_bodyless_delete_and_returns_none_on_204(self) -> None:
        client, rec = mock_client(json_response(status=204))
        out = client.delete_llm_key()
        assert rec.calls[0].method == "DELETE"
        assert rec.calls[0].body is None
        assert "Content-Type" not in rec.calls[0].headers
        assert out is None

    def test_get_llm_key_returns_the_masked_status_body(self) -> None:
        client, _ = mock_client(json_response({"set": True, "last4": "1234"}))
        res = client.get_llm_key()
        assert res.model_dump(exclude_none=True) == {"set": True, "last4": "1234"}


# ── audit export (CSV or JSON) ───────────────────────────────────────────


class TestAuditExport:
    def test_json_default_returns_the_parsed_body(self) -> None:
        client, rec = mock_client(
            json_response(
                {"rows": [{"id": "a"}], "meta": {"total": 1, "limit": 100, "offset": 0, "window": {}}}
            )
        )
        res = client.audit_export({"from": "2026-01-01T00:00:00Z", "to": "2026-02-01T00:00:00Z"})
        assert rec.calls[0].method == "GET"
        assert (
            rec.calls[0].url
            == "https://x/v1/audit/export?from=2026-01-01T00%3A00%3A00Z&to=2026-02-01T00%3A00%3A00Z"
        )
        assert not isinstance(res, str)
        assert len(res.rows) == 1
        assert res.meta.total == 1

    def test_format_csv_returns_the_raw_csv_string(self) -> None:
        csv = "id,activity,score\nabc,kitesurfing,82\n"
        client, rec = mock_client(json_response(csv))
        out = client.audit_export(
            {"from": "2026-01-01T00:00:00Z", "to": "2026-02-01T00:00:00Z", "format": "csv"}
        )
        assert (
            rec.calls[0].url == "https://x/v1/audit/export?from=2026-01-01T00%3A00%3A00Z"
            "&to=2026-02-01T00%3A00%3A00Z&format=csv"
        )
        assert isinstance(out, str)
        assert out == csv


# ── idempotency keys ──────────────────────────────────────────────────────


class TestIdempotencyKeys:
    def test_bind_policy_sends_idempotency_key_header_when_provided(self) -> None:
        client, rec = mock_client(
            json_response(
                {"policy": _SERIALISED_POLICY, "quoteId": "00000000-0000-0000-0000-000000000003"},
                status=201,
            )
        )
        client.bind_policy(
            {"quoteId": "q-1", "coverageYear": 2027, "premiumCollection": "external"},
            idempotency_key="idem-abc",
        )
        assert rec.calls[0].headers["Idempotency-Key"] == "idem-abc"

    def test_bind_policy_omits_the_header_when_no_key_is_given(self) -> None:
        client, rec = mock_client(
            json_response(
                {"policy": _SERIALISED_POLICY, "quoteId": "00000000-0000-0000-0000-000000000003"},
                status=201,
            )
        )
        client.bind_policy({"quoteId": "q-1", "coverageYear": 2027, "premiumCollection": "external"})
        assert "Idempotency-Key" not in rec.calls[0].headers

    def test_report_outcome_forwards_the_idempotency_key_header(self) -> None:
        client, rec = mock_client(json_response({}))
        client.report_outcome("sess-1", {"outcome_type": "ran"}, idempotency_key="idem-xyz")
        assert rec.calls[0].url == "https://x/v1/score/sess-1/outcome"
        assert rec.calls[0].headers["Idempotency-Key"] == "idem-xyz"


# ── rate-limit headers on errors ─────────────────────────────────────────


class TestRateLimitHeaders:
    def test_429_surfaces_retry_after_and_rate_limit(self) -> None:
        client, _ = mock_client(
            json_response(
                {"error": "RATE_LIMITED", "message": "Slow down"},
                status=429,
                headers={
                    "Retry-After": "42",
                    "X-RateLimit-Limit": "100",
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "1799999999",
                },
            )
        )
        with pytest.raises(GoableAPIError) as exc_info:
            client.score({"activity": "a", "location": {"lat": 0, "lng": 0}})
        err = exc_info.value
        assert err.code == "RATE_LIMITED"
        assert err.retry_after_seconds == 42
        assert err.rate_limit == {"limit": 100, "remaining": 0, "reset": 1799999999}

    def test_non_429_error_leaves_fields_none(self) -> None:
        client, _ = mock_client(json_response({"error": "PAYMENT_REQUIRED"}, status=402))
        with pytest.raises(GoableAPIError) as exc_info:
            client.score({"activity": "a", "location": {"lat": 0, "lng": 0}})
        err = exc_info.value
        assert err.retry_after_seconds is None
        assert err.rate_limit is None


# ── NDJSON research exports ──────────────────────────────────────────────


class TestNdjsonExports:
    def test_verification_export_returns_the_raw_ndjson_string(self) -> None:
        ndjson = '{"key":"a","brier":0.1}\n{"key":"b","brier":0.2}\n{"_type":"meta"}\n'
        client, rec = mock_client(json_response(ndjson))
        out = client.verification_export({"from": "2026-01-01T00:00:00Z"})
        assert rec.calls[0].method == "GET"
        assert rec.calls[0].url == "https://x/v1/research/verification/export?from=2026-01-01T00%3A00%3A00Z"
        assert isinstance(out, str)
        assert out == ndjson

    def test_difficulty_atlas_export_streams_from_the_jsonl_path(self) -> None:
        client, rec = mock_client(json_response('{"row":1}\n'))
        out = client.difficulty_atlas_export()
        assert rec.calls[0].url == "https://x/v1/research/difficulty-atlas/export.jsonl"
        assert out == '{"row":1}\n'

    def test_ndjson_export_surfaces_api_errors(self) -> None:
        client, _ = mock_client(json_response({"error": "SERVICE_UNAVAILABLE"}, status=503))
        with pytest.raises(GoableAPIError) as exc_info:
            client.difficulty_atlas_export()
        assert exc_info.value.code == "SERVICE_UNAVAILABLE"


# ── bind_policy drift handling ───────────────────────────────────────────


class TestBindPolicyDriftHandling:
    def test_422_drift_active_raises_drift_active_error(self) -> None:
        client, _ = mock_client(
            json_response(
                {
                    "error": "DRIFT_ACTIVE",
                    "message": "Open drift event on resolved cell",
                    "detail": {
                        "openDriftEvents": [
                            {
                                "activity": "kitesurfing",
                                "subSpotSlug": "tarifa-los-lances",
                                "severity": "warning",
                            }
                        ]
                    },
                },
                status=422,
            )
        )
        with pytest.raises(DriftActiveError) as exc_info:
            client.bind_policy({"quoteId": "q-1", "coverageYear": 2027, "premiumCollection": "external"})
        err = exc_info.value
        assert isinstance(err, GoableAPIError)
        assert type(err).__name__ == "DriftActiveError"
        assert err.code == "DRIFT_ACTIVE"
        assert len(err.open_drift_events) == 1
        assert err.open_drift_events[0]["subSpotSlug"] == "tarifa-los-lances"

    def test_non_drift_422_stays_a_plain_api_error(self) -> None:
        client, _ = mock_client(
            json_response(
                {"error": "VALIDATION_ERROR", "issues": [{"path": ["quoteId"], "message": "Required"}]},
                status=422,
            )
        )
        with pytest.raises(GoableAPIError) as exc_info:
            client.bind_policy({"quoteId": "", "coverageYear": 2027, "premiumCollection": "external"})
        err = exc_info.value
        assert not isinstance(err, DriftActiveError)
        assert err.code == "VALIDATION_ERROR"

    def test_successful_bind_surfaces_drift_advisories(self) -> None:
        client, _ = mock_client(
            json_response(
                {
                    "policy": _SERIALISED_POLICY,
                    "quoteId": "00000000-0000-0000-0000-000000000003",
                    "driftAdvisories": [
                        {
                            "spotIndex": 0,
                            "activity": "kitesurfing",
                            "subSpotSlug": "x",
                            "severity": "watch",
                            "since": "2026-07-01T00:00:00Z",
                        }
                    ],
                },
                status=201,
            )
        )
        res = client.bind_policy({"quoteId": "q-1", "coverageYear": 2027, "premiumCollection": "external"})
        dumped = res.model_dump(mode="json", exclude_none=True)
        assert dumped["driftAdvisories"][0]["severity"] == "watch"


# ── error mapping ─────────────────────────────────────────────────────────


class TestErrorMapping:
    def test_non_2xx_raises_api_error_with_code_and_detail(self) -> None:
        client, _ = mock_client(
            json_response(
                {"error": "PAYMENT_REQUIRED", "message": "Upgrade plan", "detail": {"plan": "free"}},
                status=402,
            )
        )
        with pytest.raises(GoableAPIError) as exc_info:
            client.score({"activity": "a", "location": {"lat": 0, "lng": 0}, "ensemble": True})
        err = exc_info.value
        assert err.status == 402
        assert err.code == "PAYMENT_REQUIRED"
        assert err.detail == {"plan": "free"}

    def test_422_surfaces_issues(self) -> None:
        client, _ = mock_client(
            json_response(
                {"error": "VALIDATION_ERROR", "issues": [{"path": ["activity"], "message": "Required"}]},
                status=422,
            )
        )
        with pytest.raises(GoableAPIError) as exc_info:
            client.score({"activity": "", "location": {"lat": 0, "lng": 0}})
        err = exc_info.value
        assert err.issues is not None
        assert err.issues[0]["message"] == "Required"

    def test_malformed_error_body_falls_back_to_http_status_code(self) -> None:
        client, _ = mock_client(json_response("<html>oops</html>", status=500))
        with pytest.raises(GoableAPIError) as exc_info:
            client.health()
        assert exc_info.value.code == "HTTP_500"

    def test_network_failure_raises_network_error(self) -> None:
        def responder(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("ECONNREFUSED")

        client, _ = mock_client(responder)
        with pytest.raises(GoableNetworkError) as exc_info:
            client.health()
        assert exc_info.value.kind == "network"

    def test_timeout_raises_network_error_timeout(self) -> None:
        def responder(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("aborted", request=request)

        client, _ = mock_client(responder)
        with pytest.raises(GoableNetworkError) as exc_info:
            client.health()
        assert exc_info.value.kind == "timeout"


# ── delete_user_data (GDPR erasure) ──────────────────────────────────────


class TestDeleteUserData:
    def test_returns_receipt_headers_from_the_204(self) -> None:
        client, rec = mock_client(
            json_response(
                status=204,
                headers={
                    "X-Anonymized-Rows": "12",
                    "X-Anonymized-Decision-Runs": "3",
                    "X-Anonymized-Recommendation-Runs": "1",
                    "X-Receipt": "receipt-abc",
                },
            )
        )
        result = client.delete_user_data("pseudo-123")
        assert rec.calls[0].method == "DELETE"
        assert rec.calls[0].url == "https://x/v1/decision/user-data/pseudo-123"
        assert result.status == 204
        assert result.anonymized_rows == 12
        assert result.anonymized_decision_runs == 3
        assert result.anonymized_recommendation_runs == 1
        assert result.receipt == "receipt-abc"

    def test_non_2xx_raises_api_error(self) -> None:
        client, _ = mock_client(json_response({"error": "NOT_FOUND"}, status=404))
        with pytest.raises(GoableAPIError) as exc_info:
            client.delete_user_data("pseudo-404")
        assert exc_info.value.code == "NOT_FOUND"


# ── context manager ───────────────────────────────────────────────────────


class TestContextManager:
    def test_closes_owned_client_on_exit(self) -> None:
        with GoableClient(api_key=KEY) as client:
            assert isinstance(client, GoableClient)
        # Closing an already-closed httpx.Client is a no-op, not an error.
        client.close()
