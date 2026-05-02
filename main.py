import os
import threading
import requests
import telebot
import sqlite3
from datetime import datetime, timedelta
from flask import Flask
from telebot import types
import urllib3

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
def health(): return "OK", 200

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8716589061:AAFI52set5odaESDkcR9bokrXk0u_z_uzy0"
CRYPTO_TOKEN = "576413:AAyvNq1n2VLIRrZy85jqOIQXqsKpTu5Gk8S"
API_URL = "https://pay.cryptopay.me/api"

# Маскируемся под браузер Windows, чтобы обойти блокировку
HEADERS = {
    'Crypto-Pay-API-Token': CRYPTO_TOKEN,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Неделя — $1.5", callback_data="buy_1.5_7"),
        types.InlineKeyboardButton("Месяц — $3", callback_data="buy_3_30"),
        types.InlineKeyboardButton("Год — $10", callback_data="buy_10_365") # Кнопка возвращена
    )
    bot.send_message(m.chat.id, "🛒 **Kairo Shop**\nВыбери тариф:\nПроверить подписку: /my", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['my'])
def my_sub(m):
    conn = sqlite3.connect('users.db', check_same_thread=False)
    cur = conn.cursor()
    cur.execute("SELECT expiry_date FROM users WHERE user_id = ?", (m.chat.id,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        expiry = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        if expiry > datetime.now():
            bot.send_message(m.chat.id, f"✅ Подписка активна до: **{row[0]}**", parse_mode="Markdown")
        else:
            bot.send_message(m.chat.id, f"❌ Подписка истекла (**{row[0]}**).")
    else:
        bot.send_message(m.chat.id, "❌ У вас нет активной подписки.")

@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    if c.data.startswith("buy_"):
        _, price, days = c.data.split("_")
        payload = {'asset': 'USDT', 'amount': price}
        try:
            r = requests.post(f"{API_URL}/createInvoice", json=payload, headers=HEADERS, verify=False)
            data = r.json()
            if data.get('ok'):
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("💳 Оплатить", url=data['result']['pay_url']))
                m.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{data['result']['invoice_id']}_{days}"))
                bot.edit_message_text(f"Счет на {price} USDT создан!", c.message.chat.id, c.message.message_id, reply_markup=m)
            else:
                # Если токен неверный, выведет это
                error_name = data.get('error', {}).get('name', 'Неизвестная ошибка')
                bot.send_message(c.message.chat.id, f"⚠️ Отказ от CryptoPay: {error_name}")
        except Exception as e:
            # Выведет точную системную ошибку прямо в чат
            bot.send_message(c.message.chat.id, f"⚠️ Системная ошибка сети:\n`{str(e)}`", parse_mode="Markdown")

    elif c.data.startswith("check_"):
        _, inv_id, days = c.data.split("_")
        try:
            r = requests.get(f"{API_URL}/getInvoices?invoice_ids={inv_id}", headers=HEADERS, verify=False)
            data = r.json()
            if data.get('ok') and data['result']['items'][0]['status'] == 'paid':
                date = add_subscription(c.from_user.id, int(days))
                bot.edit_message_text(f"🎉 Оплачено! Доступ до: {date}", c.message.chat.id, c.message.message_id)
            else:
                bot.answer_callback_query(c.id, "❌ Оплата не найдена", show_alert=True)
        except Exception as e:
             bot.answer_callback_query(c.id, f"Ошибка: {str(e)[:50]}")

if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    bot.polling(none_stop=True)
