import docker
import random
import string
import requests
import time
import re
import json

# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = '8167962294:AAF3Y2AqbvAmHe7WvB4GOzUIGqmxNFSCgQQ'  # توکن ربات تلگرام
TELEGRAM_CHAT_ID = '71228850'  # شناسه تلگرام مدیر

# تنظیمات Docker
client = docker.from_env()

def generate_random_password(length=16):
    """تولید پسورد تصادفی"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def send_telegram_message(message, chat_id=TELEGRAM_CHAT_ID, reply_markup=None):
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

def count_shadowsocks_containers():
    """محاسبه تعداد کانتینرهای فعال Shadowsocks"""
    containers = client.containers.list()
    return sum(1 for container in containers if container.name.startswith("shadowsocks_"))

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

def create_and_check_shadowsocks_container():
    """ایجاد کانتینر جدید Shadowsocks و ارسال اطلاعات به تلگرام"""
    container_name = get_next_container_name()
    port = random.randint(20000, 40000)
    password = generate_random_password()

    try:
        existing_container = client.containers.get(container_name)
        existing_container.remove(force=True)
    except docker.errors.NotFound:
        pass

    try:
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

        user_message = (
            f"✅ *Your Shadowsocks Account is Ready!*\n\n"
            f"🔹 *Code:* `{container_name}`\n"
            f"🔹 *Port:* `{port}`\n"
            f"🔹 *Password:* `{password}`\n"
            f"🔹 *Method:* `aes-256-gcm`\n\n"
            f"⚡ *Enjoy your connection!*"
        )
        send_telegram_message(user_message)

        active_containers = count_shadowsocks_containers()

        admin_message = (
            f"🛠 **New Shadowsocks Container Created**\n\n"
            f"🔹 **Container Name:** `{container_name}`\n"
            f"🔹 **Port:** `{port}`\n"
            f"🔹 **Password:** `{password}`\n\n"
            f"📌 *Total Active Shadowsocks Containers:* `{active_containers}`"
        )
        send_telegram_message(admin_message, chat_id=TELEGRAM_CHAT_ID)

        # **ارسال دوباره دکمه‌های اصلی بعد از ساخت اکانت**
        send_telegram_message(
            "📌 What do you want to do next?",
            chat_id=TELEGRAM_CHAT_ID,
            reply_markup=create_keyboard()
        )

    except Exception as e:
        send_telegram_message(f"❌ *Error creating container {container_name}:* `{e}`", chat_id=TELEGRAM_CHAT_ID)

def list_active_containers():
    """لیست کانتینرهای Shadowsocks را برای مدیر ارسال می‌کند"""
    containers = client.containers.list()
    shadowsocks_containers = [c for c in containers if c.name.startswith("shadowsocks_")]
    active_count = len(shadowsocks_containers)

    if not shadowsocks_containers:
        send_telegram_message("⚠️ No active Shadowsocks containers found.", chat_id=TELEGRAM_CHAT_ID)
        return

    keyboard = {"inline_keyboard": []}
    message = f"📜 *Active Shadowsocks Containers ({active_count} running):*\n\n"
    
    for container in shadowsocks_containers:
        message += f"🔹 `{container.name}`\n"
        keyboard["inline_keyboard"].append(
            [{"text": f"❌ Delete {container.name}", "callback_data": f"delete_{container.name}"}]
        )

    send_telegram_message(message, chat_id=TELEGRAM_CHAT_ID, reply_markup=keyboard)

def delete_container(container_name):
    """حذف کانتینر Shadowsocks"""
    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
        send_telegram_message(f"✅ *Container {container_name} has been deleted successfully!*", chat_id=TELEGRAM_CHAT_ID)

        # **نمایش تعداد کانتینرهای Shadowsocks باقی‌مانده**
        remaining_count = count_shadowsocks_containers()
        send_telegram_message(f"📌 *Remaining Shadowsocks containers:* `{remaining_count}`", chat_id=TELEGRAM_CHAT_ID)

        # **ارسال دوباره دکمه‌های اصلی به مدیر**
        send_telegram_message(
            "📌 What do you want to do next?",
            chat_id=TELEGRAM_CHAT_ID,
            reply_markup=create_keyboard()
        )

    except docker.errors.NotFound:
        send_telegram_message(f"⚠️ *Container {container_name} not found.*", chat_id=TELEGRAM_CHAT_ID)

def process_telegram_updates():
    """بررسی و پردازش به‌روزرسانی‌های تلگرام"""
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

                if 'message' in update and 'text' in update['message']:
                    if update['message']['text'] == '/start':
                        send_telegram_message(
                            "👋 Welcome! Click the button below to create a new Shadowsocks account.",
                            reply_markup=create_keyboard()
                        )
                    elif update['message']['text'] == '/admin':
                        list_active_containers()

                if "callback_query" in update:
                    callback_data = update["callback_query"].get("data")

                    if callback_data == "create_shadowsocks":
                        create_and_check_shadowsocks_container()
                    elif callback_data == "list_containers":
                        list_active_containers()
                    elif callback_data.startswith("delete_"):
                        container_name = callback_data.replace("delete_", "")
                        delete_container(container_name)

            time.sleep(2)

        except Exception as e:
            time.sleep(5)

def create_keyboard():
    """ایجاد دکمه برای مدیریت اکانت‌ها"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ Create Shadowsocks Account", "callback_data": "create_shadowsocks"}],
            [{"text": "🔧 Manage Containers", "callback_data": "list_containers"}]
        ]
    }
    return keyboard

if __name__ == "__main__":
    process_telegram_updates()

