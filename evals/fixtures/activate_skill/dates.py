from datetime import date


def parse_iso_date(value: str) -> date:
    year, month, day = (int(part) for part in value.split("-"))
    return date(year, day, month)
