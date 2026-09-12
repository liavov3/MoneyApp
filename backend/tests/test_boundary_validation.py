"""Malformed filters must be 422 errors before a database query is attempted."""
import base64
import json
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.errors import AppError
from app.routers.transactions import _decode_cursor, _encode_cursor, _month_bounds


@pytest.mark.parametrize("month", ["9999-12", "2026-00", "2026-13", "2026- 1", "２０２６-01", "2026-1"])
def test_invalid_months_are_validation_errors(month):
    with pytest.raises(AppError) as caught:
        _month_bounds(month)
    assert caught.value.code == "validation_error"


@pytest.mark.parametrize("month,start,end", [
    ("2024-02", date(2024, 2, 1), date(2024, 3, 1)),
    ("2025-12", date(2025, 12, 1), date(2026, 1, 1)),
])
def test_month_boundaries(month, start, end):
    assert _month_bounds(month) == (start, end)


@pytest.mark.parametrize("payload", [
    {"o": "2026-01-01", "c": "2026-01-01T01:00:00", "id": str(uuid4())},
    {"o": "2026-01-01", "c": "2026-01-01T01:00:00Z", "id": "invalid"},
    [], None,
])
def test_malformed_cursor(payload):
    cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(AppError) as caught:
        _decode_cursor(cursor)
    assert caught.value.code == "validation_error"


def test_unicode_cursor_is_validation_error():
    with pytest.raises(AppError):
        _decode_cursor("לא תקין")


def test_cursor_roundtrip_preserves_microseconds_and_tie_breaker():
    now = datetime(2026, 1, 1, 1, 2, 3, 456789, tzinfo=timezone.utc)
    txn_id = str(uuid4())
    assert _decode_cursor(_encode_cursor("2026-01-01", now, txn_id)) == (date(2026, 1, 1), now, txn_id)
