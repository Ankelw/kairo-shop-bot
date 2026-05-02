import os
import threading
import requests
import telebot
import sqlite3
from datetime import datetime, timedelta
from flask import Flask
from telebot import types

app = Flask(__name__)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, expiry_date TEXT)''')
    conn.commit()
    conn.close()

def add_subscription(user_id, days):
    conn = sqlite3.connect('users.db')
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
    return new_expiry.strftime('%d.%m.%Y')

# --- СЕРВЕР ДЛЯ RENDER ---
@app.route('/')
def health(): return "OK", 200

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- НАСТРОЙКИ БОТА ---
BOT_TOKEN = "8716589061:AAFI52set5odaESDkcR9bokrXk0u_z_uzy0"
CRYPTO_TOKEN = "576413:AAyvNq1n2VLIRrZy85jqOIQXqsKpTu5Gk8S"
# ЖЕСТКИЙ IP (чтобы не было ошибок как на скриншоте 345)
API_URL = "https://104.26.11.164/api" 
HEADERS = {'Crypto-Pay-API-Token': CRYPTO_TOKEN, 'Host': 'pay.cryptopay.me'}

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Неделя — $1.5", callback_data="buy_1.5_7"),
        types.InlineKeyboardButton("Месяц — $3", callback_data="buy_3_30"),
        types.InlineKeyboardButton("Год — $10", callback_data="buy_10_365")
    )
    bot.send_message(m.chat.id, "🛒 **Kairo Shop**\nТвои подписки: /my", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['my'])
def my_sub(m):
    conn = sqlite3.connect('users.db')
    cur = conn.cursor()
    cur.execute("SELECT expiry_date FROM users WHERE user_id = ?", (m.chat.id,))
    row = cur.fetchone()
    conn.close()
    if row:
        bot.send_message(m.chat.id, f"✅ Подписка активна до: **{row[0]}**", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "❌ У вас нет активной подписки.")

@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    if c.data.startswith("buy_"):
        _, price, days = c.data.split("_")
        payload = {'asset': 'USDT', 'amount': price, 'description': f'Access for {days} days'}
        try:
            r = requests.post(f"{API_URL}/createInvoice", json=payload, headers=HEADERS, verify=False).json()
            if r.get('ok'):
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("💳 Оплатить", url=r['result']['pay_url']))
                m.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{r['result']['invoice_id']}_{days}"))
                bot.edit_message_text(f"Счет на {price} USDT создан!", c.message.chat.id, c.message.message_id, reply_markup=m)
        except Exception as e:
            bot.send_message(c.message.chat.id, f"Ошибка: {e}")

    elif c.data.startswith("check_"):
        _, inv_id, days = c.data.split("_")
        try:
            r = requests.get(f"{API_URL}/getInvoices?invoice_ids={inv_id}", headers=HEADERS, verify=False).json()
            if r.get('ok') and r['result']['items'][0]['status'] == 'paid':
                date = add_subscription(c.from_user.id, int(days))
                bot.edit_message_text(f"🎉 Оплачено! Доступ до: {date}", c.message.chat.id, c.message.message_id)
            else:
                bot.answer_callback_query(c.id, "❌ Оплата не найдена", show_alert=True)
        except:
            bot.answer_callback_query(c.id, "Ошибка связи.")

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web, daemon=True).start()
    bot.polling(none_stop=True)
