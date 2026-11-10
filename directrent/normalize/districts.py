"""Lviv district names and a neighbourhood → district map (lowercase regex stems)."""
import re

_L = "а-яіїєґa-z"  # letters that must not precede a stem (word-start boundary)

EXPLICIT: dict[str, str] = {
    r"(?<!івано-)(?<!ивано-)франк[іо]вськ|франковск": "Франківський",
    r"сихівськ|сиховск|сыховск": "Сихівський",
    r"галицьк|галицк": "Галицький",
    r"личаківськ|личаковск|лычаковск": "Личаківський",
    r"залізничн|железнодорожн": "Залізничний",
    r"шевченківськ|шевченковск": "Шевченківський",
    r"приміськ|пригород": "Приміські",
}

NEIGHBOURHOODS: dict[str, str] = {
    r"сих[іо]в|сыхов": "Сихівський",
    r"левандів|левандов|рясн|білогорщ|белогорщ": "Залізничний",
    r"кастелів|науков|стрийськ|стрыйск": "Франківський",
    r"брюхович|винник|сокільник|сокольник|рудн": "Приміські",
    r"погулянк|личак[іо]в|лычаков": "Личаківський",
    r"замарстин|голоск|підзамч|подзамч": "Шевченківський",
    r"центр[іу]? міста|в центрі|центр львова|площ[аі] ринок|пл\. ринок|центр города": "Галицький",
}


def _compile(table: dict[str, str]) -> list[tuple[re.Pattern[str], str]]:
    return [(re.compile(rf"(?<![{_L}])(?:{stem})"), d) for stem, d in table.items()]


EXPLICIT_RE = _compile(EXPLICIT)
NEIGHBOURHOOD_RE = _compile(NEIGHBOURHOODS)
