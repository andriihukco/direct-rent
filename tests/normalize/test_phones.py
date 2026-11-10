import pytest

from directrent.models import Contact
from directrent.normalize.phones import extract_contacts, extract_phones


@pytest.mark.parametrize(
    "text,expected",
    [
        ("+38 (067) 123-45-67", ["+380671234567"]),
        ("067 123 45 67", ["+380671234567"]),
        ("380671234567", ["+380671234567"]),
        ("тел. 097.123.45.67", ["+380971234567"]),
        ("0671234567, 0671234567", ["+380671234567"]),
        ("0671234567 або 0931112233", ["+380671234567", "+380931112233"]),
        ("ціна 16000, 2 кімн", []),
        ("18 000 грн", []),
        ("0123456789", []),  # operator code must start with 3-9
    ],
)
def test_extract_phones(text, expected):
    assert extract_phones(text) == expected


def test_extract_contacts_merges_usernames_and_author():
    got = extract_contacts("пишіть @Owner_Lviv або +380671234567", [Contact("tg_user_id", "42")])
    assert Contact("tg_username", "owner_lviv") in got
    assert Contact("tg_user_id", "42") in got
    assert Contact("phone", "+380671234567") in got
    assert len(got) == 3


def test_extract_contacts_ignores_emails_and_short_handles():
    assert extract_contacts("mail me a@gmail.com or @abc", []) == []
