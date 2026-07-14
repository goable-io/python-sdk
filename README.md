# goable-sdk

[![PyPI](https://img.shields.io/pypi/v/goable-sdk.svg)](https://pypi.org/project/goable-sdk/)
[![CI](https://github.com/goable-io/python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/goable-io/python-sdk/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

Python client for the [Goable](https://goable.io) API — 0-100 suitability
scoring for outdoor activities (water, snow, air, land) from real-time weather
and multi-domain physics.

Thin, typed transport over the public tenant-facing REST surface. Sync only
(built on [httpx](https://www.python-httpx.org/)) in v0.1.0. Python 3.10+.

This is the Python sibling of [`@goable-io/sdk`](https://github.com/goable-io/sdk)
(TypeScript) — same methods, same semantics, snake_case instead of camelCase.

## Install

```bash
pip install goable-sdk
```

## Quickstart

```python
import os
from goable_sdk import GoableClient

goable = GoableClient(api_key=os.environ["GOABLE_API_KEY"])

# Score a single activity at a location + time window
result = goable.score({
    "activity": "kitesurfing",
    "location": {"lat": 43.7, "lng": 7.27},
    "window": {"from": "2026-06-01T06:00:00Z", "to": "2026-06-01T18:00:00Z"},
})

result.score       # 0-100
result.verdict      # "unsafe" | "poor" | "marginal" | "fair" | "favorable" | "excellent"
result.confidence
```

Inverse query — "where should I go?" — ranks sub-spots for an activity within
a region:

```python
spots = goable.recommend_spot({
    "activity": "kitesurfing",
    "region": {"center": {"lat": 43.7, "lng": 7.27}, "radiusKm": 50},
    "window": {"from": "2026-06-01T06:00:00Z", "to": "2026-06-01T18:00:00Z"},
    "topK": 5,
})
```

Use it as a context manager to close the underlying connection pool
deterministically:

```python
with GoableClient(api_key=os.environ["GOABLE_API_KEY"]) as goable:
    result = goable.score({"activity": "kitesurfing", "location": {"lat": 43.7, "lng": 7.27}})
```

## Authentication

Every request carries your tenant API key. The canonical production header is
**`X-Goable-Key`**, which the client sends automatically:

```python
GoableClient(api_key="gk_...")   # -> sends "X-Goable-Key: gk_..."
```

> The API also accepts `Authorization: Bearer <key>` as a legacy fallback for
> direct testing, but new integrations should use the default `X-Goable-Key`
> path. (Production traffic sits behind CloudFront, which reserves the
> `Authorization` header for its own signature — the custom header sidesteps
> that.)

Mint a key from the tenant portal at
[console.goable.io/portal/keys](https://console.goable.io/portal/keys).

## Configuration

```python
GoableClient(
    api_key="...",                    # required — sent as X-Goable-Key
    base_url="https://api.goable.io", # default
    timeout=30.0,                     # seconds; default 30, 0/None disables
    client=custom_httpx_client,       # default: an owned httpx.Client(); inject for tests
)
```

## Request bodies and query params

Every method accepts either a plain `dict` or the matching generated pydantic
model as the request body (`ScoreRequest`-shaped code lives in
`goable_sdk._models` as `V1ScorePostRequest`, etc. — see below). A plain dict
is usually the path of least resistance:

```python
goable.score({"activity": "kitesurfing", "location": {"lat": 43.7, "lng": 7.27}})
```

Query-string parameters (`list_policies`, `recent_observations`,
`sustainability_index`, `verification_export`, `audit_export`) are always a
plain `Mapping[str, Any]` — several of the underlying query schemas alias a
field to the Python keyword `from` (e.g. `audit_export`'s date range), which
is far more natural to write as `{"from": ..., "to": ...}` than to fight a
generated model's alias-only constructor for.

## Methods

The client mirrors the full public tenant-facing surface — one method per
OpenAPI path (camelCase in the TS SDK becomes snake_case here). Grouped by
area:

### Score

| Method | Endpoint | Notes |
|---|---|---|
| `score(input)` | `POST /v1/score` | `ensemble: true` → probabilistic (Pro+); `rider_skill_level` skill-conditioned (Pro+) |
| `score_series(input)` | `POST /v1/score/series` | per-step over a window |
| `score_multi(input)` | `POST /v1/score/multi` | many activities, one location |
| `score_historical(input)` | `POST /v1/score/historical` | climatology percentiles (Pro+) |
| `score_portfolio(input)` | `POST /v1/score/portfolio` | multi-spot joint variance |
| `score_difficulty(input)` | `POST /v1/score/difficulty` | L15 skill-conditioned difficulty grids (Pro+) |
| `explain_counterfactual(input)` | `POST /v1/score/explain-counterfactual` | binding constraint, sensitivities, best window/spot |
| `report_outcome(session_id, input, idempotency_key=None)` | `POST /v1/score/{sessionId}/outcome` | close the calibration loop |

### Recommend

| Method | Endpoint | Notes |
|---|---|---|
| `recommend_spot(input)` | `POST /v1/recommend-spot` | inverse query: top-K ranked sub-spots |

### Decision

| Method | Endpoint | Notes |
|---|---|---|
| `decision(input)` | `POST /v1/decision` | personalized go/no-go (Pro+) |
| `delete_user_data(pseudonym)` | `DELETE /v1/decision/user-data/{pseudonym}` | GDPR erasure; returns receipt headers |

### Intelligence

| Method | Endpoint | Notes |
|---|---|---|
| `explain(input)` | `POST /v1/intelligence/explain` | LLM narrative (Pro+) |
| `briefing(input)` | `POST /v1/intelligence/briefing` | LLM briefing (Pro+) |
| `edge_case(input)` | `POST /v1/intelligence/edge-case` | LLM edge-case narrative for a marginal score |

### Projections (Scale)

| Method | Endpoint | Notes |
|---|---|---|
| `projections(input)` | `POST /v1/projections` | single-spot climate-decadal |
| `projections_portfolio(input)` | `POST /v1/projections/portfolio` | multi-spot |
| `adaptation_report(input)` | `POST /v1/projections/adaptation-report` | months × scenarios × decades |

### Underwriting (Scale)

| Method | Endpoint | Notes |
|---|---|---|
| `quote(input)` | `POST /v1/underwriting/quote` | parametric premium |
| `get_quote(id)` | `GET /v1/underwriting/quote/{id}` | fetch a stored quote |
| `bind_policy(input, idempotency_key=None)` | `POST /v1/underwriting/policy/bind` | bind a quote; 422 `DRIFT_ACTIVE` → `DriftActiveError` |
| `list_policies(query=None)` | `GET /v1/underwriting/policy` | paginated, `boundAt` DESC |
| `get_policy(policy_id)` | `GET /v1/underwriting/policy/{policyId}` | policy + payout events |
| `evaluate_policy(policy_id)` | `POST /v1/underwriting/policy/{policyId}/evaluate` | re-evaluate; bodyless |
| `settle_policy(policy_id, input)` | `POST /v1/underwriting/policy/{policyId}/settle` | platform-ops only |

### Observations / nowcasting (L5.3)

| Method | Endpoint | Notes |
|---|---|---|
| `create_station(input)` | `POST /v1/observations/stations` | register a station |
| `list_stations()` | `GET /v1/observations/stations` | the tenant's stations |
| `update_station(station_id, input)` | `PATCH /v1/observations/stations/{stationId}` | partial update |
| `recent_observations(station_id, query=None)` | `GET /v1/observations/stations/{stationId}/recent` | most-recent observations |
| `submit_observations(input)` | `POST /v1/observations` | push into the 0-6h window (Pro+) |
| `submit_outcome(input)` | `POST /v1/outcomes` | standalone outcome (not tied to a scored session) |

### Audit & compliance

| Method | Endpoint | Notes |
|---|---|---|
| `audit_export(query)` | `GET /v1/audit/export` | `query["format"] == "csv"` → `str`, else parsed JSON |

### LLM BYOK (bring-your-own Anthropic key)

| Method | Endpoint | Notes |
|---|---|---|
| `set_llm_key(input)` | `PUT /v1/tenant/llm-key` | validate + store; resolves `None` (204) |
| `get_llm_key()` | `GET /v1/tenant/llm-key` | masked status (never the key) |
| `delete_llm_key()` | `DELETE /v1/tenant/llm-key` | remove; resolves `None` (204) |

### Health, legal & public (no auth)

| Method | Endpoint | Notes |
|---|---|---|
| `health()` | `GET /v1/health` | liveness |
| `health_ready()` | `GET /v1/health/ready` | readiness (503 → `GoableAPIError`) |
| `legal_document(kind)` | `GET /v1/legal/{kind}/current` | current published legal doc |
| `catalog_stats()` | `GET /v1/public/catalog-stats` | open catalogue coverage stats |
| `sustainability_index(query)` | `GET /v1/public/sustainability-index` | Goable Sustainability Index (JSON-LD) |
| `public_signup(input)` | `POST /v1/public/signup` | self-service tenant signup |

### Research (open data, CC BY — NDJSON streams returned as `str`)

| Method | Endpoint | Notes |
|---|---|---|
| `difficulty_atlas_export()` | `GET /v1/research/difficulty-atlas/export.jsonl` | L15 Difficulty Atlas |
| `verification_export(query=None)` | `GET /v1/research/verification/export` | Stream F forecast verification |

Full endpoint reference: [goable.io/docs](https://goable.io/docs).

## Errors

```python
from goable_sdk import GoableAPIError, GoableNetworkError

try:
    goable.score({"activity": "kitesurfing", "location": {"lat": 43.7, "lng": 7.27}, "ensemble": True})
except GoableAPIError as err:
    err.status                # e.g. 402
    err.code                  # e.g. "PAYMENT_REQUIRED"
    err.issues                # Zod issues on 422 VALIDATION_ERROR
    err.detail                # free-form context (e.g. plan info)
    err.retry_after_seconds   # seconds from `Retry-After` on a 429 (else None)
    err.rate_limit            # {"limit", "remaining", "reset"} when the response carried X-RateLimit-* headers
except GoableNetworkError as err:
    err.kind  # "timeout" | "network" | "parse"
```

On a `429`, back off using the server's hint:

```python
import time

try:
    ...
except GoableAPIError as err:
    if err.status == 429 and err.retry_after_seconds is not None:
        time.sleep(err.retry_after_seconds)
        # ...then retry
```

`DriftActiveError` (a `GoableAPIError` subclass) is raised on `422 DRIFT_ACTIVE`
from `bind_policy()` and exposes `open_drift_events`.

## Testing without network access

The client never hits the network directly in your own tests either — inject
an `httpx.Client` built on `httpx.MockTransport`:

```python
import httpx
from goable_sdk import GoableClient

def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"status": "ok"})

client = GoableClient(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))
```

## Types are generated from the API contract

The request/response models in `goable_sdk._models` (re-exported from the
top-level package, and fully available via `goable_sdk.models`) are
**generated** from the Goable API's OpenAPI document (`openapi.json`) via
[`datamodel-code-generator`](https://github.com/koxudaxi/datamodel-code-generator)
— they are never hand-authored, so they can't drift from the contract. Never
hand-edit `src/goable_sdk/_models.py`; regenerate it with:

```bash
python scripts/generate_models.py
```

The committed `openapi.json` tracks the live public API contract.

## Contributing & releases

Releases are automated via PyPI Trusted Publishing: merging to `main` (with a
version bump in `pyproject.toml`) publishes to PyPI on tag.

## License

MIT © Fabio Carucci
