from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models import ApiModel, Timestamp
from app.timestamps import format_timestamp, now


class Thing(ApiModel):
    at: Timestamp


def serialise(dt: datetime) -> str:
    return Thing(at=dt).model_dump(mode="json")["at"]


# --- format_timestamp --------------------------------------------------------


def test_format_timestamp_with_zero_milliseconds_keeps_the_zeros():
    result = format_timestamp(datetime(2026, 10, 22, 9, 30, 0, tzinfo=UTC))

    assert result == "2026-10-22T09:30:00.000Z"


def test_format_timestamp_with_microseconds_keeps_three_digit_milliseconds():
    result = format_timestamp(datetime(2026, 10, 22, 9, 30, 0, 123456, tzinfo=UTC))

    assert result == "2026-10-22T09:30:00.123Z"


def test_format_timestamp_truncates_milliseconds_instead_of_rounding():
    result = format_timestamp(datetime(2026, 10, 22, 9, 30, 0, 999999, tzinfo=UTC))

    assert result == "2026-10-22T09:30:00.999Z"


def test_format_timestamp_converts_non_utc_input_to_utc():
    plus_two = timezone(timedelta(hours=2))

    result = format_timestamp(datetime(2026, 10, 22, 11, 30, 0, tzinfo=plus_two))

    assert result == "2026-10-22T09:30:00.000Z"


def test_format_timestamp_never_uses_offset_or_microseconds():
    result = format_timestamp(datetime(2026, 10, 22, 9, 30, 0, 5000, tzinfo=UTC))

    assert result.endswith("Z")
    assert "+00:00" not in result
    assert len(result) == len("2026-10-22T09:30:00.000Z")


def test_format_timestamp_with_naive_datetime_raises_value_error():
    with pytest.raises(ValueError):
        format_timestamp(datetime(2026, 10, 22, 9, 30, 0))


def test_now_returns_an_aware_utc_datetime():
    result = now()

    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)


# --- Timestamp model type ----------------------------------------------------


def test_timestamp_field_serialises_microseconds_as_milliseconds():
    result = serialise(datetime(2026, 10, 22, 9, 30, 0, 123456, tzinfo=UTC))

    assert result == "2026-10-22T09:30:00.123Z"


def test_timestamp_field_with_zero_microseconds_keeps_the_dot_zero_zero_zero():
    result = serialise(datetime(2026, 10, 22, 9, 30, 0, tzinfo=UTC))

    assert result == "2026-10-22T09:30:00.000Z"


def test_timestamp_field_converts_non_utc_input_to_utc():
    plus_two = timezone(timedelta(hours=2))

    result = serialise(datetime(2026, 10, 22, 11, 30, 0, tzinfo=plus_two))

    assert result == "2026-10-22T09:30:00.000Z"


def test_timestamp_field_serialises_in_json_string_output():
    thing = Thing(at=datetime(2026, 10, 22, 9, 30, 0, 123456, tzinfo=UTC))

    assert thing.model_dump_json() == '{"at":"2026-10-22T09:30:00.123Z"}'


# --- String ordering ---------------------------------------------------------


def test_formatted_timestamps_across_a_second_boundary_sort_chronologically():
    earlier = format_timestamp(datetime(2026, 10, 22, 9, 30, 59, 999000, tzinfo=UTC))
    later = format_timestamp(datetime(2026, 10, 22, 9, 31, 0, 0, tzinfo=UTC))

    assert earlier < later


def test_formatted_timestamps_one_millisecond_apart_sort_chronologically():
    earlier = format_timestamp(datetime(2026, 10, 22, 9, 30, 0, 1000, tzinfo=UTC))
    later = format_timestamp(datetime(2026, 10, 22, 9, 30, 0, 2000, tzinfo=UTC))

    assert earlier < later


def test_formatted_timestamps_from_different_zones_sort_by_instant():
    plus_two = timezone(timedelta(hours=2))
    earlier = format_timestamp(datetime(2026, 10, 22, 11, 0, 0, tzinfo=plus_two))  # 09:00Z
    later = format_timestamp(datetime(2026, 10, 22, 9, 30, 0, tzinfo=UTC))

    assert earlier < later
