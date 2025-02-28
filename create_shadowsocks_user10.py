import docker
import random
import string
import requests
import time
import re
import json
from datetime import datetime, timedelta
import subprocess

# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = '8167962294:AAF3Y2AqbvAmHe7WvB4GOzUIGqmxNFSCgQQ'
ADMIN_CHAT_ID = '71228850'

# تنظیمات Docker
client = docker.from_env()

# دیکشنری برای اطلاعات کاربر (در حال حاضر استفاده نمی‌شود چون از Labels استفاده می‌کنیم)
user_accounts = {}

def generate_random_password(length=16):
    """تولید پسورد تصادفی"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_server_ip():
    """دریافت آی‌پی سرور"""
    try:
        output = subprocess.check_output(["hostname", "-I"]).decode().strip()
        if output:
            ip = output.split()[0]
            return ip
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
    """پاسخ به callback query"""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery'
    payload = {"callback_query_id": callback_query_id, "text": text, "show_alert": False}
    requests.post(url, data=payload)

def count_shadowsocks_containers():
    """محاسبه تعداد کانتینرهای فعال Shadowsocks"""
    containers = client.containers.list()
    return sum(1 for container in containers if container.name.startswith("shadowsocks_"))

def list_shadowsocks_containers():
    """دریافت لیست همه کانتینرهای Shadowsocks (فعال و غیرفعال)"""
    containers = client.containers.list(all=True)
    return [container for container in containers if container.name.startswith("shadowsocks_")]

def delete_shadowsocks_container(container_name):
    """حذف کانتینر Shadowsocks"""
    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
        return True
    except docker.errors.NotFound:
        return False

def start_shadowsocks_container(container_name):
    """فعال کردن کانتینر Shadowsocks"""
    try:
        container = client.containers.get(container_name)
        if container.status == "running":
            return False, "Container is already running."
        container.start()
        return True, "Container started successfully."
    except docker.errors.NotFound:
        return False, "Container not found."

def stop_shadowsocks_container(container_name):
    """غیرفعال کردن کانتینر Shadowsocks"""
    try:
        container = client.containers.get(container_name)
        if container.status != "running":
            return False, "Container is already stopped."
        container.stop()
        return True, "Container stopped successfully."
    except docker.errors.NotFound:
        return False, "Container not found."

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
    """بررسی امکان ایجاد اکانت جدید"""
    containers = client.containers.list(all=True)
    for container in containers:
        labels = container.labels
        if labels.get("user_id") == str(user_chat_id):
            created_at = datetime.fromisoformat(labels.get("created_at"))
            expiration_date = datetime.fromisoformat(labels.get("expiration_date"))
            if datetime.now() > expiration_date:
                return True
            if container.status == "exited" and (datetime.now() - created_at) < timedelta(days=1):
                return False
            return False
    return True

def create_and_check_shadowsocks_container(user_chat_id):
    """ایجاد کانتینر Shadowsocks و ارسال اطلاعات به کاربر و مدیر"""
    container_name = get_next_container_name()
    port = random.randint(20000, 40000)
    password = generate_random_password()
    server_ip = get_server_ip()
    expiration_date = (datetime.now() + timedelta(days=30)).isoformat()

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
            labels={
                "user_id": str(user_chat_id),
                "created_at": datetime.now().isoformat(),
                "expiration_date": expiration_date
            },
            ports={f"{port}/tcp": ("0.0.0.0", port)},
            detach=True,
            restart_policy={"Name": "always"}
        )
        time.sleep(5)

        # پیام به کاربر
        user_message = (
            f"✅ *Your Shadowsocks Account is Ready!*\n\n"
            f"🔹 *Code:* `{container_name}`\n"
            f"🔹 *IP:* `{server_ip}`\n"
            f"🔹 *Port:* `{port}`\n"
            f"🔹 *Password:* `{password}`\n"
            f"🔹 *Method:* `aes-256-gcm`\n\n"
            f"⚡ *Enjoy your connection!*"
        )
        send_telegram_message(user_message, chat_id=user_chat_id)

        # پیام به مدیر با اطلاعات کامل
        admin_message = (
            f"🔔 *New Shadowsocks Account Created!*\n\n"
            f"👤 *User Chat ID:* `{user_chat_id}`\n"
            f"🔹 *Code:* `{container_name}`\n"
            f"🔹 *IP:* `{server_ip}`\n"
            f"🔹 *Port:* `{port}`\n"
            f"🔹 *Password:* `{password}`\n"
            f"🔹 *Method:* `aes-256-gcm`\n"
            f"⏳ *Expiration:* `{expiration_date}`\n\n"
            f"✅ *Account successfully created.*"
        )
        send_telegram_message(admin_message, chat_id=ADMIN_CHAT_ID)

    except Exception as e:
        error_message = f"❌ *Error creating container {container_name}:* `{e}`"
        send_telegram_message(error_message, chat_id=ADMIN_CHAT_ID)

def create_keyboard(chat_id):
    """ایجاد کیبورد برای ربات"""
    active_containers = count_shadowsocks_containers()
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ Create Shadowsocks Account", "callback_data": "create_shadowsocks"}],
            [{"text": "📚 آموزش اتصال به Shadowsocks", "callback_data": "help_connection"}]
        ]
    }
    if str(chat_id) == ADMIN_CHAT_ID:
        keyboard["inline_keyboard"].append(
            [{"text": f"⚙️ Manage Containers ({active_containers})", "callback_data": "manage_containers"}]
        )
    return keyboard

def process_telegram_updates():
    """پردازش به‌روزرسانی‌های تلگرام"""
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
                            answer_callback_query(callback_query_id, "شما قبلاً یک اکانت فعال دارید!")

                    elif callback_data == "manage_containers" and str(chat_id) == ADMIN_CHAT_ID:
                        containers = list_shadowsocks_containers()
                        active_count = count_shadowsocks_containers()
                        if containers:
                            message = f"📦 **Shadowsocks Containers ({active_count} active):**\n\n"
                            buttons = []
                            for container in containers:
                                status = "فعال" if container.status == "running" else "غیرفعال"
                                message += f"🔹 `{container.name}` ({status})\n"
                                if container.status == "running":
                                    buttons.append([
                                        {"text": f"🛑 Stop {container.name}", "callback_data": f"stop_{container.name}"},
                                        {"text": f"🗑 Delete {container.name}", "callback_data": f"delete_{container.name}"}
                                    ])
                                else:
                                    buttons.append([
                                        {"text": f"▶️ Start {container.name}", "callback_data": f"start_{container.name}"},
                                        {"text": f"🗑 Delete {container.name}", "callback_data": f"delete_{container.name}"}
                                    ])
                            send_telegram_message(message, chat_id=ADMIN_CHAT_ID, reply_markup={"inline_keyboard": buttons})
                        else:
                            send_telegram_message("❌ هیچ کانتینر Shadowsocks یافت نشد.", chat_id=ADMIN_CHAT_ID)

                    elif callback_data.startswith("delete_") and str(chat_id) == ADMIN_CHAT_ID:
                        container_name = callback_data.split("_", 1)[1]
                        if delete_shadowsocks_container(container_name):
                            send_telegram_message(f"✅ `{container_name}` با موفقیت حذف شد.", chat_id=ADMIN_CHAT_ID)
                        else:
                            send_telegram_message(f"❌ خطا در حذف `{container_name}`.", chat_id=ADMIN_CHAT_ID)
                        active_count = count_shadowsocks_containers()
                        send_telegram_message(f"📊 *تعداد کانتینرهای فعال:* `{active_count}`", chat_id=ADMIN_CHAT_ID, reply_markup=create_keyboard(ADMIN_CHAT_ID))

                    elif callback_data.startswith("start_") and str(chat_id) == ADMIN_CHAT_ID:
                        container_name = callback_data.split("_", 1)[1]
                        success, msg = start_shadowsocks_container(container_name)
                        if success:
                            send_telegram_message(f"✅ `{container_name}` با موفقیت فعال شد.", chat_id=ADMIN_CHAT_ID)
                        else:
                            send_telegram_message(f"❌ خطا: {msg}", chat_id=ADMIN_CHAT_ID)
                        active_count = count_shadowsocks_containers()
                        send_telegram_message(f"📊 *تعداد کانتینرهای فعال:* `{active_count}`", chat_id=ADMIN_CHAT_ID, reply_markup=create_keyboard(ADMIN_CHAT_ID))

                    elif callback_data.startswith("stop_") and str(chat_id) == ADMIN_CHAT_ID:
                        container_name = callback_data.split("_", 1)[1]
                        success, msg = stop_shadowsocks_container(container_name)
                        if success:
                            send_telegram_message(f"✅ `{container_name}` با موفقیت غیرفعال شد.", chat_id=ADMIN_CHAT_ID)
                        else:
                            send_telegram_message(f"❌ خطا: {msg}", chat_id=ADMIN_CHAT_ID)
                        active_count = count_shadowsocks_containers()
                        send_telegram_message(f"📊 *تعداد کانتینرهای فعال:* `{active_count}`", chat_id=ADMIN_CHAT_ID, reply_markup=create_keyboard(ADMIN_CHAT_ID))

                    elif callback_data == "help_connection":
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
            send_telegram_message(f"❌ خطا در پردازش: `{e}`", chat_id=ADMIN_CHAT_ID)
            time.sleep(5)

if __name__ == "__main__":
    process_telegram_updates()
