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

CHAT_ID = None

sent_signals = set()

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
# MARKET DATA
# =========================

def pretty_pair(symbol):
    return (
        symbol
        .replace("=X", "")
        .replace("USD", "USD/")
        .replace("EURUSD/", "EUR/USD")
        .replace("GBPUSD/", "GBP/USD")
        .replace("USD/JPY", "USD/JPY")
        .replace("AUDUSD/", "AUD/USD")
        .replace("USD/CAD", "USD/CAD")
        .replace("NZDUSD/", "NZD/USD")
        .replace("EURJPY", "EUR/JPY")
        .replace("GBPJPY", "GBP/JPY")
    )


def get_market_data(symbol, period="5d", interval="5m"):
    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True
        )

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()

        df.columns = [
            str(col).lower().replace(" ", "_")
            for col in df.columns
        ]

        return df

    except Exception:
        return pd.DataFrame()


def get_last_price(symbol):
    df = get_market_data(symbol)

    if df.empty or "close" not in df.columns:
        return 0.0

    try:
        return float(df["close"].iloc[-1])
    except Exception:
        return 0.0
# =========================
# INDICATORS
# =========================

from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator


def add_indicators(df):

    if df.empty:
        return df

    try:

        df["ema50"] = EMAIndicator(
            close=df["close"],
            window=50
        ).ema_indicator()

        df["ema200"] = EMAIndicator(
            close=df["close"],
            window=200
        ).ema_indicator()

        df["rsi"] = RSIIndicator(
            close=df["close"],
            window=14
        ).rsi()

        macd = MACD(
            close=df["close"]
        )

        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()

        adx = ADXIndicator(
            high=df["high"],
            low=df["low"],
            close=df["close"]
        )

        df["adx"] = adx.adx()

        return df

    except Exception as e:

        print(
            f"Indicator error: {e}"
        )

        return df

# =========================
# SIGNAL ENGINE
# =========================

def analyze_pair(symbol):

    df = get_market_data(symbol)

    if df.empty:
        return None

    df = add_indicators(df)

    if len(df) < 210:
        return None

    last = df.iloc[-1]

    try:

        ema50 = float(last["ema50"])
        ema200 = float(last["ema200"])

        rsi = float(last["rsi"])

        macd = float(last["macd"])
        macd_signal = float(last["macd_signal"])

        adx = float(last["adx"])

    except:
        return None

    score = 0

    # ========= CALL =========

    if ema50 > ema200:
        score += 1

    if macd > macd_signal:
        score += 1

    if 45 <= rsi <= 70:
        score += 1

    if adx > 20:
        score += 1

    if score >= 4:

        return {
            "symbol": symbol,
            "signal": "CALL",
            "score": score,
            "rsi": round(rsi, 1),
            "adx": round(adx, 1)
        }

    # ========= PUT =========

    score = 0

    if ema50 < ema200:
        score += 1

    if macd < macd_signal:
        score += 1

    if 30 <= rsi <= 55:
        score += 1

    if adx > 20:
        score += 1

    if score >= 4:

        return {
            "symbol": symbol,
            "signal": "PUT",
            "score": score,
            "rsi": round(rsi, 1),
            "adx": round(adx, 1)
        }

    return None
# =========================
# SIGNAL STRENGTH
# =========================

def build_signal_message(signal_data):

    if signal_data is None:

        return (
            "⚪ Сигнал не найден"
        )

    signal = signal_data["signal"]

    symbol = (
        signal_data["symbol"]
        .replace("=X", "")
    )

    rsi = signal_data["rsi"]
    adx = signal_data["adx"]

    strength = signal_data["score"] * 25

    emoji = (
        "🟢"
        if signal == "CALL"
        else "🔴"
    )

    arrow = (
        "CALL"
        if signal == "CALL"
        else "PUT"
    )

    message = (

        f"{emoji} {arrow}\n\n"

        f"Пара:\n"
        f"{symbol}\n\n"

        f"Сила сигнала:\n"
        f"{strength}%\n\n"

        f"RSI: {rsi}\n"
        f"ADX: {adx}\n\n"

        f"Экспирация:\n"
        f"5 минут"

    )

    return message
# =========================
# SCANNER
# =========================

def scan_market():

    signals = []

    for symbol in SIGNAL_PAIRS:

        try:

            signal_data = analyze_pair(symbol)

            if signal_data:

                signals.append(signal_data)

        except Exception as e:

            print(
                f"Scan error {symbol}: {e}"
            )

    return signals
# =========================
# AUTO SCANNER
# =========================

async def auto_scanner():

    global sent_signals

    while True:

        if AUTO_SCAN_ENABLED and CHAT_ID:

            try:

                signals = scan_market()

                for signal_data in signals:

                    signal_id = (
                        signal_data["symbol"]
                        + signal_data["signal"]
                    )

                    if signal_id in sent_signals:
                        continue

                    sent_signals.add(
                        signal_id
                    )

                    text = build_signal_message(
                        signal_data
                    )

                    await bot.send_message(
                        CHAT_ID,
                        "🚨 Новый сигнал\n\n" + text
                    )

            except Exception as e:

                print(
                    f"Auto scanner error: {e}"
                )

        await asyncio.sleep(
            AUTO_INTERVAL
        )
# =========================
# BEST SIGNAL
# =========================

def get_best_signal():

    signals = scan_market()

    if not signals:
        return None

    signals = sorted(
        signals,
        key=lambda x: x["score"],
        reverse=True
    )

    return signals[0]
# =========================
# TOP-3 SIGNALS
# =========================

def get_top3_signals():

    signals = scan_market()

    if not signals:
        return []

    signals = sorted(
        signals,
        key=lambda x: x["score"],
        reverse=True
    )

    return signals[:3]
# =========================
# STATISTICS
# =========================

stats = {

    "total_signals": 0,

    "call_signals": 0,

    "put_signals": 0,

    "day_signals": 0,

    "week_signals": 0,

    "month_signals": 0

}
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
    global CHAT_ID

    CHAT_ID = message.chat.id

    await message.answer(

        "📈 Binarium Signal Bot\n\n"
        f"Режим: {MODE}\n"
        f"Автосканирование: {'🟢 ВКЛ' if AUTO_SCAN_ENABLED else '🔴 ВЫКЛ'}\n"
        f"Интервал: {AUTO_INTERVAL} сек.",

        reply_markup=keyboard

    )

@dp.message(lambda message: message.text == "🔍 Сканер")
async def scanner_button(message: types.Message):

    signals = scan_market()

    if not signals:

        await message.answer(
            "⚪ Сигналы не найдены"
        )

        return

    text = "🔍 Найденные сигналы\n\n"

    for signal in signals:

        symbol = (
            signal["symbol"]
            .replace("=X", "")
        )

        strength = signal["score"] * 25

        text += (
            f"{'🟢' if signal['signal']=='CALL' else '🔴'} "
            f"{signal['signal']} "
            f"{symbol}\n"
            f"Сила: {strength}%\n\n"
        )

    await message.answer(text)
@dp.message(lambda message: message.text == "🏆 Лучшая")
async def best_signal_button(message: types.Message):

    signal_data = get_best_signal()

    if signal_data is None:

        await message.answer(
            "⚪ Сигналы не найдены"
        )

        return

    text = build_signal_message(
        signal_data
    )

    await message.answer(
        "🏆 Лучший сигнал\n\n" + text
    )

@dp.message(lambda message: message.text == "🥇 Топ-3")
async def top3_button(message: types.Message):

    signals = get_top3_signals()

    if len(signals) == 0:

        await message.answer(
            "⚪ Сигналы не найдены"
        )

        return

    text = "🥇 ТОП-3 сигнала\n\n"

    for i, signal in enumerate(signals, start=1):

        symbol = signal["symbol"].replace("=X", "")

        text += (
            f"{i}. "
            f"{'🟢' if signal['signal']=='CALL' else '🔴'} "
            f"{signal['signal']} "
            f"{symbol}\n"
            f"Сила: {signal['score']*25}%\n\n"
        )

    await message.answer(text)
@dp.message(lambda message: message.text == "📊 Статус")
async def status_button(message: types.Message):

    await message.answer(

        "📊 Binarium Signal Bot\n\n"

        f"Режим: {MODE}\n\n"

        f"Автосканирование: "
        f"{'🟢 ВКЛ' if AUTO_SCAN_ENABLED else '🔴 ВЫКЛ'}\n\n"

        f"Интервал:\n"
        f"{AUTO_INTERVAL} сек.\n\n"

        f"Валютных пар:\n"
        f"{len(SIGNAL_PAIRS)}"

    )


@dp.message(lambda message: message.text == "📈 Статистика")
async def statistics_button(message: types.Message):

    await message.answer(

        "📈 Статистика\n\n"

        f"Всего сигналов:\n"
        f"{stats['total_signals']}\n\n"

        f"CALL:\n"
        f"{stats['call_signals']}\n\n"

        f"PUT:\n"
        f"{stats['put_signals']}"

    )


@dp.message(lambda message: message.text == "📅 День")
async def day_button(message: types.Message):

    await message.answer(

        "📅 Сегодня\n\n"

        f"Сигналов:\n"
        f"{stats['day_signals']}"

    )


@dp.message(lambda message: message.text == "🗓 Неделя")
async def week_button(message: types.Message):

    await message.answer(

        "🗓 Неделя\n\n"

        f"Сигналов:\n"
        f"{stats['week_signals']}"

    )


@dp.message(lambda message: message.text == "📆 Месяц")
async def month_button(message: types.Message):

    await message.answer(

        "📆 Месяц\n\n"

        f"Сигналов:\n"
        f"{stats['month_signals']}"

    )
@dp.message(lambda message: message.text == "🟢 Авто ВКЛ")
async def auto_on(message: types.Message):

    global AUTO_SCAN_ENABLED

    AUTO_SCAN_ENABLED = True

    await message.answer(
        "🟢 Автосканирование включено"
    )


@dp.message(lambda message: message.text == "🔴 Авто ВЫКЛ")
async def auto_off(message: types.Message):

    global AUTO_SCAN_ENABLED

    AUTO_SCAN_ENABLED = False

    await message.answer(
        "🔴 Автосканирование выключено"
    )
# =========================
# MAIN
# =========================

async def main():

    asyncio.create_task(
        auto_scanner()
    )

    await dp.start_polling(bot)

if __name__ == "__main__":

    asyncio.run(main())
