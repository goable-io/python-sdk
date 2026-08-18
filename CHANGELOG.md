# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.0] - 2026-08-18

Contract re-sync to the live API (deployed). Additive within contract **v0.6** —
the new field is optional, so existing code keeps working.

### Added

- **`breakdown[].metric`** on the score responses (`/v1/score` and
  `/v1/score-multi`). Each breakdown row now carries its `metric` — the closed,
  versioned join key from the fixed `Metric` vocabulary, identical to
  `dimensions[].metric` (GET /v1/activities) and to a profile gate's
  `alerts[].subject`. Prefer it over `breakdown[].name` for attaching a unit
  (join `breakdown[].metric` → `dimensions[].metric` → `dimensions[].unit`) or
  wiring a per-dimension detail view, so hazard subjects and dimension rows key
  off ONE vocabulary.

### Changed

- Model docs now state explicitly that `breakdown[].name` / `dimensions[].name`
  is **NOT end-user-facing text** — a snake_case join key, never a display
  label. The `dimensions[].name` example was corrected `"Wind"` → `"wind_speed"`
  (the real runtime value), and `breakdown[].value`'s unit prose collapsed to a
  single pointer at `dimensions[].unit` (joined on `metric`). Docs-only; no model
  change.

## [0.9.0] - 2026-08-14

Contract re-sync to the live API (deployed) — catches the SDK up through contract
**v0.6**. Additive at the model level (new optional fields flow through the
regenerated pydantic models); the only semantic change is `unsafe` reserved for
danger (see *Changed*).

### Added

- **`confidence_normalized`** and **`confidence_ceiling`** on the score responses
  (`/v1/score`, `/v1/score-multi`, `/v1/score-series`, forecast AND ensemble
  reads). `confidence_ceiling` = `profile_maturity × hierarchical_calibration`
  (the best `confidence` this profile+spot can reach); `confidence_normalized` =
  server-computed `confidence / confidence_ceiling` ∈ [0, 1]. Both are now
  required on the score response. Prefer these over a hard-coded absolute
  confidence threshold.
- **`engine_version`** (required) on the three score responses — one value
  tracking both engine behaviour and the API schema.
- **`dataCoverage`** on `/v1/score-multi` results and `/v1/score-series` buckets
  (fraction of the window covered by real samples) — previously documented but
  absent.
- **`alerts[].source`** = `"observed" | "forecast"` on the lightning safety alert:
  whether the danger signal is based on real observed strikes near the point or
  on forecast convective instability only. Uniform across `/v1/score` and
  `/v1/score-multi`; always `"forecast"` on `/v1/score-series` (observed strikes
  are a nowcast, not looked up per bucket).
- **`SAFETY_HAZARD_SUBJECTS`** exported (`("air_quality", "lightning")`) with the
  `SafetyHazardSubject` type and an `is_safety_hazard_subject()` guard — the
  known, stable `alerts[].subject` slugs for the two universal safety gates.
  `subject` stays an open string (a profile gate-trip subject is the tripped
  gate's metric, e.g. `"wind_speed_kn"`), so this is the KNOWN safety-subject set,
  not an exhaustive enum.
- Closed `unit` enum on `GET /v1/activities` and the full frozen `eco` observation
  schema — both flow through the regenerated models.

### Changed

- **`unsafe` verdict reserved for DANGER only (behaviour).** `unsafe` now means a
  SAFETY gate trip (a real evaluated hazard); a no-data window is `not_feasible`;
  a uniformly-poor score that floors to 0 with no gate is `poor`. **Recheck any
  consumer that colours or branches on the `unsafe` verdict for no-data or poor
  days.** The `Verdict`/`ScoreBasis` types are unchanged (same members) — only the
  emission semantics moved.
- **`unsafe ⟹ scoreBasis == "gated" ⟹ confidence == ceiling == normalized == 1`**
  now holds uniformly, including on ensemble reads (previously a gated ensemble
  no-go could report a confidence < 1). A gated no-go is a certain outcome, so a
  consumer suppressing low-confidence numbers can rely on a gate-trip no-go
  clearing any confidence floor.

### Fixed

- `goable_sdk.__version__` was stuck at `"0.4.0"` while the package shipped as
  `0.8.0`; it now tracks `pyproject.toml` (`0.9.0`).

## [0.8.0] - 2026-08-13

Contract re-sync to the live API (goable monorepo #72, deployed). Additive; existing code keeps working.

### Added

- **`alerts[].subject`** on all scoring alerts (`/v1/score`, `/v1/score-series`,
  `/v1/score-multi`, and the per-activity `/v1/score/multi` alerts): a
  machine-readable slug for the specific hazard, gate, or dimension an alert is
  about — the field that disambiguates two alerts sharing the same `code`. Two
  `SAFETY_DATA_UNAVAILABLE` warnings on one response now carry
  `subject="lightning"` and `subject="air_quality"`, so a consumer can tell which
  safety gate went unevaluated without parsing the English `description`. On a
  gate-trip alert it is the gate's metric name (e.g. `"wind_speed_kn"`); on the
  consolidated `SAFETY_GATE_UNEVALUATED` advisory it is the comma-joined metric
  slug(s). Open string, not a closed enum.

### Changed

- **`alerts[].kind`** now also rides the safety-advisory warnings
  (`SAFETY_GATE_UNEVALUATED`, `SAFETY_DATA_UNAVAILABLE`), always `"safety"`, so a
  caller can treat "a safety check did not run" distinctly from an ordinary data
  gap — previously it was documented only on gate-trip (critical) alerts. No type
  change; spec description synced.

## [0.7.0] - 2026-08-12

Contract re-sync to the live API (PR #69, deployed). Additive; existing code keeps working.

### Added

- **Full stable `Error` code enum**, including `SESSION_NOT_FOUND` (404 from
  `POST /v1/score/:id/outcome` when the id is not a scored session) and
  `AUDIT_LOG_NOT_FOUND` (404 from `POST /v1/outcomes` when `audit_log_id`
  does not resolve to a scored session). Error handling can switch on real
  codes instead of loose strings.
- **`ScoreSeriesResponse`** now exposes typed `session_id`, `profile_slug`,
  and `granularity` (all always-returned); **`ScoreMultiResponse.session_id`**
  is now typed and required. Series/multi session ids are correlation ids
  only, not linkable as `audit_log_id` (only single `POST /v1/score` ids
  close the calibration loop).

### Changed

- **Outcome submission is durable/synchronous.** `POST /v1/score/:id/outcome`
  now persists on the request path (no longer documented as queued) and
  returns `404 SESSION_NOT_FOUND` for an unknown session. Docstrings corrected.
- **Confidence semantics.** The score `confidence` is now horizon-decaying
  (near-term baseline around 0.55-0.62, higher for a nowcast, lower far out)
  rather than the old near-flat value. No type change; spec description synced.

### Note

- `void_outcomes()` (lot recall) and the outcome `reason_category` / `batch_ref`
  / `Idempotency-Key` surface shipped earlier and are unchanged here.

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
