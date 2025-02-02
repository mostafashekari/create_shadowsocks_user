import docker
import random
import string
import requests
import time
import re
import json  # اضافه کردن کتابخانه JSON برای بررسی ساختار دکمه‌ها

# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = '8167962294:AAF3Y2AqbvAmHe7WvB4GOzUIGqmxNFSCgQQ'  # توکن ربات تلگرام خود را وارد کنید
TELEGRAM_CHAT_ID = '71228850'  # شناسه چت تلگرام خود را وارد کنید

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
        'text': message
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)  # استفاده از json.dumps برای تبدیل به فرمت صحیح
    response = requests.post(url, data=payload)
    print(f"Sending message: {message}")  # چاپ برای بررسی
    print(f"Response: {response.text}")  # چاپ پاسخ برای اشکال‌زدایی
    return response.json()

def check_shadowsocks_status(container):
    """چک کردن وضعیت شادوساکس در کانتینر"""
    try:
        # چک کردن با دستور pgrep
        result = container.exec_run("pgrep -f ss-server")
        if result.exit_code == 0:
            return True
        return False
    except Exception as e:
        print(f"Error checking Shadowsocks status: {e}")
        return False

def get_next_container_name():
    """دریافت نام بعدی برای کانتینر"""
    containers = client.containers.list(all=True)
    max_number = 0
    # جستجو برای کانتینرهایی که اسم آن‌ها به صورت shadowsocks_ شماره است
    for container in containers:
        match = re.match(r"^shadowsocks_(\d+)$", container.name)
        if match:
            num = int(match.group(1))
            max_number = max(max_number, num)
    
    # شماره بعدی کانتینر
    return f"shadowsocks_{max_number + 1}"

def create_and_check_shadowsocks_container():
    """ایجاد کانتینر جدید شادوساکس و ارسال نتیجه به تلگرام"""
    # دریافت نام کانتینر جدید
    container_name = get_next_container_name()
    port = random.randint(1024, 65535)
    
    # تولید پسورد تصادفی
    password = generate_random_password()
    
    # حذف کانتینر با همین نام اگر موجود باشد
    try:
        existing_container = client.containers.get(container_name)
        existing_container.remove(force=True)
        print(f"Container {container_name} already exists and was removed.")
    except docker.errors.NotFound:
        print(f"No existing container with name {container_name}.")

    # ایجاد کانتینر جدید
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
            ports={f"{port}/tcp": port},
            detach=True
        )
        
        # بررسی وضعیت شادوساکس
        time.sleep(5)  # مدت زمانی برای راه‌اندازی کانتینر
        if check_shadowsocks_status(container):
            message = f"Your Shadowsocks Account:\n\nPort: {port}\nPassword: {password}"
            print(message)
            send_telegram_message(message, reply_markup=create_keyboard())
        else:
            message = f"Shadowsocks failed to start correctly inside the container {container_name} on port {port}."
            print(message)
            send_telegram_message(message, reply_markup=create_keyboard())
    
    except Exception as e:
        print(f"Error creating container {container_name}: {e}")
        send_telegram_message(f"Error creating container {container_name}: {e}", reply_markup=create_keyboard())

def create_keyboard():
    """ایجاد دکمه برای ساخت کانتینر جدید"""
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Create Shadowsocks Container", "callback_data": "create_shadowsocks"}
            ]
        ]
    }
    return keyboard

def process_telegram_updates():
    """بررسی به روز رسانی های تلگرام و پردازش آن ها"""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates'
    last_update_id = None
    
    while True:
        try:
            # دریافت به روز رسانی های جدید
            response = requests.get(url)
            updates = response.json().get('result', [])
            
            if updates:
                print("Received updates:", updates)  # چاپ به روز رسانی ها برای بررسی

            for update in updates:
                update_id = update["update_id"]
                if update_id != last_update_id:
                    last_update_id = update_id
                    
                    # بررسی پیام /start و ارسال دکمه
                    if 'message' in update and 'text' in update['message'] and update['message']['text'] == '/start':
                        print("Received /start command")
                        send_telegram_message("Welcome to the Shadowsocks Bot! Click the button below to create a new Shadowsocks container.", reply_markup=create_keyboard())
                    
                    # بررسی callback_query برای دریافت دکمه
                    if "callback_query" in update:
                        callback_data = update["callback_query"].get("data")
                        print(f"Callback query received: {callback_data}")  # برای بررسی دقیق‌تر داده‌ها
                        if callback_data == "create_shadowsocks":
                            print("Received 'create_shadowsocks' callback")  # برای بررسی
                            create_and_check_shadowsocks_container()

                    # حذف به روز رسانی ها بعد از پردازش
                    requests.get(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={update_id+1}')
                
            time.sleep(2)
        except Exception as e:
            print(f"Error while processing updates: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_telegram_updates()
