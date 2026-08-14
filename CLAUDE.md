# CLAUDE.md — `goable-sdk` (Python)

Public Python client for the Goable API. Pydantic v2 models are **generated**
from the committed `openapi.json` (the API contract); only a handful of wrappers
are hand-written. Tooling: `uv` + `datamodel-code-generator` + `ruff` + `mypy` +
`pytest`.

## Release / branch convention (IMPORTANT)

Each change gets its OWN new branch, named for the WORK it does — **never for a
release version** (the version is decided at merge/publish time and is unknown
when the branch opens). Use a Conventional-Commits-style type prefix + a short
topic:

**`<type>/<topic>`** — `type` ∈ `feature` | `fix` | `chore` (| `docs` | `refactor`),
e.g. `feature/contract-v0.6-sync`, `fix/rate-limit-headers`, `chore/deps-bump`.

- Do **NOT** put a presumed release version (`v0.9`) in the branch name. A topic
  MAY reference the CONTRACT version being synced (known at branch time), e.g.
  `contract-v0.6-sync`.
- Do **NOT** reuse a generic or session-assigned branch name.
- One PR per change, base `main`; delete the branch after merge.
- Bump the version in **both** `pyproject.toml` AND `src/goable_sdk/__init__.py`
  (`__version__`), and add a dated `CHANGELOG.md` section — all in the SAME PR.

## Contract-sync workflow

The SDK mirrors the live API contract. To sync to a new contract version:

1. Refresh `openapi.json` from the API (the `.github/workflows/refresh-openapi.yml`
   job does this daily; to do it by hand, copy the API's generated
   `apps/api/openapi.json`), then normalize: `python scripts/normalize_spec.py openapi.json`.
2. Install dev deps and regenerate models: `uv sync --extra dev` then
   `uv run python scripts/generate_models.py` (writes `src/goable_sdk/_models.py`
   — **never** hand-edit or lint it; ruff/mypy exclude it).
3. New response fields flow through the regenerated models automatically — the
   per-endpoint models are re-exported by name from `__init__.py`; touch that only
   for a genuinely new endpoint (a new client method in `client.py`).
4. Hand-written first-class surface: `client.py`, `errors.py`, `safety.py`,
   `__init__.py`. Add exports here only when the contract promises a named SDK
   symbol (e.g. `SAFETY_HAZARD_SUBJECTS`), and add them to `__all__`.
5. Bump version (both places) + CHANGELOG; then:
   `uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest`.
