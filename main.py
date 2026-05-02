import os
import threading
import requests
import telebot
from flask import Flask
from telebot import types

app = Flask(__name__)

# --- ФУНКЦИИ СЕРВЕРА ---
@app.route('/')
def health_check():
    return "Kairo Bot is online!", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8716589061:AAFI52set5odaESDkcR9bokrXk0u_z_uzy0"
CRYPTO_TOKEN = "576413:AAyvNq1n2VLIRrZy85jqOIQXqsKpTu5Gk8S"

# Используем надежный домен (если не сработает, поменяй на https://104.26.11.164/api)
API_URL = "https://pay.cryptopay.me/api"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_message(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Неделя — $1.5", callback_data="buy_1.5_week"),
        types.InlineKeyboardButton("Месяц — $3", callback_data="buy_3_month"),
        types.InlineKeyboardButton("Год — $10", callback_data="buy_10_year")
    )
    bot.send_message(message.chat.id, "🛒 **Kairo Store**\nВыберите подписку:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data.startswith("buy_"):
        _, amount, plan = call.data.split("_")
        headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
        payload = {'asset': 'USDT', 'amount': amount, 'description': f'Kairo: {plan}'}
        
        try:
            resp = requests.post(f"{API_URL}/createInvoice", json=payload, headers=headers).json()
            if resp.get('ok'):
                pay_url = resp['result']['pay_url']
                inv_id = resp['result']['invoice_id']
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))
                markup.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{inv_id}_{plan}"))
                bot.edit_message_text(f"Счет на {amount} USDT создан!", call.message.chat.id, call.message.message_id, reply_markup=markup)
            else:
                bot.send_message(call.message.chat.id, f"Ошибка API: {resp.get('error', {}).get('name')}")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"⚠️ Сетевая ошибка: {e}")

    elif call.data.startswith("check_"):
        _, inv_id, plan = call.data.split("_")
        headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
        try:
            res = requests.get(f"{API_URL}/getInvoices?invoice_ids={inv_id}", headers=headers).json()
            if res.get('ok') and res['result']['items'][0]['status'] == 'paid':
                bot.send_message(call.message.chat.id, f"🎉 Подписка {plan} активна!")
            else:
                bot.answer_callback_query(call.id, "❌ Не оплачено.", show_alert=True)
        except:
            bot.answer_callback_query(call.id, "Ошибка проверки.")

if __name__ == "__main__":
    # Запуск веб-сервера для Render
    threading.Thread(target=run_web_server, daemon=True).start()
    print("Kairo Bot started!")
    bot.polling(none_stop=True)