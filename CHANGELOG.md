# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-08-11

Contract re-sync to the live API: typed `session_id` on the score response.

### Added

- **`ScoreResponse.session_id`** is now a typed, required field — the
  scored-session id returned on every `/v1/score` response. Pass it back as
  `audit_log_id` on `POST /v1/outcomes` (or as the `:id` on
  `POST /v1/score/:id/outcome`) to link an observed outcome to the exact
  forecast that produced it.

### Changed

- Re-synced `openapi.json` and regenerated `_models.py`. `alerts[].code` is
  now documented as the stable, machine-readable identifier to key UI and
  localization off (the `description` is English debug prose, not localized),
  and `breakdown[].value` / `.suitability` carry native-unit documentation.

## [0.5.0] - 2026-08-04

Contract re-sync to the live API for the `/v1/score/series` bucket shape.

### Changed

- **`/v1/score/series` bucket (breaking)** — the per-bucket `at` field is
  renamed to **`timestamp`**, and **`confidence`** + **`alerts`** (same
  per-bucket alerts shape as `/v1/score/multi`) are now present on every
  bucket. Callers reading `series[].at` must switch to `series[].timestamp`.

The committed `openapi.json` is byte-for-byte identical (normalized) to the
canonical `apps/api/openapi.json` on the monorepo's `main`; Pydantic v2
models regenerated via `datamodel-code-generator`.

## [0.4.0] - 2026-08-03

Contract re-sync to the live API adding activity discovery and a dedicated
"not feasible" verdict. Additive only — no breaking changes to existing
methods or models.

### Added

- **`activities()`** — new client method for `GET /v1/activities`, the
  catalogue's base activity slugs (`slug` / `display_name` / `family`) — the
  canonical list a caller can pass as `activity`. Public: no API key required
  (the client still sends one if configured). The server's `GET /v1/profiles`
  is an alias for the same response.
- **`KNOWN_ACTIVITY_SLUGS`** (a committed snapshot tuple, refreshed by
  `scripts/generate_slugs.py`) and **`ActivitySlug`** — a plain `str` alias,
  intentionally **not** a closed `Literal[...]`. Python's type system has no
  equivalent of the TS SDK's open literal union (`KnownSlug | (string &
  {})`), so a closed `Literal` here would wrongly reject a brand-new catalog
  activity the moment it shipped, before this snapshot caught up. Treat
  `KNOWN_ACTIVITY_SLUGS` as a runtime autocomplete/validation aid only —
  `activities()` is the authoritative source.
- **`not_feasible` verdict** — a new `Verdict` member for a `score: 0` caused
  by a FEASIBILITY gate (e.g. no rideable wind) rather than a safety gate
  (lightning, AQI, etc.) — "not doable", not "dangerous". `unsafe` is
  reserved for the latter.
- **`scoreBasis` field** (new `ScoreBasis` enum: `forecast` / `gated` /
  `no_data`) on score responses — a gated `0` now carries the full
  `breakdown` + `physics` payload instead of a bare zero, so callers can see
  *why* an activity was gated out.
- **`did_you_mean` / `valid_slugs`** on the `ACTIVITY_NOT_FOUND` error detail
  — typo suggestions and the current valid-slug list for a rejected
  `activity`.

The committed `openapi.json` is byte-for-byte identical (normalized) to the
canonical `apps/api/openapi.json` on the monorepo's `main`; Pydantic v2
models regenerated via `datamodel-code-generator`.

## [0.3.0] - 2026-08-02

Contract re-sync to the live API exposing the new outcomes recall surface.
Additive only — no breaking changes to existing methods or models.

### Added

- **`void_outcomes(...)`** — new client method for `POST /v1/outcomes/void`, a
  non-destructive "lot recall" that stamps matching outcome rows voided (kept
  for audit) so they stop feeding calibration + research. Requires at least one
  narrowing selector (`batch_ref`, `audit_log_id`, `submitted_by_key_id`,
  `occurred_from`, `occurred_to`) alongside the mandatory `reason`; returns the
  count of rows newly voided. Requires the `outcomes:write` scope.
- **`submit_outcome(..., idempotency_key=...)`** — `POST /v1/outcomes` now
  accepts an optional `Idempotency-Key` header (parity with `report_outcome`),
  so a retried batch submission records each outcome exactly once.
- **`reason_category`** (enum `weather` / `operational` / `customer_demand` /
  `safety` / `mechanical` / `unknown`) and **`batch_ref`** on the
  `/v1/outcomes` request body — structured cause when a session didn't run
  (only `weather` / `safety` feed calibration) and a client lot handle for
  later recall. `reason_category` also lands on the `/v1/score/{id}/outcome`
  request body. Both flow through automatically from the generated models.
- **`DriftFlag` enrichment** — the drift-flag response schema now carries
  `cell`, `metric`, `reference_type`, `days_in_decline`, and
  `recalibration_triggered` (was `severity` + `since_timestamp` only).

The committed `openapi.json` is byte-for-byte identical (normalized) to the
canonical `apps/api/openapi.json` on the monorepo's `main`; Pydantic v2 models
regenerated via `datamodel-code-generator`.

## [0.2.0] - 2026-07-30

Contract re-sync to the live API after the monorepo's score-family coherence
release. Additive only — no breaking changes to existing methods or models.

### Added

- **`/v1/score/multi` response fully modelled** — per-spot dimension breakdown,
  end-to-end typed (was a loose object).
- **`breakdown[].prerequisite`** — the go/no-go feasibility flag now surfaces on
  each dimension breakdown entry.
- **`alert.kind`** — score alerts carry a `safety` / `feasibility` discriminator;
  the multi-alert shape is modelled.

The committed `openapi.json` is byte-for-byte identical (normalized) to the
canonical `apps/api/openapi.json` on the monorepo's `main`; Pydantic v2 models
regenerated via `datamodel-code-generator`.

## [0.1.0] - 2026-07-14

### Added

- Initial release. Sync `GoableClient` (httpx-based) mirroring the full
  public tenant-facing surface of [`@goable-io/sdk`](https://github.com/goable-io/sdk)
  (TypeScript) 1:1 — every method, same HTTP verbs/paths, `X-Goable-Key`
  auth, `Idempotency-Key` header support (`report_outcome`, `bind_policy`),
  `Retry-After` + `X-RateLimit-*` parsing, NDJSON/CSV passthrough for
  research + audit export streams.
- `GoableAPIError`, `DriftActiveError`, `GoableNetworkError` error model
  mirroring the TS SDK's `errors.ts`.
- Pydantic v2 request/response models generated from the committed
  `openapi.json` via `datamodel-code-generator`.
- Python 3.10+, fully typed (`mypy --strict` green).
