import os
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

subscribers = set()
history = []
expiry_settings = {}

ASSETS = {
    "EUR/USD": "EUR/USD",
    "GBP/USD": "GBP/USD",
    "USD/JPY": "USD/JPY",
    "GOLD": "XAU/USD",
    "BTC": "BTC/USD",
}

keyboard = ReplyKeyboardMarkup(
    [
        ["📈 EUR/USD", "📈 GBP/USD"],
        ["📈 USD/JPY", "🥇 GOLD"],
        ["₿ BTC", "📊 Статус"],
        ["📜 История", "📊 Статистика"],
        ["ℹ️ Помощь", "⏸ Стоп"],
    ],
    resize_keyboard=True
)


def get_expiry(chat_id):
    return expiry_settings.get(chat_id, 3)


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


def ema(values, period):
    if len(values) < period:
        return sum(values) / len(values)

    multiplier = 2 / (period + 1)
    ema_value = sum(values[:period]) / period

    for price in values[period:]:
        ema_value = (price - ema_value) * multiplier + ema_value

    return ema_value


def calculate_macd(closes):
    if len(closes) < 26:
        return 0, 0

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = ema12 - ema26

    signal_line = macd_line * 0.8
    return macd_line, signal_line


def get_market_data(asset):
    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={asset}&interval=1min&outputsize=80"
    )

    response = requests.get(url, timeout=10)
    data = response.json()

    if "values" not in data:
        raise Exception("Нет данных от API")

    closes = [float(x["close"]) for x in reversed(data["values"])]
    return closes


def analyze_asset(asset_name):
    asset_symbol = ASSETS[asset_name]

    try:
        closes = get_market_data(asset_symbol)

        last_price = closes[-1]
        ema9 = ema(closes, 9)
        ema21 = ema(closes, 21)
        rsi = calculate_rsi(closes)
        macd_line, macd_signal = calculate_macd(closes)

        call_score = 0
        put_score = 0
        reasons = []

        if ema9 > ema21:
            call_score += 35
            reasons.append("EMA показывает рост")
        elif ema9 < ema21:
            put_score += 35
            reasons.append("EMA показывает снижение")

        if 45 <= rsi <= 68:
            call_score += 25
            reasons.append(f"RSI подходит для CALL: {rsi:.1f}")
        elif 32 <= rsi <= 55:
            put_score += 25
            reasons.append(f"RSI подходит для PUT: {rsi:.1f}")
        else:
            reasons.append(f"RSI нейтральный: {rsi:.1f}")

        if macd_line > macd_signal:
            call_score += 25
            reasons.append("MACD подтверждает рост")
        elif macd_line < macd_signal:
            put_score += 25
            reasons.append("MACD подтверждает снижение")

        if call_score >= 70 and call_score > put_score:
            signal = "🟢 CALL"
            confidence = min(95, call_score)
        elif put_score >= 70 and put_score > call_score:
            signal = "🔴 PUT"
            confidence = min(95, put_score)
        else:
            signal = "⚪ WAIT"
            confidence = max(call_score, put_score, 50)

        result = {
            "asset": asset_name,
            "symbol": asset_symbol,
            "signal": signal,
            "confidence": confidence,
            "price": last_price,
            "ema9": ema9,
            "ema21": ema21,
            "rsi": rsi,
            "macd": macd_line,
            "macd_signal": macd_signal,
            "reason": ", ".join(reasons),
            "time": datetime.utcnow().strftime("%H:%M UTC")
        }

        history.append(result)
        if len(history) > 50:
            history.pop(0)

        return result

    except Exception as e:
        return {
            "asset": asset_name,
            "symbol": asset_symbol,
            "signal": "⚪ WAIT",
            "confidence": 50,
            "price": 0,
            "ema9": 0,
            "ema21": 0,
            "rsi": 50,
            "macd": 0,
            "macd_signal": 0,
            "reason": f"Ошибка данных: {e}",
            "time": datetime.utcnow().strftime("%H:%M UTC")
        }


def format_signal(asset_name, chat_id=None):
    data = analyze_asset(asset_name)
    expiry = get_expiry(chat_id) if chat_id else 3

    return (
        f"📊 PRO-сигнал\n\n"
        f"📈 Актив: {data['asset']}\n"
        f"💵 Цена: {data['price']:.5f}\n\n"
        f"Сигнал: {data['signal']}\n"
        f"🔥 Уверенность: {data['confidence']}%\n"
        f"⏱ Экспирация: {expiry} мин.\n\n"
        f"📉 EMA 9: {data['ema9']:.5f}\n"
        f"📉 EMA 21: {data['ema21']:.5f}\n"
        f"📊 RSI: {data['rsi']:.1f}\n"
        f"📊 MACD: {data['macd']:.5f}\n\n"
        f"🧠 Анализ: {data['reason']}\n"
        f"🕒 Время: {data['time']}\n\n"
        f"⚠️ Это не финансовая рекомендация.\n"
        f"Сначала тестируйте только на демо-счёте."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)

    await update.message.reply_text(
        "👋 Добро пожаловать в Binarium Signal PRO!\n\n"
        "✅ Автоматические сигналы включены.\n\n"
        "📌 Доступные активы:\n"
        "EUR/USD, GBP/USD, USD/JPY, GOLD, BTC\n\n"
        "📊 Стратегия:\n"
        "EMA 9 + EMA 21 + RSI + MACD\n\n"
        "Используйте кнопки ниже 👇",
        reply_markup=keyboard
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Помощь\n\n"
        "/start — запустить бота\n"
        "/signal — быстрый сигнал EUR/USD\n"
        "/eurusd — EUR/USD\n"
        "/gbpusd — GBP/USD\n"
        "/usdjpy — USD/JPY\n"
        "/gold — GOLD\n"
        "/btc — BTC\n"
        "/history — история сигналов\n"
        "/stats — статистика сигналов\n"
        "/setexpiry 1 — экспирация 1 минута\n"
        "/setexpiry 3 — экспирация 3 минуты\n"
        "/setexpiry 5 — экспирация 5 минут\n"
        "/status — статус\n"
        "/stop — остановить автосигналы\n\n"
        "⚠️ Перед реальной торговлей тестируйте на демо-счёте.",
        reply_markup=keyboard
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_chat.id)
    await update.message.reply_text(
        "⏸ Автоматические сигналы отключены.\n\n"
        "Чтобы включить снова, нажмите /start.",
        reply_markup=keyboard
    )


async def send_signal(update: Update, asset_name):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        format_signal(asset_name, chat_id),
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


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    active = "включены ✅" if chat_id in subscribers else "отключены ⏸"

    await update.message.reply_text(
        f"📊 Статус бота\n\n"
        f"🤖 Бот работает: ✅\n"
        f"🔔 Автосигналы: {active}\n"
        f"👥 Активных подписчиков: {len(subscribers)}\n"
        f"⏱ Экспирация: {get_expiry(chat_id)} мин.\n"
        f"📈 Активы: EUR/USD, GBP/USD, USD/JPY, GOLD, BTC\n"
        f"📊 История сигналов: {len(history)}",
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
            f"Цена: {item['price']:.5f}\n\n"
        )

    await update.message.reply_text(text, reply_markup=keyboard)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = len(history)

    if total == 0:
        await update.message.reply_text(
            "📊 Статистики пока нет.",
            reply_markup=keyboard
        )
        return

    calls = sum(1 for x in history if "CALL" in x["signal"])
    puts = sum(1 for x in history if "PUT" in x["signal"])
    waits = sum(1 for x in history if "WAIT" in x["signal"])

    await update.message.reply_text(
        f"📊 Статистика сигналов\n\n"
        f"Всего сигналов: {total}\n\n"
        f"🟢 CALL: {calls} — {calls / total * 100:.1f}%\n"
        f"🔴 PUT: {puts} — {puts / total * 100:.1f}%\n"
        f"⚪ WAIT: {waits} — {waits / total * 100:.1f}%",
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
        "📈 EUR/USD": "EUR/USD",
        "📈 GBP/USD": "GBP/USD",
        "📈 USD/JPY": "USD/JPY",
        "🥇 GOLD": "GOLD",
        "₿ BTC": "BTC",
    }

    if text in mapping:
        await send_signal(update, mapping[text])
    elif text == "📊 Статус":
        await status(update, context)
    elif text == "📜 История":
        await show_history(update, context)
    elif text == "📊 Статистика":
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
        for asset_name in ["EUR/USD", "GBP/USD", "USD/JPY"]:
            try:
                data = analyze_asset(asset_name)

                if data["signal"] != "⚪ WAIT" and data["confidence"] >= 75:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "🔔 Сильный автоматический сигнал\n\n"
                            + format_signal(asset_name, chat_id)
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
    app.add_handler(CommandHandler("eurusd", eurusd))
    app.add_handler(CommandHandler("gbpusd", gbpusd))
    app.add_handler(CommandHandler("usdjpy", usdjpy))
    app.add_handler(CommandHandler("gold", gold))
    app.add_handler(CommandHandler("btc", btc))
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

    print("Binarium Signal PRO запущен...", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
