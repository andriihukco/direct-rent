"""Regression tests for final-review findings C1 (extraction part), I7, I9, I10."""
import pytest

from directrent.antibroker.rules import classify_rules
from directrent.bot.budget import parse_budget
from directrent.models import Contact, Verdict
from directrent.normalize.fields import parse_price
from directrent.normalize.phones import extract_contacts


# I9
def test_vlasnym_is_not_an_owner_phrase():
    assert classify_rules("Квартира з власним опаленням") is None


@pytest.mark.parametrize("text", ["Агентствам не турбувати", "без агентств", "Агенціям прохання не дзвонити",
                                  "Рієлтори, не турбуйте!"])
def test_agency_negations_are_owner_phrases(text):
    assert classify_rules(text).verdict == Verdict.PASS


def test_rieltor_with_e_cyrillic():
    assert classify_rules("без риэлторов").verdict == Verdict.PASS


# I10
def test_price_takes_earliest_amount_not_deposit():
    assert parse_price("15 000 грн + комунальні 3000 грн, депозит 500$", 41.5) == (15000, "15 000 грн")


def test_price_skips_deposit_first():
    assert parse_price("депозит 20000 грн, оренда 15000 грн", 41.5)[0] == 15000


# I7
@pytest.mark.parametrize("text,expected", [
    ("будь-який", (None, None)), ("Будь-який", (None, None)), ("від 10000 до 18000", (10000, 18000)),
    ("18 тис", (None, 18000)), ("18к", (None, 18000)), ("10-18 тис", (10000, 18000)),
])
def test_budget_more_forms(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize("text", ["10-18", "до 18", "10000 18000", "до 99999999999", "0"])
def test_budget_out_of_range_rejected(text):
    with pytest.raises(ValueError):
        parse_budget(text)


# C1 (extraction)
def test_channel_own_handle_and_bots_ignored():
    got = extract_contacts("Підписуйтесь @lviv_rent, подати оголошення @lviv_rent_bot, пишіть @owner_ann",
                           [], ignore={"lviv_rent"})
    assert got == [Contact("tg_username", "owner_ann")]
