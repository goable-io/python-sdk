#!/usr/bin/env python3
"""Normalise a freshly-fetched openapi.json before diffing it against the
committed snapshot.

    python scripts/normalize_spec.py openapi.json

Pins ``info.version`` to a stable placeholder (the live route reports the
current deployment's version string, e.g. "1.0.0", which is not a contract
change) and re-serialises with stable 2-space indentation + a trailing
newline, so the drift check in ``.github/workflows/refresh-openapi.yml``
fires only on a REAL contract change. Mirrors
``/home/user/sdk/scripts/normalizeSpec.mjs``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PINNED_VERSION = "0.0.0"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <openapi.json>", file=sys.stderr)
        return 1

    path = Path(argv[1])
    spec = json.loads(path.read_text())

    if isinstance(spec.get("info"), dict):
        spec["info"]["version"] = PINNED_VERSION

    path.write_text(json.dumps(spec, indent=2, sort_keys=False, ensure_ascii=False) + "\n")
    print(f"[normalize_spec] normalised {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
