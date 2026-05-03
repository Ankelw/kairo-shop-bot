import os
import telebot
from flask import Flask, request
import sqlite3
from datetime import datetime, timedelta
import requests

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8384323577:AAFRz-QZATjtSad5DSu_8a8Ge0qB7Qt-OVk"
CRYPTO_TOKEN = "576769:AAaLX6VEhaxSyMX33tZB6IBpvY0gAKp5327"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('kairo.db', check_same_thread=False)
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expire_date TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS pending_invoices (invoice_id INTEGER PRIMARY KEY, user_id INTEGER, days INTEGER)')
    conn.commit()
    conn.close()

# --- ФУНКЦИИ ОПЛАТЫ ---
def create_invoice(amount):
    url = 'https://pay.cryptopay.me/api/createInvoice'
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    payload = {"asset": "USDT", "amount": str(amount), "description": "Kairo Client"}
    try:
        r = requests.post(url, headers=headers, data=payload, timeout=10).json()
        return r.get('result') if r.get('ok') else None
    except: return None

def check_invoice(invoice_id):
    url = f'https://pay.cryptopay.me/api/getInvoices?invoice_ids={invoice_id}'
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    try:
        r = requests.get(url, headers=headers, timeout=10).json()
        if r.get('ok') and r['result']['items']:
            return r['result']['items'][0]['status']
    except: pass
    return None

# --- ЛОГИКА ВЕБХУКА (ДЛЯ RENDER) ---
@app.route('/')
def home():
    return "Бот активен!", 200

@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

# --- ОБРАБОТЧИКИ БОТА ---
@bot.message_handler(commands=['start'])
def start(m):
    kb = telebot.types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        telebot.types.InlineKeyboardButton("Неделя – $1.5", callback_data="buy_1.5_7"),
        telebot.types.InlineKeyboardButton("Месяц – $3", callback_data="buy_3_30"),
        telebot.types.InlineKeyboardButton("Год – $10", callback_data="buy_10_365")
    )
    bot.send_message(m.chat.id, "🛒 **Kairo Shop**\nВыбери тариф:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def handle_calls(c):
    if c.data.startswith("buy_"):
        _, price, days = c.data.split("_")
        inv = create_invoice(price)
        if inv:
            conn = sqlite3.connect('kairo.db')
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO pending_invoices VALUES (?, ?, ?)", (inv['invoice_id'], c.from_user.id, int(days)))
            conn.commit()
            conn.close()
            
            kb = telebot.types.InlineKeyboardMarkup()
            kb.add(telebot.types.InlineKeyboardButton("💳 Оплатить", url=inv['pay_url']))
            kb.add(telebot.types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{inv['invoice_id']}"))
            bot.edit_message_text(f"Счет на {price} USDT создан. У тебя 1 час на оплату.", c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif c.data.startswith("check_"):
        inv_id = c.data.split("_")[1]
        if check_invoice(inv_id) == 'paid':
            conn = sqlite3.connect('kairo.db')
            cur = conn.cursor()
            cur.execute("SELECT days FROM pending_invoices WHERE invoice_id = ?", (inv_id,))
            res = cur.fetchone()
            if res:
                exp = (datetime.now() + timedelta(days=res[0])).strftime('%Y-%m-%d %H:%M:%S')
                cur.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (c.from_user.id, exp))
                cur.execute("DELETE FROM pending_invoices WHERE invoice_id = ?", (inv_id,))
                conn.commit()
                bot.send_message(c.message.chat.id, f"🎉 Оплата прошла! Подписка активна до: {exp}")
            conn.close()
        else:
            bot.answer_callback_query(c.id, "❌ Оплата не найдена", show_alert=True)

# --- ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
