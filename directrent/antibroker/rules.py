"""Stage 2: owner phrases, broker stop-words, ambiguous phrases (spec §8, steps 2a–2d)."""
import re

from directrent.models import Decision, Verdict

_I = re.IGNORECASE
_R = r"р[іи][еєе]лтор"  # рієлтор / ріелтор / риелтор / риэлтор-ish spellings

# 2a. Cut these out first: several contain stop-word stems ("без комісії").
OWNER_PHRASES = [
    r"без\s+комісі\w*", r"без\s+комисси\w*", r"без\s+посередник\w*", r"без\s+посредник\w*",
    rf"без\s+{_R}\w*", rf"{_R}\w*\s+(?:прошу\s+)?не\s+(?:турбувати|беспокоить|дзвонити|звонить)",
    r"власни\w*", r"від\s+господар\w*", r"собственни\w*", r"от\s+хозя\w*",
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


def classify_rules(text: str) -> Decision | None:
    rest = _URL.sub(" ", text)
    if len(_LETTER.findall(rest)) < MIN_LETTERS:
        return Decision(Verdict.REJECT, "rules", "empty")

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
