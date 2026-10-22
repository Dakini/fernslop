from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models import ApiModel, Timestamp
from app.timestamps import format_timestamp


class Thing(ApiModel):
    at: Timestamp


# --- format_timestamp --------------------------------------------------------


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


def test_format_timestamp_with_naive_datetime_raises_value_error():
    with pytest.raises(ValueError):
        format_timestamp(datetime(2026, 10, 22, 9, 30, 0))


# --- Timestamp model type ----------------------------------------------------


def test_timestamp_field_serialises_in_json_string_output():
    thing = Thing(at=datetime(2026, 10, 22, 9, 30, 0, 123456, tzinfo=UTC))

    assert thing.model_dump_json() == '{"at":"2026-10-22T09:30:00.123Z"}'


# --- String ordering ---------------------------------------------------------


