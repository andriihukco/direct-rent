"""Pull Ukrainian phone numbers and Telegram handles out of free text."""
import re

from directrent.models import Contact

# A run that starts with + or a digit, allows separators between digits, ends on a digit.
_RUN = re.compile(r"(?<![\w+])\+?\d[\d\s().\-]{7,20}\d(?!\d)")
_USERNAME = re.compile(r"(?<![\w@.])@([A-Za-z][A-Za-z0-9_]{4,31})\b")


def _to_e164(digits: str) -> str | None:
    if len(digits) == 12 and digits.startswith("380"):
        national = digits[3:]
    elif len(digits) == 11 and digits.startswith("80"):
        national = digits[2:]
    elif len(digits) == 10 and digits.startswith("0"):
        national = digits[1:]
    else:
        return None
    if national[0] not in "3456789":
        return None
    return "+380" + national


def extract_phones(text: str) -> list[str]:
    """Unique +380XXXXXXXXX numbers in order of first appearance."""
    out: list[str] = []
    for m in _RUN.finditer(text):
        phone = _to_e164(re.sub(r"\D", "", m.group()))
        if phone and phone not in out:
            out.append(phone)
    return out


def extract_contacts(text: str, author: list[Contact], ignore: frozenset[str] | set[str] = frozenset()
                     ) -> list[Contact]:
    """Phones and @usernames from the text plus the author's contacts, deduplicated.

    Handles in `ignore` (the channel's own username) and bot handles are channel signatures, not contacts.
    """
    found = [Contact("phone", p) for p in extract_phones(text)]
    found += [Contact("tg_username", u) for u in (h.lower() for h in _USERNAME.findall(text))
              if u not in ignore and not u.endswith("bot")]
    found += author
    return list(dict.fromkeys(found))
