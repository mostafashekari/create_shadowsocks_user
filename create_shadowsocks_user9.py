import docker
import random
import string
import requests
import time
import re
import json
from datetime import datetime, timedelta  # Added for time tracking
import subprocess  # For running shell commands

# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = '8167962294:AAF3Y2AqbvAmHe7WvB4GOzUIGqmxNFSCgQQ'  # Replace with your token
ADMIN_CHAT_ID = '71228850'  # شناسه تلگرام مدیر

# تنظیمات Docker
client = docker.from_env()

# This dictionary maps a user's chat id (as a string) to their account info:
# { chat_id: { "container_name": <name>, "created_at": <datetime>, "expiration_date": <datetime> } }
user_accounts = {}

def generate_random_password(length=16):
    """تولید پسورد تصادفی"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_server_ip():
    """
    دریافت آی‌پی سرور از طریق اجرای دستور 'hostname -I' در اوبونتو.
    خروجی معمولاً شامل چندین آی‌پی (space separated) است؛
    در اینجا از اولین آی‌پی استفاده می‌شود.
    در صورت بروز خطا، مقدار "Unknown" برگردانده می‌شود.
    """
    try:
        output = subprocess.check_output(["hostname", "-I"]).decode().strip()
        if output:
            # خروجی ممکن است شامل چندین آی‌پی باشد؛ اولین آی‌پی انتخاب می‌شود.
            ip = output.split()[0]
            return ip
        else:
            return "Unknown"
    except Exception:
        return "Unknown"

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
      - اگر تاریخ انقضای اکانت گذشته باشد، اجازه داده می‌شود.
    """
    user_id = str(user_chat_id)
    if user_id not in user_accounts:
         return True

    account_info = user_accounts[user_id]
    container_name = account_info["container_name"]
    
    # بررسی تاریخ انقضا
    expiration_date = account_info["expiration_date"]
    if datetime.now() > expiration_date:
        # اکانت منقضی شده است، اجازه ساخت اکانت جدید داده می‌شود
        del user_accounts[user_id]
        return True

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
    server_ip = get_server_ip()  # دریافت آی‌پی سرور از داخل اوبونتو

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
            f"🔹 *IP:* `{server_ip}`\n"
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
            expiration_date = datetime.now() + timedelta(days=30)  # تاریخ انقضا بعد از 30 روز
            user_accounts[str(user_chat_id)] = {
                "container_name": container_name,
                "created_at": datetime.now(),
                "expiration_date": expiration_date
            }

    except Exception as e:
        error_message = f"❌ *Error creating container {container_name}:* `{e}`"
        send_telegram_message(error_message, chat_id=ADMIN_CHAT_ID)

def create_keyboard(chat_id):
    """ایجاد دکمه برای مدیریت یا ساخت اکانت جدید"""
    active_containers = count_shadowsocks_containers()
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ Create Shadowsocks Account", "callback_data": "create_shadowsocks"}],
            [{"text": "📚 آموزش اتصال به Shadowsocks", "callback_data": "help_connection"}]  # دکمه جدید
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
                            "👋 *سلام خوش آمدید!*\n\n"
                            "با ربات ما، شما می‌توانید به‌راحتی و بلافاصله اکانت Shadowsocks اختصاصی خود را بسازید و از اینترنت آزاد و امن بهره‌مند شوید. تنها با یک دکمه، اکانت جدید شما آماده است و در لحظه اطلاعات آن برای شما ارسال می‌شود.\n\n"
                            "🔑 *مزایای Shadowsocks:*\n"
                            "• *آی‌پی اختصاصی*: اکانت شما با یک آی‌پی اختصاصی به شما تعلق می‌گیرد که از امنیت و دسترسی منحصر به فرد برخوردار خواهید بود.\n"
                            "• *اتصال امن و پایدار*: از اینترنت بدون محدودیت و با امنیت بالا استفاده کنید.\n"
                            "• *بدون تایید دستی*: اطلاعات اکانت شما بلافاصله پس از ساخت ارسال خواهد شد.\n"
                            "• *دسترس‌پذیری ۲۴ ساعته*: حتی در ساعات غیرکاری نیز می‌توانید اکانت خود را بسازید و از اینترنت آزاد استفاده کنید.\n\n"
                            "🕒 *مهلت تست اکانت شما: ۱ ساعت*\n"
                            "در این مدت می‌توانید از سرویس به‌صورت کامل استفاده کنید و اگر از عملکرد آن راضی بودید، برای خرید اشتراک یک ماهه اقدام کنید.\n\n"
                            "💳 *اشتراک یک ماهه: ۹۰ هزار تومان*\n"
                            "اگر از کیفیت سرویس راضی بودید و خواستید اشتراک یک ماهه تهیه کنید، فقط کافی است به پشتیبانی تلگرام پیام دهید:\n\n"
                            "👈 [پشتیبانی تلگرام](https://t.me/filterali_vpn)\n\n"
                            "💬 *پشتیبانی در دسترس شماست!*\n"
                            "پشتیبانی از ۸ صبح تا ۴ عصر آماده پاسخگویی به شما است. "
                            "اگر سوال یا مشکلی داشتید، در این ساعات می‌توانید با ما تماس بگیرید.\n"
                            "ما سعی می‌کنیم در سریع‌ترین زمان ممکن به شما کمک کنیم.\n\n"
                            "📌 *نکته:* در صورتی که سوال یا مشکلی داشتید، حتماً در ساعات ذکر شده با پشتیبانی تماس بگیرید تا پاسخ سریع‌تری دریافت کنید.\n\n"
                            "*نکته مهم:*\n"
                            "هر کاربر می‌تواند فقط یک اکانت برای خود بسازد. "
                            "در صورتی که نیاز به اکانت‌های بیشتری داشته باشید، باید با پشتیبانی هماهنگ کنید تا درخواست شما رسیدگی شود.\n\n"
                            "*با دکمه‌های ربات بیشتر آشنا شوید:*\n"
                            "➕ *Create Shadowsocks Account*\n"
                            "برای ایجاد یک اکانت جدید، روی این دکمه کلیک کنید.\n\n"
                            "*📚 آموزش اتصال به Shadowsocks*\n"
                            "راهنمای گام به گام برای اتصال به Shadowsocks در دستگاه‌های مختلف.",
                            chat_id=chat_id,
                            reply_markup=create_keyboard(chat_id)
                        )

                if "callback_query" in update:
                    callback_data = update["callback_query"].get("data")
                    chat_id = update["callback_query"]["message"]["chat"]["id"]
                    callback_query_id = update["callback_query"]["id"]

                    if callback_data == "create_shadowsocks":
                        if str(chat_id) == ADMIN_CHAT_ID or can_create_account(chat_id):
                            create_and_check_shadowsocks_container(chat_id)
                        else:
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

                    if callback_data == "help_connection":
                        connection_instructions = (
                            "📚 *آموزش اتصال به Shadowsocks*\n\n"
                            "1. **برای ویندوز:**\n"
                            "   - ابتدا آخرین نسخه‌ی نرم‌افزار Shadowsocks برای ویندوز را از [گیت‌هاب Shadowsocks-Windows](https://github.com/shadowsocks/shadowsocks-windows/releases) دانلود و نصب کنید.\n"
                            "   - بعد از نصب، برنامه Shadowsocks را باز کنید.\n"
                            "   - روی آیکون Shadowsocks در نوار وظیفه کلیک کرده و \"Settings\" را انتخاب کنید.\n"
                            "   - آدرس سرور، پورت و پسورد را وارد کنید.\n"
                            "   - گزینه‌ی `aes-256-gcm` را به عنوان روش انتخاب کنید.\n"
                            "   - برای اتصال، از منوی Shadowsocks گزینه \"Connect\" را انتخاب کنید.\n\n"
                            "2. **برای اندروید:**\n"
                            "   - اپلیکیشن Shadowsocks را از [Google Play](https://play.google.com/store/apps/details?id=com.github.shadowsocks) دانلود و نصب کنید.\n"
                            "   - روی آیکون \"+\" کلیک کنید.\n"
                            "   - آدرس سرور، پورت و پسورد را وارد کنید.\n"
                            "   - روش `aes-256-gcm` را انتخاب کنید.\n"
                            "   - برای اتصال، روی \"Connect\" کلیک کنید.\n\n"
                            "3. **برای آیفون:**\n"
                            "   - اپلیکیشن Shadowsocks را از App Store دانلود و نصب کنید.\n"
                            "   - روی آیکون \"+\" کلیک کنید.\n"
                            "   - آدرس سرور، پورت و پسورد را وارد کنید.\n"
                            "   - روش `aes-256-gcm` را انتخاب کنید.\n"
                            "   - برای اتصال، روی \"Connect\" کلیک کنید.\n\n"
                            "4. **برای مک:**\n"
                            "   - ShadowsocksX-NG را از [گیت‌هاب ShadowsocksX-NG](https://github.com/shadowsocks/ShadowsocksX-NG) دانلود و نصب کنید.\n"
                            "   - برنامه را باز کرده و در منوی Preferences، آدرس سرور، پورت و پسورد را وارد کنید.\n"
                            "   - روش `aes-256-gcm` را انتخاب کنید.\n"
                            "   - برای اتصال، روی \"Connect\" کلیک کنید.\n\n"
                            "⚡ *Enjoy your connection!*"
                        )
                        send_telegram_message(connection_instructions, chat_id=chat_id)
                        answer_callback_query(callback_query_id)

            time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing updates: {e}")
            time.sleep(5)

if __name__ == "__main__":
    process_telegram_updates()
