from datetime import UTC, datetime
from types import SimpleNamespace

from telethon.tl.types import PeerChannel, PeerUser

from directrent.models import Contact, RawPost
from directrent.sources.telegram import album_to_raw, mark_processed, message_to_raw

D = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def msg(id=10, text="Здам 2к", from_id=None, username=None, grouped_id=None):
    sender = SimpleNamespace(username=username) if username else None
    return SimpleNamespace(id=id, date=D, message=text, from_id=from_id, sender=sender, grouped_id=grouped_id)


def test_message_from_user_in_chat():
    raw = message_to_raw(msg(from_id=PeerUser(42), username="Owner"), "lviv_rent", "Оренда", b"img")
    assert raw.source == "telegram" and raw.source_id == "lviv_rent:10"
    assert raw.url == "https://t.me/lviv_rent/10" and raw.posted_at == D and raw.photo_bytes == b"img"
    assert Contact("tg_user_id", "42") in raw.author_contacts
    assert Contact("tg_username", "owner") in raw.author_contacts


def test_channel_post_has_no_author_contacts():
    assert message_to_raw(msg(from_id=None), "lviv_rent", "Оренда", None).author_contacts == []
    assert message_to_raw(msg(from_id=PeerChannel(5)), "lviv_rent", "Оренда", None).author_contacts == []


def test_album_uses_first_caption_and_first_message_id():
    msgs = [msg(id=20, text=""), msg(id=21, text="Здам 1к, власник"), msg(id=22, text="")]
    raw = album_to_raw(msgs, "lviv_rent", "Оренда", b"p")
    assert raw.text == "Здам 1к, власник" and raw.source_id == "lviv_rent:20" and raw.photo_bytes == b"p"


async def test_mark_processed_keeps_highest_id(db):
    for n in (5, 9, 7):
        await mark_processed(db, RawPost("telegram", f"lviv_rent:{n}", "u", "t", D, "Оренда"))
    assert await db.fetchval("SELECT value FROM source_state WHERE source='telegram' AND key='lviv_rent'") == "9"


def test_chat_key_resolves_marked_channel_ids():
    from directrent.sources.telegram import chat_key
    assert chat_key(-1001234567890) == 1234567890
    assert chat_key(-1002147483648) == 2147483648
    assert chat_key(-4242) == 4242  # basic group
