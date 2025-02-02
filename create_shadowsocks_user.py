import docker
import random
import string
import requests
import time
import re

# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = '8167962294:AAF3Y2AqbvAmHe7WvB4GOzUIGqmxNFSCgQQ'  # توکن ربات تلگرام خود را وارد کنید
TELEGRAM_CHAT_ID = '71228850'  # شناسه چت تلگرام خود را وارد کنید

# تنظیمات Docker
client = docker.from_env()

def generate_random_password(length=16):
    """تولید پسورد تصادفی"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def send_telegram_message(message):
    """ارسال پیام به تلگرام"""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    response = requests.post(url, data=payload)
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
            message = f"Shadowsocks is running correctly inside the container {container_name} on port {port}. Password: {password}"
            print(message)
            send_telegram_message(message)
        else:
            message = f"Shadowsocks failed to start correctly inside the container {container_name} on port {port}."
            print(message)
            send_telegram_message(message)
    
    except Exception as e:
        print(f"Error creating container {container_name}: {e}")
        send_telegram_message(f"Error creating container {container_name}: {e}")

# اجرای کد
if __name__ == "__main__":
    create_and_check_shadowsocks_container()
