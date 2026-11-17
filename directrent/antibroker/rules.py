"""Stage 2: owner phrases, broker stop-words, ambiguous phrases (spec §8, steps 2a–2d)."""
import re

from directrent.models import Decision, Verdict

_I = re.IGNORECASE
_R = r"р[іи][еєэ]лтор"  # рієлтор / ріелтор / риелтор / риэлтор

# 2a. Cut these out first: several contain stop-word stems ("без комісії").
OWNER_PHRASES = [
    r"без\s+комісі\w*", r"без\s+комисси\w*", r"без\s+посередник\w*", r"без\s+посредник\w*",
    rf"без\s+(?:{_R}|агентств|агенці|агентів|агентов)\w*",
    rf"(?:{_R}|агентств|агенці|агентов)\w*,?\s+(?:прохання\s+|прошу\s+|просьба\s+)?не\s+(?:турбу|дзвон|звон|беспоко)\w*",
    r"власни[кц]\w*", r"від\s+господар\w*", r"собственни[кц]\w*", r"от\s+хозя\w*",
]
# 2d. Can mean either; cut out, and send the listing to the LLM unless a stop-word remains.
AMBIGUOUS_PHRASES = [rf"співпрац\w*(?:\s+\w+)?\s+з\s+(?:агентств|агенці|{_R})\w*", r"співпрац\w*", r"сотрудничеств\w*"]
# 2b. Any of these left after cutting means a broker.
STOPWORDS = [
    r"комісі\w*", r"комисси\w*", r"агентств\w*", r"агенці\w*", r"агентство\w*", r"агенство\w*",
    rf"{_R}\w*", r"посередни\w*", r"послуги\s*\d+\s?%", r"\d+\s?%\s*(?:від|от)\b",
]

_OWNER = [re.compile(p, _I) for p in OWNER_PHRASES]
_AMBIG = [re.compile(p, _I) for p in AMBIGUOUS_PHRASES]
_STOP = [re.compile(p, _I) for p in STOPWORDS]
_URL = re.compile(r"https?://\S+|t\.me/\S+|www\.\S+", _I)
_LETTER = re.compile(r"[^\W\d_]")
MIN_LETTERS = 3


_RENTAL = re.compile(r"здам|зда[єю]т|здаєть|оренд|аренд|сда[мюёе]|сдаёт|квартир|кімнат|комнат|житл|будин|дом\b", _I)
EMPTY = Decision(Verdict.REJECT, "rules", "empty")
NOT_LISTING = Decision(Verdict.REJECT, "rules", "not_listing")
WANTED = Decision(Verdict.REJECT, "rules", "wanted")

# Someone looking for a flat, not offering one. "Шукаю орендарів" (looking for tenants) is an owner,
# so a search verb followed by a tenant word does not count, and neither does any post that offers a flat.
_SEEKING = re.compile(
    r"(?<![а-яіїєґ])(?:шука[юєєм]\w*|ищ[уеё]\w*|сниму|снимем|зніму|знімемо|винайм\w*|орендую|орендуємо)"
    r"(?!\s+(?:\w+\s+)?(?:орендар|квартирант|наймач|жильц|жильц|арендатор|порядн))", _I)
_OFFERING = re.compile(r"(?<![а-яіїєґ])(?:здам|здаю|здаємо|здає\w*|сдам|сдаю|сдаём|сдаем|сда[её]тся|пропону\w*)", _I)


def is_empty(text: str) -> bool:
    return len(_LETTER.findall(_URL.sub(" ", text))) < MIN_LETTERS


def pre_screen(text: str, has_price: bool, has_rooms: bool, has_photo: bool) -> Decision | None:
    """Drop chatter and 'looking for a flat' posts before they create an object or reach the LLM."""
    if is_empty(text):
        return EMPTY
    if _SEEKING.search(text) and not _OFFERING.search(text):
        return WANTED
    if not (has_price or has_rooms or has_photo or _RENTAL.search(text)):
        return NOT_LISTING
    return None


def classify_rules(text: str) -> Decision | None:
    rest = _URL.sub(" ", text)
    if is_empty(text):
        return EMPTY

    owner_hit: str | None = None
    for p in _OWNER:
        if m := p.search(rest):
            owner_hit = owner_hit or m.group(0).lower()
            rest = p.sub(" ", rest)

    ambiguous = False
    for p in _AMBIG:
        if p.search(rest):
            ambiguous = True
            rest = p.sub(" ", rest)

    for p in _STOP:
        if m := p.search(rest):
            return Decision(Verdict.REJECT, "rules", f"stopword:{m.group(0).lower()}")
    if ambiguous:
        return None
    if owner_hit:
        return Decision(Verdict.PASS, "rules", f"owner:{owner_hit}")
    return None
