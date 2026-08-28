from calculator import add


def test_adds_positive_and_negative_values() -> None:
    assert add(2, 3) == 5
    assert add(-2, 1) == -1
