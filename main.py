import os
import threading
import requests
import telebot
import sqlite3
from datetime import datetime, timedelta
from flask import Flask
from telebot import types

app = Flask(__name__)

# --- ОБЯЗАТЕЛЬНО ВСТАВЬ СВОЮ ССЫЛКУ СЮДА ---
GOOGLE_BRIDGE = "https://script.google.com/macros/s/AKfycbwDK0eHs4bH2xr9DeTHI8gB9u0ADIez1RPf-aOkbBkfqQewmYoqkvonJzWb3ROGE7sP/exec"

BOT_TOKEN = "8716589061:AAFI52set5odaESDkcR9bokrXk0u_z_uzy0"
CRYPTO_TOKEN = "576540:AAIMOZdjl6DvSRNzQgSImitflQqMPnbpjb2"

bot = telebot.TeleBot(BOT_TOKEN)

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

@bot.message_handler(commands=['start'])
def start(m):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Неделя — $1.5", callback_data="buy_1.5_7"),
        types.InlineKeyboardButton("Месяц — $3", callback_data="buy_3_30"),
        types.InlineKeyboardButton("Год — $10", callback_data="buy_10_365")
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
        bot.send_message(m.chat.id, f"✅ Подписка активна до: **{row[0]}**", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "❌ У вас нет активной подписки.")

@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    if c.data.startswith("buy_"):
        _, price, days = c.data.split("_")
        try:
            # Запрос через Google мост
            response = requests.post(GOOGLE_BRIDGE, json={
                "token": CRYPTO_TOKEN,
                "payload": {"asset": "USDT", "amount": price}
            })
            data = response.json()
            
            if data.get('ok'):
                res = data['result']
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("💳 Оплатить", url=res['pay_url']))
                m.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{res['invoice_id']}_{days}"))
                bot.edit_message_text(f"Счет на {price} USDT создан!", c.message.chat.id, c.message.message_id, reply_markup=m)
            else:
                bot.send_message(c.message.chat.id, "⚠️ Ошибка платежной системы. Проверьте настройки моста.")
        except Exception as e:
            bot.send_message(c.message.chat.id, f"⚠️ Ошибка связи с мостом. Проверьте ссылку GOOGLE_BRIDGE.")

    elif c.data.startswith("check_"):
        _, inv_id, days = c.data.split("_")
        try:
            # Проверка через Google мост
            response = requests.get(f"{GOOGLE_BRIDGE}?id={inv_id}&token={CRYPTO_TOKEN}")
            data = response.json()
            
            if data.get('ok') and data['result']['items'][0]['status'] == 'paid':
                date = add_subscription(c.from_user.id, int(days))
                bot.edit_message_text(f"🎉 Оплата принята! Подписка активна до: {date}", c.message.chat.id, c.message.message_id)
            else:
                bot.answer_callback_query(c.id, "❌ Оплата еще не поступила", show_alert=True)
        except:
            bot.answer_callback_query(c.id, "❌ Ошибка при проверке оплаты.")

if __name__ == "__main__":
    init_db()
    # Запуск Flask для Render в отдельном потоке
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    # Запуск бота
    bot.polling(none_stop=True)
