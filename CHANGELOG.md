# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
