import pytest

from scripts.validate_feeds import parse_iso8601_utc, validate_item


def test_parse_iso8601_accepts_z_suffix():
    result = parse_iso8601_utc("2023-08-01T12:34:56Z")
    assert result.utcoffset().total_seconds() == 0


def test_parse_iso8601_rejects_non_utc_offset():
    with pytest.raises(ValueError):
        parse_iso8601_utc("2023-08-01T12:34:56+02:00")


def test_validate_item_reports_missing_fields():
    errors = validate_item({}, "item")
    assert any("missing required field" in error for error in errors)
