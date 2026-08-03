"""SNAPSHOT of the base activity slugs the live catalog exposes at
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

KNOWN_ACTIVITY_SLUGS: tuple[str, ...] = (
    "alpine-skiing",
    "boat-excursion",
    "bodyboarding",
    "bouldering",
    "canyoning",
    "climbing",
    "freeride",
    "hang-gliding",
    "hot-air-ballooning",
    "jet-ski",
    "kayak",
    "kitesurfing",
    "mountain-biking",
    "open-water-swimming",
    "paragliding",
    "road-cycling",
    "sailing",
    "scuba",
    "ski-touring",
    "snorkeling",
    "snowboarding",
    "sup",
    "surfing",
    "trail-running",
    "trekking",
    "wakeboarding",
    "windsurfing",
    "wing-foiling",
)

# A base activity slug. See the module docstring: stays `str` (open set), not a
# closed Literal -- a new catalog activity must never fail type-checking.
ActivitySlug = str
