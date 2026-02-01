import asyncio
import json
import os

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv

# ------------------ CONFIG ------------------

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = list(map(int, os.getenv("ADMINS").split(",")))

DATA_FILE = "keywords.json"

# ------------------ STORAGE ------------------

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)


def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ------------------ FSM ------------------

class KeywordFSM(StatesGroup):
    waiting_text = State()
    waiting_photo = State()
    waiting_button = State()


# ------------------ KEYBOARDS ------------------

def keyword_panel(key: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Мәтін", callback_data=f"text:{key}")],
            [InlineKeyboardButton(text="🖼 Фото", callback_data=f"photo:{key}")],
            [InlineKeyboardButton(text="🔘 Батырма", callback_data=f"button:{key}")],
            [InlineKeyboardButton(text="❌ Өшіру", callback_data=f"delete:{key}")],
        ]
    )


# ------------------ ROUTER ------------------

router = Router()


def is_admin(user_id: int):
    return user_id in ADMINS


# ------------------ COMMANDS ------------------

@router.message(Command("add"))
async def add_keyword(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("❗ /add кілтсөз")
        return

    key = parts[1].lower()
    data = load_data()

    if key not in data:
        data[key] = {
            "text": None,
            "photo": None,
            "button": None
        }
        save_data(data)

    await message.reply(
        f"🔧 «{key}» кілтсөзі",
        reply_markup=keyword_panel(key)
    )


@router.message(Command("keywords"))
async def list_keywords(message: Message):
    if not is_admin(message.from_user.id):
        return

    data = load_data()

    if not data:
        await message.reply("📭 Кілтсөздер әлі жоқ")
        return

    lines = ["📚 <b>Кілтсөздер тізімі:</b>\n"]

    for key, cfg in data.items():
        status = []
        if cfg.get("text"):
            status.append("✍️")
        if cfg.get("photo"):
            status.append("🖼")
        if cfg.get("button"):
            status.append("🔘")

        marks = " ".join(status) if status else "⚠️ бос"
        lines.append(f"• <code>{key}</code> — {marks}")

    await message.reply(
        "\n".join(lines),
        parse_mode="HTML"
    )


# ------------------ CALLBACKS ------------------

@router.callback_query(F.data.startswith(("text:", "photo:", "button:", "delete:")))
async def keyword_actions(call: CallbackQuery, state: FSMContext):
    action, key = call.data.split(":", 1)
    data = load_data()

    if key not in data:
        await call.answer("Жоқ")
        return

    await state.update_data(key=key)

    if action == "text":
        await state.set_state(KeywordFSM.waiting_text)
        await call.message.reply("✍️ Мәтінді жібер")
    elif action == "photo":
        await state.set_state(KeywordFSM.waiting_photo)
        await call.message.reply("🖼 Фото жібер (немесе file_id)")
    elif action == "button":
        await state.set_state(KeywordFSM.waiting_button)
        await call.message.reply("🔘 Батырма форматы:\nМәтін | https://url")
    elif action == "delete":
        del data[key]
        save_data(data)
        await call.message.reply(f"❌ «{key}» өшірілді")

    await call.answer()


# ------------------ FSM INPUT ------------------

@router.message(KeywordFSM.waiting_text)
async def set_text(message: Message, state: FSMContext):
    data = load_data()
    st = await state.get_data()
    key = st["key"]

    data[key]["text"] = message.text
    save_data(data)

    await message.reply("✅ Мәтін сақталды")
    await state.clear()


@router.message(KeywordFSM.waiting_photo)
async def set_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.reply("❗ Фото жібер")
        return

    data = load_data()
    st = await state.get_data()
    key = st["key"]

    data[key]["photo"] = message.photo[-1].file_id
    save_data(data)

    await message.reply("✅ Фото сақталды")
    await state.clear()


@router.message(KeywordFSM.waiting_button)
async def set_button(message: Message, state: FSMContext):
    if "|" not in message.text:
        await message.reply("❗ Формат: Мәтін | https://url")
        return

    text, url = map(str.strip, message.text.split("|", 1))

    data = load_data()
    st = await state.get_data()
    key = st["key"]

    data[key]["button"] = {"text": text, "url": url}
    save_data(data)

    await message.reply("✅ Батырма сақталды")
    await state.clear()


# ------------------ LISTENER (TOP) ------------------

@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def keyword_listener(message: Message):
    if not message.text:
        return

    data = load_data()
    text = message.text.lower()

    for key, cfg in data.items():
        if key in text:
            kb = None
            if cfg["button"]:
                kb = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(
                            text=cfg["button"]["text"],
                            url=cfg["button"]["url"]
                        )]
                    ]
                )

            if cfg["photo"]:
                await message.reply_photo(
                    photo=cfg["photo"],
                    caption=cfg["text"],
                    reply_markup=kb
                )
            else:
                await message.reply(
                    cfg["text"],
                    reply_markup=kb
                )
            break


# ------------------ START ------------------

async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
