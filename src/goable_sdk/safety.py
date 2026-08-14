"""Universal safety-hazard subject slugs.

``alerts[].subject`` is an OPEN string, but the two UNIVERSAL safety gates
(lightning + air quality) carry STABLE, documentable subject slugs on both their
gate-trip alerts and their ``SAFETY_DATA_UNAVAILABLE`` advisories. The OpenAPI
``alerts[].subject`` description points consumers at this exported set as the
known safety-subject vocabulary, so you can localise the universal hazards from a
fixed table.

This is NOT an exhaustive ``subject`` enum: a PROFILE gate-trip alert's subject is
the tripped gate's metric (e.g. ``"wind_speed_kn"``, drawn from the same
vocabulary as ``dimensions[].metric`` in ``GET /v1/activities``). Treat these two
as the KNOWN safety subjects and keep a generic fallback for the rest.

Mirrors the server's ``SAFETY_HAZARD_SUBJECTS`` (single source of truth),
including its order.
"""

from __future__ import annotations

from typing import Literal, TypeGuard

SafetyHazardSubject = Literal["air_quality", "lightning"]
"""A universal safety-hazard subject slug -- see :data:`SAFETY_HAZARD_SUBJECTS`."""

SAFETY_HAZARD_SUBJECTS: tuple[SafetyHazardSubject, ...] = ("air_quality", "lightning")
"""The known universal safety-hazard subject slugs, in the server's order."""


def is_safety_hazard_subject(subject: str | None) -> TypeGuard[SafetyHazardSubject]:
    """Narrow an ``alerts[].subject`` to one of the known universal safety subjects.

    Returns ``False`` for a profile-gate metric subject (e.g. ``"wind_speed_kn"``)
    and for a missing subject.
    """
    return subject in SAFETY_HAZARD_SUBJECTS
