"""Auto-join of source channels, and rejecting posts from people looking for a flat."""
import asyncio
from types import SimpleNamespace

import pytest

from directrent.antibroker.rules import pre_screen
from directrent.models import Verdict
from directrent.sources.telegram import TelegramSource
from tests.test_review_fixes_runtime import FakeClient


class JoinClient(FakeClient):
    def __init__(self, left):
        super().__init__()
        self.left = left

    async def get_entity(self, name):
        return SimpleNamespace(id=5, username=name, title="T", left=self.left)

    async def __call__(self, request):
        self.log.append(type(request).__name__)


async def test_joins_channel_it_is_not_in(db):
    client = JoinClient(left=True)
    await TelegramSource(client, ["lviv_rent"], asyncio.Queue(), db).run()
    assert client.log == ["JoinChannelRequest", "handler", "handler", "backfill", "run"]


async def test_does_not_rejoin(db):
    client = JoinClient(left=False)
    await TelegramSource(client, ["lviv_rent"], asyncio.Queue(), db).run()
    assert "JoinChannelRequest" not in client.log


@pytest.mark.parametrize("text", [
    "Оренда: Шукаємо 1.5–2 кімнатну квартиру в ЖК (до $1000). Контакти: @tenant_x",
    "Шукаю 1к квартиру на Сихові до 12000 грн",
    "Сниму квартиру на Сихове, до 15000",
    "Зніму 2-кімнатну квартиру на тривалий термін",
    "Ищем квартиру для семьи, бюджет до 800$",
])
def test_wanted_posts_rejected(text):
    d = pre_screen(text, has_price=True, has_rooms=True, has_photo=False)
    assert (d.verdict, d.reason) == (Verdict.REJECT, "wanted")


@pytest.mark.parametrize("text", [
    "Шукаю орендарів на 2к квартиру, 15000 грн",
    "Здам 2к квартиру, шукаємо охайних орендарів без тварин",
    "Сдам квартиру, ищу порядочных жильцов",
    "Здається 1-кімнатна квартира, вул. Стрийська, 12000 грн",
])
def test_owner_offers_not_rejected_as_wanted(text):
    assert pre_screen(text, has_price=True, has_rooms=True, has_photo=False) is None
