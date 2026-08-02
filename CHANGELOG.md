# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
