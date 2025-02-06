import docker
import random
import string
import requests
import time
import re
import json
from datetime import datetime, timedelta  # Added for time tracking

# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = '8167962294:AAF3Y2AqbvAmHe7WvB4GOzUIGqmxNFSCgQQ'  # Replace with your token
ADMIN_CHAT_ID = '71228850'  # شناسه تلگرام مدیر

# تنظیمات Docker
client = docker.from_env()

# This dictionary will map a user's chat id (as a string) to their account info:
# { chat_id: { "container_name": <name>, "created_at": <datetime> } }
user_accounts = {}

def generate_random_password(length=16):
    """تولید پسورد تصادفی"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def send_telegram_message(message, chat_id, reply_markup=None):
    """ارسال پیام به تلگرام"""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)

    response = requests.post(url, data=payload)
    return response.json()

def answer_callback_query(callback_query_id, text=""):
    """پاسخ به callback query (بدون نمایش متن برای کاربر)"""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery'
    payload = {"callback_query_id": callback_query_id, "text": text, "show_alert": False}
    requests.post(url, data=payload)

def count_shadowsocks_containers():
    """محاسبه تعداد کانتینرهای Shadowsocks"""
    containers = client.containers.list()
    return sum(1 for container in containers if container.name.startswith("shadowsocks_"))

def list_shadowsocks_containers():
    """دریافت لیست کانتینرهای Shadowsocks"""
    containers = client.containers.list()
    shadowsocks_containers = [container.name for container in containers if container.name.startswith("shadowsocks_")]
    return shadowsocks_containers

def delete_shadowsocks_container(container_name):
    """حذف کانتینر Shadowsocks"""
    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
        return True
    except docker.errors.NotFound:
        return False

def get_next_container_name():
    """دریافت نام بعدی برای کانتینر"""
    containers = client.containers.list(all=True)
    max_number = 0
    for container in containers:
        match = re.match(r"^shadowsocks_(\d+)$", container.name)
        if match:
            num = int(match.group(1))
            max_number = max(max_number, num)
    
    return f"shadowsocks_{max_number + 1}"

def can_create_account(user_chat_id):
    """
    بررسی می‌کند که آیا کاربر می‌تواند یک حساب جدید بسازد:
      - اگر کاربر قبلاً حسابی نداشته باشد، اجازه داده می‌شود.
      - اگر حسابی وجود داشته باشد و کانتینر آن هنوز موجود باشد، مجاز نیست.
      - اگر کانتینر قبلی حذف شده اما کمتر از 24 ساعت از ایجاد آن گذشته باشد، نیز اجازه داده نمی‌شود.
      - در غیر این صورت (یعنی کانتینر حذف شده و بیش از 24 ساعت گذشته) حساب قدیمی پاک شده و می‌توان حساب جدید ساخت.
    """
    user_id = str(user_chat_id)
    if user_id not in user_accounts:
         return True

    account_info = user_accounts[user_id]
    container_name = account_info["container_name"]
    try:
         # اگر کانتینر هنوز وجود داشته باشد، کاربر حساب دارد
         client.containers.get(container_name)
         return False
    except docker.errors.NotFound:
         # کانتینر حذف شده؛ اگر کمتر از 24 ساعت از ایجاد گذشته باشد، اجازه جدید کردن نمی‌دهد
         created_at = account_info["created_at"]
         if datetime.now() - created_at >= timedelta(days=1):
              # گذشت بیش از 24 ساعت؛ پاک کردن سابقه کاربر برای اجازه ایجاد مجدد
              del user_accounts[user_id]
              return True
         else:
              return False

def create_and_check_shadowsocks_container(user_chat_id):
    """ایجاد کانتینر جدید Shadowsocks و ارسال اطلاعات به تلگرام"""
    container_name = get_next_container_name()
    port = random.randint(20000, 40000)
    password = generate_random_password()

    try:
        print(f"Creating new container {container_name} on port {port}...")
        container = client.containers.run(
            "shadowsocks/shadowsocks-libev",
            name=container_name,
            environment={
                'PASSWORD': password,
                'SERVER_PORT': str(port),
                'METHOD': 'aes-256-gcm',
                'TIMEOUT': '300',
                'DNS_ADDRS': '8.8.8.8,8.8.4.4',
                'TZ': 'UTC'
            },
            ports={f"{port}/tcp": ("0.0.0.0", port)},
            detach=True
        )

        time.sleep(5)  # زمان برای راه‌اندازی کانتینر

        active_containers = count_shadowsocks_containers()

        user_message = (
            f"✅ *Your Shadowsocks Account is Ready!*\n\n"
            f"🔹 *Code:* `{container_name}`\n"
            f"🔹 *Port:* `{port}`\n"
            f"🔹 *Password:* `{password}`\n"
            f"🔹 *Method:* `aes-256-gcm`\n\n"
            f"⚡ *Enjoy your connection!*"
        )
        send_telegram_message(user_message, chat_id=user_chat_id, reply_markup=create_keyboard(user_chat_id))

        admin_message = (
            f"🛠 **New Shadowsocks Container Created**\n\n"
            f"🔹 **Container Name:** `{container_name}`\n"
            f"🔹 **Port:** `{port}`\n"
            f"🔹 **Password:** `{password}`\n\n"
            f"📌 This info is for admin monitoring.\n\n"
            f"📊 *Total Active Containers:* `{active_containers}`"
        )
        send_telegram_message(admin_message, chat_id=ADMIN_CHAT_ID, reply_markup=create_keyboard(ADMIN_CHAT_ID))

        # Record the account for this user (using the chat id as a key) only if not admin.
        if str(user_chat_id) != ADMIN_CHAT_ID:
            user_accounts[str(user_chat_id)] = {
                "container_name": container_name,
                "created_at": datetime.now()
            }

    except Exception as e:
        error_message = f"❌ *Error creating container {container_name}:* `{e}`"
        send_telegram_message(error_message, chat_id=ADMIN_CHAT_ID)

def create_keyboard(chat_id):
    """ایجاد دکمه برای مدیریت یا ساخت اکانت جدید"""
    active_containers = count_shadowsocks_containers()
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ Create Shadowsocks Account", "callback_data": "create_shadowsocks"}]
        ]
    }

    if str(chat_id) == ADMIN_CHAT_ID:
        keyboard["inline_keyboard"].append(
            [{"text": f"⚙️ Manage Containers ({active_containers})", "callback_data": "manage_containers"}]
        )

    return keyboard

def process_telegram_updates():
    """بررسی و پردازش به روز رسانی های تلگرام"""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates'
    last_update_id = None
    
    while True:
        try:
            params = {'offset': last_update_id + 1} if last_update_id else {}
            response = requests.get(url, params=params)
            updates = response.json().get('result', [])
            
            for update in updates:
                update_id = update["update_id"]
                last_update_id = update_id
                
                if 'message' in update:
                    chat_id = update['message']['chat']['id']
                    text = update['message']['text']

                    if text == '/start':
                        send_telegram_message(
                            "👋 Welcome! Click the button below to create a new Shadowsocks account.",
                            chat_id=chat_id,
                            reply_markup=create_keyboard(chat_id)
                        )

                if "callback_query" in update:
                    callback_data = update["callback_query"].get("data")
                    chat_id = update["callback_query"]["message"]["chat"]["id"]
                    callback_query_id = update["callback_query"]["id"]

                    if callback_data == "create_shadowsocks":
                        # If the user is the admin, bypass the account creation restrictions.
                        if str(chat_id) == ADMIN_CHAT_ID or can_create_account(chat_id):
                            create_and_check_shadowsocks_container(chat_id)
                        else:
                            # Do not send any message if account exists or the 24h cooldown isn’t over.
                            answer_callback_query(callback_query_id)

                    if callback_data == "manage_containers" and str(chat_id) == ADMIN_CHAT_ID:
                        containers = list_shadowsocks_containers()
                        active_count = count_shadowsocks_containers()
                        if containers:
                            message = f"📦 **Active Shadowsocks Containers ({active_count}):**\n\n"
                            buttons = []
                            for container in containers:
                                message += f"🔹 `{container}`\n"
                                buttons.append([{"text": f"🗑 Delete {container}", "callback_data": f"delete_{container}"}])
                            send_telegram_message(message, chat_id=ADMIN_CHAT_ID, reply_markup={"inline_keyboard": buttons})
                        else:
                            send_telegram_message("❌ No active Shadowsocks containers found.", chat_id=ADMIN_CHAT_ID)

                    if callback_data.startswith("delete_") and str(chat_id) == ADMIN_CHAT_ID:
                        container_name = callback_data.split("_", 1)[1]
                        if delete_shadowsocks_container(container_name):
                            send_telegram_message(f"✅ `{container_name}` has been deleted.", chat_id=ADMIN_CHAT_ID)
                        else:
                            send_telegram_message(f"❌ Failed to delete `{container_name}`.", chat_id=ADMIN_CHAT_ID)

                        active_count = count_shadowsocks_containers()
                        send_telegram_message(f"📊 *Active Containers:* `{active_count}`", chat_id=ADMIN_CHAT_ID)

                        send_telegram_message("⚙️ Manage your Shadowsocks containers:", chat_id=ADMIN_CHAT_ID, reply_markup=create_keyboard(ADMIN_CHAT_ID))

            time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing updates: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_telegram_updates()
