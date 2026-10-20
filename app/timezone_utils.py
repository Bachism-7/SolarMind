"""Strict IANA timezone handling, including daylight-saving folds and gaps."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class LocalTimeError(ValueError):
    """A local timestamp is invalid, ambiguous, or nonexistent."""


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise LocalTimeError(f"Unknown IANA timezone: {name}") from error


def local_candidates(naive: datetime, zone_name: str) -> list[datetime]:
    """Return valid local-time interpretations, with duplicate folds removed."""
    if naive.tzinfo is not None:
        raise LocalTimeError("Local datetime must not contain a UTC offset")
    zone = get_zone(zone_name)
    candidates: list[datetime] = []
    seen_offsets = set()
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if round_trip == naive and candidate.utcoffset() not in seen_offsets:
            candidates.append(candidate)
            seen_offsets.add(candidate.utcoffset())
    return candidates


def resolve_local_datetime(local_value: str, zone_name: str, fold: int | None = None) -> datetime:
    """Resolve a local ISO datetime; reject gaps and require fold for overlaps."""
    try:
        naive = datetime.fromisoformat(local_value)
    except (TypeError, ValueError) as error:
        raise LocalTimeError("Local datetime must use ISO 8601 date and time") from error
    candidates = local_candidates(naive, zone_name)
    if not candidates:
        raise LocalTimeError(f"Nonexistent local time in {zone_name}: {local_value}")
    if len(candidates) == 2:
        if fold not in (0, 1):
            raise LocalTimeError(f"Ambiguous local time in {zone_name}; choose fold 0 or fold 1")
        return next(candidate for candidate in candidates if candidate.fold == fold)
    if fold not in (None, 0, 1):
        raise LocalTimeError("fold must be 0 or 1")
    return candidates[0]


def parse_aware_timestamp(value: str) -> datetime:
    """Parse an ISO timestamp only when it includes an explicit UTC offset."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise LocalTimeError("Timestamp must be ISO 8601 and include a UTC offset") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LocalTimeError("Timestamp must include a UTC offset")
    return parsed


def first_valid_local_midnight(day: date, zone_name: str) -> datetime:
    """Find first representable minute on a local date, including rare midnight gaps."""
    zone = get_zone(zone_name)
    value = datetime.combine(day, time.min)
    for _ in range(24 * 60):
        candidates = local_candidates(value, zone_name)
        if candidates:
            return candidates[0]
        value += timedelta(minutes=1)
    raise LocalTimeError(f"No valid local time exists on {day.isoformat()} in {zone.key}")
