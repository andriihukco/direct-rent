"""Regex extraction of price, rooms, pets, district and street from listing text."""
import re

from directrent.models import Pets
from directrent.normalize.districts import EXPLICIT_RE, NEIGHBOURHOOD_RE

PRICE_MIN_UAH, PRICE_MAX_UAH = 3000, 200000

_NUM = r"\d{1,3}(?:[   ]\d{3})+|\d+"
_I = re.IGNORECASE
_USD = re.compile(rf"\$\s*(?P<n>{_NUM})|(?P<m>{_NUM})\s*(?:\$|usd\b|дол)", _I)
_UAH = re.compile(rf"(?P<n>{_NUM})\s*(?:грн|₴|uah\b|гривень)", _I)
_THOUSANDS = re.compile(r"(?P<n>\d+(?:[.,]\d+)?)\s*тис", _I)
_LABELLED = re.compile(rf"(?:ціна|вартість|цена|стоимость)\s*:?\s*(?P<n>{_NUM})(?!\s*(?:\$|usd|дол))", _I)


def _int(s: str) -> int:
    return int(re.sub(r"\D", "", s))


def parse_price(text: str, usd_rate: float) -> tuple[int | None, str | None]:
    """Monthly rent in UAH and the raw matched text, or (None, None)."""
    candidates: list[tuple[re.Pattern[str], float]] = [(_USD, usd_rate), (_UAH, 1), (_THOUSANDS, 1000), (_LABELLED, 1)]
    for pattern, mult in candidates:
        for m in pattern.finditer(text):
            num = m.group("n") or m.groupdict().get("m")
            if pattern is _THOUSANDS:
                value = round(float(num.replace(",", ".")) * mult)
            else:
                value = round(_int(num) * mult)
            if PRICE_MIN_UAH <= value <= PRICE_MAX_UAH:
                return value, m.group(0).strip()
    return None, None


_ROOMS_DIGIT = re.compile(r"(?<!\d)([1-9])\s*(?:-\s*)?(?:х\s*)?(?:кімн|кім\b|комн|к(?![а-яіїєґa-z])|room)", _I)
_ROOMS_WORD = [
    (re.compile(r"чотир\w*кімн|четыр\w*комн", _I), 3),
    (re.compile(r"тр[иь]\w*кімн|тр[её]х\w*комн|трикомн", _I), 3),
    (re.compile(r"дв[оу]х?\w*кімн|двух\w*комн|двокомн", _I), 2),
    (re.compile(r"одно\w*кімн|одно\w*комн|студі|студи|смарт", _I), 1),
]


def parse_rooms(text: str) -> int | None:
    """1, 2 or 3 (3 means 3+)."""
    if m := _ROOMS_DIGIT.search(text):
        return min(int(m.group(1)), 3)
    for pattern, rooms in _ROOMS_WORD:
        if pattern.search(text):
            return rooms
    return None


_PETS_NO = re.compile(
    r"без\s+(?:домашніх\s+|домашних\s+)?(?:тварин|животн|кот|собак)|(?:тварин|животн)\w*\s+не\b", _I
)
_PETS_YES = re.compile(
    r"з\s+(?:тварин|котом|собак)|pet[\s-]?friendly|тварини\s+(?:дозволен|можна)"
    r"|можна\s+з\s+(?:кот|кіш|собак|тварин|пес)|с\s+животн|можно\s+с\s+(?:кот|собак|живот)",
    _I,
)


def parse_pets(text: str) -> Pets:
    if _PETS_NO.search(text):
        return "no"
    if _PETS_YES.search(text):
        return "yes"
    return "unknown"


def parse_district(text: str) -> str | None:
    """Explicit district names win; otherwise the first neighbourhood mentioned."""
    low = text.lower()
    for pattern, district in EXPLICIT_RE:
        if pattern.search(low):
            return district
    hits = [(m.start(), d) for p, d in NEIGHBOURHOOD_RE if (m := p.search(low))]
    return min(hits)[1] if hits else None


_STREET = re.compile(
    r"(?:вул\.|вулиця|вул\s|просп\.|проспект|ул\.|улица)\s*"
    r"((?:[А-ЯІЇЄҐA-Z]\.\s*)?[А-ЯІЇЄҐA-Z0-9][\w'’\-]*(?:\s+[А-ЯІЇЄҐA-Z][\w'’\-]*)*)"
)


def parse_street(text: str) -> str | None:
    if m := _STREET.search(text):
        return m.group(1).strip()[:40]
    return None
