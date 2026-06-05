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

ASSETS = {
    "EUR/USD": "EUR/USD",
    "GBP/USD": "GBP/USD",
    "USD/JPY": "USD/JPY",
}

keyboard = ReplyKeyboardMarkup(
    [
        ["📈 EUR/USD", "📈 GBP/USD"],
        ["📈 USD/JPY", "📊 Статус"],
        ["ℹ️ Помощь", "⏸ Стоп"]
    ],
    resize_keyboard=True
)


def get_signal(asset):
    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={asset}&interval=1min&outputsize=30"
    )

    try:
        data = requests.get(url, timeout=10).json()

        if "values" not in data:
            return {
                "asset": asset,
                "signal": "⚪ WAIT",
                "confidence": 50,
                "reason": "Нет данных от API"
            }

        closes = [float(x["close"]) for x in reversed(data["values"])]

        ema9 = sum(closes[-9:]) / 9
        ema21 = sum(closes[-21:]) / 21

        diff = abs(ema9 - ema21)
        confidence = min(95, max(55, int(60 + diff * 10000)))

        if ema9 > ema21:
            signal = "🟢 CALL"
            reason = "EMA 9 выше EMA 21"
        elif ema9 < ema21:
            signal = "🔴 PUT"
            reason = "EMA 9 ниже EMA 21"
        else:
            signal = "⚪ WAIT"
            confidence = 50
            reason = "Нет явного направления"

        return {
            "asset": asset,
            "signal": signal,
            "confidence": confidence,
            "reason": reason
        }

    except Exception:
        return {
            "asset": asset,
            "signal": "⚪ WAIT",
            "confidence": 50,
            "reason": "Ошибка получения данных"
        }


def format_signal(asset):
    data = get_signal(asset)
    now = datetime.utcnow().strftime("%H:%M UTC")

    return (
        f"📊 Сигнал по активу: {data['asset']}\n\n"
        f"{data['signal']}\n"
        f"🔥 Уверенность: {data['confidence']}%\n"
        f"⏱ Экспирация: 1 минута\n"
        f"🧠 Анализ: {data['reason']}\n"
        f"🕒 Время: {now}\n\n"
        f"⚠️ Не является финансовой рекомендацией.\n"
        f"Тестируй сначала на демо-счёте."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.add(update.effective_chat.id)

    text = (
        "👋 Добро пожаловать в Binarium Signal Bot!\n\n"
        "✅ Автоматические сигналы включены.\n\n"
        "Выбирай актив кнопками ниже или используй команды:\n\n"
        "/signal — сигнал EUR/USD\n"
        "/eurusd — EUR/USD\n"
        "/gbpusd — GBP/USD\n"
        "/usdjpy — USD/JPY\n"
        "/status — статус бота\n"
        "/help — помощь\n"
        "/stop — остановить сигналы"
    )

    await update.message.reply_text(text, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Помощь по боту\n\n"
        "📈 Нажми кнопку с нужным активом, чтобы получить сигнал.\n\n"
        "Команды:\n"
        "/start — запустить бота\n"
        "/signal — быстрый сигнал EUR/USD\n"
        "/eurusd — сигнал EUR/USD\n"
        "/gbpusd — сигнал GBP/USD\n"
        "/usdjpy — сигнал USD/JPY\n"
        "/status — статус\n"
        "/stop — остановить автоматические сигналы\n\n"
        "⚠️ Используй сигналы сначала только на демо-счёте.",
        reply_markup=keyboard
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_chat.id)

    await update.message.reply_text(
        "⏸ Автоматические сигналы отключены.\n\n"
        "Чтобы включить снова, нажми /start.",
        reply_markup=keyboard
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_signal("EUR/USD"), reply_markup=keyboard)


async def eurusd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_signal("EUR/USD"), reply_markup=keyboard)


async def gbpusd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_signal("GBP/USD"), reply_markup=keyboard)


async def usdjpy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_signal("USD/JPY"), reply_markup=keyboard)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 Статус бота\n\n"
        f"✅ Работает: да\n"
        f"👥 Активных подписчиков: {len(subscribers)}\n"
        f"📈 Активы: EUR/USD, GBP/USD, USD/JPY\n"
        f"⏱ Автосигналы: каждые 60 секунд",
        reply_markup=keyboard
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📈 EUR/USD":
        await update.message.reply_text(format_signal("EUR/USD"), reply_markup=keyboard)

    elif text == "📈 GBP/USD":
        await update.message.reply_text(format_signal("GBP/USD"), reply_markup=keyboard)

    elif text == "📈 USD/JPY":
        await update.message.reply_text(format_signal("USD/JPY"), reply_markup=keyboard)

    elif text == "📊 Статус":
        await status(update, context)

    elif text == "ℹ️ Помощь":
        await help_command(update, context)

    elif text == "⏸ Стоп":
        await stop(update, context)

    else:
        await update.message.reply_text(
            "Не понял команду. Используй кнопки ниже 👇",
            reply_markup=keyboard
        )


async def auto_signals(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in list(subscribers):
        try:
            text = (
                "🔔 Автоматический сигнал\n\n"
                + format_signal("EUR/USD")
            )

            await context.bot.send_message(
                chat_id=chat_id,
                text=text
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
    app.add_handler(CommandHandler("status", status))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))

    app.job_queue.run_repeating(
        auto_signals,
        interval=60,
        first=20
    )

    print("Бот запущен...", flush=True)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
