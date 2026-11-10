from datetime import UTC, datetime, timedelta

from directrent.bot.cards import CardData, card_keyboard, render_caption

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def card(**kw) -> CardData:
    base = dict(rooms=2, district="Франківський", street="Наукова", price_raw="16 000 грн", price_uah=16000,
                pets="yes", phones=["+380670000001"], text="Здам власну квартиру. Без комісії!",
                posted_at=NOW - timedelta(minutes=1), source_label="Telegram: Оренда Львів",
                url="https://t.me/ch/1", object_id=7, unverified=False)
    base.update(kw)
    return CardData(**base)


def test_full_card_golden():
    assert render_caption(card(), NOW) == (
        "🏠 2-кімнатна квартира\n"
        "📍 Франківський (вул. Наукова)\n"
        "💰 16 000 грн / міс\n"
        "🐾 Тварини: дозволено\n"
        "📞 +380670000001\n"
        "📝 Здам власну квартиру. Без комісії!\n"
        "⏰ 1 хв тому · Telegram: Оренда Львів"
    )


def test_unknowns_and_unverified():
    c = render_caption(card(rooms=None, district=None, street=None, price_uah=None, price_raw=None, pets="unknown",
                            phones=[], unverified=True, posted_at=NOW - timedelta(seconds=20)), NOW)
    lines = c.split("\n")
    assert lines[0] == "⚠️ не перевірено"
    assert "🏠 Квартира" in lines and "📍 не вказано" in lines and "💰 не вказано" in lines
    assert "🐾 Тварини: не вказано" in lines
    assert not any(line.startswith("📞") for line in lines)
    assert lines[-1].startswith("⏰ щойно")


def test_three_plus_rooms_pets_no_hours_and_usd():
    c = render_caption(card(rooms=3, pets="no", price_raw="$400", price_uah=16600,
                            posted_at=NOW - timedelta(hours=2, minutes=5)), NOW)
    assert "🏠 3+ кімнатна квартира" in c
    assert "🐾 Тварини: заборонено" in c
    assert "💰 $400 (≈16 600 грн) / міс" in c
    assert "⏰ 2 год тому" in c


def test_long_description_is_cut_to_fit():
    c = render_caption(card(text="Дуже " * 600), NOW)
    assert len(c) <= 1024
    assert c.endswith("⏰ 1 хв тому · Telegram: Оренда Львів")
    assert "…" in c


def test_html_is_escaped():
    assert "&lt;b&gt;x&lt;/b&gt;" in render_caption(card(text="<b>x</b>"), NOW)


def test_keyboard():
    kb = card_keyboard(card())
    orig, broker = kb.inline_keyboard[0]
    assert (orig.text, orig.url) == ("🔗 Оригінал", "https://t.me/ch/1")
    assert (broker.text, broker.callback_data) == ("🚩 Це рієлтор", "broker:7")
