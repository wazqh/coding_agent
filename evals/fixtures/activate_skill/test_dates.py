from datetime import date

from dates import parse_iso_date


def test_parses_iso_date() -> None:
    assert parse_iso_date("2026-08-28") == date(2026, 8, 28)
