"""Inline keyboards for the filter form and the profile screen."""
from aiogram.types import InlineKeyboardButton as Btn
from aiogram.types import InlineKeyboardMarkup

from directrent.models import DISTRICTS

ROOM_LABELS = {1: "1", 2: "2", 3: "3+"}


def _mark(on: bool, text: str) -> str:
    return f"✅ {text}" if on else text


def districts_kb(selected: set[str]) -> InlineKeyboardMarkup:
    buttons = [Btn(text=_mark(d in selected, d), callback_data=f"d:{i}") for i, d in enumerate(DISTRICTS)]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Btn(text=_mark(not selected, "Будь-який"), callback_data="d:any"),
                 Btn(text="Далі ➡️", callback_data="d:next")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rooms_kb(selected: set[int]) -> InlineKeyboardMarkup:
    row = [Btn(text=_mark(r in selected, label), callback_data=f"r:{r}") for r, label in ROOM_LABELS.items()]
    return InlineKeyboardMarkup(inline_keyboard=[row, [Btn(text="Далі ➡️", callback_data="r:next")]])


def pets_kb(required: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text=f"🐾 Потрібно з тваринами: {'так' if required else 'ні'}", callback_data="p:toggle")],
        [Btn(text="Зберегти ✅", callback_data="p:save")],
    ])


def profile_kb(paused: bool) -> InlineKeyboardMarkup:
    pause = Btn(text="▶️ Відновити", callback_data="prof:resume") if paused else \
        Btn(text="⏸ Пауза", callback_data="prof:pause")
    return InlineKeyboardMarkup(inline_keyboard=[
        [pause, Btn(text="✏️ Змінити фільтр", callback_data="prof:edit")],
        [Btn(text="🗑 Видалити мої дані", callback_data="prof:delete")],
    ])


def confirm_delete_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        Btn(text="Так, видалити", callback_data="prof:delete_yes"),
        Btn(text="Скасувати", callback_data="prof:delete_no"),
    ]])
