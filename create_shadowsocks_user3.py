import docker
import random
import string
import requests
import time
import re
import json

# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = '8167962294:AAF3Y2AqbvAmHe7WvB4GOzUIGqmxNFSCgQQ'  # توکن ربات تلگرام
ADMIN_CHAT_ID = '71228850'  # شناسه تلگرام مدیر

# تنظیمات Docker
client = docker.from_env()

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

    except Exception as e:
        error_message = f"❌ *Error creating container {container_name}:* `{e}`"
        send_telegram_message(error_message, chat_id=ADMIN_CHAT_ID)

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

                    if callback_data == "create_shadowsocks":
                        create_and_check_shadowsocks_container(chat_id)

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

if __name__ == "__main__":
    process_telegram_updates()


