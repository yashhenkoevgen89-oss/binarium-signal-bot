import os
import requests
import pandas as pd
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")

ASSETS = {
    "eurusd": {"name": "EUR/USD", "symbol": "EUR/USD"},
    "gbpusd": {"name": "GBP/USD", "symbol": "GBP/USD"},
    "usdjpy": {"name": "USD/JPY", "symbol": "USD/JPY"},
    "gold": {"name": "XAU/USD", "symbol": "XAU/USD"},
    "btc": {"name": "BTC/USD", "symbol": "BTC/USD"},
}

subscribers = set()
chat_settings = {}
history = []

keyboard = ReplyKeyboardMarkup(
    [
        ["📊 Сигнал", "⚙️ Статус"],
        ["📈 EUR/USD", "📈 GBP/USD", "📈 USD/JPY"],
        ["🥇 GOLD", "₿ BTC"],
        ["📜 История", "📊 Статистика"],
        ["▶️ Старт", "⏸ Стоп"],
    ],
    resize_keyboard=True
)

def get_setting(chat_id):
    if chat_id not in chat_settings:
        chat_settings[chat_id] = {
            "assets": ["eurusd", "gbpusd", "usdjpy"],
            "expiry": 3,
            "last_sent": {}
        }
    return chat_settings[chat_id]

def get_prices(symbol, interval="1min", outputsize=100):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": "demo"
    }
    data = requests.get(url, params=params, timeout=15).json()

    if "values" not in data:
        raise Exception(f"Нет данных по {symbol}: {data}")

    values = list(reversed(data["values"]))
    closes = [float(v["close"]) for v in values]
    return pd.Series(closes)

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def macd(series):
    ema12 = series.ewm(span=12).mean()
    ema26 = series.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]

def analyze_timeframe(symbol, interval):
    prices = get_prices(symbol, interval)
    price = prices.iloc[-1]
    ema9 = prices.ewm(span=9).mean().iloc[-1]
    ema21 = prices.ewm(span=21).mean().iloc[-1]
    rsi_val = rsi(prices).iloc[-1]
    macd_line, macd_signal = macd(prices)

    if ema9 > ema21 and 45 <= rsi_val <= 65 and macd_line > macd_signal:
        direction = "CALL"
    elif ema9 < ema21 and 35 <= rsi_val <= 55 and macd_line < macd_signal:
        direction = "PUT"
    else:
        direction = "WAIT"

    return {
        "direction": direction,
        "price": price,
        "ema9": ema9,
        "ema21": ema21,
        "rsi": rsi_val,
        "macd": macd_line,
        "macd_signal": macd_signal
    }

def make_signal(asset_key, expiry=3):
    asset = ASSETS[asset_key]
    one_min = analyze_timeframe(asset["symbol"], "1min")
    five_min = analyze_timeframe(asset["symbol"], "5min")

    if one_min["direction"] == "CALL" and five_min["direction"] == "CALL":
        signal = "ВВЕРХ 🟢"
        confidence = 85
    elif one_min["direction"] == "PUT" and five_min["direction"] == "PUT":
        signal = "ВНИЗ 🔴"
        confidence = 85
    else:
        signal = "ЖДАТЬ ⚪"
        confidence = 55

    item = {
        "time": datetime.utcnow().strftime("%H:%M:%S UTC"),
        "asset": asset["name"],
        "signal": signal,
        "price": one_min["price"],
        "rsi": one_min["rsi"],
        "ema9": one_min["ema9"],
        "ema21": one_min["ema21"],
        "confidence": confidence
    }

    history.append(item)
    if len(history) > 50:
        history.pop(0)

    return f"""
📊 Сигнал для Binarium

Актив: {asset["name"]}
Сигнал: {signal}
Экспирация: {expiry} мин.

Цена: {one_min["price"]:.5f}
RSI: {one_min["rsi"]:.2f}
EMA 9: {one_min["ema9"]:.5f}
EMA 21: {one_min["ema21"]:.5f}

⏱ Подтверждение:
1 минута: {one_min["direction"]}
5 минут: {five_min["direction"]}

Уверенность: {confidence}%

⚠️ Это не финансовая рекомендация.
Сначала тестируйте только на демо-счёте.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    get_setting(chat_id)

    await update.message.reply_text(
        """
👋 Добро пожаловать в бота сигналов Binarium!

✅ Вы подписаны на автоматические сигналы.

📊 Доступные активы:
EUR/USD | GBP/USD | USD/JPY | XAU/USD | BTC/USD

Команды:
/signal — общий сигнал
/eurusd — EUR/USD
/gbpusd — GBP/USD
/usdjpy — USD/JPY
/gold — золото
/btc — Bitcoin
/status — статус
/history — история
/stats — статистика
/stop — остановить сигналы

⚠️ Это не финансовая рекомендация.
Сначала тестируйте только на демо-счёте.
""",
        reply_markup=keyboard
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_chat.id)
    await update.message.reply_text("⏸ Автоматические сигналы остановлены.", reply_markup=keyboard)

async def send_asset(update: Update, asset_key):
    chat_id = update.effective_chat.id
    expiry = get_setting(chat_id)["expiry"]
    try:
        await update.message.reply_text(make_signal(asset_key, expiry), reply_markup=keyboard)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}", reply_markup=keyboard)

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_asset(update, "eurusd")

async def eurusd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_asset(update, "eurusd")

async def gbpusd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_asset(update, "gbpusd")

async def usdjpy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_asset(update, "usdjpy")

async def gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_asset(update, "gold")

async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_asset(update, "btc")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_setting(chat_id)
    active = "активны ✅" if chat_id in subscribers else "остановлены ⏸"
    assets = ", ".join([ASSETS[a]["name"] for a in settings["assets"]])

    await update.message.reply_text(
        f"""
⚙️ Статус бота

Автосигналы: {active}
Активы: {assets}
Экспирация: {settings["expiry"]} мин.
История сигналов: {len(history)}

Команды работают ✅
""",
        reply_markup=keyboard
    )

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history:
        await update.message.reply_text("📜 История пока пустая.", reply_markup=keyboard)
        return

    text = "📜 Последние сигналы:\n\n"
    for h in history[-10:]:
        text += (
            f"{h['time']} | {h['asset']}\n"
            f"{h['signal']} | Цена: {h['price']:.5f}\n"
            f"RSI: {h['rsi']:.2f} | Уверенность: {h['confidence']}%\n\n"
        )

    await update.message.reply_text(text, reply_markup=keyboard)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = len(history)
    if total == 0:
        await update.message.reply_text("📊 Статистики пока нет.", reply_markup=keyboard)
        return

    up = sum(1 for h in history if "ВВЕРХ" in h["signal"])
    down = sum(1 for h in history if "ВНИЗ" in h["signal"])
    wait = sum(1 for h in history if "ЖДАТЬ" in h["signal"])

    await update.message.reply_text(
        f"""
📊 Статистика сигналов

Всего: {total}

🟢 ВВЕРХ: {up} — {up / total * 100:.1f}%
🔴 ВНИЗ: {down} — {down / total * 100:.1f}%
⚪ ЖДАТЬ: {wait} — {wait / total * 100:.1f}%
""",
        reply_markup=keyboard
    )

async def setasset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_setting(chat_id)

    if not context.args:
        await update.message.reply_text("Используйте: /setasset eurusd|gbpusd|usdjpy|gold|btc|all")
        return

    value = context.args[0].lower()

    if value == "all":
        settings["assets"] = list(ASSETS.keys())
    elif value in ASSETS:
        settings["assets"] = [value]
    else:
        await update.message.reply_text("Неизвестный актив.")
        return

    await update.message.reply_text("✅ Активы обновлены.", reply_markup=keyboard)

async def setexpiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = get_setting(chat_id)

    if not context.args or context.args[0] not in ["1", "3", "5"]:
        await update.message.reply_text("Используйте: /setexpiry 1, /setexpiry 3 или /setexpiry 5")
        return

    settings["expiry"] = int(context.args[0])
    await update.message.reply_text(f"✅ Экспирация установлена: {settings['expiry']} мин.", reply_markup=keyboard)

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    mapping = {
        "📊 Сигнал": "eurusd",
        "📈 EUR/USD": "eurusd",
        "📈 GBP/USD": "gbpusd",
        "📈 USD/JPY": "usdjpy",
        "🥇 GOLD": "gold",
        "₿ BTC": "btc",
    }

    if text in mapping:
        await send_asset(update, mapping[text])
    elif text == "⚙️ Статус":
        await status(update, context)
    elif text == "📜 История":
        await show_history(update, context)
    elif text == "📊 Статистика":
        await stats(update, context)
    elif text == "▶️ Старт":
        await start(update, context)
    elif text == "⏸ Стоп":
        await stop(update, context)

async def auto_signals(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in list(subscribers):
        settings = get_setting(chat_id)
        for asset_key in settings["assets"]:
            try:
                text = make_signal(asset_key, settings["expiry"])
                if "ЖДАТЬ" not in text:
                    await context.bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                pass

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
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
    app.add_handler(CommandHandler("setasset", setasset))
    app.add_handler(CommandHandler("setexpiry", setexpiry))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))

    app.job_queue.run_repeating(auto_signals, interval=60, first=15)

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
