#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==========================================================================
⚡ NEXUS ASYNC EXTREME CORE + WEB SERVER (KEEP ALIVE) ⚡
 Starlink (Ruijie) Voucher Scanner + Telegram Bot  |  Replit Optimized
--------------------------------------------------------------------------
 FULL FEATURES MAINTAINED (LOGIC UNCHANGED)
 WEB SERVER ADDED TO KEEP BOT ONLINE ON REPLIT FREE TIER
 STRICTLY NO MYANMAR TEXT IN CODE.
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
from threading import Thread

from urllib.parse import urljoin

import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType

import ddddocr
from flask import Flask

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
#  KEEP ALIVE WEB SERVER (FOR REPLIT)
# ==============================================================================

app_web = Flask('')

@app_web.route('/')
def home():
    return "Nexus Bot is Alive and Running 24/7!"

def run_web():
    app_web.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ==============================================================================
#  CONFIG
# ==============================================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

ADMIN_IDS = [7294591323]

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

NUM_WORKERS = 1
MAX_CODES_PER_SESSION = 15
MAX_CODES_PER_SID = 15
TIMEOUT_SEC = 10

# Proxy settings
USE_PROXY = True
PROXY_TIMEOUT = 10
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
CHARSET_ABC = "abcdefghijkmnpqrstuvwxyz"
CHARSET_MIX = "0123456789abcdefghijklmnopqrstuvwxyz"

_CHARSET_DIGITS_T = tuple(CHARSET_DIGITS)
_CHARSET_ABC_T = tuple(CHARSET_ABC)
_CHARSET_MIX_T = tuple(CHARSET_MIX)

MODES = {
    "num6": "💎 06 • NUM",
    "num7": "💎 07 • NUM",
    "num8": "💎 08 • NUM",
    "num9": "💎 09 • NUM",
    "eng6": "🚀 06 • ENG",
    "eng7": "🚀 07 • ENG",
    "eng8": "🚀 08 • ENG",
    "mix6": "⚡ 06 • MIX",
    "mix7": "⚡ 07 • MIX",
    "mix8": "⚡ 08 • MIX",
    "abc6": "📜 06 • ABC",
    "custom": "🔮 Custom",
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


# ==============================================================================
#  BANNER / LICENSE
# ==============================================================================

def show_banner():
    line = "═" * 60
    print(bcyan + line)
    print("   ⚡  NEXUS EXTREME • REPLIT KEEP-ALIVE  ⚡   ")
    print("            Telegram @ravenboii            ")
    print(line + reset)
    print(white + "Initializing web server & core protocols..." + reset)


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
    print(yellow + f"[*] Nexus License Remaining: {time_str}  ")
    print(f"[-] Expiration Date: ({expiry_date.strftime('%Y-%m-%d %H:%M')}) " + reset)


def check_approval():
    if not os.path.exists(OWNER_LICENSE_FILE):
        print(bgreen + "[+] Nexus Portal Granted Access!" + reset)
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
                        print(bred + f"[!] OWNER LICENSE EXPIRED" + reset)
                        sys.exit(1)
                    print(bgreen + "[+] Nexus Portal Granted Access!" + reset)
                    display_remaining_time(expiry_date)
                    return
    except Exception as e:
        print(yellow + f"[License] Error: {e}" + reset)
    print(bgreen + "[+] Nexus Portal Granted Access!" + reset)


# ==============================================================================
#  PAID KEY SYSTEM
# ==============================================================================

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