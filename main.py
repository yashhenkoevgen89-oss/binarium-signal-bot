import os
import asyncio
from datetime import datetime

import pandas as pd
import numpy as np
import yfinance as yf

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

MODE = os.getenv("MODE", "DEMO")

AUTO_INTERVAL = int(
    os.getenv("AUTO_INTERVAL", "300")
)

# =========================
# TELEGRAM
# =========================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# =========================
# SIGNAL SETTINGS
# =========================

AUTO_SCAN_ENABLED = True

SIGNAL_PAIRS = [

    "EURUSD=X",
    "GBPUSD=X",
    "USDJPY=X",
    "AUDUSD=X",
    "USDCAD=X",
    "NZDUSD=X",
    "EURJPY=X",
    "GBPJPY=X"

]

# =========================
# KEYBOARD
# =========================

keyboard = ReplyKeyboardMarkup(
    keyboard=[

        [
            KeyboardButton(text="📊 Статус"),
            KeyboardButton(text="🔍 Сканер")
        ],

        [
            KeyboardButton(text="🏆 Лучшая"),
            KeyboardButton(text="🥇 Топ-3")
        ],

        [
            KeyboardButton(text="📈 Статистика"),
            KeyboardButton(text="📅 День")
        ],

        [
            KeyboardButton(text="🗓 Неделя"),
            KeyboardButton(text="📆 Месяц")
        ],

        [
            KeyboardButton(text="🟢 Авто ВКЛ"),
            KeyboardButton(text="🔴 Авто ВЫКЛ")
        ]

    ],

    resize_keyboard=True
)

# =========================
# START
# =========================

@dp.message(Command("start"))
async def start_command(message: types.Message):

    await message.answer(

        "📈 Binarium Signal Bot\n\n"
        f"Режим: {MODE}\n"
        f"Автосканирование: {'🟢 ВКЛ' if AUTO_SCAN_ENABLED else '🔴 ВЫКЛ'}\n"
        f"Интервал: {AUTO_INTERVAL} сек.",

        reply_markup=keyboard

    )

# =========================
# MAIN
# =========================

async def main():

    await dp.start_polling(bot)

if __name__ == "__main__":

    asyncio.run(main())
