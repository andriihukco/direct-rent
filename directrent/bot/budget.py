"""Parse a monthly budget typed by the user: '10000-18000', 'до 18000', 'від 10000', '-18000'."""
import re

_DASH = r"[-–—]"
_JOIN_DIGITS = re.compile(r"(?<=\d)[\s  ](?=\d)")
_NOISE = re.compile(r"грн\.?|₴|uah|гривень|/\s*міс\w*|в\s+міс\w*", re.IGNORECASE)


def _num(s: str | None) -> int | None:
    if s is None or s == "":
        return None
    n = int(s)
    return n or None


def parse_budget(text: str) -> tuple[int | None, int | None]:
    t = _NOISE.sub(" ", _JOIN_DIGITS.sub("", text.strip().lower())).strip()
    if m := re.fullmatch(r"(?:до|до\s*-)\s*(\d+)", t):
        lo, hi = None, _num(m.group(1))
    elif m := re.fullmatch(r"(?:від|от)\s*(\d+)", t):
        lo, hi = _num(m.group(1)), None
    elif m := re.fullmatch(rf"(\d*)\s*{_DASH}\s*(\d*)", t):
        lo, hi = _num(m.group(1)), _num(m.group(2))
    elif m := re.fullmatch(r"(\d+)", t):
        lo, hi = None, _num(m.group(1))
    else:
        raise ValueError(f"cannot parse budget: {text!r}")
    if lo is None and hi is None:
        raise ValueError("empty budget")
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    return lo, hi
