# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
