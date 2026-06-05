import os
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

subscribers = set()


def get_signal(asset):
    url = (
        f"https://api.twelvedata.com/time_series"
        f"?symbol={asset}&interval=1min&outputsize=30"
    )

    try:
        data = requests.get(url).json()

        if "values" not in data:
            return "⚪ WAIT"

        closes = [float(x["close"]) for x in reversed(data["values"])]

        ema9 = sum(closes[-9:]) / 9
        ema21 = sum(closes[-21:]) / 21

        if ema9 > ema21:
            return "🟢 CALL"
        elif ema9 < ema21:
            return "🔴 PUT"
        else:
            return "⚪ WAIT"

    except:
        return "⚪ WAIT"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.add(update.effective_chat.id)

    text = (
        "👋 Добро пожаловать в Binarium Signals Bot!\n\n"
        "✅ Автоматические сигналы включены.\n\n"
        "📌 Команды:\n\n"
        "/signal — сигнал EUR/USD\n"
        "/eurusd — EUR/USD\n"
        "/gbpusd — GBP/USD\n"
        "/usdjpy — USD/JPY\n"
        "/status — статус бота\n"
        "/stop — остановить сигналы"
    )

    await update.message.reply_text(text)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_chat.id)

    await update.message.reply_text(
        "⏸ Автоматические сигналы отключены."
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sig = get_signal("EUR/USD")

    await update.message.reply_text(
        f"📈 EUR/USD\n\n{sig}"
    )


async def eurusd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sig = get_signal("EUR/USD")

    await update.message.reply_text(
        f"📈 EUR/USD\n\n{sig}"
    )


async def gbpusd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sig = get_signal("GBP/USD")

    await update.message.reply_text(
        f"📈 GBP/USD\n\n{sig}"
    )


async def usdjpy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sig = get_signal("USD/JPY")

    await update.message.reply_text(
        f"📈 USD/JPY\n\n{sig}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 Статус бота\n\n"
        f"Подписчиков: {len(subscribers)}\n"
        f"Работает: ✅"
    )


async def auto_signals(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in subscribers:
        try:
            signal = get_signal("EUR/USD")

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📈 EUR/USD\n\n{signal}"
            )

        except:
            pass


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("eurusd", eurusd))
    app.add_handler(CommandHandler("gbpusd", gbpusd))
    app.add_handler(CommandHandler("usdjpy", usdjpy))
    app.add_handler(CommandHandler("status", status))

    app.job_queue.run_repeating(
        auto_signals,
        interval=60,
        first=15
    )

    print("Бот запущен...")

    app.run_polling()


if __name__ == "__main__":
    main()
