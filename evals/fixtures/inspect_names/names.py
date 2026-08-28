def normalize_name(value: str) -> str:
    """Normalize spaces and case for use in stable identifiers."""
    return "-".join(value.casefold().split())
