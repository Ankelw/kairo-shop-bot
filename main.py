import telebot
from telebot import types
import requests
import sqlite3
from datetime import datetime, timedelta
import threading
import time

# --- НАСТРОЙКИ ---
# Токены оставляю в точности как на твоих скриншотах
BOT_TOKEN = "8384323577:AAFRz-QZATjtSad5DSu_8a8Ge0qB7Qt-OVk"
CRYPTO_TOKEN = "576769:AAaLX6VEhaxSyMX33tZB6IBpvY0gAKp5327"

bot = telebot.TeleBot(BOT_TOKEN)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('kairo.db', check_same_thread=False)
    cur = conn.cursor()
    # Таблица пользователей
    cur.execute('''CREATE TABLE IF NOT EXISTS users
                  (user_id INTEGER PRIMARY KEY, expire_date TEXT)''')
    # Таблица ожидающих платежей
    cur.execute('''CREATE TABLE IF NOT EXISTS pending_invoices
                  (invoice_id INTEGER PRIMARY KEY, user_id INTEGER, days INTEGER)''')
    conn.commit()
    conn.close()

# --- ФУНКЦИИ CRYPTO PAY ---
def create_invoice(amount):
    url = 'https://pay.cryptopay.me/api/createInvoice'
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": str(amount),
        "description": "Оплата Kairo Client"
    }
    try:
        response = requests.post(url, headers=headers, data=payload).json()
        if response.get('ok'):
            return response['result']
    except Exception as e:
        print(f"Ошибка оплаты: {e}")
    return None

def check_invoice(invoice_id):
    url = f'https://pay.cryptopay.me/api/getInvoices?invoice_ids={invoice_id}'
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    try:
        response = requests.get(url, headers=headers).json()
        if response.get('ok') and response['result']['items']:
            return response['result']['items'][0]['status']
    except:
        pass
    return None

# --- АВТОМАТИЧЕСКАЯ ОЧИСТКА БАЗЫ ---
def clean_expired_subs():
    while True:
        try:
            conn = sqlite3.connect('kairo.db', check_same_thread=False)
            cur = conn.cursor()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cur.execute("DELETE FROM users WHERE expire_date < ?", (now_str,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка очистки: {e}")
        time.sleep(3600) # Проверка каждый час

# --- ОБРАБОТЧИКИ БОТА ---
@bot.message_handler(commands=['start'])
def start(m):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Неделя – $1.5", callback_data="buy_1.5_7"),
        types.InlineKeyboardButton("Месяц – $3", callback_data="buy_3_30"),
        types.InlineKeyboardButton("Год – $10", callback_data="buy_10_365")
    )
    bot.send_message(m.chat.id, "🛒 **Kairo Shop**\nВыбери тариф:\nПроверить подписку: /my", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['my'])
def my_sub(m):
    conn = sqlite3.connect('kairo.db')
    cur = conn.cursor()
    cur.execute("SELECT expire_date FROM users WHERE user_id = ?", (m.chat.id,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        bot.send_message(m.chat.id, f"✅ Твой доступ активен до: **{row[0]}**", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "❌ У вас нет активной подписки или она истекла.")

@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    if c.data.startswith("buy_"):
        _, price, days = c.data.split("_")
        invoice = create_invoice(price)
        
        if invoice:
            inv_id = invoice['invoice_id']
            pay_url = invoice['pay_url']
            
            conn = sqlite3.connect('kairo.db')
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO pending_invoices VALUES (?, ?, ?)", (inv_id, c.from_user.id, int(days)))
            conn.commit()
            conn.close()

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))
            markup.add(types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{inv_id}"))
            bot.edit_message_text(f"Счет на {price} USDT создан.", c.message.chat.id, c.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(c.id, "Ошибка создания счета.", show_alert=True)

    elif c.data.startswith("check_"):
        inv_id = c.data.split("_")[1]
        status = check_invoice(inv_id)
        
        if status == 'paid':
            conn = sqlite3.connect('kairo.db')
            cur = conn.cursor()
            cur.execute("SELECT days FROM pending_invoices WHERE invoice_id = ?", (inv_id,))
            row = cur.fetchone()
            
            if row:
                days = row[0]
                expire_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                cur.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (c.from_user.id, expire_date))
                cur.execute("DELETE FROM pending_invoices WHERE invoice_id = ?", (inv_id,))
                conn.commit()
                bot.edit_message_text(f"🎉 Оплата прошла! Подписка до: {expire_date}", c.message.chat.id, c.message.message_id)
            conn.close()
        else:
            bot.answer_callback_query(c.id, "❌ Оплата еще не поступила.", show_alert=True)

# --- ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    # Запускаем поток очистки базы
    threading.Thread(target=clean_expired_subs, daemon=True).start()
    print("Бот запущен локально. Нажмите Ctrl+C для остановки.")
    bot.polling(none_stop=True)
