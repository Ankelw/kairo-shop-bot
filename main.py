import telebot
from telebot import types
import requests
import sqlite3
from datetime import datetime, timedelta
import threading
import time

# --- НАСТРОЙКИ ---
BOT_TOKEN = "import telebot
from telebot import types
import requests
import sqlite3
from datetime import datetime, timedelta
import threading
import time

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8384323577:AAFRz-QZATjtSad5DSu_8a8Ge0qB7Qt-OVk"
CRYPTO_TOKEN = "576769:AAaLX6VEhaxSyMX33tZB6IBpvYOgAKp5327"
# Никаких ссылок на Google больше нет!

bot = telebot.TeleBot(BOT_TOKEN)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('kairo.db', check_same_thread=False)
    cur = conn.cursor()
    # Таблица пользователей: кто купил и до какого числа
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, expire_date TEXT)''')
    # Таблица ожидающих платежей: чтобы бот знал, что проверять
    cur.execute('''CREATE TABLE IF NOT EXISTS pending_invoices 
                   (invoice_id INTEGER PRIMARY KEY, user_id INTEGER, days INTEGER)''')
    conn.commit()
    conn.close()

# --- ФУНКЦИИ CRYPTO PAY (ПРЯМОЙ ЗАПРОС) ---
def create_invoice(amount):
    url = 'https://pay.cryptopay.me/api/createInvoice'
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": str(amount),
        "description": "Оплата Kairo Client"
    }
    response = requests.post(url, headers=headers, data=payload).json()
    if response.get('ok'):
        return response['result']
    return None

def check_invoice(invoice_id):
    url = f'https://pay.cryptopay.me/api/getInvoices?invoice_ids={invoice_id}'
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    response = requests.get(url, headers=headers).json()
    if response.get('ok') and response['result']['items']:
        return response['result']['items'][0]['status'] # вернет 'paid' или 'active'
    return None

# --- АВТОМАТИЧЕСКАЯ ОЧИСТКА БАЗЫ ---
def clean_expired_subs():
    while True:
        conn = sqlite3.connect('kairo.db', check_same_thread=False)
        cur = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Удаляем всех, у кого время вышло
        cur.execute("DELETE FROM users WHERE expire_date < ?", (now_str,))
        conn.commit()
        conn.close()
        time.sleep(3600) # Проверяем каждый час

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
        bot.send_message(m.chat.id, f"✅ Твой доступ к клиенту активен до: **{row[0]}**", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "❌ У вас нет активной подписки или она истекла.")

@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    if c.data.startswith("buy_"):
        _, price, days = c.data.split("_")
        
        # Создаем счет напрямую
        invoice = create_invoice(price)
        
        if invoice:
            inv_id = invoice['invoice_id']
            pay_url = invoice['pay_url']
            
            # Сохраняем счет в ожидание
            conn = sqlite3.connect('kairo.db')
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO pending_invoices VALUES (?, ?, ?)", (inv_id, c.from_user.id, int(days)))
            conn.commit()
            conn.close()

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))
            markup.add(types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{inv_id}"))
            
            bot.edit_message_text(f"Счет на {price} USDT создан. У тебя 1 час на оплату.", c.message.chat.id, c.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(c.id, "Ошибка создания счета. Проверь токен CryptoBot.", show_alert=True)

    elif c.data.startswith("check_"):
        _, inv_id = c.data.split("_")
        status = check_invoice(inv_id)

        if status == 'paid':
            conn = sqlite3.connect('kairo.db')
            cur = conn.cursor()
            cur.execute("SELECT days FROM pending_invoices WHERE invoice_id = ?", (inv_id,))
            row = cur.fetchone()
            
            if row:
                days = row[0]
                # Считаем дату окончания
                expire_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                
                # Добавляем в активные юзеры и удаляем из ожидающих
                cur.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (c.from_user.id, expire_date))
                cur.execute("DELETE FROM pending_invoices WHERE invoice_id = ?", (inv_id,))
                conn.commit()
                
                bot.edit_message_text(f"🎉 Оплата прошла успешно!\nПодписка активна до: {expire_date}\nСкачать клиент: [ССЫЛКА_НА_ФАЙЛ]", c.message.chat.id, c.message.message_id)
            conn.close()
        else:
            bot.answer_callback_query(c.id, "❌ Оплата еще не поступила или счет отменен.", show_alert=True)

if __name__ == "__main__":
    init_db()
    # Запускаем фоновый поток, который будет удалять истекшие подписки
    threading.Thread(target=clean_expired_subs, daemon=True).start()
    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    bot.polling(none_stop=True)"
CRYPTO_TOKEN = "ТВОЙ_ТОКЕН_ОТ_CRYPTOBOT_MAINNET"
# Никаких ссылок на Google больше нет!

bot = telebot.TeleBot(BOT_TOKEN)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('kairo.db', check_same_thread=False)
    cur = conn.cursor()
    # Таблица пользователей: кто купил и до какого числа
    cur.execute('''CREATE TABLE IF NOT EXISTS users 
                   (user_id INTEGER PRIMARY KEY, expire_date TEXT)''')
    # Таблица ожидающих платежей: чтобы бот знал, что проверять
    cur.execute('''CREATE TABLE IF NOT EXISTS pending_invoices 
                   (invoice_id INTEGER PRIMARY KEY, user_id INTEGER, days INTEGER)''')
    conn.commit()
    conn.close()

# --- ФУНКЦИИ CRYPTO PAY (ПРЯМОЙ ЗАПРОС) ---
def create_invoice(amount):
    url = 'https://pay.cryptopay.me/api/createInvoice'
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    payload = {
        "asset": "USDT",
        "amount": str(amount),
        "description": "Оплата Kairo Client"
    }
    response = requests.post(url, headers=headers, data=payload).json()
    if response.get('ok'):
        return response['result']
    return None

def check_invoice(invoice_id):
    url = f'https://pay.cryptopay.me/api/getInvoices?invoice_ids={invoice_id}'
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    response = requests.get(url, headers=headers).json()
    if response.get('ok') and response['result']['items']:
        return response['result']['items'][0]['status'] # вернет 'paid' или 'active'
    return None

# --- АВТОМАТИЧЕСКАЯ ОЧИСТКА БАЗЫ ---
def clean_expired_subs():
    while True:
        conn = sqlite3.connect('kairo.db', check_same_thread=False)
        cur = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Удаляем всех, у кого время вышло
        cur.execute("DELETE FROM users WHERE expire_date < ?", (now_str,))
        conn.commit()
        conn.close()
        time.sleep(3600) # Проверяем каждый час

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
        bot.send_message(m.chat.id, f"✅ Твой доступ к клиенту активен до: **{row[0]}**", parse_mode="Markdown")
    else:
        bot.send_message(m.chat.id, "❌ У вас нет активной подписки или она истекла.")

@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    if c.data.startswith("buy_"):
        _, price, days = c.data.split("_")
        
        # Создаем счет напрямую
        invoice = create_invoice(price)
        
        if invoice:
            inv_id = invoice['invoice_id']
            pay_url = invoice['pay_url']
            
            # Сохраняем счет в ожидание
            conn = sqlite3.connect('kairo.db')
            cur = conn.cursor()
            cur.execute("INSERT OR REPLACE INTO pending_invoices VALUES (?, ?, ?)", (inv_id, c.from_user.id, int(days)))
            conn.commit()
            conn.close()

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))
            markup.add(types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{inv_id}"))
            
            bot.edit_message_text(f"Счет на {price} USDT создан. У тебя 1 час на оплату.", c.message.chat.id, c.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(c.id, "Ошибка создания счета. Проверь токен CryptoBot.", show_alert=True)

    elif c.data.startswith("check_"):
        _, inv_id = c.data.split("_")
        status = check_invoice(inv_id)

        if status == 'paid':
            conn = sqlite3.connect('kairo.db')
            cur = conn.cursor()
            cur.execute("SELECT days FROM pending_invoices WHERE invoice_id = ?", (inv_id,))
            row = cur.fetchone()
            
            if row:
                days = row[0]
                # Считаем дату окончания
                expire_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
                
                # Добавляем в активные юзеры и удаляем из ожидающих
                cur.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (c.from_user.id, expire_date))
                cur.execute("DELETE FROM pending_invoices WHERE invoice_id = ?", (inv_id,))
                conn.commit()
                
                bot.edit_message_text(f"🎉 Оплата прошла успешно!\nПодписка активна до: {expire_date}\nСкачать клиент: [ССЫЛКА_НА_ФАЙЛ]", c.message.chat.id, c.message.message_id)
            conn.close()
        else:
            bot.answer_callback_query(c.id, "❌ Оплата еще не поступила или счет отменен.", show_alert=True)

if __name__ == "__main__":
    init_db()
    # Запускаем фоновый поток, который будет удалять истекшие подписки
    threading.Thread(target=clean_expired_subs, daemon=True).start()
    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    bot.polling(none_stop=True)
