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

user_accounts = {}
expiration_dates = {}

def generate_random_password(length=16):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_server_ip():
    try:
        output = subprocess.check_output(["hostname", "-I"]).decode().strip()
        if output:
            ip = output.split()[0]
            return ip
        return "Unknown"
    except Exception:
        return "Unknown"

def send_telegram_message(message, chat_id, reply_markup=None):
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
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery'
    payload = {"callback_query_id": callback_query_id, "text": text, "show_alert": False}
    requests.post(url, data=payload)

def count_shadowsocks_containers():
    containers = client.containers.list()
    return sum(1 for container in containers if container.name.startswith("shadowsocks_"))

def list_shadowsocks_containers():
    containers = client.containers.list(all=True)
    return [container for container in containers if container.name.startswith("shadowsocks_")]

def delete_shadowsocks_container(container_name):
    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
        if container_name in expiration_dates:
            del expiration_dates[container_name]
        return True
    except docker.errors.NotFound:
        return False

def start_shadowsocks_container(container_name):
    try:
        container = client.containers.get(container_name)
        if container.status == "running":
            return False, "Container is already running."

        labels = container.labels
        environment = container.attrs['Config']['Env']
        ports = container.attrs['HostConfig']['PortBindings']
        user_chat_id = labels.get("user_id")

        container.stop()
        container.remove()

        new_expiration_date = (datetime.now() + timedelta(days=30)).isoformat()
        expiration_dates[container_name] = new_expiration_date

        new_container = client.containers.run(
            "shadowsocks/shadowsocks-libev",
            name=container_name,
            environment=environment,
            labels={
                "user_id": labels.get("user_id"),
                "created_at": labels.get("created_at")
            },
            ports=ports,
            detach=True,
            restart_policy={"Name": "always"}
        )

        send_telegram_message(
            f"✅ *اکانت شما دوباره فعال شد!*\n\n"
            f"🔹 *Code:* `{container_name}`\n"
            f"⏳ *Expiration:* `{new_expiration_date}`\n"
            f"📡 *ترافیک:* نامحدود\n"
            f"⚡ ادامه لذت از اتصال!",
            chat_id=user_chat_id
        )

        return True, f"Container restarted successfully. New expiration: {new_expiration_date}"
    except docker.errors.NotFound:
        return False, "Container not found."
    except Exception as e:
        return False, f"Error restarting container: {e}"

def stop_shadowsocks_container(container_name):
    try:
        container = client.containers.get(container_name)
        if container.status != "running":
            return False, "Container is already stopped."
        container.stop()
        return True, "Container stopped successfully."
    except docker.errors.NotFound:
        return False, "Container not found."

def extend_container_expiration(container_name):
    try:
        container = client.containers.get(container_name)
        user_chat_id = container.labels.get("user_id")
        new_expiration_date = (datetime.now() + timedelta(days=30)).isoformat()
        expiration_dates[container_name] = new_expiration_date
        
        send_telegram_message(
            f"⏳ *تاریخ انقضای `{container_name}` تمدید شد!*\n"
            f"⏳ *New Expiration:* `{new_expiration_date}`",
            chat_id=ADMIN_CHAT_ID
        )
        send_telegram_message(
            f"⏳ *اکانت شما تمدید شد!*\n\n"
            f"🔹 *Code:* `{container_name}`\n"
            f"⏳ *New Expiration:* `{new_expiration_date}`\n"
            f"📡 *ترافیک:* نامحدود",
            chat_id=user_chat_id
        )
        return True, f"Expiration extended to {new_expiration_date}"
    except docker.errors.NotFound:
        return False, "Container not found."

def check_expired_containers():
    containers = list_shadowsocks_containers()
    for container in containers:
        container_name = container.name
        expiration_date = datetime.fromisoformat(expiration_dates.get(container_name, "1970-01-01T00:00:00"))
        user_chat_id = container.labels.get("user_id")
        remaining_days = (expiration_date - datetime.now()).days

        if datetime.now() > expiration_date and container.status == "running":
            stop_shadowsocks_container(container_name)
            send_telegram_message(
                f"⏰ *Container Expired and Stopped*\n\n"
                f"🔹 *Code:* `{container_name}`\n"
                f"👤 *User Chat ID:* `{user_chat_id}`\n"
                f"⏳ *Expiration Date:* `{expiration_date}`",
                chat_id=ADMIN_CHAT_ID
            )
            send_telegram_message(
                f"⏰ *اکانت شما منقضی شد!*\n\n"
                f"🔹 *Code:* `{container_name}`\n"
                f"📅 *Expired on:* `{expiration_date}`\n"
                f"👉 برای تمدید با پشتیبانی تماس بگیرید: [پشتیبانی](https://t.me/filterali_vpn)",
                chat_id=user_chat_id
            )
        elif 0 < remaining_days <= 1 and container.status == "running":
            send_telegram_message(
                f"⚠️ *هشدار نزدیک شدن به انقضا*\n\n"
                f"🔹 *Code:* `{container_name}`\n"
                f"👤 *User Chat ID:* `{user_chat_id}`\n"
                f"⏳ *Expires in:* `{remaining_days} روز`\n"
                f"👉 برای تمدید اقدام کنید!",
                chat_id=ADMIN_CHAT_ID
            )
            send_telegram_message(
                f"⚠️ *هشدار: اکانت شما نزدیک انقضاست!*\n\n"
                f"🔹 *Code:* `{container_name}`\n"
                f"⏳ *Expires in:* `{remaining_days} روز`\n"
                f"👉 برای تمدید با پشتیبانی تماس بگیرید: [پشتیبانی](https://t.me/filterali_vpn)",
                chat_id=user_chat_id
            )

def get_next_container_name():
    containers = client.containers.list(all=True)
    max_number = 0
    for container in containers:
        match = re.match(r"^shadowsocks_(\d+)$", container.name)
        if match:
            num = int(match.group(1))
            max_number = max(max_number, num)
    return f"shadowsocks_{max_number + 1}"

def can_create_account(user_chat_id):
    containers = client.containers.list(all=True)
    for container in containers:
        labels = container.labels
        if labels.get("user_id") == str(user_chat_id):
            return False
    return True

def create_and_check_shadowsocks_container(user_chat_id):
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
                "created_at": datetime.now().isoformat()
            },
            ports={f"{port}/tcp": ("0.0.0.0", port)},
            detach=True,
            restart_policy={"Name": "always"}
        )
        expiration_dates[container_name] = expiration_date
        time.sleep(5)

        user_message = (
            f"✅ *Your Shadowsocks Account is Ready!*\n\n"
            f"🔹 *Code:* `{container_name}`\n"
            f"🔹 *IP:* `{server_ip}`\n"
            f"🔹 *Port:* `{port}`\n"
            f"🔹 *Password:* `{password}`\n"
            f"🔹 *Method:* `aes-256-gcm`\n"
            f"⏳ *Expiration:* `{expiration_date}`\n"
            f"📡 *ترافیک:* نامحدود\n\n"
            f"⚡ *Enjoy your connection!*"
        )
        send_telegram_message(user_message, chat_id=user_chat_id)

        admin_message = (
            f"🔔 *New Shadowsocks Account Created!*\n\n"
            f"👤 *User Chat ID:* `{user_chat_id}`\n"
            f"🔹 *Code:* `{container_name}`\n"
            f"🔹 *IP:* `{server_ip}`\n"
            f"🔹 *Port:* `{port}`\n"
            f"🔹 *Password:* `{password}`\n"
            f"🔹 *Method:* `aes-256-gcm`\n"
            f"⏳ *Expiration:* `{expiration_date}`\n"
            f"📡 *ترافیک:* نامحدود\n\n"
            f"✅ *Account successfully created.*"
        )
        send_telegram_message(admin_message, chat_id=ADMIN_CHAT_ID)

    except Exception as e:
        error_message = f"❌ *Error creating container {container_name}:* `{e}`"
        send_telegram_message(error_message, chat_id=ADMIN_CHAT_ID)

def get_user_container_status(user_chat_id):
    containers = list_shadowsocks_containers()
    for container in containers:
        if container.labels.get("user_id") == str(user_chat_id):
            status = "فعال" if container.status == "running" else "غیرفعال"
            expiration_date = expiration_dates.get(container.name, "نامشخص")
            remaining_days = (datetime.fromisoformat(expiration_date) - datetime.now()).days
            return f"🔹 *وضعیت اکانت شما:*\n" \
                   f"🔹 *Code:* `{container.name}`\n" \
                   f"🔹 *وضعیت:* `{status}`\n" \
                   f"⏳ *Expiration:* `{expiration_date}`\n" \
                   f"⏳ *روزهای باقی‌مونده:* `{remaining_days if remaining_days > 0 else 'منقضی شده'}`\n" \
                   f"📡 *ترافیک:* نامحدود"
    return "❌ شما اکانتی ندارید!"

def create_keyboard(chat_id):
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
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates'
    last_update_id = None
    last_check_time = time.time()

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
                            "با ربات ما، اکانت Shadowsocks اختصاصی بسازید:\n"
                            "🔑 *مزایا:*\n"
                            "• آی‌پی اختصاصی\n"
                            "• اتصال امن و پایدار\n"
                            "• بدون تایید دستی\n"
                            "• دسترس‌پذیری ۲۴ ساعته\n"
                            "• *ترافیک نامحدود*\n"
                            "🕒 *تست: ۱ ساعت*\n"
                            "💳 *اشتراک: ۹۰ هزار تومان*\n"
                            "👈 [پشتیبانی](https://t.me/filterali_vpn)\n"
                            "💬 *پشتیبانی: ۸ صبح تا ۴ عصر*\n"
                            "📌 فقط یک اکانت برای هر کاربر。\n"
                            "➕ اکانت جدید\n"
                            "📚 آموزش اتصال\n"
                            "ℹ️ وضعیت: /status",
                            chat_id=chat_id,
                            reply_markup=create_keyboard(chat_id)
                        )
                    elif text == '/status':
                        status_message = get_user_container_status(str(chat_id))
                        send_telegram_message(status_message, chat_id=chat_id)

                if "callback_query" in update:
                    callback_data = update["callback_query"].get("data")
                    chat_id = update["callback_query"]["message"]["chat"]["id"]
                    callback_query_id = update["callback_query"]["id"]

                    if callback_data == "create_shadowsocks":
                        if str(chat_id) == ADMIN_CHAT_ID or can_create_account(chat_id):
                            create_and_check_shadowsocks_container(chat_id)
                        else:
                            answer_callback_query(callback_query_id, "ابتدا اکانت قبلی خود را حذف کنید یا با پشتیبانی تماس بگیرید!")

                    elif callback_data == "manage_containers" and str(chat_id) == ADMIN_CHAT_ID:
                        containers = list_shadowsocks_containers()
                        active_count = count_shadowsocks_containers()
                        if containers:
                            message = f"📦 **Shadowsocks Containers ({active_count} active):**\n\n"
                            buttons = []
                            for container in containers:
                                status = "فعال" if container.status == "running" else "غیرفعال"
                                expiration_date = expiration_dates.get(container.name, "نامشخص")
                                if expiration_date != "نامشخص":
                                    remaining_days = (datetime.fromisoformat(expiration_date) - datetime.now()).days
                                    remaining_text = f"{remaining_days} روز" if remaining_days > 0 else "منقضی شده"
                                else:
                                    remaining_days = "نامشخص"
                                    remaining_text = "نامشخص"
                                message += f"🔹 `{container.name}` ({status}) - انقضا: `{expiration_date}` ({remaining_text})\n"
                                row = [{"text": f"⏳ Extend {container.name}", "callback_data": f"extend_{container.name}"}]
                                if container.status == "running":
                                    row.append({"text": f"🛑 Stop {container.name}", "callback_data": f"stop_{container.name}"})
                                else:
                                    row.append({"text": f"▶️ Start {container.name}", "callback_data": f"start_{container.name}"})
                                row.append({"text": f"🗑 Delete {container.name}", "callback_data": f"delete_{container.name}"})
                                buttons.append(row)
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
                            send_telegram_message(f"✅ `{container_name}` با موفقیت فعال شد.\n{msg}", chat_id=ADMIN_CHAT_ID)
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

                    elif callback_data.startswith("extend_") and str(chat_id) == ADMIN_CHAT_ID:
                        container_name = callback_data.split("_", 1)[1]
                        success, msg = extend_container_expiration(container_name)
                        if success:
                            send_telegram_message(f"✅ `{container_name}` با موفقیت تمدید شد.\n{msg}", chat_id=ADMIN_CHAT_ID)
                        else:
                            send_telegram_message(f"❌ خطا: {msg}", chat_id=ADMIN_CHAT_ID)
                        active_count = count_shadowsocks_containers()
                        send_telegram_message(f"📊 *تعداد کانتینرهای فعال:* `{active_count}`", chat_id=ADMIN_CHAT_ID, reply_markup=create_keyboard(ADMIN_CHAT_ID))

                    elif callback_data == "help_connection":
                        connection_instructions = (
                            "📚 *آموزش اتصال به Shadowsocks*\n\n"
                            "1. **ویندوز:**\n"
                            "   - [دانلود](https://github.com/shadowsocks/shadowsocks-windows/releases)\n"
                            "   - تنظیمات: سرور، پورت، پسورد، `aes-256-gcm`\n"
                            "   - اتصال: Connect\n\n"
                            "2. **اندروید:**\n"
                            "   - [دانلود](https://play.google.com/store/apps/details?id=com.github.shadowsocks)\n"
                            "   - تنظیمات: سرور، پورت، پسورد، `aes-256-gcm`\n"
                            "   - اتصال: Connect\n\n"
                            "3. **آیفون:**\n"
                            "   - دانلود از App Store\n"
                            "   - تنظیمات: سرور، پورت، پسورد، `aes-256-gcm`\n"
                            "   - اتصال: Connect\n\n"
                            "4. **مک:**\n"
                            "   - [دانلود](https://github.com/shadowsocks/ShadowsocksX-NG)\n"
                            "   - تنظیمات: سرور، پورت، پسورد، `aes-256-gcm`\n"
                            "   - اتصال: Connect\n\n"
                            "⚡ *Enjoy your connection!*"
                        )
                        send_telegram_message(connection_instructions, chat_id=chat_id)
                        answer_callback_query(callback_query_id)

            current_time = time.time()
            if current_time - last_check_time >= 300:
                check_expired_containers()
                last_check_time = current_time

            time.sleep(2)

        except Exception as e:
            print(f"❌ Error processing updates: {e}")
            send_telegram_message(f"❌ خطا در پردازش: `{e}`", chat_id=ADMIN_CHAT_ID)
            time.sleep(5)

if __name__ == "__main__":
    process_telegram_updates()
