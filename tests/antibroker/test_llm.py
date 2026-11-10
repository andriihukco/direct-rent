from types import SimpleNamespace

import pytest

from directrent.antibroker.llm import HaikuClassifier, LlmError
from tests.factories import make_listing

GOOD = {"is_owner": True, "confidence": 0.9, "reason": "owner wording", "district": "Сихівський",
        "rooms": 2, "price_uah": 15000, "pets": None}


class FakeMessages:
    def __init__(self, content):
        self.content, self.kwargs = content, None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(content=self.content, stop_reason="tool_use")


def _client(content):
    return SimpleNamespace(messages=FakeMessages(content))


async def test_parses_tool_use():
    client = _client([SimpleNamespace(type="tool_use", name="report_verdict", input=GOOD)])
    r = await HaikuClassifier(client).classify(make_listing())
    assert (r.is_owner, r.confidence, r.district, r.rooms, r.pets) == (True, 0.9, "Сихівський", 2, None)
    kw = client.messages.kwargs
    assert kw["tool_choice"] == {"type": "tool", "name": "report_verdict"}
    assert kw["model"] == "claude-haiku-5-5"
    assert "temperature" not in kw


async def test_text_only_response_raises():
    client = _client([SimpleNamespace(type="text", text="I think owner")])
    with pytest.raises(LlmError):
        await HaikuClassifier(client).classify(make_listing())


async def test_invalid_district_is_dropped_not_fatal():
    bad = dict(GOOD, district="Київ", rooms=7)
    client = _client([SimpleNamespace(type="tool_use", name="report_verdict", input=bad)])
    r = await HaikuClassifier(client).classify(make_listing())
    assert r.district is None and r.rooms == 3


async def test_missing_field_raises():
    client = _client([SimpleNamespace(type="tool_use", name="report_verdict", input={"is_owner": True})])
    with pytest.raises(LlmError):
        await HaikuClassifier(client).classify(make_listing())
