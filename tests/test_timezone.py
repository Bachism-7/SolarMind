from datetime import UTC

import pytest

from app.timezone_utils import LocalTimeError, parse_aware_timestamp, resolve_local_datetime


def test_dst_fold_requires_choice_and_selects_both_instants():
    local_value = "2024-11-03T01:30:00"
    with pytest.raises(LocalTimeError, match="Ambiguous"):
        resolve_local_datetime(local_value, "America/Los_Angeles")
    first = resolve_local_datetime(local_value, "America/Los_Angeles", fold=0)
    second = resolve_local_datetime(local_value, "America/Los_Angeles", fold=1)
    assert second.timestamp() - first.timestamp() == 3600
    assert first.fold == 0
    assert second.fold == 1


def test_dst_gap_is_rejected_without_silent_adjustment():
    with pytest.raises(LocalTimeError, match="Nonexistent"):
        resolve_local_datetime("2024-03-10T02:30:00", "America/Los_Angeles")


def test_offset_timestamp_is_required_and_preserved():
    with pytest.raises(LocalTimeError, match="offset"):
        parse_aware_timestamp("2024-06-21T12:00:00")
    parsed = parse_aware_timestamp("2024-06-21T12:00:00-07:00")
    assert parsed.utcoffset().total_seconds() == -7 * 3600
    assert parsed.astimezone(UTC).isoformat() == "2024-06-21T19:00:00+00:00"
