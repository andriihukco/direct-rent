import pytest

from directrent.antibroker.rules import classify_rules
from directrent.models import Verdict


@pytest.mark.parametrize(
    "text,verdict",
    [
        ("Здам квартиру без комісії, власник", Verdict.PASS),
        ("Комісія 50%", Verdict.REJECT),
        ("Агентство нерухомості пропонує", Verdict.REJECT),
        ("Ріелторам не турбувати", Verdict.PASS),
        ("Без рієлторів. Послуги 30%", Verdict.REJECT),
        ("Співпраця з агентствами можлива", None),
        ("Здам 2к квартиру, Сихів", None),
        ("👍 https://t.me/x", Verdict.REJECT),
        ("Сдам квартиру, без комиссии, собственник", Verdict.PASS),
        ("Комиссия 50% риелтор", Verdict.REJECT),
    ],
)
def test_classify_rules(text, verdict):
    d = classify_rules(text)
    assert (d.verdict if d else None) == verdict
    if d:
        assert d.stage == "rules"


def test_reasons():
    assert classify_rules("Комісія 50%").reason.startswith("stopword:")
    assert classify_rules("власник").reason.startswith("owner:")
    assert classify_rules("👍 https://t.me/x").reason == "empty"
