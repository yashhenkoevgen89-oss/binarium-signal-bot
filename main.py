import os
import math
import requests
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_KEY")

subscribers = set()
history = []
expiry_settings = {}

ASSETS = {
    "EUR/USD": "EUR/USD",
    "GBP/USD": "GBP/USD",
    "USD/JPY": "USD/JPY",
    "GOLD": "XAU/USD",
    "BTC": "BTC/USD",
    "ETH": "ETH/USD",
}

keyboard = ReplyKeyboardMarkup(
    [
        ["📊 EUR/USD", "📊 GBP/USD"],
        ["📊 USD/JPY", "🥇 GOLD"],
        ["₿ BTC", "Ξ ETH"],
        ["🚀 VIP-сигнал", "🏆 ТОП-сигнал"],
        ["📜 История", "📈 Статистика"],
        ["⚙️ Статус", "ℹ️ Помощь"],
        ["⏸ Стоп"],
    ],
    resize_keyboard=True
)


def get_expiry(chat_id):
    return expiry_settings.get(chat_id, 3)


def ema(values, period):
    if len(values) < period:
        return sum(values) / len(values)

    k = 2 / (period + 1)
    result = sum(values[:period]) / period

    for price in values[period:]:
        result = price * k + result * (1 - k)

    return result


def sma(values, period):
    if len(values) < period:
        return sum(values) / len(values)
    return sum(values[-period:]) / period


def stddev(values, period):
    if len(values) < period:
        period = len(values)

    avg = sma(values, period)
    data = values[-period:]
    variance = sum((x - avg) ** 2 for x in data) / period

    return math.sqrt(variance)


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50

    gains = []
    losses = []

    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]

        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_macd(closes):
    if len(closes) < 26:
        return 0, 0

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)

    macd_line = ema12 - ema26
    signal_line = macd_line * 0.8

    return macd_line, signal_line


def calculate_stochastic(closes, period=14):
    if len(closes) < period:
        return 50

    recent = closes[-period:]
    low = min(recent)
    high = max(recent)

    if high == low:
        return 50

    return ((closes[-1] - low) / (high - low)) * 100


def calculate_bollinger(closes, period=20):
    middle = sma(closes, period)
    deviation = stddev(closes, period)

    upper = middle + deviation * 2
    lower = middle - deviation * 2

    return upper, middle, lower


def get_market_data(symbol, interval="1min"):
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": 100,
        "format": "JSON",
    }

    if TWELVE_DATA_KEY:
        params["apikey"] = TWELVE_DATA_KEY

    response = requests.get(
        "https://api.twelvedata.com/time_series",
        params=params,
        timeout=15
    )

    data = response.json()

    if "values" not in data:
        message = data.get("message") or data.get("status") or "Нет данных от API"
        raise Exception(message)

    closes = [float(x["close"]) for x in reversed(data["values"])]

    if len(closes) < 30:
        raise Exception("Недостаточно свечей")

    return closes


def analyze_timeframe(symbol, interval):
    closes = get_market_data(symbol, interval)

    price = closes[-1]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi = calculate_rsi(closes)
    macd_line, macd_signal = calculate_macd(closes)
    stochastic = calculate_stochastic(closes)
    boll_upper, boll_middle, boll_lower = calculate_bollinger(closes)

    call = 0
    put = 0
    notes = []

    if ema9 > ema21:
        call += 25
        notes.append("EMA вверх")
    elif ema9 < ema21:
        put += 25
        notes.append("EMA вниз")

    if macd_line > macd_signal:
        call += 20
        notes.append("MACD вверх")
    elif macd_line < macd_signal:
        put += 20
        notes.append("MACD вниз")

    if 45 <= rsi <= 67:
        call += 20
        notes.append(f"RSI CALL {rsi:.1f}")
    elif 33 <= rsi <= 55:
        put += 20
        notes.append(f"RSI PUT {rsi:.1f}")
    elif rsi > 72:
        put += 10
        notes.append(f"RSI перекуплен {rsi:.1f}")
    elif rsi < 28:
        call += 10
        notes.append(f"RSI перепродан {rsi:.1f}")
    else:
        notes.append(f"RSI нейтральный {rsi:.1f}")

    if stochastic < 25:
        call += 15
        notes.append(f"Stochastic низкий {stochastic:.1f}")
    elif stochastic > 75:
        put += 15
        notes.append(f"Stochastic высокий {stochastic:.1f}")
    else:
        notes.append(f"Stochastic нейтральный {stochastic:.1f}")

    if price <= boll_lower:
        call += 15
        notes.append("Цена у нижней Bollinger")
    elif price >= boll_upper:
        put += 15
        notes.append("Цена у верхней Bollinger")
    else:
        notes.append("Цена внутри Bollinger")

    flat = abs(ema9 - ema21) / price if price else 0

    if flat < 0.00005:
        call -= 15
        put -= 15
        notes.append("возможный флэт")

    return {
        "price": price,
        "ema9": ema9,
        "ema21": ema21,
        "rsi": rsi,
        "macd": macd_line,
        "macd_signal": macd_signal,
        "stochastic": stochastic,
        "boll_upper": boll_upper,
        "boll_middle": boll_middle,
        "boll_lower": boll_lower,
        "call": max(call, 0),
        "put": max(put, 0),
        "notes": notes,
    }


def analyze_asset(asset_name):
    symbol = ASSETS[asset_name]

    try:
        tf1 = analyze_timeframe(symbol, "1min")
        tf5 = analyze_timeframe(symbol, "5min")
        tf15 = analyze_timeframe(symbol, "15min")

        call_score = tf1["call"] + tf5["call"] + tf15["call"]
        put_score = tf1["put"] + tf5["put"] + tf15["put"]

        reasons = []
        reasons.extend([f"1м: {x}" for x in tf1["notes"]])
        reasons.extend([f"5м: {x}" for x in tf5["notes"]])
        reasons.extend([f"15м: {x}" for x in tf15["notes"]])

        if call_score > put_score and call_score >= 130:
            signal = "🟢 CALL"
            confidence = min(95, int(call_score / 2.1))
        elif put_score > call_score and put_score >= 130:
            signal = "🔴 PUT"
            confidence = min(95, int(put_score / 2.1))
        else:
            signal = "⚪ WAIT"
            confidence = max(55, min(79, int(max(call_score, put_score) / 2.2)))

        if confidence >= 88:
            strength = "🔥 Очень сильный"
        elif confidence >= 80:
            strength = "✅ Сильный"
        elif confidence >= 70:
            strength = "⚠️ Средний"
        else:
            strength = "⏳ Лучше подождать"

        result = {
            "asset": asset_name,
            "symbol": symbol,
            "signal": signal,
            "confidence": confidence,
            "strength": strength,
            "price": tf1["price"],
            "ema9": tf1["ema9"],
            "ema21": tf1["ema21"],
            "rsi": tf1["rsi"],
            "macd": tf1["macd"],
            "stochastic": tf1["stochastic"],
            "boll_upper": tf1["boll_upper"],
            "boll_middle": tf1["boll_middle"],
            "boll_lower": tf1["boll_lower"],
            "tf1_call": tf1["call"],
            "tf1_put": tf1["put"],
            "tf5_call": tf5["call"],
            "tf5_put": tf5["put"],
            "tf15_call": tf15["call"],
            "tf15_put": tf15["put"],
            "reason": ", ".join(reasons),
            "time": datetime.utcnow().strftime("%H:%M UTC")
        }

        history.append(result)

        if len(history) > 150:
            history.pop(0)

        return result

    except Exception as e:
        return {
            "asset": asset_name,
            "symbol": symbol,
            "signal": "⚪ WAIT",
            "confidence": 50,
            "strength": "Ошибка данных",
            "price": 0,
            "ema9": 0,
            "ema21": 0,
            "rsi": 50,
            "macd": 0,
            "stochastic": 50,
            "boll_upper": 0,
            "boll_middle": 0,
            "boll_lower": 0,
            "tf1_call": 0,
            "tf1_put": 0,
            "tf5_call": 0,
            "tf5_put": 0,
            "tf15_call": 0,
            "tf15_put": 0,
            "reason": f"Ошибка данных: {e}",
            "time": datetime.utcnow().strftime("%H:%M UTC")
        }


def format_signal(asset_name, chat_id=None, vip=False):
    data = analyze_asset(asset_name)
    expiry = get_expiry(chat_id) if chat_id else 3

    title = "🚀 VIP-СИГНАЛ" if vip else "📊 PRO-сигнал"

    return (
        f"{title}\n\n"
        f"📈 Актив: {data['asset']}\n"
        f"💵 Цена: {data['price']:.5f}\n\n"
        f"Сигнал: {data['signal']}\n"
        f"🔥 Уверенность: {data['confidence']}%\n"
        f"💎 Сила: {data['strength']}\n"
        f"⏱ Экспирация: {expiry} мин.\n\n"
        f"📉 EMA 9: {data['ema9']:.5f}\n"
        f"📉 EMA 21: {data['ema21']:.5f}\n"
        f"📊 RSI: {data['rsi']:.1f}\n"
        f"📊 MACD: {data['macd']:.5f}\n"
        f"📊 Stochastic: {data['stochastic']:.1f}\n\n"
        f"📦 Bollinger Bands:\n"
        f"Верх: {data['boll_upper']:.5f}\n"
        f"Середина: {data['boll_middle']:.5f}\n"
        f"Низ: {data['boll_lower']:.5f}\n\n"
        f"🧩 Подтверждение:\n"
        f"1 минута: CALL {data['tf1_call']} / PUT {data['tf1_put']}\n"
        f"5 минут: CALL {data['tf5_call']} / PUT {data['tf5_put']}\n"
        f"15 минут: CALL {data['tf15_call']} / PUT {data['tf15_put']}\n\n"
        f"🧠 Анализ: {data['reason']}\n"
        f"🕒 Время: {data['time']}\n\n"
        f"⚠️ Это не финансовая рекомендация.\n"
        f"Сначала тестируйте только на демо-счёте."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)

    await update.message.reply_text(
        "👋 Добро пожаловать в Binarium Signal VIP!\n\n"
        "✅ Автоматические сигналы включены.\n\n"
        "📊 Анализ:\n"
        "EMA 9 + EMA 21 + RSI + MACD + Stochastic + Bollinger Bands\n\n"
        "🧩 Подтверждение:\n"
        "1 минута + 5 минут + 15 минут\n\n"
        "📈 Активы:\n"
        "EUR/USD, GBP/USD, USD/JPY, GOLD, BTC, ETH\n\n"
        "Используйте кнопки ниже 👇",
        reply_markup=keyboard
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Помощь\n\n"
        "/start — запустить бота\n"
        "/signal — сигнал EUR/USD\n"
        "/vip — лучший VIP-сигнал\n"
        "/top — топ-сигнал по рынку\n"
        "/eurusd — EUR/USD\n"
        "/gbpusd — GBP/USD\n"
        "/usdjpy — USD/JPY\n"
        "/gold — GOLD\n"
        "/btc — BTC\n"
        "/eth — ETH\n"
        "/history — история\n"
        "/stats — статистика\n"
        "/setexpiry 1 — экспирация 1 минута\n"
        "/setexpiry 3 — экспирация 3 минуты\n"
        "/setexpiry 5 — экспирация 5 минут\n"
        "/status — статус\n"
        "/stop — остановить автосигналы",
        reply_markup=keyboard
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_chat.id)

    await update.message.reply_text(
        "⏸ Автоматические сигналы отключены.\n\n"
        "Чтобы включить снова, нажмите /start.",
        reply_markup=keyboard
    )


async def send_signal(update: Update, asset_name, vip=False):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        format_signal(asset_name, chat_id, vip),
        reply_markup=keyboard
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_signal(update, "EUR/USD")


async def eurusd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_signal(update, "EUR/USD")


async def gbpusd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_signal(update, "GBP/USD")


async def usdjpy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_signal(update, "USD/JPY")


async def gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_signal(update, "GOLD")


async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_signal(update, "BTC")


async def eth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_signal(update, "ETH")


async def top_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        "🔎 Ищу лучший сигнал по рынку...",
        reply_markup=keyboard
    )

    best_asset = None
    best_data = None

    for asset_name in ASSETS.keys():
        data = analyze_asset(asset_name)

        if best_data is None or data["confidence"] > best_data["confidence"]:
            best_data = data
            best_asset = asset_name

    await update.message.reply_text(
        format_signal(best_asset, chat_id, vip=True),
        reply_markup=keyboard
    )


async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await top_signal(update, context)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active = "включены ✅" if chat_id in subscribers else "отключены ⏸"

    await update.message.reply_text(
        f"⚙️ Статус бота\n\n"
        f"🤖 Бот работает: ✅\n"
        f"🔔 Автосигналы: {active}\n"
        f"👥 Подписчиков: {len(subscribers)}\n"
        f"⏱ Экспирация: {get_expiry(chat_id)} мин.\n"
        f"📊 История: {len(history)} сигналов\n"
        f"📈 Активы: EUR/USD, GBP/USD, USD/JPY, GOLD, BTC, ETH",
        reply_markup=keyboard
    )


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history:
        await update.message.reply_text(
            "📜 История пока пустая.",
            reply_markup=keyboard
        )
        return

    text = "📜 Последние 10 сигналов:\n\n"

    for item in history[-10:]:
        text += (
            f"{item['time']} | {item['asset']}\n"
            f"{item['signal']} | {item['confidence']}%\n"
            f"{item['strength']}\n\n"
        )

    await update.message.reply_text(text, reply_markup=keyboard)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = len(history)

    if total == 0:
        await update.message.reply_text(
            "📈 Статистики пока нет.",
            reply_markup=keyboard
        )
        return

    calls = sum(1 for x in history if "CALL" in x["signal"])
    puts = sum(1 for x in history if "PUT" in x["signal"])
    waits = sum(1 for x in history if "WAIT" in x["signal"])
    strong = sum(1 for x in history if x["confidence"] >= 80)

    await update.message.reply_text(
        f"📈 Статистика сигналов\n\n"
        f"Всего сигналов: {total}\n\n"
        f"🟢 CALL: {calls} — {calls / total * 100:.1f}%\n"
        f"🔴 PUT: {puts} — {puts / total * 100:.1f}%\n"
        f"⚪ WAIT: {waits} — {waits / total * 100:.1f}%\n"
        f"🔥 VIP-сигналов: {strong} — {strong / total * 100:.1f}%",
        reply_markup=keyboard
    )


async def setexpiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if not context.args or context.args[0] not in ["1", "3", "5"]:
        await update.message.reply_text(
            "Используйте:\n"
            "/setexpiry 1\n"
            "/setexpiry 3\n"
            "/setexpiry 5",
            reply_markup=keyboard
        )
        return

    expiry_settings[chat_id] = int(context.args[0])

    await update.message.reply_text(
        f"✅ Экспирация установлена: {context.args[0]} мин.",
        reply_markup=keyboard
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    mapping = {
        "📊 EUR/USD": "EUR/USD",
        "📊 GBP/USD": "GBP/USD",
        "📊 USD/JPY": "USD/JPY",
        "🥇 GOLD": "GOLD",
        "₿ BTC": "BTC",
        "Ξ ETH": "ETH",
    }

    if text in mapping:
        await send_signal(update, mapping[text])

    elif text == "🚀 VIP-сигнал":
        await vip(update, context)

    elif text == "🏆 ТОП-сигнал":
        await top_signal(update, context)

    elif text == "⚙️ Статус":
        await status(update, context)

    elif text == "📜 История":
        await show_history(update, context)

    elif text == "📈 Статистика":
        await stats(update, context)

    elif text == "ℹ️ Помощь":
        await help_command(update, context)

    elif text == "⏸ Стоп":
        await stop(update, context)

    else:
        await update.message.reply_text(
            "Не понял команду. Используйте кнопки ниже 👇",
            reply_markup=keyboard
        )


async def auto_signals(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in list(subscribers):
        for asset_name in ["EUR/USD", "GBP/USD", "USD/JPY", "GOLD", "BTC"]:
            try:
                data = analyze_asset(asset_name)

                if data["signal"] != "⚪ WAIT" and data["confidence"] >= 80:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "🚨 VIP автоматический сигнал\n\n"
                            + format_signal(asset_name, chat_id, vip=True)
                        )
                    )

            except Exception:
                pass


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден в переменных окружения")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("vip", vip))
    app.add_handler(CommandHandler("top", top_signal))
    app.add_handler(CommandHandler("eurusd", eurusd))
    app.add_handler(CommandHandler("gbpusd", gbpusd))
    app.add_handler(CommandHandler("usdjpy", usdjpy))
    app.add_handler(CommandHandler("gold", gold))
    app.add_handler(CommandHandler("btc", btc))
    app.add_handler(CommandHandler("eth", eth))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("setexpiry", setexpiry))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))

    app.job_queue.run_repeating(
        auto_signals,
        interval=60,
        first=20
    )

    print("Binarium Signal VIP запущен...", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
