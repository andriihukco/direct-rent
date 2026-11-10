from datetime import UTC, datetime

import pytest

from directrent.models import Contact, RawPost
from directrent.normalize import normalize
from directrent.normalize.fields import parse_district, parse_pets, parse_price, parse_rooms, parse_street

R = 41.5


def test_price_uah():
    assert parse_price("16 000 грн/міс", R) == (16000, "16 000 грн")


def test_price_usd_prefix():
    assert parse_price("$400", R) == (16600, "$400")


def test_price_usd_suffix():
    assert parse_price("400$ + комуналка", R)[0] == 16600


def test_price_ignores_rooms_and_floors():
    assert parse_price("2 кімнати, 3 поверх", R) == (None, None)


@pytest.mark.parametrize("text", ["1500 грн", "300000 грн"])
def test_price_out_of_range(text):
    assert parse_price(text, R) == (None, None)


@pytest.mark.parametrize(
    "text,rooms",
    [("2-кімнатна", 2), ("двокімнатна", 2), ("2к", 2), ("4-кімн", 3), ("однокімнатна", 1),
     ("3 поверх", None), ("2-х кімнатна", 2), ("двухкомнатная", 2)],
)
def test_rooms(text, rooms):
    assert parse_rooms(text) == rooms


@pytest.mark.parametrize(
    "text,pets",
    [("без тварин", "no"), ("можна з котом", "yes"), ("pet friendly", "yes"), ("ремонт", "unknown"),
     ("тварини не розглядаємо", "no")],
)
def test_pets(text, pets):
    assert parse_pets(text) == pets


def test_district_from_neighbourhood():
    assert parse_district("Сихів, вул. Червоної Калини") == "Сихівський"


def test_district_explicit_wins():
    assert parse_district("Личаківський район, біля Сихова") == "Личаківський"


def test_district_not_fooled_by_shopping_centre():
    assert parse_district("поруч торговий центр") is None


def test_street():
    assert parse_street("квартира, вул. Наукова, 5 поверх") == "Наукова"


def test_normalize_builds_listing():
    raw = RawPost("telegram", "ch:1", "https://t.me/ch/1", "2к, Сихів, 15000 грн, 0670000002",
                  datetime(2026, 11, 10, tzinfo=UTC), "Ch", [Contact("tg_user_id", "5")])
    li = normalize(raw, R)
    assert (li.price_uah, li.rooms, li.district, li.pets) == (15000, 2, "Сихівський", "unknown")
    assert Contact("phone", "+380670000002") in li.contacts and Contact("tg_user_id", "5") in li.contacts
    assert li.photo_hash is None
