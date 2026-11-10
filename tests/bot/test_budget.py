import pytest

from directrent.bot.budget import parse_budget


@pytest.mark.parametrize(
    "text,expected",
    [
        ("10000-18000", (10000, 18000)),
        ("10 000 - 18 000 грн", (10000, 18000)),
        ("10000–18000", (10000, 18000)),
        ("-18000", (None, 18000)),
        ("до 18000", (None, 18000)),
        ("від 10000", (10000, None)),
        ("10000-", (10000, None)),
        ("18000-10000", (10000, 18000)),
        ("18000", (None, 18000)),
    ],
)
def test_parse_budget(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize("text", ["дешево", "0-0", "", "-", "10-20-30"])
def test_parse_budget_rejects(text):
    with pytest.raises(ValueError):
        parse_budget(text)
