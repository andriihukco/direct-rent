"""Parse a monthly budget typed by the user.

Accepts '10000-18000', '10 000 - 18 000 грн', 'до 18000', 'від 10000', 'від 10000 до 18000', '-18000',
'18 тис' / '18к', '10-18 тис', and 'будь-який' (no limit). Values must be plausible monthly rents.
"""
import re

BUDGET_MIN, BUDGET_MAX = 1000, 500000
ANY_WORDS = {"будь-який", "будь який", "будьякий", "any", "любой", "без обмежень", "неважливо", "байдуже"}

_DASH = r"[-–—]"
_JOIN_DIGITS = re.compile(r"(?<=\d)[\s  ](?=\d)")
_NOISE = re.compile(r"грн\.?|₴|uah|гривень|/\s*міс\w*|в\s+міс\w*|на\s+міс\w*", re.IGNORECASE)
_THOUSANDS = re.compile(r"(?<=\d)\s*(?:тис\w*\.?|тыс\w*\.?|[кk])(?![а-яіїєa-z])", re.IGNORECASE)


def _num(s: str | None, mult: int) -> int | None:
    if not s:
        return None
    return int(s) * mult or None


def parse_budget(text: str) -> tuple[int | None, int | None]:
    t = text.strip().lower()
    if t in ANY_WORDS:
        return None, None
    t = _NOISE.sub(" ", _JOIN_DIGITS.sub("", t))
    mult = 1000 if _THOUSANDS.search(t) else 1
    t = _THOUSANDS.sub("", t).strip()
    if m := re.fullmatch(r"(?:від|от)\s*(\d+)\s*(?:до|по)\s*(\d+)", t):
        lo, hi = m.group(1), m.group(2)
    elif m := re.fullmatch(r"до\s*(\d+)", t):
        lo, hi = None, m.group(1)
    elif m := re.fullmatch(r"(?:від|от)\s*(\d+)", t):
        lo, hi = m.group(1), None
    elif m := re.fullmatch(rf"(\d*)\s*{_DASH}\s*(\d*)", t):
        lo, hi = m.group(1), m.group(2)
    elif m := re.fullmatch(r"(\d+)", t):
        lo, hi = None, m.group(1)
    else:
        raise ValueError(f"cannot parse budget: {text!r}")
    lo_v, hi_v = _num(lo, mult), _num(hi, mult)
    if lo_v is None and hi_v is None:
        raise ValueError("empty budget")
    for v in (lo_v, hi_v):
        if v is not None and not BUDGET_MIN <= v <= BUDGET_MAX:
            raise ValueError(f"implausible budget: {v}")
    if lo_v is not None and hi_v is not None and lo_v > hi_v:
        lo_v, hi_v = hi_v, lo_v
    return lo_v, hi_v
