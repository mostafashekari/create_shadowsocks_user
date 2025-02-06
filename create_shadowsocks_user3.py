import docker
import random
import string
import requests
import time
import re
import json

# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = '8167962294:AAF3Y2AqbvAmHe7WvB4GOzUIGqmxNFSCgQQ'  # توکن ربات تلگرام خود را وارد کنید
TELEGRAM_CHAT_ID = '71228850'  # شناسه چت تلگرام شما را وارد کنید

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

def check_shadowsocks_status(container):
    """بررسی وضعیت Shadowsocks درون کانتینر"""
    try:
        result = container.exec_run("pgrep -f ss-server")
        return result.exit_code == 0
    except Exception as e:
        print(f"⚠️ Error checking Shadowsocks status: {e}")
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

def create_and_check_shadowsocks_container():
    """ایجاد کانتینر جدید شادوساکس و ارسال اطلاعات به تلگرام"""
    container_name = get_next_container_name()
    port = random.randint(20000, 40000)  # انتخاب پورت تصادفی بین 20000 تا 40000
    password = generate_random_password()

    # حذف کانتینر قبلی در صورت وجود
    try:
        existing_container = client.containers.get(container_name)
        existing_container.remove(force=True)
        print(f"Container {container_name} already exists and was removed.")
    except docker.errors.NotFound:
        print(f"No existing container with name {container_name}.")

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
        logs = container.logs().decode('utf-8')
        print(f"Container Logs: \n{logs}")

        if check_shadowsocks_status(container):
            message = f"✅ *Shadowsocks Account Created!*\n\n🔹 *Port:* `{port}`\n🔹 *Password:* `{password}`\n🔹 *Method:* `aes-256-gcm`\n\n⚡ *Enjoy your connection!*"
            send_telegram_message(message, reply_markup=create_keyboard())
        else:
            message = f"⚠️ *Shadowsocks failed to start correctly in container {container_name}*."
            send_telegram_message(message, reply_markup=create_keyboard())

    except Exception as e:
        print(f"❌ Error creating container {container_name}: {e}")
        send_telegram_message(f"❌ *Error creating container {container_name}:* `{e}`", reply_markup=create_keyboard())

def create_keyboard():
    """ایجاد دکمه برای ساخت اکانت جدید"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ Create Shadowsocks Account", "callback_data": "create_shadowsocks"}]
        ]
    }
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
            
            if updates:
                print("Received updates:", updates)

            for update in updates:
                update_id = update["update_id"]
                last_update_id = update_id  # ذخیره آخرین آپدیت پردازش شده
                
                # بررسی پیام /start و ارسال دکمه
                if 'message' in update and 'text' in update['message'] and update['message']['text'] == '/start':
                    send_telegram_message("👋 Welcome! Click the button below to create a new Shadowsocks account.", reply_markup=create_keyboard())

                # بررسی callback_query برای دریافت دکمه
                if "callback_query" in update:
                    callback_data = update["callback_query"].get("data")
                    if callback_data == "create_shadowsocks":
                        create_and_check_shadowsocks_container()

            time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing updates: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_telegram_updates()
