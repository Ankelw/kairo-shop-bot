import os
import threading
import httpx
import telebot
import sqlite3
from datetime import datetime, timedelta
from flask import Flask
from telebot import types

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('users.db', check_same_thread=False)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, expiry_date TEXT)''')
    conn.commit()
    conn.close()

def add_subscription(user_id, days):
    conn = sqlite3.connect('users.db', check_same_thread=False)
    cur = conn.cursor()
    cur.execute("SELECT expiry_date FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    now = datetime.now()
    if row:
        expiry = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        new_expiry = max(expiry, now) + timedelta(days=days)
    else:
        new_expiry = now + timedelta(days=days)
    cur.execute("INSERT OR REPLACE INTO users (user_id, expiry_date) VALUES (?, ?)",
                (user_id, new_expiry.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    return new_expiry.strftime('%d.%m.%Y %H:%M')

@app.route('/')
def health(): return "Kairo Bot is Live", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8716589061:AAFI52set5odaESDkcR9bokrXk0u_z_uzy0"
CRYPTO_TOKEN = "576413:AAyvNq1n2VLIRrZy85jqOIQXqsKpTu5Gk8S"
API_URL = "https://pay.cryptopay.me/api"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Неделя — $1.5", callback_data="buy_1.5_7"),
        types.InlineKeyboardButton("Месяц — $3", callback_data="buy_3_30"),
        types.InlineKeyboardButton("Год — $10", callback_data="buy_10_365")
    )
    bot.send_message(m.chat.id, "🛒 **Kairo Shop**\nВыбери период подписки:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    # Используем httpx с имитацией браузера
    with httpx.Client(http2=True, headers={'Crypto-Pay-API-Token': CRYPTO_TOKEN, 'User-Agent': 'Mozilla/5.0'}) as client:
        if c.data.startswith("buy_"):
            _, price, days = c.data.split("_")
            try:
                r = client.post(f"{API_URL}/createInvoice", json={'asset': 'USDT', 'amount': price}).json()
                if r.get('ok'):
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("💳 Оплатить", url=r['result']['pay_url']))
                    m.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{r['result']['invoice_id']}_{days}"))
                    bot.edit_message_text(f"Счет на {price} USDT создан!", c.message.chat.id, c.message.message_id, reply_markup=m)
                else:
                    bot.send_message(c.message.chat.id, "Ошибка платежки. Проверь токен в CryptoPay.")
            except Exception as e:
                bot.send_message(c.message.chat.id, f"Ошибка сети. Попробуй еще раз.")

        elif c.data.startswith("check_"):
            _, inv_id, days = c.data.split("_")
            try:
                r = client.get(f"{API_URL}/getInvoices?invoice_ids={inv_id}").json()
                if r.get('ok') and r['result']['items'][0]['status'] == 'paid':
                    date = add_subscription(c.from_user.id, int(days))
                    bot.edit_message_text(f"🎉 Оплачено! Доступ до: {date}", c.message.chat.id, c.message.message_id)
                else:
                    bot.answer_callback_query(c.id, "❌ Не оплачено", show_alert=True)
            except:
                bot.answer_callback_query(c.id, "Ошибка связи.")

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    bot.polling(none_stop=True)
