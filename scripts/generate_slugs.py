#!/usr/bin/env python3
"""Refresh the committed activity-slug snapshot from the live catalog.

    python scripts/generate_slugs.py

Fetches ``GET {GOABLE_API_BASE}/v1/activities`` (public, no auth) and
rewrites ``src/goable_sdk/_activity_slugs.py`` with the current sorted,
deduped slug list. NOT part of ``scripts/generate_models.py`` -- this talks
to the live network, unlike the offline model generator (openapi.json ->
_models.py). Run from ``.github/workflows/refresh-openapi.yml``, which
already has live-API reachability for the OpenAPI contract sync.

Never overwrites the committed file on failure or an empty result -- the
seed stays offline-authoritative even if the live endpoint is briefly
unreachable or misbehaves.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

PKG_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = PKG_ROOT / "src" / "goable_sdk" / "_activity_slugs.py"

BASE_URL = "https://api.goable.io"

_HEADER = '''"""SNAPSHOT of the base activity slugs the live catalog exposes at
``GET /v1/activities`` (public, no auth) -- committed so the SDK installs and
imports fully offline, with no network dependency at install/build time.

REFRESHED from the live endpoint by ``scripts/generate_slugs.py``, run as
part of the ``.github/workflows/refresh-openapi.yml`` job (the same job that
already has live-API reachability for the OpenAPI contract sync).

This is intentionally an OPEN set -- see ``ActivitySlug`` below: the catalog
(discoverable at runtime via ``client.activities()``) is the source of
truth, and a newly-added catalog activity must never fail type-checking just
because this snapshot hasn't been refreshed yet. Python's type system has no
equivalent of TypeScript's open literal union (``KnownSlug | (string & {})``),
so ``ActivitySlug`` stays a plain ``str`` alias rather than a closed
``Literal[...]`` -- a closed ``Literal`` would wrongly reject a brand-new
catalog activity that just hasn't made it into this snapshot yet.
``KNOWN_ACTIVITY_SLUGS`` is a runtime aid (autocomplete / validation helper
in editors and lint rules that understand tuples of literals);
``client.activities()`` is the authoritative runtime source.

Do not hand-edit. To refresh, run ``python scripts/generate_slugs.py``.
"""

from __future__ import annotations

'''


def render_file(slugs: list[str]) -> str:
    items = ",\n    ".join(f'"{s}"' for s in slugs)
    body = (
        f"KNOWN_ACTIVITY_SLUGS: tuple[str, ...] = (\n    {items},\n)\n\n"
        "# A base activity slug. See the module docstring: stays `str` (open set), not a\n"
        "# closed Literal -- a new catalog activity must never fail type-checking.\n"
        "ActivitySlug = str\n"
    )
    return _HEADER + body


def main() -> int:
    base = (os.environ.get("GOABLE_API_BASE") or BASE_URL).rstrip("/")
    url = f"{base}/v1/activities"

    try:
        res = httpx.get(url, timeout=30.0)
        res.raise_for_status()
        payload: Any = res.json()
    except (httpx.HTTPError, ValueError) as err:
        print(f"[generate_slugs] failed to fetch {url}: {err}", file=sys.stderr)
        print("[generate_slugs] leaving the committed _activity_slugs.py untouched.", file=sys.stderr)
        return 1

    activities = payload.get("activities") if isinstance(payload, dict) else None
    if not isinstance(activities, list):
        print(f"[generate_slugs] {url} returned an unexpected body shape.", file=sys.stderr)
        return 1

    slugs = sorted({a["slug"] for a in activities if isinstance(a, dict) and "slug" in a})

    if not slugs:
        print(
            f"[generate_slugs] {url} returned zero activities -- refusing to overwrite the seed.",
            file=sys.stderr,
        )
        return 1

    OUTPUT.write_text(render_file(slugs))

    # Normalise formatting to match the repo's ruff config.
    for cmd in (["ruff", "format", str(OUTPUT)], ["ruff", "check", "--fix", str(OUTPUT)]):
        fmt = subprocess.run([sys.executable, "-m", *cmd], cwd=PKG_ROOT, check=False)
        if fmt.returncode != 0:
            print(f"[generate_slugs] warning: `{' '.join(cmd)}` exited {fmt.returncode}", file=sys.stderr)

    print(f"[generate_slugs] wrote {OUTPUT.relative_to(PKG_ROOT)} with {len(slugs)} slugs from {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
