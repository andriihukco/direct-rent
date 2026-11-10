"""User-facing bot flows: /start, /filters, /my_profile, and the 'broker' complaint button."""
import asyncpg
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from directrent.antibroker.reputation import record_complaint
from directrent.bot import repo
from directrent.bot.budget import parse_budget
from directrent.bot.cards import BROKER_CB_PREFIX
from directrent.bot.keyboards import ROOM_LABELS, confirm_delete_kb, districts_kb, pets_kb, profile_kb, rooms_kb
from directrent.models import DISTRICTS, Filter

GREETING = ("Привіт! Я надсилаю нові оголошення про оренду квартир у Львові — тільки від власників, "
            "без рієлторів і комісії.\n\nНалаштуймо фільтр.")
ASK_DISTRICTS = "Оберіть райони (можна кілька) і натисніть «Далі»:"
ASK_BUDGET = "Бюджет на місяць у гривнях. Наприклад: 10000-18000, до 18000, від 10000 або «будь-який»:"
BAD_BUDGET = "Не зрозумів. Приклад: 10000-18000"
ASK_ROOMS = "Скільки кімнат? Можна кілька або жодної — тоді будь-яка кількість:"
ASK_PETS = "Вам потрібна квартира, де дозволені тварини?"
SAVED = "Готово! Надсилатиму нові оголошення, що підходять."
NO_FILTER = "Фільтр ще не налаштовано. Натисніть /filters"
COMPLAINT_THANKS = "Дякуємо, приховали це оголошення"
CONFIRM_DELETE = "Видалити всі ваші дані (фільтр та історію)? Це не можна скасувати."
DELETED = "Дані видалено. Щоб почати знову — /start"


class FilterForm(StatesGroup):
    districts = State()
    budget = State()
    rooms = State()
    pets = State()


def _money(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def summary(f: Filter, paused: bool) -> str:
    if f.price_min and f.price_max:
        budget = f"{_money(f.price_min)} – {_money(f.price_max)} грн"
    elif f.price_max:
        budget = f"до {_money(f.price_max)} грн"
    elif f.price_min:
        budget = f"від {_money(f.price_min)} грн"
    else:
        budget = "будь-який"
    rooms = ", ".join(ROOM_LABELS[r] for r in sorted(f.rooms)) or "будь-яка кількість"
    return (f"Ваш фільтр:\n📍 Райони: {', '.join(f.districts) or 'будь-який'}\n💰 Бюджет: {budget}\n"
            f"🏠 Кімнати: {rooms}\n🐾 З тваринами: {'так' if f.pets_required else 'не обовʼязково'}\n"
            f"Статус: {'на паузі' if paused else 'активний'}")


def build_router(pool: asyncpg.Pool) -> Router:
    router = Router(name="user")

    async def start_form(message: Message, state: FSMContext, user_id: int) -> None:
        async with pool.acquire() as c:
            existing = await repo.get_filter(c, user_id)
        await state.set_state(FilterForm.districts)
        await state.set_data({
            "districts": existing.districts if existing else [],
            "price_min": existing.price_min if existing else None,
            "price_max": existing.price_max if existing else None,
            "rooms": existing.rooms if existing else [],
            "pets_required": existing.pets_required if existing else False,
        })
        await message.answer(ASK_DISTRICTS, reply_markup=districts_kb(set(existing.districts if existing else [])))

    @router.message(CommandStart())
    async def on_start(message: Message, state: FSMContext) -> None:
        async with pool.acquire() as c:
            await repo.upsert_user(c, message.from_user.id, message.from_user.username)
            await repo.set_paused(c, message.from_user.id, False)  # e.g. after unblocking the bot
        await message.answer(GREETING)
        await start_form(message, state, message.from_user.id)

    @router.message(Command("filters"))
    async def on_filters(message: Message, state: FSMContext) -> None:
        async with pool.acquire() as c:
            await repo.upsert_user(c, message.from_user.id, message.from_user.username)
        await start_form(message, state, message.from_user.id)

    @router.callback_query(FilterForm.districts, F.data.startswith("d:"))
    async def on_district(cb: CallbackQuery, state: FSMContext) -> None:
        arg = cb.data[2:]
        data = await state.get_data()
        selected = set(data["districts"])
        if arg == "next":
            await state.set_state(FilterForm.budget)
            await cb.message.answer(ASK_BUDGET)
        else:
            if arg == "any":
                selected.clear()
            elif arg.isdigit() and int(arg) < len(DISTRICTS):
                selected ^= {DISTRICTS[int(arg)]}
            await state.update_data(districts=[d for d in DISTRICTS if d in selected])
            await cb.message.edit_reply_markup(reply_markup=districts_kb(selected))
        await cb.answer()

    @router.message(FilterForm.budget, F.text, ~F.text.startswith("/"))
    async def on_budget(message: Message, state: FSMContext) -> None:
        try:
            lo, hi = parse_budget(message.text)
        except ValueError:
            await message.answer(BAD_BUDGET)
            return
        await state.update_data(price_min=lo, price_max=hi)
        await state.set_state(FilterForm.rooms)
        data = await state.get_data()
        await message.answer(ASK_ROOMS, reply_markup=rooms_kb(set(data["rooms"])))

    @router.callback_query(FilterForm.rooms, F.data.startswith("r:"))
    async def on_rooms(cb: CallbackQuery, state: FSMContext) -> None:
        arg = cb.data[2:]
        data = await state.get_data()
        if arg == "next":
            await state.set_state(FilterForm.pets)
            await cb.message.answer(ASK_PETS, reply_markup=pets_kb(data["pets_required"]))
        elif arg.isdigit() and int(arg) in ROOM_LABELS:
            rooms = set(data["rooms"]) ^ {int(arg)}
            await state.update_data(rooms=sorted(rooms))
            await cb.message.edit_reply_markup(reply_markup=rooms_kb(rooms))
        await cb.answer()

    @router.callback_query(FilterForm.pets, F.data.in_({"p:toggle", "p:save"}))
    async def on_pets(cb: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if cb.data == "p:toggle":
            required = not data["pets_required"]
            await state.update_data(pets_required=required)
            await cb.message.edit_reply_markup(reply_markup=pets_kb(required))
            await cb.answer()
            return
        f = Filter(cb.from_user.id, data["districts"], data["price_min"], data["price_max"], data["rooms"],
                   data["pets_required"])
        async with pool.acquire() as c:
            await repo.upsert_user(c, cb.from_user.id, cb.from_user.username)
            await repo.save_filter(c, f)
            paused = await repo.is_paused(c, cb.from_user.id)
        await state.clear()
        await cb.message.answer(f"{SAVED}\n\n{summary(f, paused)}", reply_markup=profile_kb(paused))
        await cb.answer()

    @router.message(Command("my_profile"))
    async def on_profile(message: Message) -> None:
        async with pool.acquire() as c:
            f = await repo.get_filter(c, message.from_user.id)
            paused = await repo.is_paused(c, message.from_user.id)
        if f is None:
            await message.answer(NO_FILTER)
            return
        await message.answer(summary(f, paused), reply_markup=profile_kb(paused))

    @router.callback_query(F.data.startswith("prof:"))
    async def on_profile_action(cb: CallbackQuery, state: FSMContext) -> None:
        action, uid = cb.data[5:], cb.from_user.id
        async with pool.acquire() as c:
            if action in ("pause", "resume"):
                await repo.set_paused(c, uid, action == "pause")
                f = await repo.get_filter(c, uid)
                if f:
                    await cb.message.edit_text(summary(f, action == "pause"),
                                               reply_markup=profile_kb(action == "pause"))
            elif action == "delete":
                await cb.message.answer(CONFIRM_DELETE, reply_markup=confirm_delete_kb())
            elif action == "delete_yes":
                await repo.delete_user_data(c, uid)
                await state.clear()
                await cb.message.edit_text(DELETED)
            elif action == "delete_no":
                await cb.message.delete()
        if action == "edit":
            await start_form(cb.message, state, uid)
        await cb.answer()

    @router.callback_query(F.data.startswith(BROKER_CB_PREFIX))
    async def on_broker(cb: CallbackQuery) -> None:
        arg = cb.data[len(BROKER_CB_PREFIX):]
        if arg.isdigit():
            async with pool.acquire() as c:
                await repo.upsert_user(c, cb.from_user.id, cb.from_user.username)
                if await c.fetchval("SELECT EXISTS (SELECT 1 FROM objects WHERE id = $1)", int(arg)):
                    await record_complaint(c, cb.from_user.id, int(arg))
        await cb.answer(COMPLAINT_THANKS)

    return router
