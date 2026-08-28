import re


def slugify(value: str) -> str:
    normalized = value.strip().casefold()
    return re.sub(r"\s+", "_", normalized)
