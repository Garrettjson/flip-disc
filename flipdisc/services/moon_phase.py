"""Moon phase calculation — pure astronomical math, no API calls.

The synodic month (new moon to new moon) is ~29.53 days. Given a reference
new-moon date, the current phase is just ``(days_since_ref % synodic) / synodic``.

Usage::

    from flipdisc.services.moon_phase import moon_phase, phase_name

    p = moon_phase()           # float in [0.0, 1.0)
    print(phase_name(p))       # e.g. "waxing_crescent"
"""

from __future__ import annotations

from datetime import UTC, datetime

# Reference new moon: 2000-01-06 18:14 UTC
_REF_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=UTC)

# Mean synodic period in days
SYNODIC_PERIOD = 29.530588853


def moon_phase(dt: datetime | None = None) -> float:
    """Return the current moon phase as a float in [0.0, 1.0).

    0.0 = new moon, 0.25 = first quarter, 0.5 = full moon, 0.75 = last quarter.
    """
    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    days_since = (dt - _REF_NEW_MOON).total_seconds() / 86400.0
    return (days_since % SYNODIC_PERIOD) / SYNODIC_PERIOD


def phase_name(phase: float) -> str:
    """Return a human-readable name for the given phase value.

    Divides the cycle into 8 segments of 0.125 each.
    """
    # Normalize to [0.0, 1.0)
    phase = phase % 1.0
    if phase < 0.0625:
        return "new_moon"
    if phase < 0.1875:
        return "waxing_crescent"
    if phase < 0.3125:
        return "first_quarter"
    if phase < 0.4375:
        return "waxing_gibbous"
    if phase < 0.5625:
        return "full_moon"
    if phase < 0.6875:
        return "waning_gibbous"
    if phase < 0.8125:
        return "last_quarter"
    if phase < 0.9375:
        return "waning_crescent"
    return "new_moon"
