from slug import slugify


def test_slug_uses_hyphens_and_collapses_whitespace() -> None:
    assert slugify("  Forge   Agent ") == "forge-agent"
