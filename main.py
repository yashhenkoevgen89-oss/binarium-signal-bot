import os
import asyncio
from datetime import datetime

import pandas as pd
import requests

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands


# ======================
# CONFIG
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

MODE = os.getenv("MODE", "DEMO")
AUTO_INTERVAL = int(os.getenv("AUTO_INTERVAL", "300"))

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# ======================
# SETTINGS
# ======================

AUTO_SCAN_ENABLED = True
CHAT_ID = None

SELECTED_EXPIRATION = "5 мин"
SELECTED_PAIR = "ALL"

SIGNAL_PAIRS = [
    "EURUSD=X",
    "EURJPY=X",
    "GBPUSD=X",
    "GBPJPY=X",
    "USDJPY=X",
    "USDCAD=X",
]

PAIR_NAMES = {
    "ALL": "🌍 Все пары",
    "EURUSD=X": "EURUSD",
    "EURJPY=X": "EURJPY",
    "GBPUSD=X": "GBPUSD",
    "GBPJPY=X": "GBPJPY",
    "USDJPY=X": "USDJPY",
    "USDCAD=X": "USDCAD",
}

pair_cache = {}
current_pair_index = 0

SIGNAL_COOLDOWN_SECONDS = 300
last_signal_time = {}

signal_history = []
stats = {
    "total_signals": 0,
    "call_signals": 0,
    "put_signals": 0,
    "day_signals": 0,
    "week_signals": 0,
    "month_signals": 0,
}


# ======================
# KEYBOARDS
# ======================

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Статус"), KeyboardButton(text="🔎 Сканер")],
        [KeyboardButton(text="🏆 Лучшая"), KeyboardButton(text="🥇 Топ-3")],
        [KeyboardButton(text="⏱ Экспирация"), KeyboardButton(text="💱 Пара")],
        [KeyboardButton(text="📈 Статистика"), KeyboardButton(text="📅 День")],
        [KeyboardButton(text="🗓 Неделя"), KeyboardButton(text="📆 Месяц")],
        [KeyboardButton(text="🟢 Авто ВКЛ"), KeyboardButton(text="🔴 Авто ВЫКЛ")],
    ],
    resize_keyboard=True
)

pair_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌍 Все пары")],
        [KeyboardButton(text="EURUSD"), KeyboardButton(text="EURJPY")],
        [KeyboardButton(text="GBPUSD"), KeyboardButton(text="GBPJPY")],
        [KeyboardButton(text="USDJPY"), KeyboardButton(text="USDCAD")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True
)

expiration_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏱ 1 мин"), KeyboardButton(text="⏱ 3 мин")],
        [KeyboardButton(text="⏱ 5 мин"), KeyboardButton(text="⏱ 10 мин")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True
)


# ======================
# MARKET DATA
# ======================

def convert_symbol(symbol):
    mapping = {
        "EURUSD=X": "EUR/USD",
        "EURJPY=X": "EUR/JPY",
        "GBPUSD=X": "GBP/USD",
        "GBPJPY=X": "GBP/JPY",
        "USDJPY=X": "USD/JPY",
        "USDCAD=X": "USD/CAD",
    }
    return mapping.get(symbol, symbol)


def get_market_data(symbol, interval="5min", outputsize=300):
    try:
        url = "https://api.twelvedata.com/time_series"

        params = {
            "symbol": convert_symbol(symbol),
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TWELVE_DATA_API_KEY,
        }

        response = requests.get(url, params=params, timeout=15)
        data = response.json()

        if "values" not in data:
            print(f"TwelveData error {symbol}: {data}")
            return pd.DataFrame()

        df = pd.DataFrame(data["values"])

        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna()
        df = df.iloc[::-1].reset_index(drop=True)

        return df

    except Exception as e:
        print(f"Market data error {symbol}: {e}")
        return pd.DataFrame()


# ======================
# INDICATORS
# ======================

def add_indicators(df):
    if df.empty:
        return df

    try:
        df["ema20"] = EMAIndicator(df["close"], window=20).ema_indicator()
        df["ema50"] = EMAIndicator(df["close"], window=50).ema_indicator()
        df["ema200"] = EMAIndicator(df["close"], window=200).ema_indicator()

        df["rsi"] = RSIIndicator(df["close"], window=14).rsi()

        macd = MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()

        adx = ADXIndicator(df["high"], df["low"], df["close"])
        df["adx"] = adx.adx()

        bb = BollingerBands(df["close"])
        df["bb_high"] = bb.bollinger_hband()
        df["bb_low"] = bb.bollinger_lband()

        stoch = StochasticOscillator(df["high"], df["low"], df["close"])
        df["stoch"] = stoch.stoch()

        return df

    except Exception as e:
        print(f"Indicator error: {e}")
        return df


# ======================
# SIGNAL ENGINE
# ======================

def analyze_pair(symbol):
    df = get_market_data(symbol)

    if df.empty:
        return None

    df = add_indicators(df)

    if len(df) < 210:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]
    prev3 = df.iloc[-4]

    try:
        rsi = float(last["rsi"])
        adx = float(last["adx"])

        close = float(last["close"])
        open_price = float(last["open"])

        prev_close = float(prev["close"])
        prev_open = float(prev["open"])

        prev2_close = float(prev2["close"])
        prev2_open = float(prev2["open"])

        prev3_close = float(prev3["close"])
        prev3_open = float(prev3["open"])

    except Exception:
        return None

    candles = [
        (prev3_open, prev3_close),
        (prev2_open, prev2_close),
        (prev_open, prev_close),
        (open_price, close),
    ]

    green_count = sum(1 for o, c in candles if c > o)
    red_count = sum(1 for o, c in candles if c < o)

    last_green = close > open_price
    last_red = close < open_price

    higher_close = close > prev_close > prev2_close
    lower_close = close < prev_close < prev2_close

    call_score = 0

    if green_count >= 3:
        call_score += 2
    if last_green:
        call_score += 1
    if higher_close:
        call_score += 2
    if 45 <= rsi <= 68:
        call_score += 1
    if adx >= 20:
        call_score += 1

    put_score = 0

    if red_count >= 3:
        put_score += 2
    if last_red:
        put_score += 1
    if lower_close:
        put_score += 2
    if 32 <= rsi <= 55:
        put_score += 1
    if adx >= 20:
        put_score += 1

    if call_score >= put_score and call_score >= 5:
        return {
            "symbol": symbol,
            "signal": "CALL",
            "score": call_score,
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
        }

    if put_score > call_score and put_score >= 5:
        return {
            "symbol": symbol,
            "signal": "PUT",
            "score": put_score,
            "rsi": round(rsi, 1),
            "adx": round(adx, 1),
        }

    return None


# ======================
# SIGNAL MESSAGE
# ======================

def build_signal_message(signal_data):
    if signal_data is None:
        return "⚪ Сигнал не найден"

    signal = signal_data["signal"]
    symbol = signal_data["symbol"].replace("=X", "")
    score = signal_data["score"]

    rating = 150 if score >= 7 else 125
    title = "🔥 VIP SIGNAL" if rating == 150 else "✅ HIGH QUALITY"
    quality = "🔥 STRONG SIGNAL" if rating == 150 else "✅ QUALITY SIGNAL"
    emoji = "🟢" if signal == "CALL" else "🔴"

    return (
        f"{title}\n\n"
        f"{emoji} {signal}\n\n"
        f"{symbol}\n\n"
        f"Рейтинг:\n{rating}%\n\n"
        f"RSI: {signal_data['rsi']}\n"
        f"ADX: {signal_data['adx']}\n\n"
        f"⏱ Экспирация:\n{SELECTED_EXPIRATION}\n\n"
        f"{quality}"
    )


# ======================
# SCANNER
# ======================

def scan_market():
    global current_pair_index
    global pair_cache

    if SELECTED_PAIR == "ALL":
        symbol = SIGNAL_PAIRS[current_pair_index]

        current_pair_index += 1

        if current_pair_index >= len(SIGNAL_PAIRS):
            current_pair_index = 0

    else:
        symbol = SELECTED_PAIR

    signal_data = analyze_pair(symbol)

    pair_cache[symbol] = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "signal": signal_data,
    }

    signals = []

    for _, data in pair_cache.items():
        if data.get("signal"):
            signals.append(data["signal"])

    return signals


def get_best_signal():
    signals = scan_market()

    if not signals:
        return None

    return sorted(signals, key=lambda x: x["score"], reverse=True)[0]


def get_top3_signals():
    signals = scan_market()

    if not signals:
        return []

    return sorted(signals, key=lambda x: x["score"], reverse=True)[:3]


# ======================
# HISTORY
# ======================

def save_signal(signal_data):
    now = datetime.now()

    item = {
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": signal_data["symbol"].replace("=X", ""),
        "signal": signal_data["signal"],
        "score": 150 if signal_data["score"] >= 7 else 125,
        "rsi": signal_data["rsi"],
        "adx": signal_data["adx"],
    }

    signal_history.append(item)

    stats["total_signals"] += 1
    stats["day_signals"] += 1
    stats["week_signals"] += 1
    stats["month_signals"] += 1

    if signal_data["signal"] == "CALL":
        stats["call_signals"] += 1

    if signal_data["signal"] == "PUT":
        stats["put_signals"] += 1 
        
# =========================
# AUTO SCANNER
# =========================

async def auto_scanner():

    global last_signal_time

    while True:

        if AUTO_SCAN_ENABLED and CHAT_ID:

            try:

                signals = scan_market()

                for signal_data in signals:

                    symbol = signal_data["symbol"]

                    now = datetime.now()

                    # защита от повторных сигналов
                    if symbol in last_signal_time:

                        seconds_passed = (
                            now - last_signal_time[symbol]
                        ).total_seconds()

                        if seconds_passed < SIGNAL_COOLDOWN_SECONDS:
                            continue

                    # сохраняем время последнего сигнала
                    last_signal_time[symbol] = now

                    save_signal(signal_data)

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

        # проверка следующей пары
        await asyncio.sleep(9)


# ======================
# HANDLERS
# ======================

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


@dp.message(lambda message: message.text == "📊 Статус")
async def status_button(message: types.Message):
    await message.answer(
        "📊 Binarium Signal Bot\n\n"
        f"Режим: {MODE}\n\n"
        f"Экспирация:\n{SELECTED_EXPIRATION}\n\n"
        f"Выбранная пара:\n{PAIR_NAMES.get(SELECTED_PAIR, SELECTED_PAIR)}\n\n"
        f"Автосканирование:\n{'🟢 ВКЛ' if AUTO_SCAN_ENABLED else '🔴 ВЫКЛ'}\n\n"
        f"Интервал:\n{AUTO_INTERVAL} сек.\n\n"
        f"Всего пар:\n{len(SIGNAL_PAIRS)}"
    )


@dp.message(lambda message: message.text in ["🔎 Сканер", "🔍 Сканер"])
async def scanner_button(message: types.Message):
    if not pair_cache:
        await message.answer(
            "⏳ Данных пока нет.\n\n"
            "Подожди 1–2 минуты, бот по очереди проверяет пары."
        )
        return

    text = "🔎 Сканер рынка\n\n"

    for symbol, data in pair_cache.items():
        signal_data = data.get("signal")
        check_time = data.get("time", "—")
        name = symbol.replace("=X", "")

        if signal_data:
            rating = 150 if signal_data["score"] >= 7 else 125
            emoji = "🟢" if signal_data["signal"] == "CALL" else "🔴"

            text += (
                f"{emoji} {signal_data['signal']} {name}\n"
                f"Рейтинг: {rating}%\n"
                f"Обновлено: {check_time}\n\n"
            )
        else:
            text += (
                f"⚪ {name}\n"
                f"Сигнала нет\n"
                f"Обновлено: {check_time}\n\n"
            )

    await message.answer(text)


@dp.message(lambda message: message.text == "🏆 Лучшая")
async def best_signal_button(message: types.Message):
    signal_data = get_best_signal()

    if signal_data is None:
        await message.answer("⚪ Сигналы не найдены")
        return

    await message.answer("🏆 Лучший сигнал\n\n" + build_signal_message(signal_data))


@dp.message(lambda message: message.text == "🥇 Топ-3")
async def top3_button(message: types.Message):
    signals = get_top3_signals()

    if not signals:
        await message.answer("⚪ Сигналы не найдены")
        return

    text = "🥇 ТОП-3 сигнала\n\n"

    for i, signal in enumerate(signals, start=1):
        symbol = signal["symbol"].replace("=X", "")
        rating = 150 if signal["score"] >= 7 else 125
        emoji = "🟢" if signal["signal"] == "CALL" else "🔴"

        text += (
            f"{i}. {emoji} {signal['signal']} {symbol}\n"
            f"Рейтинг: {rating}%\n\n"
        )

    await message.answer(text)


@dp.message(lambda message: message.text == "⏱ Экспирация")
async def expiration_menu(message: types.Message):
    await message.answer(
        "⏱ Выбери экспирацию:",
        reply_markup=expiration_keyboard
    )


@dp.message(lambda message: message.text in ["⏱ 1 мин", "⏱ 3 мин", "⏱ 5 мин", "⏱ 10 мин"])
async def set_expiration(message: types.Message):
    global SELECTED_EXPIRATION

    SELECTED_EXPIRATION = message.text.replace("⏱ ", "")

    await message.answer(
        f"✅ Экспирация установлена: {SELECTED_EXPIRATION}",
        reply_markup=keyboard
    )


@dp.message(lambda message: message.text == "💱 Пара")
async def pair_menu(message: types.Message):
    await message.answer(
        "💱 Выбери пару для сигналов:",
        reply_markup=pair_keyboard
    )


@dp.message(lambda message: message.text @dp.message(lambda message: message.text in [
    "🌍 Все пары",
    "EURUSD",
    "EURJPY",
    "GBPUSD",
    "GBPJPY",
    "USDJPY",
    "USDCAD"
])
async def set_pair(message: types.Message):

    global SELECTED_PAIR
    global pair_cache
    global current_pair_index
    global last_signal_time

    if message.text == "🌍 Все пары":
        SELECTED_PAIR = "ALL"
    else:
        SELECTED_PAIR = f"{message.text}=X"

    pair_cache.clear()
    current_pair_index = 0
    last_signal_time.clear()

    await message.answer(
        f"✅ Выбранная пара: {PAIR_NAMES.get(SELECTED_PAIR, SELECTED_PAIR)}",
        reply_markup=keyboard
    )


@dp.message(lambda message: message.text == "📈 Статистика")
async def statistics_button(message: types.Message):
    await message.answer(
        "📈 Статистика\n\n"
        f"Всего сигналов: {stats['total_signals']}\n"
        f"CALL: {stats['call_signals']}\n"
        f"PUT: {stats['put_signals']}"
    )


@dp.message(lambda message: message.text == "📅 День")
async def day_button(message: types.Message):
    await message.answer(f"📅 Сегодня\n\nСигналов: {stats['day_signals']}")


@dp.message(lambda message: message.text == "🗓 Неделя")
async def week_button(message: types.Message):
    await message.answer(f"🗓 Неделя\n\nСигналов: {stats['week_signals']}")


@dp.message(lambda message: message.text == "📆 Месяц")
async def month_button(message: types.Message):
    await message.answer(f"📆 Месяц\n\nСигналов: {stats['month_signals']}")


@dp.message(lambda message: message.text == "🟢 Авто ВКЛ")
async def auto_on(message: types.Message):
    global AUTO_SCAN_ENABLED

    AUTO_SCAN_ENABLED = True
    await message.answer("🟢 Автосканирование включено", reply_markup=keyboard)


@dp.message(lambda message: message.text == "🔴 Авто ВЫКЛ")
async def auto_off(message: types.Message):
    global AUTO_SCAN_ENABLED

    AUTO_SCAN_ENABLED = False
    await message.answer("🔴 Автосканирование выключено", reply_markup=keyboard)


@dp.message(lambda message: message.text == "⬅️ Назад")
async def back_button(message: types.Message):
    await message.answer("Главное меню", reply_markup=keyboard)


# ======================
# MAIN
# ======================

async def main():
    asyncio.create_task(auto_scanner())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
