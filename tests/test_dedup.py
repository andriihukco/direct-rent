import io

from PIL import Image

from directrent.dedup import find_or_create_object, photo_hash, seen
from directrent.models import Contact
from directrent.store import save_listing
from tests.factories import PASS, make_listing

H = 0x0F0F_0F0F_0F0F_0F0F


async def _store(conn, li):
    oid = await find_or_create_object(conn, li)
    await save_listing(conn, li, oid, PASS)
    return oid


def test_photo_hash_rejects_garbage():
    assert photo_hash(b"not an image") is None


def test_photo_hash_fits_signed_bigint():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 10, 10)).save(buf, "PNG")
    h = photo_hash(buf.getvalue())
    assert isinstance(h, int) and -(2**63) <= h < 2**63


async def test_same_contact_close_photo_hash_same_object(db):
    async with db.acquire() as c:
        a = await _store(c, make_listing(photo_hash=H, price_uah=10000))
        b = await find_or_create_object(c, make_listing(photo_hash=H ^ 0b111, price_uah=30000))
        assert a == b


async def test_same_contact_far_hash_but_close_price_same_object(db):
    async with db.acquire() as c:
        a = await _store(c, make_listing(photo_hash=H, price_uah=16000))
        b = await find_or_create_object(c, make_listing(photo_hash=H ^ 0xFFFFF, price_uah=16500))
        assert a == b


async def test_same_contact_different_rooms_new_object(db):
    async with db.acquire() as c:
        a = await _store(c, make_listing(rooms=1))
        b = await find_or_create_object(c, make_listing(rooms=3))
        assert a != b


async def test_no_shared_contact_new_object(db):
    async with db.acquire() as c:
        a = await _store(c, make_listing(photo_hash=H))
        b = await find_or_create_object(c, make_listing(photo_hash=H, contacts=[Contact("phone", "+380930000009")]))
        assert a != b


async def test_shared_contact_older_than_30_days_new_object(db):
    async with db.acquire() as c:
        a = await _store(c, make_listing(photo_hash=H))
        await c.execute("UPDATE listings SET ingested_at = now() - interval '31 days'")
        b = await find_or_create_object(c, make_listing(photo_hash=H))
        assert a != b


async def test_seen_after_save(db):
    async with db.acquire() as c:
        li = make_listing()
        assert not await seen(c, li.source, li.source_id)
        await _store(c, li)
        assert await seen(c, li.source, li.source_id)


async def test_save_listing_links_contacts_once(db):
    async with db.acquire() as c:
        await _store(c, make_listing())
        await _store(c, make_listing())
        assert await c.fetchval("SELECT count(*) FROM contacts") == 1
        assert await c.fetchval("SELECT count(*) FROM listing_contacts") == 2
