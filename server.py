import base64
import copy
import email
import email.header
import email.utils
import hashlib
import hmac
import imaplib
import json
import logging
import os
import random
import re
import secrets
import string
import subprocess
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import uiautomator2 as u2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ==========================================
# الإعدادات العامة
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "nusuk_engine.log")
STATE_FILE = os.path.join(BASE_DIR, "nusuk_state.json")
SHOTS_DIR = os.path.join(BASE_DIR, "fail_shots")
INDEX_FILE = os.getenv("NUSUK_INDEX_FILE", os.path.join(BASE_DIR, "index.html"))
os.makedirs(SHOTS_DIR, exist_ok=True)
MAX_SHOT_FILES = 120

LDPLAYER_PATH = os.getenv("LDPLAYER_PATH", r"C:\LDPlayer\LDPlayer9")
LDCONSOLE = os.path.join(LDPLAYER_PATH, "ldconsole.exe")
PACKAGE_NAME = os.getenv("NUSUK_PACKAGE", "com.moh.nusukapp")

EMUS = {
    "emu1": {
        "serial": os.getenv("EMU1_SERIAL", "emulator-5596"),
        "index": os.getenv("EMU1_INDEX", "21"),
        "label": "المحاكي الأول (الرئيسي)",
    },
    "emu2": {
        "serial": os.getenv("EMU2_SERIAL", "emulator-5594"),
        "index": os.getenv("EMU2_INDEX", "20"),
        "label": "المحاكي الثاني (المرافق)",
    },
}

FINGERPRINT_EVERY = 5
MAX_COMPANIONS = 3
DEFAULT_PASSWORD = os.getenv("NUSUK_DEFAULT_PASSWORD", "Msamy2006**")
LOCK_WAIT = float(os.getenv("NUSUK_LOCK_WAIT", "0"))
HOST = os.getenv("NUSUK_HOST", "127.0.0.1")
PORT = int(os.getenv("NUSUK_PORT", "8000"))

_raw_origins = os.getenv("NUSUK_ALLOWED_ORIGINS", "*").strip()
ALLOWED_ORIGINS = ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",") if o.strip()]

WELCOME_MARKERS = [
    "هل أنت مستعد",
    "تسجيل الدخول أو إنشاء حساب",
    "متابعة كضيف",
    "Continue as",
    "ready to start",
    "Login or Sign up",
    "Log in or Sign up",
]
LOGIN_MARKERS = [
    "هل أنت مستعد",
    "تسجيل الدخول أو إنشاء حساب",
    "تسجيل الدخول للمتابعة",
    "أنشئ حسابًا جديدًا",
    "أنشئ حسابك",
    "Create",
    "Sign up",
    "Register",
    "تسجيل الدخول",
    "Login",
    "Log in",
]
CREATE_MARKERS = ["أنشئ حسابًا جديدًا", "أنشئ حسابك", "Create", "Sign up", "Register"]
ALREADY_KEYS = [
    "مسجل مسبق", "مسجّل مسبق", "مسجل باسم حساب", "مسجّل باسم حساب",
    "سجل الخروج واستعد حسابك", "سجّل الخروج واستعد حسابك", "استعد حسابك",
    "رقم الهوية مسجل", "رقم الهوية مسجّل", "مرتبط بحساب آخر",
    "مسجل بالفعل", "موجود مسبق", "مسجلة مسبق", "لديك حساب",
    "already registered", "already exists", "account already",
]
SUCCESS_KEYS = ["exploring", "استكشاف", "نجاح"]
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
ARABIC_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")


def strip_arabic_diacritics(text: str) -> str:
    return ARABIC_DIACRITICS_RE.sub("", text or "")

# ==========================================
# Logging
# ==========================================
def setup_logging() -> logging.Logger:
    logger = logging.getLogger("nusuk")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.propagate = False
    return logger


log = setup_logging()

# ==========================================
# الحالة المحفوظة
# ==========================================
_state_lock = threading.RLock()


def _default_group() -> dict:
    return {"leader_active": False, "leader_name": None, "leader_id": None, "companions": []}


def _default_state() -> dict:
    return {
        "counters": {"emu1": 0, "emu2": 0},
        "group": _default_group(),
        "health": {"emu1": {"ok": True, "reason": ""}, "emu2": {"ok": True, "reason": ""}},
        "speed_multiplier": 1.0,
    }


def load_state() -> dict:
    st = _default_state()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for k in st["counters"]:
            st["counters"][k] = int(saved.get("counters", {}).get(k, 0))
        g = saved.get("group", {})
        for k in st["group"]:
            if k in g:
                st["group"][k] = g[k]
        for k in st["health"]:
            h = saved.get("health", {}).get(k)
            if isinstance(h, dict):
                st["health"][k] = {"ok": bool(h.get("ok", True)), "reason": str(h.get("reason", ""))}
        if "speed_multiplier" in saved:
            st["speed_multiplier"] = float(saved["speed_multiplier"])
        log.info("تم تحميل الحالة المحفوظة من %s", STATE_FILE)
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("تعذر قراءة ملف الحالة (%s) - البدء بحالة جديدة", e)
    return st


STATE = load_state()


def save_state():
    with _state_lock:
        tmp = STATE_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(STATE, f, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception as e:
            log.error("فشل حفظ الحالة: %s", e)


def reset_group():
    with _state_lock:
        STATE["group"] = _default_group()
    save_state()


def set_health(emu_key: str, ok: bool, reason: str = ""):
    with _state_lock:
        STATE["health"][emu_key] = {"ok": ok, "reason": reason}
    save_state()


# ==========================================
# الاتصال بالمحاكيات + أدوات مقاومة اللاج
# ==========================================
OP_LOCK = threading.Lock()


@contextmanager
def exclusive(wait: float = 0.0):
    got = OP_LOCK.acquire(timeout=wait) if wait > 0 else OP_LOCK.acquire(blocking=False)
    try:
        yield got
    finally:
        if got:
            OP_LOCK.release()


class FlowError(Exception):
    pass


_devices_cache = {}


def get_device(serial: str, timeout: int = 120):
    if serial in _devices_cache:
        try:
            if _devices_cache[serial].info.get("screenOn") is not None:
                return _devices_cache[serial]
        except Exception:
            _devices_cache.pop(serial, None)

    start_t = time.time()
    while time.time() - start_t < timeout:
        try:
            dev = u2.connect(serial)
            if dev.info.get("screenOn") is not None:
                _devices_cache[serial] = dev
                return dev
        except Exception:
            pass
        time.sleep(1.5)
    raise RuntimeError(f"تعذر الاتصال بالمحاكي {serial}")


def smart_sleep(base_seconds: float, mult: float = 1.0):
    time.sleep(max(0.1, base_seconds * mult))


def wait_for_network_loading(dev, max_wait: float = 12.0) -> bool:
    start_t = time.time()
    time.sleep(0.25)
    while time.time() - start_t < max_wait:
        try:
            xml_str = dev.dump_hierarchy()
            is_loading = (
                "ProgressBar" in xml_str
                or "جاري التحميل" in xml_str
                or "يرجى الانتظار" in xml_str
                or "Loading" in xml_str
                or "Please wait" in xml_str
            )
            if not is_loading:
                return True
        except Exception:
            pass
        time.sleep(0.6)
    return False


def wait_edits(dev, min_count: int, timeout: float = 7.0, interval: float = 0.25):
    end = time.time() + timeout
    while True:
        edits = dev(className="android.widget.EditText")
        if len(edits) >= min_count:
            return edits
        if time.time() >= end:
            return None
        time.sleep(interval)


def wait_app_foreground(dev, package: str, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if dev.app_current().get("package") == package:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ==========================================
# قواميس تحويل الجنسيات
# ==========================================
NAT_TO_ENGLISH = {
    "تايلاند": "Thailand", "مصر": "Egypt", "المغرب": "Morocco", "الجزائر": "Algeria",
    "تونس": "Tunisia", "الأردن": "Jordan", "الاردن": "Jordan", "العراق": "Iraq",
    "السودان": "Sudan", "اليمن": "Yemen", "لبنان": "Lebanon", "سوريا": "Syria",
    "فلسطين": "Palestine", "الكويت": "Kuwait", "الإمارات": "United Arab Emirates",
    "الامارات": "United Arab Emirates", "قطر": "Qatar", "البحرين": "Bahrain",
    "عمان": "Oman", "تركيا": "Turkey", "باكستان": "Pakistan", "الهند": "India",
    "بنغلاديش": "Bangladesh", "بنجلاديش": "Bangladesh", "إندونيسيا": "Indonesia",
    "اندونيسيا": "Indonesia", "ماليزيا": "Malaysia", "بريطانيا": "United Kingdom",
    "فرنسا": "France", "ألمانيا": "Germany", "المانيا": "Germany",
    "أمريكا": "United States", "امريكا": "United States",
}

NAT_TO_ARABIC = {
    "thailand": "تايلاند", "egypt": "مصر", "morocco": "المغرب", "algeria": "الجزائر",
    "tunisia": "تونس", "jordan": "الأردن", "iraq": "العراق", "sudan": "السودان",
    "yemen": "اليمن", "lebanon": "لبنان", "syria": "سوريا", "palestine": "فلسطين",
    "kuwait": "الكويت", "united arab emirates": "الإمارات", "qatar": "قطر",
    "bahrain": "البحرين", "oman": "عمان", "turkey": "تركيا", "pakistan": "باكستان",
    "india": "الهند", "bangladesh": "بنغلاديش", "indonesia": "إندونيسيا",
    "malaysia": "ماليزيا", "united kingdom": "بريطانيا", "france": "فرنسا",
    "germany": "ألمانيا", "united states": "أمريكا",
}


def get_both_nat_versions(raw_nat: str, default_y: int):
    clean = raw_nat.strip()
    ar_ver = NAT_TO_ARABIC.get(clean.lower(), clean)
    en_ver = NAT_TO_ENGLISH.get(clean, clean)

    if clean in NAT_TO_ENGLISH:
        ar_ver = clean
        en_ver = NAT_TO_ENGLISH[clean]
    elif clean.lower() in NAT_TO_ARABIC:
        ar_ver = NAT_TO_ARABIC[clean.lower()]
        en_ver = clean

    final_y = 275 if (ar_ver == "مصر" or en_ver.lower() == "egypt") else default_y
    return ar_ver, en_ver, final_y


def visible_text_without_inputs(xml_str: str) -> str:
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
    except Exception:
        return xml_str.lower()
    parts = []
    for node in root.iter():
        if node.attrib.get("class") == "android.widget.EditText":
            continue
        t = node.attrib.get("text") or ""
        d = node.attrib.get("content-desc") or ""
        if t:
            parts.append(t)
        if d:
            parts.append(d)
    return " ".join(parts).lower()


def smart_search_nationality(dev, raw_nat: str, default_y: int, mult: float = 1.0):
    ar_ver, en_ver, final_y = get_both_nat_versions(raw_nat, default_y)
    dump_xml = dev.dump_hierarchy()
    visible_init = visible_text_without_inputs(dump_xml)
    if any(eng_c in visible_init for eng_c in ("afghanistan", "albania", "algeria", "bahrain")):
        is_arabic_screen = False
    elif any(ar_c in visible_init for ar_c in ("أفغانستان", "افغانستان", "ألبانيا", "الجزائر", "البحرين")):
        is_arabic_screen = True
    else:
        is_arabic_screen = bool(re.search(r"[\u0600-\u06FF]", visible_init))

    first_try = ar_ver if is_arabic_screen else en_ver
    second_try = en_ver if is_arabic_screen else ar_ver

    target_box = None
    try:
        edits = dev(className="android.widget.EditText")
        if len(edits) > 0:
            target_box = min(edits, key=lambda el: el.info.get("bounds", {}).get("top", 9999))
            target_box.click()
        else:
            dev.click(540, 115)
    except Exception:
        target_box = None
        dev.click(540, 115)

    smart_sleep(0.25, mult)
    wrote = False
    if target_box is not None:
        try:
            target_box.set_text(first_try)
            wrote = True
        except Exception:
            wrote = False
    if not wrote:
        dev.click(540, 115)
        smart_sleep(0.15, mult)
        dev.send_keys(first_try, clear=True)

    smart_sleep(0.65, mult)
    after_dump = dev.dump_hierarchy()
    visible = visible_text_without_inputs(after_dump)
    no_result_keywords = ["no result", "not found", "no data", "لا توجد", "لا يوجد", "غير موجود"]

    need_fallback = any(k in visible for k in no_result_keywords) or (first_try[:3].lower() not in visible)

    if need_fallback and first_try != second_try:
        log.info(f"تبديل فوري للجنسية إلى ({second_try})")
        wrote2 = False
        if target_box is not None:
            try:
                target_box.set_text(second_try)
                wrote2 = True
            except Exception:
                wrote2 = False
        if not wrote2:
            dev.click(540, 115)
            smart_sleep(0.15, mult)
            dev.send_keys(second_try, clear=True)
        smart_sleep(0.65, mult)

    return final_y


# ==========================================
# دالة الريستارت وفتح التطبيق
# ==========================================
def restart_and_randomize_ldplayer(emu_key: str) -> bool:
    emu = EMUS[emu_key]
    emu_index = emu["index"]
    emu_serial = emu["serial"]
    emu_name = emu["label"]

    log.info("#" * 60)
    log.info(f"[*] تغيير البصمة وإعادة التشغيل لـ {emu_name} (Index: {emu_index})...")
    log.info("#" * 60)

    _devices_cache.pop(emu_serial, None)

    try:
        subprocess.run([
            LDCONSOLE, "modify", "--index", emu_index,
            "--androidid", "auto", "--mac", "auto", "--imei", "auto"
        ], check=True)
        log.info(f"[✓] تم تحديث معرّفات {emu_name} بنجاح.")

        subprocess.run([LDCONSOLE, "reboot", "--index", emu_index], check=True)
        log.info(f"[*] إرسال أمر ريستارت لـ {emu_name}.. في انتظار الإقلاع...")

        time.sleep(15)
        dev = get_device(emu_serial, timeout=180)
        time.sleep(5)

        subprocess.run([LDCONSOLE, "runapp", "--index", emu_index, "--packagename", PACKAGE_NAME])
        time.sleep(2)

        nusuk_icon = dev(text="Nusuk")
        if not nusuk_icon.exists:
            nusuk_icon = dev(text="نسك")

        if nusuk_icon.exists:
            nusuk_icon.click()
        else:
            dev.click(694, 280)

        time.sleep(10)
        pass_welcome_screen_if_needed(dev)
        set_health(emu_key, True, "")
        log.info(f"[✓] التطبيق مفتوح وجاهز على {emu_name}!")
        return True

    except Exception as e:
        log.error(f"[X] خطأ أثناء تدوير بصمة {emu_name}: {e}")
        set_health(emu_key, False, "restart_failed")
        return False


def bump_counter(emu_key: str):
    with _state_lock:
        STATE["counters"][emu_key] += 1
        n = STATE["counters"][emu_key]
    save_state()
    log.info(f"عداد بصمة {EMUS[emu_key]['label']}: {n}/{FINGERPRINT_EVERY}")
    if n >= FINGERPRINT_EVERY:
        if restart_and_randomize_ldplayer(emu_key):
            with _state_lock:
                STATE["counters"][emu_key] = 0
            save_state()


# ==========================================
# قراءة OTP من Gmail
# ==========================================
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5, "يونيو": 6,
    "يوليو": 7, "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12
}
OTP_KEYWORDS = ["nusuk", "نسك", "verification", "رمز", "otp"]
_used_otp_ids = set()


def _imap_date(dt: datetime) -> str:
    return f"{dt.day:02d}-{MONTHS[dt.month - 1]}-{dt.year}"


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    return re.sub(r"(?s)<[^>]+>", " ", html)


def message_text(msg) -> str:
    texts = []
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="ignore")
        except LookupError:
            text = payload.decode("utf-8", errors="ignore")
        if ctype == "text/html":
            text = _html_to_text(text)
        texts.append(text)
    return "\n".join(texts)


def _decode_header(raw) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(raw or "")))
    except Exception:
        return str(raw or "")


def _msg_timestamp(msg) -> Optional[float]:
    try:
        dt = email.utils.parsedate_to_datetime(msg.get("Date"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _open_imap(user: str, password: str):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=15)
    except TypeError:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(user, password)
    return mail


def fetch_nusuk_otp(client_email: str, client_pass: str, timeout: int = 55, sent_after: Optional[float] = None) -> Optional[str]:
    log.info(f"مراقبة كود OTP على: {client_email}...")
    start_time = time.time()
    min_ts = (sent_after - 15) if sent_after is not None else (start_time - 45)
    clean_pass = client_pass.replace(" ", "")
    year_str = str(datetime.now().year)
    checked = set()
    mail = None
    last_err_text = None

    if len(_used_otp_ids) > 200:
        _used_otp_ids.clear()

    try:
        while time.time() - start_time < timeout:
            try:
                if mail is None:
                    mail = _open_imap(client_email, clean_pass)
                mail.select("inbox")
                since = _imap_date(datetime.now(timezone.utc) - timedelta(days=1))
                status, messages = mail.search(None, "SINCE", since)
                ids = messages[0].split() if status == "OK" and messages and messages[0] else []

                for mid in reversed(ids[-15:]):
                    status, data = mail.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
                    if status != "OK" or not data or not isinstance(data[0], tuple):
                        continue
                    head = email.message_from_bytes(data[0][1])
                    msgid = (head.get("Message-ID") or "").strip() or mid.decode(errors="ignore")
                    key = f"{client_email}|{msgid}"
                    if key in checked or key in _used_otp_ids:
                        continue
                    ts = _msg_timestamp(head)
                    if ts is not None and ts < min_ts:
                        checked.add(key)
                        continue

                    status, data = mail.fetch(mid, "(BODY.PEEK[])")
                    if status != "OK" or not data or not isinstance(data[0], tuple):
                        continue
                    msg = email.message_from_bytes(data[0][1])
                    sender = (msg.get("From") or "").lower()
                    subject = _decode_header(msg.get("Subject")).lower()
                    body = message_text(msg)

                    if any(k in sender or k in subject or k in body.lower() for k in OTP_KEYWORDS):
                        codes = [c for c in re.findall(r"\b\d{4}\b", body) if c != year_str]
                        if codes:
                            otp = codes[0]
                            mail.store(mid, "+FLAGS", "\\Seen")
                            _used_otp_ids.add(key)
                            log.info(f"[✓] تم التقاط OTP: {otp}")
                            return otp
                    checked.add(key)

            except imaplib.IMAP4.error as e:
                text = str(e)
                if "AUTHENTICATIONFAILED" in text.upper() or "invalid credentials" in text.lower():
                    raise FlowError("فشل الدخول لإيميل الـ OTP - تأكد من الإيميل وكلمة App Password")
                if text != last_err_text:
                    log.warning(f"خطأ IMAP: {text}")
                    last_err_text = text
                mail = None
            except FlowError:
                raise
            except Exception as e:
                text = f"{type(e).__name__}: {e}"
                if text != last_err_text:
                    log.warning(f"خطأ أثناء قراءة البريد: {text}")
                    last_err_text = text
                mail = None

            time.sleep(1.0)
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass
    return None


# ==========================================
# تسجيل الخروج + الدرع الذاتي لمنع التخريف المتسلسل
# ==========================================
def perform_safe_logout(dev, slow: bool = True):
    log.info("سحب القائمة لأسفل لتسجيل الخروج...")
    time.sleep(1.2)
    dev.swipe(0.5, 0.85, 0.5, 0.15, steps=25)
    time.sleep(1.0)
    dev.swipe(0.5, 0.85, 0.5, 0.15, steps=25)
    time.sleep(1.2)

    log.info("النقر على تسجيل الخروج (540, 1730)...")
    dev.click(540, 1730)
    time.sleep(1.5)

    clicked_confirm = False
    for _ in range(3):
        for txt in ["نعم", "تأكيد", "ديكأت", "موافق", "Yes", "Confirm", "Logout", "Log out"]:
            btn_confirm = dev(textContains=txt)
            if btn_confirm.exists:
                btn_confirm.click()
                clicked_confirm = True
                break
        if clicked_confirm:
            break
        time.sleep(0.5)

    if not clicked_confirm:
        dev.click(540, 1150)

    time.sleep(3.0)
    wait_for_network_loading(dev, max_wait=6.0)


def pass_welcome_screen_if_needed(dev, mult: float = 1.0) -> bool:
    """تخطي الشاشة الترحيبية (هل أنت مستعد لبدء رحلتك؟ -> تسجيل الدخول أو إنشاء حساب) إن وُجدت"""
    try:
        dump = dev.dump_hierarchy()
        if "تسجيل الدخول للمتابعة" in dump or "أنشئ حسابًا جديدًا" in dump:
            return True
        if any(m in dump for m in WELCOME_MARKERS):
            log.info("تخطي شاشة البداية الترحيبية (تسجيل الدخول أو إنشاء حساب)...")
            btn = dev(textContains="تسجيل الدخول أو إنشاء حساب")
            if not btn.exists:
                btn = dev(textContains="Login or Sign up")
            if not btn.exists:
                btn = dev(textContains="Log in or Sign up")
            if btn.exists:
                btn.click()
            else:
                dev.click(540, 1768)
            smart_sleep(1.2, mult)
            wait_for_network_loading(dev, max_wait=6.0)
            return True
    except Exception:
        pass
    return False


def open_registration_form(dev, mult: float = 1.0):
    """يضمن الوصول لشاشة إنشاء الحساب (الـ 3 خانات) سواء من الشاشة الترحيبية أو النافذة السفلية المنبثقة"""
    for _ in range(3):
        edits = dev(className="android.widget.EditText")
        if len(edits) >= 3:
            return edits

        dump = dev.dump_hierarchy()

        # لو دخل بالخطأ على شاشة تسجيل الدخول بالبريد (خانتين فقط)، نرجع بالسهم العلوي (1019, 91)
        if len(edits) == 2 or "مرحبًا بعودتك" in dump or "تسجيل الدخول إلى حسابك" in dump:
            dev.click(1019, 91)
            smart_sleep(1.0, mult)
            dump = dev.dump_hierarchy()

        # 1. لو على الشاشة الترحيبية ("هل أنت مستعد لبدء رحلتك؟") نضغط الزر الأسود (540, 1768)
        if ("تسجيل الدخول للمتابعة" not in dump and "أنشئ حسابًا جديدًا" not in dump) and any(
            m in dump for m in WELCOME_MARKERS
        ):
            log.info("الضغط على الزر الأسود (تسجيل الدخول أو إنشاء حساب)...")
            btn_w = dev(textContains="تسجيل الدخول أو إنشاء حساب")
            if btn_w.exists:
                btn_w.click()
            else:
                dev.click(540, 1768)
            smart_sleep(1.2, mult)
            dump = dev.dump_hierarchy()

        # 2. الآن على النافذة المنبثقة ("تسجيل الدخول للمتابعة") -> نضغط "أنشئ حسابًا جديدًا" (540, 1704)
        clicked = False
        for txt in CREATE_MARKERS:
            if txt in dump:
                btn = dev(textContains=txt)
                if not btn.exists:
                    btn = dev(descriptionContains=txt)
                if btn.exists:
                    btn[-1].click()
                    clicked = True
                    break

        if not clicked:
            dev.click(540, 1704)

        inputs = wait_edits(dev, 3, timeout=4.5 * mult)
        if inputs is not None:
            return inputs
    return None


def on_login_screen(dev) -> bool:
    try:
        if dev.app_current().get("package") != PACKAGE_NAME:
            return False
        dump = dev.dump_hierarchy()
        return any(t in dump for t in LOGIN_MARKERS) or len(dev(className="android.widget.EditText")) >= 3
    except Exception:
        return False


def _wait_login_screen(dev, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if on_login_screen(dev):
            return True
        time.sleep(0.6)
    return False


def force_clean_login_state(dev, emu_key: str) -> bool:
    label = EMUS[emu_key]["label"]
    idx = EMUS[emu_key]["index"]

    try:
        if on_login_screen(dev):
            return True
    except Exception:
        pass

    log.warning(f"🛡️ [{label}] الشاشة ليست على نقطة البداية! جاري التنظيف الذاتي قبل البدء...")

    try:
        dev.app_stop(PACKAGE_NAME)
        time.sleep(1.0)
        subprocess.run([LDCONSOLE, "runapp", "--index", idx, "--packagename", PACKAGE_NAME])
        time.sleep(2.0)
        if not wait_app_foreground(dev, PACKAGE_NAME, 4.0):
            nusuk_icon = dev(text="Nusuk")
            if not nusuk_icon.exists:
                nusuk_icon = dev(text="نسك")
            if nusuk_icon.exists:
                nusuk_icon.click()
            else:
                dev.click(694, 280)
        time.sleep(6.0)
        wait_for_network_loading(dev, max_wait=8.0)
    except Exception as e:
        log.warning(f"خطأ أثناء إعادة فتح التطبيق: {e}")

    if _wait_login_screen(dev, timeout=5.0):
        log.info(f"[✓] [{label}] تم استعادة شاشة الدخول بنجاح!")
        return True

    log.warning(f"[{label}] يوجد حساب سابق عالق بالداخل.. جاري إخراجه إجبارياً...")
    try:
        for _ in range(3):
            dev.click(1000, 100)
            time.sleep(0.25)
        dev.click(52, 103)
        time.sleep(0.6)
        dev.click(1019, 91)
        time.sleep(0.8)
        dev.click(65, 101)
        time.sleep(1.8)
        perform_safe_logout(dev, slow=True)
    except Exception:
        pass

    if _wait_login_screen(dev, timeout=6.0):
        log.info(f"[✓] [{label}] تم إخراج الحساب العالق والعودة لشاشة الدخول!")
        return True

    log.error(f"[{label}] تعذر الوصول لشاشة الدخول بعد التنظيف الذاتي")
    return False


def reopen_nusuk_app(dev, emu_key: str, mult: float = 1.0) -> bool:
    """إغلاق تطبيق نسك وإعادة فتحه للوصول النظيف للشاشة الرئيسية بدون لخبطة في التنقل"""
    label = EMUS[emu_key]["label"]
    idx = EMUS[emu_key]["index"]
    log.info(f"🔄 [{label}] إعادة تشغيل تطبيق نسك للرجوع للشاشة الرئيسية النظيفة...")
    try:
        dev.app_stop(PACKAGE_NAME)
        time.sleep(1.0)
        subprocess.run([LDCONSOLE, "runapp", "--index", idx, "--packagename", PACKAGE_NAME])
        time.sleep(2.0)
        if not wait_app_foreground(dev, PACKAGE_NAME, 4.0):
            nusuk_icon = dev(text="Nusuk")
            if not nusuk_icon.exists:
                nusuk_icon = dev(text="نسك")
            if nusuk_icon.exists:
                nusuk_icon.click()
            else:
                dev.click(694, 280)
        time.sleep(5.0 * mult)
        wait_for_network_loading(dev, max_wait=8.0)
        pass_welcome_screen_if_needed(dev, mult=mult)
        smart_sleep(1.5, mult)

        # التأكد من اختفاء أي نوافذ وظهور الشاشة الرئيسية
        for _ in range(10):
            dump = dev.dump_hierarchy()
            if any(h in dump for h in ("المحفظة", "العمرة", "الروضة", "نسك AI", "حجز تصريح")):
                log.info(f"[✓] [{label}] تم فتح تطبيق نسك والوصول للشاشة الرئيسية بنجاح!")
                return True
            if any(m in dump for m in WELCOME_MARKERS):
                pass_welcome_screen_if_needed(dev, mult=mult)
            if "تابع واستكشف" in dump or "استكشف" in dump:
                click_text_in_xml(dev, dump, ("تابع واستكشف", "استكشف", "تابع"), min_y=1600, max_y=1900)
            time.sleep(0.8)
        return True
    except Exception as e:
        log.warning(f"خطأ أثناء إعادة تشغيل تطبيق نسك: {e}")
        return False


def save_failure_artifacts(dev, tag: str) -> Optional[str]:
    if dev is None:
        return None
    try:
        os.makedirs(SHOTS_DIR, exist_ok=True)
        fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{tag}"
        base = os.path.join(SHOTS_DIR, fname)
        dev.screenshot(base + ".png")
        try:
            with open(base + ".xml", "w", encoding="utf-8") as f:
                f.write(dev.dump_hierarchy())
        except Exception:
            pass
        files = sorted(
            (os.path.join(SHOTS_DIR, n) for n in os.listdir(SHOTS_DIR)),
            key=os.path.getmtime,
        )
        for old in files[:-MAX_SHOT_FILES]:
            try:
                os.remove(old)
            except Exception:
                pass
        return f"/fail_shots/{fname}.png"
    except Exception as e:
        log.warning(f"تعذر حفظ لقطة الفشل: {e}")
        return None


# ==========================================
# استخراج بيانات الملف الشخصي + إدارة صفحة الأصدقاء
# ==========================================
def click_text_in_xml(dev, xml_str: str, targets: tuple, min_y: int = 0, max_y: int = 1920) -> bool:
    """البحث عن نص داخل XML الملتقط (مع تجاهل التشكيل والشدّة) والضغط على مركز العنصر فوراً بدون استدعاءات RPC إضافية"""
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
        lowered_targets = [strip_arabic_diacritics(t).lower() for t in targets]
        for node in root.iter():
            t = strip_arabic_diacritics(node.attrib.get("text") or "").strip().lower()
            d = strip_arabic_diacritics(node.attrib.get("content-desc") or "").strip().lower()
            if not t and not d:
                continue
            if any(lt in t or lt in d for lt in lowered_targets):
                bounds = node.attrib.get("bounds") or ""
                bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                if bm:
                    x1, y1, x2, y2 = map(int, bm.groups())
                    cy = (y1 + y2) // 2
                    if min_y <= cy <= max_y:
                        cx = (x1 + x2) // 2
                        dev.click(cx, cy)
                        return True
    except Exception:
        pass
    return False


def is_on_friends_show_all_page(xml_str: str) -> bool:
    """التحقق الصارم أن الشاشة داخل صفحة الأصدقاء (Show All) وليست على صفحة البروفايل الخارجية"""
    profile_only_markers = (
        "عرض الكل", "Show All", "Show all", "بطاقاتي", "My Cards",
        "البطاقات والتصاريح", "التصاريح السارية", "Active Permits", "الحجوزات",
    )
    if any(pm in xml_str for pm in profile_only_markers):
        return False
    show_all_markers = (
        "جميع الأصدقاء", "All Friends", "المفضلة", "Favorites",
        "اضف للمفضلة", "إدارة علاقاتك", "Manage your",
    )
    return any(sm in xml_str for sm in show_all_markers)


def get_add_friend_input_box(dev):
    """إرجاع مربع إدخال Nusuk ID في نافذة إضافة صديق (top > 200 لتجاهل مربع البحث العلوي في صفحة الأصدقاء)"""
    try:
        for el in dev(className="android.widget.EditText"):
            top = el.info.get("bounds", {}).get("top", 0)
            if top > 200:
                return el
    except Exception:
        pass
    return None


def is_add_friend_dialog_open(dev) -> bool:
    return get_add_friend_input_box(dev) is not None


def wait_add_friend_dialog(dev, timeout: float):
    end_t = time.time() + timeout
    while time.time() < end_t:
        box = get_add_friend_input_box(dev)
        if box is not None:
            return box
        time.sleep(0.25)
    return None


def ensure_leader_on_friends_page(dev1, mult: float = 1.0) -> bool:
    """ضمان وجود المحاكي الأول داخل صفحة الأصدقاء (Show All) وإعادته إليها تلقائياً لو خرج منها لأي سبب"""
    for attempt in range(3):
        if is_add_friend_dialog_open(dev1):
            dev1.press("back")
            smart_sleep(1.0, mult)

        dump1 = dev1.dump_hierarchy()
        if is_on_friends_show_all_page(dump1):
            return True

        if attempt > 0:
            log.warning(f"🛡️ المحاكي الأول ليس في صفحة الأصدقاء (محاولة {attempt + 1}/3) - جاري فتح Show All...")
        else:
            log.info("فتح/استعادة صفحة الأصدقاء (Show All) في المحاكي الأول...")

        profile_markers = (
            "عرض الكل", "Show All", "Show all", "بطاقاتي", "My Cards",
            "العائلة والأصدقاء", "Family & Friends", "البطاقات والتصاريح",
        )
        leader_id_val = (STATE.get("group") or {}).get("leader_id") or ""
        if any(m in dump1 for m in profile_markers) or (leader_id_val and leader_id_val in dump1):
            if not click_text_in_xml(dev1, dump1, ("عرض الكل", "Show All", "Show all"), min_y=700, max_y=1300):
                dev1.click(140, 1025)
            smart_sleep(1.3, mult)
            wait_for_network_loading(dev1, max_wait=6.0)
        elif any(m in dump1 for m in ("التصاريح", "Permits", "أكمل", "نوع الهوية")):
            dev1.click(1019, 91)
            smart_sleep(1.3, mult)
            wait_for_network_loading(dev1, max_wait=6.0)
            dump_prof = dev1.dump_hierarchy()
            if not click_text_in_xml(dev1, dump_prof, ("عرض الكل", "Show All", "Show all"), min_y=700, max_y=1300):
                dev1.click(140, 1025)
            smart_sleep(1.3, mult)
        else:
            dev1.click(65, 101)
            smart_sleep(1.5, mult)
            wait_for_network_loading(dev1, max_wait=6.0)
            dump_prof = dev1.dump_hierarchy()
            if not click_text_in_xml(dev1, dump_prof, ("عرض الكل", "Show All", "Show all"), min_y=700, max_y=1300):
                dev1.click(140, 1025)
            smart_sleep(1.3, mult)

    return is_on_friends_show_all_page(dev1.dump_hierarchy())


def _click_add_friend_on_show_all(dev1, comp_num: int, mult: float = 1.0):
    add_labels = ("أضف صديق", "إضافة صديق", "اضف صديق", "Add friend", "Add Friend")
    dump1 = dev1.dump_hierarchy()
    if click_text_in_xml(dev1, dump1, add_labels, min_y=400, max_y=1850):
        return
    # لو القائمة طويلة ونزل الزر لأسفل الشاشة نسحب سحبة خفيفة للأعلى ثم نبحث عنه
    if comp_num >= 2:
        dev1.swipe(0.5, 0.75, 0.5, 0.35, steps=12)
        smart_sleep(0.45, mult)
        dump2 = dev1.dump_hierarchy()
        if click_text_in_xml(dev1, dump2, add_labels, min_y=350, max_y=1850):
            return
    if comp_num == 1:
        dev1.click(540, 1151)
    elif comp_num == 2:
        dev1.click(804, 943)
    else:
        dev1.click(804, 1106)


def open_add_friend_and_send_request(dev1, comp_id: str, comp_num: int, mult: float = 1.0):
    """فتح نافذة إضافة صديق في المحاكي الأول وكتابة الـ ID وإرسال الطلب بموثوقية عالية جداً"""
    id_box = None
    for attempt in range(3):
        ensure_leader_on_friends_page(dev1, mult=mult)
        _click_add_friend_on_show_all(dev1, comp_num, mult=mult)
        id_box = wait_add_friend_dialog(dev1, timeout=(2.8 if attempt == 0 else 3.5) * mult)
        if id_box is not None:
            break
        log.warning(f"إعادة محاولة فتح شاشة إضافة صديق في المحاكي الأول ({attempt + 1}/3)...")

    if id_box is None:
        save_failure_artifacts(dev1, "emu1_add_friend_fail")
        raise FlowError("لم تظهر شاشة إضافة صديق في المحاكي الأول")

    smart_sleep(0.25, mult)
    wrote_id = False
    try:
        b = id_box.info.get("bounds", {})
        cx = (b.get("left", 100) + b.get("right", 980)) // 2
        cy = (b.get("top", 400) + b.get("bottom", 490)) // 2
        dev1.click(cx, cy)
        smart_sleep(0.2, mult)
        id_box.set_text(comp_id)
        wrote_id = True
    except Exception:
        wrote_id = False

    if not wrote_id:
        dev1.click(540, 445)
        smart_sleep(0.25, mult)
        dev1.send_keys(comp_id, clear=True)

    smart_sleep(0.25, mult)
    dev1.shell("input keyevent 111")
    smart_sleep(0.35, mult)

    dev1.click(540, 1742)
    smart_sleep(1.5, mult)
    wait_for_network_loading(dev1, max_wait=10.0)

    # تأكيد إغلاق نافذة الإدخال وإرسال الطلب فعلياً
    if is_add_friend_dialog_open(dev1):
        log.warning("نافذة إدخال الصديق ما زالت مفتوحة - إعادة الضغط على زر الإرسال (540, 1742)...")
        dev1.shell("input keyevent 111")
        smart_sleep(0.3, mult)
        dev1.click(540, 1742)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev1, max_wait=8.0)
        if is_add_friend_dialog_open(dev1):
            dev1.press("back")
            smart_sleep(0.8, mult)


def fast_extract_id_and_name(dev, max_wait: float = 4.0) -> Tuple[Optional[str], str]:
    start_t = time.time()
    nusuk_id = None
    profile_name = "معتمر"

    while time.time() - start_t < max_wait:
        xml_str = dev.dump_hierarchy()

        m = re.search(r"Nusuk ID\s*(\d+)", xml_str, re.IGNORECASE)
        if m:
            nusuk_id = m.group(1)
        else:
            m2 = re.search(r"\b(20\d{2}\d{8,12})\b", xml_str)
            if m2:
                nusuk_id = m2.group(1)

        if nusuk_id:
            try:
                root = ET.fromstring(xml_str.encode("utf-8"))
                for node in root.iter():
                    txt = (node.attrib.get("text") or "").strip()
                    bounds = node.attrib.get("bounds") or ""
                    if txt and "Cards" not in txt and "Nusuk" not in txt and bounds:
                        bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                        if bm:
                            top_y = int(bm.group(2))
                            if 140 <= top_y <= 260:
                                profile_name = txt
                                break
            except Exception:
                pass
            return nusuk_id, profile_name

        time.sleep(0.35)

    return nusuk_id, profile_name


def reach_profile_and_extract_id(dev, mult: float = 1.0) -> Tuple[Optional[str], str]:
    """استخراج Nusuk ID والاسم مع محاولة استرجاع تلقائية لصفحة البروفايل لو تأخر الانتقال إليها"""
    nid, pname = fast_extract_id_and_name(dev, max_wait=3.5 * mult)
    if nid:
        return nid, pname

    dump = dev.dump_hierarchy()
    dump_low = dump.lower()
    if any(k in dump_low for k in SUCCESS_KEYS):
        dev.click(540, 1793)
        smart_sleep(1.3, mult)
        wait_for_network_loading(dev, max_wait=6.0)
        dev.click(1019, 91)
        smart_sleep(1.5, mult)
    elif any(k in dump for k in ("التصاريح", "Permits", "أكمل", "نوع الهوية")):
        dev.click(1019, 91)
        smart_sleep(1.5, mult)
    else:
        dev.click(65, 101)
        smart_sleep(1.5, mult)

    wait_for_network_loading(dev, max_wait=6.0)
    return fast_extract_id_and_name(dev, max_wait=3.5 * mult)


def _norm_key(s) -> str:
    return str(s).strip().replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").lower()


def extract_field(p: dict, keys) -> str:
    wanted = {_norm_key(k) for k in keys}
    for k, v in p.items():
        if _norm_key(k) in wanted:
            return str(v).strip()
    return ""


def close_leader_group(dev1) -> bool:
    log.info("إنهاء مجموعة الحساب الرئيسي من المحاكي الأول...")
    ok = True
    try:
        if is_add_friend_dialog_open(dev1):
            dev1.press("back")
            time.sleep(0.8)
        dump1 = dev1.dump_hierarchy()
        if is_on_friends_show_all_page(dump1):
            dev1.click(52, 103)
            time.sleep(1.2)
        perform_safe_logout(dev1, slow=True)
        if not on_login_screen(dev1):
            ok = force_clean_login_state(dev1, "emu1")
    except Exception as e:
        log.error(f"فشل خروج الحساب الرئيسي: {e}")
        ok = force_clean_login_state(dev1, "emu1")
    reset_group()
    if ok:
        bump_counter("emu1")
    return ok


# ==========================================
# فحص تصاريح الروضة ونظام استرجاع الحساب
# ==========================================
def evaluate_rawdah_permits_from_xml(xml_str: str) -> Tuple[bool, str, dict]:
    """
    فحص تصاريح الروضة الشريفة من شاشة المواعيد:
    - لو حاجز لنفسه حالياً (مؤكد / منتظر التأكيد / ساري) -> مينفعش
    - لو مستخدم أو منتهي:
      - لو عدى 365 يوم على أحدث تصريح -> ينفع
      - لو لم يمر 365 يوم -> مينفعش
    - لو لا توجد أي تصاريح روضة سابقة -> ينفع
    """
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
        nodes = [n.attrib.get("text", "").strip() for n in root.iter() if n.attrib.get("text")]
    except Exception:
        nodes = []

    permits = []
    curr = None
    for t in nodes:
        if "رقم الحجز" in t:
            if curr:
                permits.append(curr)
            curr = {"id": t, "type": "", "status": "", "date_str": "", "time_str": "", "date": None}
        elif curr:
            if "تصريح الروضة" in t:
                curr["type"] = t
            elif any(s in t for s in ("مستخدم", "منتهي", "ساري", "ملغى", "ملغي", "مؤكد", "مؤكّد", "منتظر التأكيد", "بانتظار التأكيد")):
                curr["status"] = t
            elif re.match(r"^\d{1,2}:\d{2}$", t):
                curr["time_str"] = t
            else:
                m = re.match(r"(\d{1,2})\s+([\u0621-\u064A]+)\s+(\d{4})", t)
                if m:
                    day, mon_name, yr = int(m.group(1)), m.group(2), int(m.group(3))
                    mon = AR_MONTHS.get(mon_name)
                    if mon:
                        curr["date_str"] = t
                        curr["date"] = datetime(yr, mon, day)
    if curr:
        permits.append(curr)

    rawdah_permits = [p for p in permits if "الروضة" in p.get("type", "")]

    # 1. هل المعتمر حاجز لنفسه حالياً (مؤكد أو بانتظار التأكيد)؟
    active_keywords = ("مؤكد", "مؤكّد", "منتظر التأكيد", "بانتظار التأكيد", "ساري", "قادم", "فعال")
    active_rawdah = [p for p in rawdah_permits if any(k in p.get("status", "") for k in active_keywords)]
    if active_rawdah:
        p = active_rawdah[0]
        date_disp = p.get("date_str") or "محدد"
        time_disp = p.get("time_str") or ""
        stat_disp = p.get("status") or "مؤكد"
        reason = f"مينفعش - المعتمر حاجز لنفسه تصريح روضة ({stat_disp}) بتاريخ {date_disp} {time_disp}".strip()
        return False, reason, {"status": stat_disp, "date": date_disp, "time": time_disp, "type": p.get("type")}

    # 2. فحص التصاريح السابقة (مستخدم / منتهي)
    used_rawdah = [p for p in rawdah_permits if any(k in p.get("status", "") for k in ("مستخدم", "منتهي")) and p.get("date")]
    now = datetime.now()
    if used_rawdah:
        latest = max(used_rawdah, key=lambda x: x["date"])
        days_passed = (now - latest["date"]).days
        date_disp = latest.get("date_str") or str(latest["date"].date())
        if days_passed >= 365:
            reason = f"ينفع - عدى أكثر من سنة ({days_passed} يوم) على آخر تصريح روضة بتاريخ {date_disp}"
            return True, reason, {"status": latest.get("status"), "date": date_disp, "days_passed": days_passed, "type": latest.get("type")}
        else:
            reason = f"مينفعش - دخل الروضة بتاريخ {date_disp} (مر فقط {days_passed} يوم ولم يكمل سنة)"
            return False, reason, {"status": latest.get("status"), "date": date_disp, "days_passed": days_passed, "type": latest.get("type")}

    # 3. لا توجد تصاريح روضة مستخدمة أو مؤكدة
    reason = "ينفع - لا توجد أي تصاريح روضة سابقة للمعتمر"
    return True, reason, {"status": "none", "date": None}


def run_account_recovery_flow(dev, req, role: str, comp_num: int, emu_key: str, mult: float = 1.0) -> dict:
    p = req.pilgrim or {}
    email_val = extract_field(p, ["email", "البريد الالكتروني", "البريد الإلكتروني", "Email", "الايميل"]) or req.client_email.strip()
    password_val = extract_field(p, ["password", "الباسورد", "كلمة المرور", "Password", "pass"]) or DEFAULT_PASSWORD
    passport_val = extract_field(p, ["رقم الجواز", "الجواز", "passport_number", "Passport", "passport", "رقم وثيقة السفر"])
    visa_val = extract_field(p, ["رقم الفيزا", "الفيزا", "رقم التاشيره", "رقم التأشيرة", "التاشيره", "التأشيرة", "visa_number", "Visa", "visa"])
    raw_nat = str(req.nationality or req.nationality_text or req.search_text or p.get("nationality") or "مصر").strip()
    default_nat_y = int(req.nationality_y or req.option_y or req.choice_y or 275)

    label = EMUS[emu_key]["label"]
    log.info(f"🔄 [{label}] بدء مسار استرجاع الحساب للمعتمر: {passport_val} / {visa_val}...")

    # 1. الانتقال لشاشة استعد حسابك
    dump = dev.dump_hierarchy()
    dump_clean = strip_arabic_diacritics(dump)

    # إذا كانت نافذة "رقم الهوية مسجّل مسبقًا" مفتوحة، نضغط الزر الأسود "سجّل الخروج واستعد حسابك" (540, 1770)
    if "سجل الخروج واستعد حسابك" in dump_clean or "مسجل مسبق" in dump_clean or "مسجل باسم حساب" in dump_clean:
        log.info(f"[{label}] الضغط على زر 'سجّل الخروج واستعد حسابك'...")
        if not click_text_in_xml(dev, dump, ("سجل الخروج واستعد حسابك", "استعد حسابك", "سجل الخروج"), min_y=1500, max_y=1850):
            dev.click(540, 1770)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=10.0)
        # الضغط مرتين في أعلى منتصف الشاشة لإغلاق أي نافذة منبثقة
        dev.click(540, 300)
        smart_sleep(0.5, mult)
        dev.click(540, 300)
        smart_sleep(0.8, mult)
        dump = dev.dump_hierarchy()
        dump_clean = strip_arabic_diacritics(dump)

    # فحص الشاشة الحالية بعد الضغط على الزر الأسود (أو عند البدء اليدوي)
    if "تسجيل الحساب من جديد" in dump_clean or "كافة الزوار" in dump_clean or "زائر دولي" in dump_clean:
        log.info(f"[{label}] تم فتح شاشة 'تسجيل الحساب من جديد' مباشرة ✓")
    elif "استعد حسابك" in dump_clean or "استعادة حسابك" in dump_clean:
        if not click_text_in_xml(dev, dump, ("استعد حسابك", "استعادة حسابك"), min_y=1400, max_y=1850):
            dev.click(780, 1650)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=8.0)
    elif "لديك مشكلة" in dump_clean:
        if not click_text_in_xml(dev, dump, ("لديك مشكلة",), min_y=600, max_y=1200):
            dev.click(500, 845)
        smart_sleep(1.2, mult)
        dev.click(780, 1650)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=8.0)
    else:
        if not (any(m in dump_clean for m in WELCOME_MARKERS) or "تسجيل الدخول أو إنشاء حساب" in dump_clean or "الدخول بواسطة البريد" in dump_clean):
            force_clean_login_state(dev, emu_key)
            dump = dev.dump_hierarchy()
            dump_clean = strip_arabic_diacritics(dump)

        if any(m in dump_clean for m in WELCOME_MARKERS) or "تسجيل الدخول أو إنشاء حساب" in dump_clean:
            dev.click(540, 1768)
            smart_sleep(1.2, mult)

        dump_sheet = dev.dump_hierarchy()
        dump_sheet_clean = strip_arabic_diacritics(dump_sheet)
        if "الدخول بواسطة البريد" in dump_sheet_clean or "البريد الإلكتروني" in dump_sheet_clean:
            if not click_text_in_xml(dev, dump_sheet, ("الدخول بواسطة البريد",), min_y=1200, max_y=1700):
                dev.click(796, 1484)
            smart_sleep(1.2, mult)

        dev.click(500, 845)
        smart_sleep(1.2, mult)
        dev.click(780, 1650)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=8.0)

    # 2. شاشة "تسجيل الحساب من جديد" -> الضغط على "كافة الزوار" (540, 1690)
    dump_rec = dev.dump_hierarchy()
    dump_rec_clean = strip_arabic_diacritics(dump_rec)
    if "كافة الزوار" in dump_rec_clean or "زائر دولي" in dump_rec_clean:
        if not click_text_in_xml(dev, dump_rec, ("كافة الزوار", "زائر دولي"), min_y=500, max_y=1850):
            dev.click(540, 1690)
    else:
        dev.click(540, 1690)
    smart_sleep(1.2, mult)
    wait_for_network_loading(dev, max_wait=8.0)

    # 3. اختيار الجنسية
    nat_y = smart_search_nationality(dev, raw_nat, default_nat_y, mult=mult)
    dev.shell("input keyevent 111")
    smart_sleep(0.4, mult)
    dev.click(540, nat_y)
    smart_sleep(0.4, mult)
    dev.click(540, 1850)
    wait_for_network_loading(dev, max_wait=8.0)

    # 4. إدخال الجواز ورقم التأشيرة (مع أولوية set_text لضمان عدم ضياع أي حرف)
    smart_sleep(0.8, mult)
    dev.click(485, 770)  # اختيار راديو التأشيرة
    smart_sleep(0.5, mult)

    rec_inputs = wait_edits(dev, 2, timeout=3.5 * mult)
    if rec_inputs is not None and len(rec_inputs) >= 2:
        rec_inputs[0].set_text(passport_val)
        smart_sleep(0.2, mult)
        rec_inputs[1].set_text(visa_val)
        smart_sleep(0.2, mult)
    else:
        dev.click(540, 600)  # جواز السفر
        smart_sleep(0.3, mult)
        dev.send_keys(passport_val, clear=True)
        smart_sleep(0.3, mult)

        dev.click(540, 890)  # رقم التأشيرة
        smart_sleep(0.3, mult)
        dev.send_keys(visa_val, clear=True)
        smart_sleep(0.3, mult)

    dev.shell("input keyevent 111")
    smart_sleep(0.4, mult)

    # الضغط على زر "التحقق من حسابك" (540, 1010)
    dev.click(540, 1010)
    smart_sleep(1.5, mult)
    wait_for_network_loading(dev, max_wait=12.0)

    # 5. إدخال الإيميل وكلمة المرور
    cred_inputs = wait_edits(dev, 2, timeout=3.5 * mult)
    if cred_inputs is not None and len(cred_inputs) >= 2:
        cred_inputs[0].set_text(email_val)
        smart_sleep(0.2, mult)
        cred_inputs[1].set_text(password_val)
        smart_sleep(0.2, mult)
    else:
        dev.click(540, 470)
        smart_sleep(0.3, mult)
        dev.send_keys(email_val, clear=True)
        smart_sleep(0.3, mult)

        dev.click(540, 600)
        smart_sleep(0.3, mult)
        dev.send_keys(password_val, clear=True)
        smart_sleep(0.3, mult)

    dev.shell("input keyevent 111")
    smart_sleep(0.4, mult)

    # الضغط على زر "تأكيد البريد الإلكتروني" (540, 1055)
    otp_sent_at = time.time()
    dev.click(540, 1055)
    smart_sleep(1.8, mult)
    wait_for_network_loading(dev, max_wait=12.0)

    # 6. استلام كود OTP
    log.info(f"[{label}] انتظار كود الـ OTP لاسترجاع الحساب من {req.client_email}...")
    otp = fetch_nusuk_otp(req.client_email.strip(), req.client_pass, timeout=55, sent_after=otp_sent_at)
    if not otp:
        raise FlowError("لم يتم استلام كود OTP لاسترجاع الحساب")

    dev.click(160, 240)
    smart_sleep(0.2, mult)
    dev.shell("input keyevent 67 67 67 67")
    dev.shell(f"input text {otp}")
    smart_sleep(0.4, mult)
    dev.shell("input keyevent 111")

    # انتظار ظهور نافذة "تم استعادة حسابك بنجاح" والضغط على الزر الأسود (تابع واستكشف)
    log.info(f"[{label}] انتظار نافذة تم استعادة حسابك بنجاح والضغط على الزر الأسود...")
    clicked_explore = False

    for _ in range(25):
        dump_succ = dev.dump_hierarchy()
        if any(w in dump_succ for w in ("استعادة حسابك بنجاح", "استعادة حسابك", "تابع واستكشف", "استكشف")):
            if not click_text_in_xml(dev, dump_succ, ("تابع واستكشف", "استكشف", "تابع"), min_y=1600, max_y=1900):
                dev.click(540, 1793)
            log.info(f"[{label}] تم الضغط على الزر الأسود (تابع واستكشف) بنجاح!")
            clicked_explore = True
            break
        if "تأكيد البريد الإلكتروني" in dump_succ:
            click_text_in_xml(dev, dump_succ, ("تأكيد البريد الإلكتروني",), min_y=700, max_y=950)
        time.sleep(0.6)

    if not clicked_explore:
        dev.click(540, 1793)

    smart_sleep(1.2, mult)

    # إغلاق التطبيق وإعادة فتحه دائماً بعد كتابة OTP والضغط على الزر الأسود لضمان الاستقرار والدخول النظيف
    log.info(f"🔄 [{label}] إعادة تشغيل تطبيق نسك بعد الاسترجاع والزر الأسود للوصول النظيف للشاشة الرئيسية...")
    reopen_nusuk_app(dev, emu_key, mult=mult)

    # 7. الضغط على دائرة البروفايل (أعلى اليسار 65, 101)
    dev.click(65, 101)
    smart_sleep(1.8, mult)
    wait_for_network_loading(dev, max_wait=8.0)

    # استخراج الاسم والـ Nusuk ID من البروفايل
    nid, pname = fast_extract_id_and_name(dev, max_wait=4.0 * mult)
    if not nid:
        dump_p = dev.dump_hierarchy()
        m_id = re.search(r"\b(202\d{9,12})\b", dump_p)
        if m_id:
            nid = m_id.group(1)

    log.info(f"[{label}] تم استرجاع البروفايل: {pname} | ID: {nid}")

    # 8. الضغط على كرت "التصاريح السارية" (750, 1780)
    dump_cards = dev.dump_hierarchy()
    if not click_text_in_xml(dev, dump_cards, ("التصاريح السارية", "Active Permits"), min_y=1500, max_y=1920):
        dev.click(750, 1780)
    smart_sleep(2.0, mult)
    wait_for_network_loading(dev, max_wait=10.0)

    # 9. فحص التصاريح (المواعيد) وتقييم الأحقية
    permits_xml = dev.dump_hierarchy()
    eligible, reason, details = evaluate_rawdah_permits_from_xml(permits_xml)
    log.info(f"📊 [{label}] نتيجة فحص الأحقية لـ {pname}: {reason}")

    # الرجوع لصفحة البروفايل
    dev.press("back")
    smart_sleep(1.2, mult)

    # 10. تنفيذ القرار
    if not eligible:
        log.warning(f"❌ [{label}] الحساب غير مؤهل ({reason}) -> تسجيل خروج آمن...")
        perform_safe_logout(dev, slow=True)
        # عمليات الاسترجاع لا تُحسب من ضمن عداد الـ 5 لتغيير البصمة
        return {
            "success": False,
            "status": "ineligible_permit",
            "eligible": False,
            "reason": reason,
            "pilgrim_name": pname,
            "nusuk_id": nid,
            "details": details,
            "message": reason,
        }

    # الحساب مؤهل ("ينفع")!
    log.info(f"✅ [{label}] الحساب مؤهل ({reason}) -> تنفيذ التوزيع...")

    if role == "leader":
        ensure_leader_on_friends_page(dev, mult=mult)
        with _state_lock:
            STATE["group"] = {
                "leader_active": True,
                "leader_name": pname,
                "leader_id": nid,
                "companions": [],
            }
        save_state()
        return {
            "success": True,
            "status": "leader_registered",
            "role": "leader",
            "eligible": True,
            "reason": reason,
            "leader_name": pname,
            "leader_id": nid,
            "details": details,
            "message": f"تم استرجاع الحساب واعتماده كرئيسي بنجاح ({reason})",
        }

    # مسار المرافق (companion على emu2)
    dev2 = dev
    dev1 = get_device(EMUS["emu1"]["serial"])
    open_add_friend_and_send_request(dev1, nid, comp_num, mult=mult)

    # قبول الطلب على emu2 مع التحقق من وصول الطلب والانتظار الكافي قبل السحب
    leader_name = (STATE.get("group") or {}).get("leader_name") or ""
    dump_dev2 = ""
    for attempt in range(2):
        dev2.click(1019, 91)
        time.sleep(1.0)
        dev2.click(65, 101)
        time.sleep(2.0)
        wait_for_network_loading(dev2, max_wait=10.0)
        dump_dev2 = dev2.dump_hierarchy()
        if any(k in dump_dev2 for k in ("قبول", "موافقة", "Accept", "Approve", "طلب", "Request")) or (leader_name and leader_name in dump_dev2):
            break

    if not click_text_in_xml(dev2, dump_dev2, ("قبول", "موافقة", "Accept", "Approve"), min_y=250, max_y=650):
        dev2.click(207, 408)
    time.sleep(1.5)
    wait_for_network_loading(dev2, max_wait=8.0)

    with _state_lock:
        STATE["group"]["companions"].append({"name": pname, "id": nid})
        group_count = len(STATE["group"]["companions"])
    save_state()

    perform_safe_logout(dev2, slow=True)
    log.info(f"[✓] تم ربط المرافق المسترجع {comp_num} ({pname}) بنجاح! (استرجاع - لا يُحسب في عداد تغيير البصمة)")

    if group_count >= MAX_COMPANIONS:
        log.info("اكتملت المجموعة (4 أفراد)! جاري إغلاق مجموعة المحاكي الأول...")
        close_leader_group(dev1)

    return {
        "success": True,
        "status": "companion_linked",
        "role": "companion",
        "eligible": True,
        "reason": reason,
        "companion_name": pname,
        "companion_id": nid,
        "group_count": group_count,
        "details": details,
        "message": f"تم استرجاع الحساب وربطه كمرافق {comp_num} بنجاح ({reason})",
    }


# ==========================================
# تعريف تطبيق FastAPI والـ Endpoints
# ==========================================
app = FastAPI(title="Nusuk Dual-Emulator Pro Engine (Anti-Lag)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/fail_shots", StaticFiles(directory=SHOTS_DIR), name="fail_shots")


class RegisterRequest(BaseModel):
    client_email: str
    client_pass: str
    pilgrim: dict
    nationality: Optional[str] = None
    nationality_text: Optional[str] = None
    search_text: Optional[str] = None
    nationality_y: Optional[int] = None
    option_y: Optional[int] = None
    choice_y: Optional[int] = None
    force_role: Optional[str] = None
    speed_multiplier: Optional[float] = None


BUSY_RESPONSE = {"success": False, "status": "busy", "error": "في عملية أخرى شغالة على المحاكيات حالياً، حاول بعد انتهائها"}


@app.get("/api/status")
def get_status():
    with _state_lock:
        group = copy.deepcopy(STATE["group"])
        counters = dict(STATE["counters"])
        health = copy.deepcopy(STATE["health"])
        speed_mult = STATE.get("speed_multiplier", 1.0)
    next_role = "companion" if group["leader_active"] else "leader"
    next_emu = (
        f"المحاكي الثاني (مرافق رقم {len(group['companions']) + 1})"
        if next_role == "companion" else "المحاكي الأول (حساب رئيسي جديد)"
    )
    return {
        "status": "ready",
        "busy": OP_LOCK.locked(),
        "emu1_counter": counters["emu1"],
        "emu2_counter": counters["emu2"],
        "leader_active": group["leader_active"],
        "leader_name": group["leader_name"],
        "leader_id": group["leader_id"],
        "companions": group["companions"],
        "companions_count": len(group["companions"]),
        "max_companions": MAX_COMPANIONS,
        "next_role": next_role,
        "next_target": next_emu,
        "health": health,
        "speed_multiplier": speed_mult,
    }


@app.post("/api/set-speed")
def set_speed_api(multiplier: float = 1.0):
    mult = max(0.8, min(3.0, float(multiplier)))
    with _state_lock:
        STATE["speed_multiplier"] = mult
    save_state()
    log.info(f"تم تغيير معامل سرعة الانتظار إلى: {mult}x")
    return {"success": True, "speed_multiplier": mult}


@app.get("/api/health")
def health_check():
    busy = OP_LOCK.locked()
    result = {"busy": busy, "emulators": {}}
    all_ok = True
    for key, emu in EMUS.items():
        with _state_lock:
            h = dict(STATE["health"][key])
            counter = STATE["counters"][key]
        item = {
            "label": emu["label"], "serial": emu["serial"], "counter": counter,
            "healthy": h["ok"], "reason": h["reason"], "connected": None,
        }
        if busy:
            item["note"] = "عملية شغالة - تم تخطي فحص الجهاز"
        else:
            try:
                dev = get_device(emu["serial"], timeout=6)
                w, hgt = dev.window_size()
                pkg = dev.app_current().get("package")
                item.update({
                    "connected": True, "screen": f"{w}x{hgt}",
                    "foreground_app": pkg, "nusuk_in_foreground": pkg == PACKAGE_NAME,
                })
            except Exception as e:
                item.update({"connected": False, "error": str(e)})
        if not h["ok"] or item["connected"] is False:
            all_ok = False
        result["emulators"][key] = item
    result["ok"] = all_ok
    return result


@app.post("/api/reset-state")
def reset_state_api(reset_counters: bool = False):
    with exclusive(LOCK_WAIT) as got:
        if not got:
            return BUSY_RESPONSE
        reset_group()
        with _state_lock:
            for k in STATE["health"]:
                STATE["health"][k] = {"ok": True, "reason": ""}
            if reset_counters:
                for k in STATE["counters"]:
                    STATE["counters"][k] = 0
        save_state()
        log.warning(f"تم تصفير الحالة يدوياً (reset_counters={reset_counters})")
        return {"success": True, "message": "تم تصفير المجموعة وحالة السلامة", "counters_reset": reset_counters}


@app.post("/api/randomize-emulator")
def randomize_emulator_api(emu_key: str):
    """تغيير بصمة محاكي محدد (emu1 أو emu2) يدوياً وإعادة تشغيله وتصفير عداده"""
    if emu_key not in EMUS:
        return {"success": False, "message": "اسم المحاكي غير صحيح"}
    with exclusive(LOCK_WAIT) as got:
        if not got:
            return BUSY_RESPONSE
        label = EMUS[emu_key]["label"]
        log.info(f"طلب يدوي لتغيير البصمة وإعادة تشغيل {label}...")
        ok = restart_and_randomize_ldplayer(emu_key)
        if ok:
            with _state_lock:
                STATE["counters"][emu_key] = 0
            save_state()
            return {"success": True, "message": f"تم تغيير بصمة {label} وإعادة تشغيله بنجاح"}
        return {"success": False, "message": f"حدث خطأ أثناء إعادة تشغيل {label}"}


@app.post("/api/force-close-group")
def force_close_group_api():
    with exclusive(LOCK_WAIT) as got:
        if not got:
            return BUSY_RESPONSE
        with _state_lock:
            active = STATE["group"]["leader_active"]
        if not active:
            return {"success": False, "message": "لا يوجد حساب رئيسي نشط حالياً"}
        try:
            dev1 = get_device(EMUS["emu1"]["serial"])
            ok = close_leader_group(dev1)
        except Exception as e:
            log.exception("فشل إنهاء المجموعة")
            return {"success": False, "message": f"فشل إنهاء المجموعة: {e}"}
        if ok:
            return {"success": True, "message": "تم إنهاء المجموعة وتسجيل خروج الحساب الرئيسي"}
        return {"success": False, "message": "تم تصفير المجموعة لكن المحاكي الأول يحتاج رجوع يدوي لشاشة الدخول"}


@app.post("/api/register")
def execute_workflow(req: RegisterRequest):
    with exclusive(LOCK_WAIT) as got:
        if not got:
            return BUSY_RESPONSE
        try:
            return _run_register(req)
        except Exception as e:
            log.exception("خطأ غير متوقع في /api/register")
            return {"success": False, "status": "error", "error": f"خطأ غير متوقع: {e}"}


@app.post("/api/recover")
def recover_account_api(req: RegisterRequest):
    """استرجاع حساب مسجل مسبقاً وفحص صلاحية تصاريح الروضة يدوياً أو برمجياً"""
    with exclusive(LOCK_WAIT) as got:
        if not got:
            return BUSY_RESPONSE
        try:
            with _state_lock:
                leader_active = STATE["group"]["leader_active"]
                comp_count = len(STATE["group"]["companions"])
            role = req.force_role or ("companion" if leader_active else "leader")
            emu_key = "emu1" if role == "leader" else "emu2"
            comp_num = comp_count + 1
            mult = float(req.speed_multiplier or STATE.get("speed_multiplier", 1.0))
            dev = get_device(EMUS[emu_key]["serial"])
            return run_account_recovery_flow(dev, req, role, comp_num, emu_key, mult=mult)
        except Exception as e:
            log.exception("خطأ في /api/recover")
            return {"success": False, "status": "error", "error": str(e)}


def _run_register(req: RegisterRequest) -> dict:
    p = req.pilgrim or {}
    dummy_name = "Ab"
    mult = float(req.speed_multiplier or STATE.get("speed_multiplier", 1.0))

    email_val = extract_field(p, ["email", "البريد الالكتروني", "البريد الإلكتروني", "Email", "الايميل"]) or req.client_email.strip()
    password_val = extract_field(p, ["password", "الباسورد", "كلمة المرور", "Password", "pass"]) or DEFAULT_PASSWORD
    passport_val = extract_field(p, ["رقم الجواز", "الجواز", "passport_number", "Passport", "passport", "رقم وثيقة السفر"])
    visa_val = extract_field(p, ["رقم الفيزا", "الفيزا", "رقم التاشيره", "رقم التأشيرة", "التاشيره", "التأشيرة", "visa_number", "Visa", "visa"])
    force_role = (req.force_role or "").strip().lower() or None

    problems = []
    if not EMAIL_RE.fullmatch(req.client_email.strip()):
        problems.append("client_email غير صالح")
    if not req.client_pass.strip():
        problems.append("client_pass فارغ")
    if not EMAIL_RE.fullmatch(email_val):
        problems.append("إيميل الحاج غير صالح")
    if not password_val:
        problems.append("لا توجد كلمة مرور")
    if not passport_val:
        problems.append("رقم الجواز فارغ")
    if not visa_val:
        problems.append("رقم التأشيرة فارغ")
    if problems:
        log.warning("طلب مرفوض: " + " | ".join(problems))
        return {"success": False, "status": "invalid_input", "error": " | ".join(problems)}

    with _state_lock:
        leader_active = STATE["group"]["leader_active"]
        comp_count = len(STATE["group"]["companions"])

    role = force_role or ("companion" if leader_active else "leader")
    if role == "companion" and not leader_active:
        return {"success": False, "status": "invalid_state", "error": "لا يوجد حساب رئيسي نشط - سجّل الرئيسي أولاً"}
    if role == "leader" and leader_active:
        return {"success": False, "status": "invalid_state", "error": "يوجد حساب رئيسي نشط - أنهِ المجموعة أولاً"}

    emu_key = "emu1" if role == "leader" else "emu2"
    emu = EMUS[emu_key]
    comp_num = comp_count + 1
    label = "المحاكي الأول (رئيسي)" if role == "leader" else f"المحاكي الثاني (مرافق {comp_num})"

    dev = get_device(emu["serial"])
    dev1 = None

    log.info("=" * 55)
    log.info(f"بدء تسجيل على [{label}] (السرعة: {mult}x) | الجواز: {passport_val} | التأشيرة: {visa_val}")

    try:
        if not force_clean_login_state(dev, emu_key):
            raise FlowError(f"{label} ليس على شاشة الدخول وتعذر تنظيفه تلقائياً")

        # لو نسجل مرافق، نتأكد أن المحاكي الأول (الرئيسي) متصل وتطبيق نسك مفتوح عليه قبل البدء
        if role == "companion":
            dev1 = get_device(EMUS["emu1"]["serial"])
            if dev1.app_current().get("package") != PACKAGE_NAME:
                log.warning("المحاكي الأول (الرئيسي) خرج من تطبيق نسك! جاري إعادة فتحه قبل تسجيل المرافق...")
                reopen_nusuk_app(dev1, "emu1", mult=mult)
            ensure_leader_on_friends_page(dev1, mult=mult)

        # 1. فتح شاشة إنشاء الحساب (تخطي الزر الأسود 540,1768 ثم أنشئ حسابًا جديدًا 540,1704)
        smart_sleep(0.4, mult)
        inputs = open_registration_form(dev, mult=mult)
        if inputs is None:
            raise FlowError("لم تظهر شاشة التسجيل (تأكد من اتصال الإنترنت)")
        smart_sleep(0.3, mult)

        # 2. ملء البيانات الأساسية
        inputs[0].set_text(dummy_name)
        smart_sleep(0.15, mult)
        inputs[1].set_text(email_val)
        smart_sleep(0.15, mult)
        inputs[2].set_text(password_val)
        smart_sleep(0.2, mult)

        dev.shell("input keyevent 111")
        smart_sleep(0.4, mult)

        # الضغط على زر التأكيد النهائي (أنشئ حسابك) بعد ملء الـ 3 خانات في إحداثياته الجديدة (558, 1138)
        otp_sent_at = time.time()
        dev.click(558, 1138)
        smart_sleep(1.8, mult)
        wait_for_network_loading(dev, max_wait=12.0)

        # 3. استلام وإدخال كود OTP
        otp = fetch_nusuk_otp(req.client_email.strip(), req.client_pass, timeout=55, sent_after=otp_sent_at)
        if not otp:
            raise FlowError("لم يتم استلام كود OTP")

        dev.click(160, 462)
        smart_sleep(0.2, mult)
        dev.shell("input keyevent 67 67 67 67")
        dev.shell(f"input text {otp}")
        smart_sleep(0.2, mult)
        dev.shell("input keyevent 111")

        # 4. انتظار انتهاء تحميل الـ OTP ثم 3 نقرات تنظيف
        smart_sleep(1.8, mult)
        wait_for_network_loading(dev, max_wait=12.0)
        for _ in range(3):
            dev.click(1000, 100)
            smart_sleep(0.3, mult)

        # 5. الدخول للملف الشخصي ثم Active Permits ثم Complete Profile
        dev.click(65, 101)
        smart_sleep(1.6, mult)
        wait_for_network_loading(dev, max_wait=8.0)

        dev.click(807, 1786)
        smart_sleep(1.3, mult)
        wait_for_network_loading(dev, max_wait=8.0)
        dump_step5 = dev.dump_hierarchy()
        if "عرض الكل" in dump_step5 or "بطاقاتي" in dump_step5 or "Show All" in dump_step5:
            dev.click(807, 1786)
            smart_sleep(1.2, mult)
            wait_for_network_loading(dev, max_wait=6.0)

        dev.click(540, 1793)
        smart_sleep(1.3, mult)

        # 6. اختيار زائر دولي
        dev.click(540, 886)
        smart_sleep(1.3, mult)

        # 7. اختيار الجنسية
        raw_nat = str(req.nationality or req.nationality_text or req.search_text or p.get("nationality") or "مصر").strip()
        default_nat_y = int(req.nationality_y or req.option_y or req.choice_y or 275)

        dev.click(540, 491)
        if wait_edits(dev, 1, timeout=4.5 * mult) is None:
            dump_step6 = dev.dump_hierarchy()
            if "نوع الهوية" in dump_step6 or "زائر دولي" in dump_step6 or "International" in dump_step6:
                dev.click(540, 886)
                smart_sleep(1.2, mult)
            dev.click(540, 491)
            if wait_edits(dev, 1, timeout=4.5 * mult) is None:
                raise FlowError("لم تظهر قائمة الجنسية بسبب بطء الاستجابة")
        smart_sleep(0.3, mult)

        nat_y = smart_search_nationality(dev, raw_nat, default_nat_y, mult=mult)
        dev.shell("input keyevent 111")
        smart_sleep(0.4, mult)

        dev.click(540, nat_y)
        smart_sleep(0.4, mult)
        dev.click(540, 1850)
        wait_for_network_loading(dev, max_wait=8.0)

        # 8. بيانات الجواز والتأشيرة
        all_inputs = wait_edits(dev, 2, timeout=6.0 * mult)
        if all_inputs is None:
            dev.click(540, 1850)
            all_inputs = wait_edits(dev, 2, timeout=5.0 * mult)
        if all_inputs is None:
            raise FlowError("لم تظهر خانات الجواز والتأشيرة")
        smart_sleep(0.2, mult)
        all_inputs[0].set_text(passport_val)
        smart_sleep(0.15, mult)
        all_inputs[1].set_text(visa_val)
        smart_sleep(0.15, mult)

        dev.shell("input keyevent 111")
        smart_sleep(0.4, mult)

        # 9. زر الحفظ النهائي وفحص النتيجة
        dev.click(540, 1040)
        smart_sleep(1.2, mult)
        wait_for_network_loading(dev, max_wait=15.0)

        outcome = None
        for _ in range(14):
            raw_dump = dev.dump_hierarchy()
            screen_dump = strip_arabic_diacritics(raw_dump).lower()
            if any(strip_arabic_diacritics(k).lower() in screen_dump for k in ALREADY_KEYS):
                outcome = "already"
                break
            if any(strip_arabic_diacritics(k).lower() in screen_dump for k in SUCCESS_KEYS):
                outcome = "success"
                break
            time.sleep(0.5)

        if outcome is None and len(dev(className="android.widget.EditText")) >= 2:
            dev.shell("input keyevent 111")
            smart_sleep(0.3, mult)
            dev.click(540, 1040)
            smart_sleep(1.2, mult)
            wait_for_network_loading(dev, max_wait=10.0)
            for _ in range(10):
                raw_dump = dev.dump_hierarchy()
                screen_dump = strip_arabic_diacritics(raw_dump).lower()
                if any(strip_arabic_diacritics(k).lower() in screen_dump for k in ALREADY_KEYS):
                    outcome = "already"
                    break
                if any(strip_arabic_diacritics(k).lower() in screen_dump for k in SUCCESS_KEYS):
                    outcome = "success"
                    break
                time.sleep(0.5)

        if outcome == "already":
            log.warning("الحساب مسجل مسبقاً! الضغط على الزر الأسود 'سجّل الخروج واستعد حسابك' وبدء مسار استرجاع الحساب تلقائياً...")
            dump_alr = dev.dump_hierarchy()
            if not click_text_in_xml(dev, dump_alr, ("سجل الخروج واستعد حسابك", "استعد حسابك", "سجل الخروج"), min_y=1500, max_y=1850):
                dev.click(540, 1770)
            smart_sleep(1.5, mult)
            wait_for_network_loading(dev, max_wait=10.0)
            # الضغط مرتين في أعلى منتصف الشاشة لإغلاق أي نافذة منبثقة
            dev.click(540, 300)
            smart_sleep(0.5, mult)
            dev.click(540, 300)
            smart_sleep(0.8, mult)
            return run_account_recovery_flow(dev, req, role, comp_num, emu_key, mult=mult)

        # 10. Continue Exploring ثم سهم الرجوع للبروفايل
        dev.click(540, 1793)
        smart_sleep(1.3, mult)
        wait_for_network_loading(dev, max_wait=8.0)

        dev.click(1019, 91)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=8.0)

        # ====================================================
        # الرئيسي أو المرافق
        # ====================================================
        if role == "leader":
            leader_id, leader_name = reach_profile_and_extract_id(dev, mult=mult)
            if not leader_id:
                raise FlowError("لم يظهر Nusuk ID في المحاكي الأول (الرئيسي)")

            log.info(f"[✓] الرئيسي جاهز: {leader_name} | ID: {leader_id} -> فتح Show All")
            with _state_lock:
                STATE["group"] = {
                    "leader_active": True, "leader_name": leader_name,
                    "leader_id": leader_id, "companions": [],
                }
            save_state()

            ensure_leader_on_friends_page(dev, mult=mult)

            return {
                "success": True, "status": "leader_registered", "role": "leader",
                "leader_name": leader_name, "leader_id": leader_id,
                "message": "تم تسجيل الحساب الرئيسي بنجاح",
            }

        # ---------------- مسار المرافق ----------------
        dev2 = dev

        comp_id, comp_name = reach_profile_and_extract_id(dev2, mult=mult)
        if not comp_id:
            raise FlowError("لم يظهر Nusuk ID في المحاكي الثاني")
        log.info(f"التقاط خاطف للمرافق {comp_num}: {comp_id} ({comp_name})")

        dev1 = get_device(EMUS["emu1"]["serial"])
        open_add_friend_and_send_request(dev1, comp_id, comp_num, mult=mult)

        leader_name = (STATE.get("group") or {}).get("leader_name") or ""
        dump_dev2 = ""
        for attempt in range(2):
            log.info(f"المحاكي الثاني: ريفريش بالخروج ثم الدخول (محاولة {attempt + 1})...")
            dev2.click(1019, 91)
            time.sleep(1.0)
            dev2.click(65, 101)
            time.sleep(2.0)
            wait_for_network_loading(dev2, max_wait=10.0)

            dump_dev2 = dev2.dump_hierarchy()
            if not any(m in dump_dev2 for m in ("عرض الكل", "Show All", "بطاقاتي", "My Cards")) and comp_id not in dump_dev2:
                dev2.click(65, 101)
                time.sleep(1.8)
                wait_for_network_loading(dev2, max_wait=6.0)
                dump_dev2 = dev2.dump_hierarchy()

            if any(k in dump_dev2 for k in ("قبول", "موافقة", "Accept", "Approve", "طلب", "Request")) or (leader_name and leader_name in dump_dev2):
                break

        log.info("المحاكي الثاني: النقر على علامة الصح (207, 408) لقبول الطلب...")
        if not click_text_in_xml(dev2, dump_dev2, ("قبول", "موافقة", "Accept", "Approve"), min_y=250, max_y=650):
            dev2.click(207, 408)
        time.sleep(1.5)
        wait_for_network_loading(dev2, max_wait=8.0)

        with _state_lock:
            STATE["group"]["companions"].append({"name": comp_name, "id": comp_id})
            group_count = len(STATE["group"]["companions"])
        save_state()

        perform_safe_logout(dev2, slow=True)
        log.info(f"[✓] تم ربط المرافق {comp_num} بنجاح!")
        bump_counter("emu2")

        if group_count >= MAX_COMPANIONS:
            log.info("اكتملت المجموعة (4 أفراد)! جاري إغلاق مجموعة المحاكي الأول...")
            close_leader_group(dev1)

        return {
            "success": True, "status": "companion_linked", "role": "companion",
            "companion_name": comp_name, "companion_id": comp_id,
            "group_count": group_count,
            "message": f"تم ربط المرافق {comp_num} وقبول الطلب بنجاح",
        }

    except Exception as e:
        log.exception(f"[{label}] استثناء أثناء التنفيذ: {e}")
        shot = save_failure_artifacts(dev, f"{emu_key}_{role}")
        if dev1 is not None and dev1 is not dev:
            try:
                if is_add_friend_dialog_open(dev1):
                    dev1.press("back")
            except Exception:
                pass
        force_clean_login_state(dev, emu_key)
        return {"success": False, "status": "error", "error": str(e), "screenshot": shot}


# ==========================================
# ميزة إلغاء الحجز عبر Nusuk API (مضافة على السيرفر الأصلي)
# ==========================================
NUSUK_STATIC_KEY = os.getenv(
    "NUSUK_STATIC_KEY",
    "d8b7986b9cd0866f8b53fc0a4b65f503cfce61c66cdef58e214525f1a6de28ce",
)
NUSUK_DYNAMIC_KEY = os.getenv(
    "NUSUK_DYNAMIC_KEY",
    "2f56343e14b347cf78956a3b4bd13a16a5b1ebe84d83de691b045beab72658f1",
)
NUSUK_API_VERSION = os.getenv("NUSUK_API_VERSION", "11")            # header "version" (KeyManager.getVersionHeaderService)
NUSUK_APP_VERSION_HEADER = os.getenv("NUSUK_APP_VERSION_HEADER", "17.5.8(175804)")  # header "x-version" (versionName(versionCode))
NUSUK_NUSUK_VERSION_HEADER = os.getenv("NUSUK_NUSUK_VERSION_HEADER", "2")            # header "NUSUK_VERSION" (bk8.Q4)
NUSUK_OS_VERSION_HEADER = os.getenv("NUSUK_OS_VERSION_HEADER", "13 (33)")            # header "os-version"
NUSUK_USER_AGENT = os.getenv("NUSUK_USER_AGENT", "okhttp/4.12.0")                    # السيرفر يرفض الطلبات بدون UA (traceError="bot")
NUSUK_DEVICE_ID = os.getenv("NUSUK_DEVICE_ID", secrets.token_hex(8)) # e9.O(context) = ANDROID_ID (16 hex)
NUSUK_BASE_URL = "https://nusukapp.nusuk.sa/nusuk/"
NUSUK_PUBLIC_BASE_URL = "https://nusukapp.nusuk.sa/nusuk/public/"    # PublicNetworkModule — كل تسجيل الدخول/الـ OTP هنا

_AES_SBOX = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]
_AES_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _aes_xtime(a: int) -> int:
    return (((a << 1) ^ 0x1b) & 0xff) if (a & 0x80) else ((a << 1) & 0xff)


def _aes_expand_key(key16: bytes):
    w = [list(key16[i:i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = [_AES_SBOX[t[1]], _AES_SBOX[t[2]], _AES_SBOX[t[3]], _AES_SBOX[t[0]]]
            t[0] ^= _AES_RCON[i // 4 - 1]
        w.append([w[i - 4][j] ^ t[j] for j in range(4)])
    return [[b for i in range(4) for b in w[4 * r + i]] for r in range(11)]


def _aes_encrypt_block(block, keys):
    s = [block[i] ^ keys[0][i] for i in range(16)]
    for rnd in range(1, 10):
        s = [_AES_SBOX[b] for b in s]
        s = [
            s[0], s[5], s[10], s[15],
            s[4], s[9], s[14], s[3],
            s[8], s[13], s[2], s[7],
            s[12], s[1], s[6], s[11],
        ]
        out = [0] * 16
        for c in range(4):
            a0, a1, a2, a3 = s[4 * c], s[4 * c + 1], s[4 * c + 2], s[4 * c + 3]
            out[4 * c] = _aes_xtime(a0) ^ (_aes_xtime(a1) ^ a1) ^ a2 ^ a3
            out[4 * c + 1] = a0 ^ _aes_xtime(a1) ^ (_aes_xtime(a2) ^ a2) ^ a3
            out[4 * c + 2] = a0 ^ a1 ^ _aes_xtime(a2) ^ (_aes_xtime(a3) ^ a3)
            out[4 * c + 3] = (_aes_xtime(a0) ^ a0) ^ a1 ^ a2 ^ _aes_xtime(a3)
        s = [out[i] ^ keys[rnd][i] for i in range(16)]
    s = [_AES_SBOX[b] for b in s]
    s = [
        s[0], s[5], s[10], s[15],
        s[4], s[9], s[14], s[3],
        s[8], s[13], s[2], s[7],
        s[12], s[1], s[6], s[11],
    ]
    return [s[i] ^ keys[10][i] for i in range(16)]


def encrypt_rawdah(request_dict: dict, key: Optional[str] = None) -> Tuple[str, str]:
    alphabet = string.ascii_lowercase + string.ascii_uppercase + string.digits
    key = key or "".join(random.choice(alphabet) for _ in range(16))
    k = key.encode("utf-8")
    keys = _aes_expand_key(k)
    pt = json.dumps(request_dict, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    pad_len = 16 - (len(pt) % 16)
    pt += bytes([pad_len]) * pad_len
    out = bytearray()
    prev = list(k)
    for i in range(0, len(pt), 16):
        blk = [pt[i + j] ^ prev[j] for j in range(16)]
        enc = _aes_encrypt_block(blk, keys)
        out += bytes(enc)
        prev = enc
    b64 = base64.b64encode(bytes(out)).decode("ascii")
    return key[:4] + b64 + key[4:], key


def build_nusuk_headers(
    bearer_token: Optional[str] = None,
    device_id: Optional[str] = None,
    lang: str = "ar",
    version: Optional[str] = None,
    timestamp: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    ts = timestamp or str(int(time.time() * 1000))
    ver = version or NUSUK_API_VERSION
    dev_id = device_id or NUSUK_DEVICE_ID
    h = hashlib.sha256((NUSUK_STATIC_KEY + NUSUK_DYNAMIC_KEY + ts).encode("utf-8")).hexdigest()
    headers = {
        "version": ver,
        "hash": h,
        "timestamp": ts,
        "deviceType": "1",
        "NUSUK_VERSION": NUSUK_NUSUK_VERSION_HEADER,
        "deviceID": dev_id,
        "x-version": NUSUK_APP_VERSION_HEADER,
        "x-device": dev_id,
        "os-version": NUSUK_OS_VERSION_HEADER,
        "Accept": "application/json",
        "accept-language": lang,
        "Content-Type": "application/json",
        "User-Agent": NUSUK_USER_AGENT,
    }
    if bearer_token:
        tok = bearer_token.strip()
        if not tok.lower().startswith("bearer "):
            tok = f"Bearer {tok}"
        headers["Authorization"] = tok
    if extra_headers:
        headers.update(extra_headers)
    return headers


def nusuk_http_request(
    endpoint: str,
    method: str = "POST",
    body_dict: Optional[dict] = None,
    bearer_token: Optional[str] = None,
    device_id: Optional[str] = None,
    lang: str = "ar",
    timeout: int = 25,
    extra_headers: Optional[Dict[str, str]] = None,
) -> dict:
    url = endpoint if endpoint.startswith("http") else (NUSUK_BASE_URL + endpoint.lstrip("/"))
    headers = build_nusuk_headers(
        bearer_token=bearer_token,
        device_id=device_id,
        lang=lang,
        extra_headers=extra_headers,
    )
    data_bytes = (
        json.dumps(body_dict, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if body_dict is not None
        else None
    )
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return {"ok": True, "http_status": resp.status, "data": parsed}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return {"ok": False, "http_status": e.code, "error": str(e), "data": parsed}
    except Exception as e:
        return {"ok": False, "http_status": None, "error": f"{type(e).__name__}: {e}", "data": None}


# ==========================================
# Nusuk API Login — جلب الـ Bearer Token تلقائياً (بدون محاكي)
#   v2/login (public) → OTP من Gmail → v2/login/validate-otp → token
# ==========================================
_NUSUK_TOKEN_CACHE: Dict[str, dict] = {}
_NUSUK_TOKEN_LOCK = threading.Lock()
NUSUK_TOKEN_TTL = float(os.getenv("NUSUK_TOKEN_TTL", "2700"))


def nusuk_make_nonce(email: str, password: str) -> Tuple[str, str]:
    """(nonce, hmacKey) مطابق لـ LoginWithEmailUseCase$invoke$nonceResult$1 (SHA3-256 + HMAC-SHA3-256)."""
    now_ms = int(datetime.now(timezone(timedelta(hours=3))).timestamp() * 1000)
    str2 = f"{now_ms % 1000000:06d}"
    rnd_a = secrets.token_bytes(4).hex()
    rnd_b = secrets.token_bytes(4).hex()
    part_email = hashlib.sha3_256((email + rnd_a).encode("utf-8")).hexdigest()[1:4]
    part_pass = hashlib.sha3_256((password + rnd_a).encode("utf-8")).hexdigest()[4:7]
    hmac_key = secrets.token_bytes(32).hex()
    joined = "|".join(["V2", str2, rnd_b, part_email, part_pass, rnd_a])
    mac = hmac.new(bytes.fromhex(hmac_key), joined.encode("utf-8"), hashlib.sha3_256).hexdigest()
    return joined + "|" + mac[:4], hmac_key


def nusuk_encrypt_login_payload(email: str, password: str) -> str:
    """loginData = AES-128-CBC(key=IV=K, PKCS7) + Base64 + K[0:4]…K[4:16] (نفس encrypt_rawdah)."""
    nonce, hmac_key = nusuk_make_nonce(email, password)
    login_obj = {"email": email, "password": password, "nonce": nonce, "hmacKey": hmac_key}
    data, _key = encrypt_rawdah(login_obj)
    return data


def nusuk_public_request(path: str, body_dict: Optional[dict] = None, method: str = "POST",
                         bearer_token: Optional[str] = None, device_id: Optional[str] = None,
                         lang: str = "ar", timeout: int = 35) -> dict:
    """طلب على base العام (/nusuk/public/) اللي عليه v2/login و validate-otp."""
    url = path if path.startswith("http") else (NUSUK_PUBLIC_BASE_URL + path.lstrip("/"))
    return nusuk_http_request(url, method=method, body_dict=body_dict, bearer_token=bearer_token,
                              device_id=device_id, lang=lang, timeout=timeout)


def _nusuk_envelope(payload) -> dict:
    if isinstance(payload, dict):
        env = payload.get("Response")
        if env is None:
            env = payload.get("response")
        if isinstance(env, dict):
            return env
    return {}


def _nusuk_response_code(payload):
    env = _nusuk_envelope(payload)
    code = env.get("ResponseCode", env.get("responseCode"))
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def _nusuk_is_session_error(payload) -> bool:
    """-401 / انتهى وقت الجلسة = التوكن منتهي أو غير صالح → لازم توكن جديد."""
    return _nusuk_response_code(payload) in (-401, -403, 401, 403)


def _nusuk_pick_user_id(data) -> Optional[int]:
    """يستخرج UserID من بيانات الرد (نسك بيرجّعه بحروف UserID)."""
    if not isinstance(data, dict):
        return None
    for key in ("UserID", "UserId", "userId", "userID", "User_ID"):
        v = data.get(key)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v.strip())
    return None


_NUSUK_ERROR_HINTS = {
    "10017026": "التصريح مستخدم من قبل ولا يمكن إلغاؤه",
    "-1010106002": "التصريح مستخدم من قبل ولا يمكن إلغاؤه",
    "113": "تعذر معالجة الطلب — بيانات غير مكتملة أو غير صحيحة",
    "-9999": "خطأ عام من نسك — راجع UserID ورقم الحجز",
    "1": "بيانات الطلب غير صحيحة أو غير مكتملة",
    "-401": "الجلسة انتهت — التوكن منتهي",
    "-403": "غير مسموح — الجلسة منتهية",
}


def nusuk_error_hint(payload) -> Optional[str]:
    """ترجمة أكواد أخطاء نسك لرسالة عربية واضحة."""
    env = _nusuk_envelope(payload)
    if not env:
        return None
    code = str(env.get("ResponseCode", env.get("responseCode")) or "")
    desc = str(env.get("ResponseDesc", env.get("responseDesc")) or "")
    hint = _NUSUK_ERROR_HINTS.get(code)
    if not hint:
        m = re.search(r"-?\d{6,}", desc)
        if m:
            hint = _NUSUK_ERROR_HINTS.get(m.group(0))
    if not hint:
        if "مستخدم" in desc:
            hint = "التصريح مستخدم من قبل ولا يمكن إلغاؤه"
        elif "منتهي" in desc or "انتهت" in desc:
            hint = "التصريح منتهي ولا يمكن إلغاؤه"
        elif "ملغ" in desc:
            hint = "التصريح ملغي بالفعل"
    return hint


def _nusuk_user_id_from_jwt(token: Optional[str]) -> Optional[int]:
    """يحاول استخراج UserID من payload التوكن لو كان JWT (لحالة التوكن المُلصق يدويًا)."""
    if not token or token.count(".") != 2:
        return None
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return None
    return _nusuk_pick_user_id(payload) if isinstance(payload, dict) else None


def _nusuk_drop_cached_token(email: Optional[str]) -> None:
    if not email:
        return
    with _NUSUK_TOKEN_LOCK:
        _NUSUK_TOKEN_CACHE.pop(email.strip().lower(), None)


def nusuk_token_is_valid(token: Optional[str], device_id: Optional[str] = None,
                         lang: str = "ar") -> bool:
    """يتحقق إن التوكن لسه شغال بنداء قراءة خفيف (ActivePermits)."""
    if not token:
        return False
    res = nusuk_http_request("manasik/ActivePermits", method="GET", body_dict=None,
                             bearer_token=token, device_id=device_id, lang=lang, timeout=20)
    payload = res.get("data")
    if _nusuk_is_session_error(payload):
        return False
    return bool(res.get("ok")) or payload is not None


def nusuk_extract_data(payload) -> dict:
    env = _nusuk_envelope(payload)
    source = env or (payload if isinstance(payload, dict) else {})
    if isinstance(source, dict):
        for key in ("data", "Data", "responseData", "ResponseData"):
            value = source.get(key)
            if isinstance(value, dict):
                return value
    return source if isinstance(source, dict) else {}


def nusuk_extract_token(payload) -> Optional[str]:
    """يبحث عن حقل token في أي مكان داخل الرد."""
    def walk(node, depth=0):
        if depth > 6:
            return None
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower() == "token" and isinstance(v, str) and v.strip():
                    return v.strip()
            for v in node.values():
                found = walk(v, depth + 1)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = walk(item, depth + 1)
                if found:
                    return found
        return None

    return walk(payload)


def nusuk_extract_permit_ids(payload) -> List[str]:
    """يستخرج أرقام التصاريح (PermitID) من أي شكل رد (Reservations[].Permits[] …)."""
    ids: List[str] = []
    seen = set()

    def walk(node, depth=0):
        if depth > 12:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
            return
        if isinstance(node, dict):
            for k, v in node.items():
                key = re.sub(r"[^a-z]", "", str(k).lower())
                if key in ("permitid", "permitno", "permitnumber"):
                    val = None
                    if isinstance(v, (int, float)):
                        val = str(int(v))
                    elif isinstance(v, str) and v.strip().isdigit():
                        val = v.strip()
                    if val and val not in seen:
                        seen.add(val)
                        ids.append(val)
                else:
                    walk(v, depth + 1)

    walk(payload, 0)
    return ids


def nusuk_summarize_active_permits(payload) -> dict:
    """يفكك رد manasik/ActivePermits لقائمة حجوزات وتصاريح قابلة للعرض والاختيار."""
    data = nusuk_extract_data(payload)

    def as_list(v):
        return v if isinstance(v, list) else []

    reservations = []
    for coll_key in ("Reservations", "RawdaReservation", "UmrahReservation"):
        for item in as_list(data.get(coll_key)):
            if not isinstance(item, dict):
                continue
            permits = []
            for p in as_list(item.get("Permits")):
                if not isinstance(p, dict):
                    continue
                permits.append({
                    "permit_id": p.get("PermitID"),
                    "status_rawdah": p.get("RawdahStatus"),
                    "status_umrah": p.get("UmrahStatus"),
                    "start": p.get("PermitStartDate"),
                    "end": p.get("PermitEndDate"),
                    "cancel_reason_id": p.get("cancelReasonId"),
                    "name_ar": p.get("UserFullNameAr"),
                })
            reservations.append({
                "source": coll_key,
                "reservation_id": item.get("ResID"),
                "rawdah_status": item.get("RawdahStatus"),
                "umrah_status": item.get("UmrahStatus"),
                "start": item.get("ResStartDateTime"),
                "end": item.get("ResEndDateTime"),
                "timeslot_ar": item.get("ResTimeslotAr"),
                "service_ar": item.get("ServiceTypeNameAr"),
                "permits": permits,
            })

    permit_ids: List[str] = []
    for r in reservations:
        for p in r["permits"]:
            pid = p.get("permit_id")
            if pid is not None and str(pid) not in permit_ids:
                permit_ids.append(str(pid))

    return {
        "reservations": reservations,
        "permit_ids": permit_ids,
        "max_allowed": data.get("MaxAllowedPermitsNo", data.get("maxAllowedPermitsNo")),
        "remaining": data.get("RemainingActivePermitsNo", data.get("remainingActivePermitsNo")),
        "top_keys": list(data.keys())[:20] if isinstance(data, dict) else [],
    }


def nusuk_summarize_certificate_permits(payload) -> List[dict]:
    """يفكك رد manasik/getPermitsForCertificate → سجل كل التصاريح (بما فيها غير النشطة)."""
    raw = payload
    items = []
    if isinstance(raw, list):
        items = raw
    else:
        env = _nusuk_envelope(raw)
        source = env if env else (raw if isinstance(raw, dict) else {})
        if isinstance(source, dict):
            for key in ("data", "Data", "responseData", "ResponseData"):
                v = source.get(key)
                if isinstance(v, list):
                    items = v
                    break

    out: List[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append({
            "permit_id": it.get("Id"),
            "reservation_id": it.get("ReservationId"),
            "status_id": it.get("StatusId"),
            "status_name": it.get("StatusName"),
            "rawdah_status_id": it.get("RawdahStatusId"),
            "service_id": it.get("ServiceId"),
            "start": it.get("DateAndTimeStart"),
            "end": it.get("DateAndTimeEnd"),
            "gate": it.get("GateName"),
            "name": it.get("Name"),
            "visitor_id": it.get("VisitorId"),
            "current_year": it.get("CurrentYear"),
        })
    return out


def nusuk_api_login(email: str, password: str, device_id: Optional[str] = None, lang: str = "ar") -> dict:
    """POST v2/login — يبعت كود OTP على إيميل الحساب ويرجع otpId/userId."""
    e = (email or "").strip().lower()
    p = (password or "").strip()
    encrypted = nusuk_encrypt_login_payload(e, p)
    res = nusuk_public_request("v2/login", {"Request": {"loginData": encrypted}}, device_id=device_id, lang=lang)
    env = _nusuk_envelope(res.get("data"))
    data = nusuk_extract_data(res.get("data"))
    otp_id = data.get("otpId", data.get("OtpId"))
    out = {
        "ok": bool(res.get("ok")) and otp_id is not None,
        "http_status": res.get("http_status"),
        "response_code": env.get("ResponseCode", env.get("responseCode")),
        "response_desc": env.get("ResponseDesc", env.get("responseDesc")),
        "otp_id": otp_id,
        "user_id": data.get("userId", data.get("UserId")),
        "data": data,
    }
    log.info("Nusuk v2/login → otpId=%s (HTTP %s)", otp_id, res.get("http_status"))
    if not out["ok"]:
        log.warning("Nusuk v2/login فشل: %s", res.get("data"))
    return out


def nusuk_api_verify_otp(email: str, password: str, otp: str, otp_id, device_id: Optional[str] = None,
                         lang: str = "ar") -> dict:
    """POST v2/login/validate-otp — يرجّع الـ Bearer Token."""
    body = {
        "Request": {
            "email": (email or "").strip().lower(),
            "otp": int(str(otp).strip()),
            "otpId": int(str(otp_id).strip()),
            "password": (password or "").strip(),
        }
    }
    res = nusuk_public_request("v2/login/validate-otp", body, device_id=device_id, lang=lang)
    env = _nusuk_envelope(res.get("data"))
    data = nusuk_extract_data(res.get("data"))
    token = nusuk_extract_token(res.get("data"))
    out = {
        "ok": bool(token),
        "http_status": res.get("http_status"),
        "response_code": env.get("ResponseCode", env.get("responseCode")),
        "response_desc": env.get("ResponseDesc", env.get("responseDesc")),
        "token": token,
        "user_id": _nusuk_pick_user_id(data),
        "data": data,
    }
    log.info("Nusuk v2/login/validate-otp → token=%s (HTTP %s)",
             ("موجود" if token else "غير موجود"), res.get("http_status"))
    if not token:
        log.warning("Nusuk validate-otp فشل: %s", res.get("data"))
    return out


def _nusuk_cache_get(email: str) -> Optional[dict]:
    with _NUSUK_TOKEN_LOCK:
        item = _NUSUK_TOKEN_CACHE.get(email)
    if not item:
        return None
    if (time.time() - float(item.get("created_at", 0))) > NUSUK_TOKEN_TTL:
        with _NUSUK_TOKEN_LOCK:
            _NUSUK_TOKEN_CACHE.pop(email, None)
        return None
    return item


def _nusuk_cache_set(email: str, token: str, otp_id=None, user_id=None):
    with _NUSUK_TOKEN_LOCK:
        _NUSUK_TOKEN_CACHE[email] = {"token": token, "created_at": time.time(),
                                     "otp_id": otp_id, "user_id": user_id}


def nusuk_api_fetch_token(email: str, password: str, otp: Optional[str] = None,
                          otp_email: Optional[str] = None, otp_app_password: Optional[str] = None,
                          otp_timeout: int = 90, device_id: Optional[str] = None,
                          lang: str = "ar", use_cache: bool = True,
                          otp_id: Optional[int] = None) -> dict:
    """التدفق الكامل: login → (OTP يدوي أو من Gmail) → validate-otp → Bearer Token.
    لو otp + otp_id مبعوتين مع بعض، يتخطى login ويؤكد الكود مباشرة على نفس otpId (بدون إرسال كود جديد)."""
    e = (email or "").strip().lower()
    p = (password or "").strip()
    if not e or not p:
        return {"ok": False, "stage": "input", "error": "لازم email و password"}

    if use_cache:
        cached = _nusuk_cache_get(e)
        if cached and cached.get("user_id") is not None:
            if nusuk_token_is_valid(cached.get("token"), device_id=device_id, lang=lang):
                log.info("استخدام توكن نسك المخزّن مؤقتاً لـ %s (UserID=%s)", e, cached.get("user_id"))
                return {"ok": True, "token": cached["token"], "otp_id": cached.get("otp_id"),
                        "user_id": cached.get("user_id"), "stage": "cache", "cached": True, "validated": True}
            log.info("♻️ التوكن المخزّن منتهي — تسجيل دخول جديد لـ %s", e)
            _nusuk_drop_cached_token(e)

    t0 = time.time()
    otp_val = (otp or "").strip()
    if otp_val and otp_id:
        otp_id = int(otp_id)
        log.info("تأكيد كود OTP مباشرة على otpId=%s (بدون login جديد)", otp_id)
    else:
        step1 = nusuk_api_login(e, p, device_id=device_id, lang=lang)
        if not step1["ok"]:
            return {"ok": False, "stage": "login",
                    "error": step1.get("response_desc") or "فشل تسجيل الدخول",
                    "http_status": step1.get("http_status"),
                    "response_code": step1.get("response_code"),
                    "data": step1.get("data")}

        otp_id = step1["otp_id"]
        if not otp_val:
            if not (otp_email and otp_app_password):
                return {"ok": False, "stage": "otp", "otp_id": otp_id,
                        "error": "مطلوب كود OTP أو otp_email + otp_app_password لقراءة الكود من Gmail"}
            log.info("انتظار OTP من بريد %s ...", otp_email)
            otp_val = fetch_nusuk_otp(otp_email, otp_app_password, timeout=otp_timeout, sent_after=t0) or ""
            if not otp_val:
                return {"ok": False, "stage": "otp", "otp_id": otp_id,
                        "error": "لم يتم العثور على كود OTP في البريد خلال الوقت المحدد"}

    step2 = nusuk_api_verify_otp(e, p, otp_val, otp_id, device_id=device_id, lang=lang)
    if not step2["ok"]:
        return {"ok": False, "stage": "validate-otp", "otp_id": otp_id,
                "error": step2.get("response_desc") or "فشل تأكيد الـ OTP",
                "http_status": step2.get("http_status"),
                "response_code": step2.get("response_code"),
                "data": step2.get("data")}

    _nusuk_cache_set(e, step2["token"], otp_id=otp_id, user_id=step2.get("user_id"))
    return {"ok": True, "token": step2["token"], "otp_id": otp_id, "user_id": step2.get("user_id"),
            "stage": "validate-otp", "cached": False}


def resolve_nusuk_bearer_token(bearer_token: Optional[str] = None, email: Optional[str] = None,
                               password: Optional[str] = None, otp: Optional[str] = None,
                               otp_email: Optional[str] = None, otp_app_password: Optional[str] = None,
                               otp_timeout: int = 90, device_id: Optional[str] = None,
                               lang: str = "ar", otp_id: Optional[int] = None) -> dict:
    """يرجّع token جاهز: إما الممرَّر مباشرة أو عن طريق تسجيل دخول تلقائي."""
    if bearer_token and bearer_token.strip():
        return {"ok": True, "token": bearer_token.strip(), "source": "request"}
    if email and password:
        res = nusuk_api_fetch_token(email, password, otp=otp, otp_email=otp_email,
                                    otp_app_password=otp_app_password, otp_timeout=otp_timeout,
                                    device_id=device_id, lang=lang, otp_id=otp_id)
        if res.get("ok"):
            return {"ok": True, "token": res["token"], "source": res.get("stage"),
                    "otp_id": res.get("otp_id"), "user_id": res.get("user_id"),
                    "cached": res.get("cached", False)}
        return {"ok": False, "error": res.get("error"), "stage": res.get("stage")}
    return {"ok": False, "stage": "input",
            "error": "مطلوب bearer_token أو email + password (مع otp أو otp_email + otp_app_password)"}


class NusukTokenRequest(BaseModel):
    email: str
    password: str
    otp: Optional[str] = None
    otp_id: Optional[int] = None
    otp_email: Optional[str] = None
    otp_app_password: Optional[str] = None
    otp_timeout: int = 90
    device_id: Optional[str] = None
    lang: str = "ar"
    use_cache: bool = True


@app.post("/api/nusuk/token")
def nusuk_token_api(req: NusukTokenRequest):
    """جلب Bearer Token تلقائياً (من غير محاكي): v2/login → OTP (يدوي أو Gmail) → v2/login/validate-otp"""
    try:
        res = nusuk_api_fetch_token(req.email, req.password, otp=req.otp, otp_email=req.otp_email,
                                    otp_app_password=req.otp_app_password, otp_timeout=req.otp_timeout,
                                    device_id=req.device_id, lang=req.lang, use_cache=req.use_cache,
                                    otp_id=req.otp_id)
    except FlowError as e:
        return {"success": False, "error": str(e), "stage": "imap"}
    except Exception as e:
        log.exception("خطأ غير متوقع أثناء جلب توكن نسك")
        return {"success": False, "error": f"{type(e).__name__}: {e}", "stage": "internal"}
    return {
        "success": bool(res.get("ok")),
        "token": res.get("token"),
        "otp_id": res.get("otp_id"),
        "user_id": res.get("user_id"),
        "stage": res.get("stage"),
        "cached": res.get("cached", False),
        "http_status": res.get("http_status"),
        "response_code": res.get("response_code"),
        "error": res.get("error"),
    }


@app.get("/api/nusuk/token")
def nusuk_token_cache_api(email: str):
    """قراءة التوكن المخزّن مؤقتاً لحساب معيّن."""
    item = _nusuk_cache_get((email or "").strip().lower())
    if not item:
        return {"success": False, "error": "لا يوجد توكن مخزّن صالح لهذا الحساب", "email": email}
    return {"success": True, "email": email, "token": item["token"], "otp_id": item.get("otp_id"),
            "age_seconds": int(time.time() - float(item.get("created_at", time.time()))),
            "ttl_seconds": int(NUSUK_TOKEN_TTL)}


class NusukTokenClearRequest(BaseModel):
    email: Optional[str] = None


@app.post("/api/nusuk/token/clear")
def nusuk_token_clear_api(req: NusukTokenClearRequest):
    """حذف التوكن المخزّن (لحساب واحد أو للكل)."""
    with _NUSUK_TOKEN_LOCK:
        if req.email:
            removed = _NUSUK_TOKEN_CACHE.pop(req.email.strip().lower(), None) is not None
        else:
            removed = len(_NUSUK_TOKEN_CACHE)
            _NUSUK_TOKEN_CACHE.clear()
    return {"success": True, "removed": removed}


class CancelPermitAPIRequest(BaseModel):
    bearer_token: Optional[str] = None          # اختياري: لو مش موجود، السيرفر يعمل login ويجيب التوكن بنفسه
    email: Optional[str] = None                 # إيميل حساب نسك
    password: Optional[str] = None              # باسورد حساب نسك
    otp: Optional[str] = None                   # كود OTP يدوي (اختياري)
    otp_email: Optional[str] = None             # بريد Gmail اللي بيوصل عليه OTP
    otp_app_password: Optional[str] = None      # App Password للـ Gmail
    otp_timeout: int = 90
    service: str = "rawdah"  # rawdah | reservations
    reservation_id: Optional[str] = None
    permit_ids: Optional[List[str]] = None
    cancel_reason_id: Optional[int] = None
    payload: Optional[dict] = None
    encrypt_body: bool = False
    device_id: Optional[str] = None
    lang: str = "ar"
    extra_headers: Optional[Dict[str, str]] = None


def build_cancel_permit_payload(req: CancelPermitAPIRequest) -> dict:
    """يبني جسم rawdah|reservations/v2/cancelPermit مطابق لـ RawdahCancelPermitRequestDTO
    (Count / DeviceID / Latitude / LocationDesc / Longitude / Permits[CancellationReasonId, PermitID, ReasonDescription])."""
    if req.payload is not None:
        return req.payload

    reason_id = req.cancel_reason_id if req.cancel_reason_id is not None else 0
    permits = []
    for pid in (req.permit_ids or []):
        pid_val = pid
        try:
            pid_val = int(str(pid).strip())
        except (TypeError, ValueError):
            pass
        permits.append({
            "CancellationReasonId": reason_id,
            "PermitID": pid_val,
            "ReasonDescription": None,
        })

    inner: dict = {
        "Count": len(permits) if permits else 1,
        "DeviceID": req.device_id or NUSUK_DEVICE_ID,
        "Latitude": "19.545",
        "LocationDesc": "KSA",
        "Longitude": "19.5757",
        "Permits": permits,
    }
    return {"Request": inner}


@app.post("/api/rawdah/cancel-permit")
def rawdah_cancel_permit_api(req: CancelPermitAPIRequest):
    """إرسال طلب إلغاء حجز/تصريح مباشرة عبر Nusuk API (rawdah/v2/cancelPermit أو reservations/v2/cancelPermit)."""
    endpoints_map = {
        "rawdah": "rawdah/v2/cancelPermit",
        "reservations": "reservations/v2/cancelPermit",
    }
    ep = endpoints_map.get((req.service or "rawdah").strip().lower())
    if not ep:
        return {"success": False, "error": f"قيمة service غير صحيحة. المتاح: {list(endpoints_map.keys())}"}

    if req.payload is None and not req.permit_ids:
        return {"success": False,
                "error": "لازم permit_ids (قائمة IDs التصاريح) أو payload جاهز — endpoint الإلغاء بياخد IDs التصاريح مش رقم الحجز لوحده"}
    raw_body = build_cancel_permit_payload(req)

    token_info = resolve_nusuk_bearer_token(
        bearer_token=req.bearer_token,
        email=req.email,
        password=req.password,
        otp=req.otp,
        otp_email=req.otp_email,
        otp_app_password=req.otp_app_password,
        otp_timeout=req.otp_timeout,
        device_id=req.device_id,
        lang=req.lang,
    )
    if not token_info.get("ok"):
        return {
            "success": False,
            "stage": token_info.get("stage"),
            "error": token_info.get("error") or "تعذر الحصول على Bearer Token",
        }

    send_body = raw_body
    if req.encrypt_body:
        enc_data, _ = encrypt_rawdah(raw_body)
        send_body = {"data": enc_data}

    log.info(f"🗑️ إرسال طلب إلغاء حجز على {ep} (encrypted={req.encrypt_body}, token_source={token_info.get('source')})...")
    res = nusuk_http_request(
        ep,
        method="POST",
        body_dict=send_body,
        bearer_token=token_info["token"],
        device_id=req.device_id,
        lang=req.lang,
        extra_headers=req.extra_headers,
    )

    refreshed = False
    if _nusuk_is_session_error(res.get("data")) and req.email and req.password:
        log.warning("🔁 توكن نسك منتهي — إعادة تسجيل دخول تلقائي ثم إعادة المحاولة...")
        _nusuk_drop_cached_token(req.email)
        retry_token = resolve_nusuk_bearer_token(
            bearer_token=None,
            email=req.email,
            password=req.password,
            otp=req.otp,
            otp_email=req.otp_email,
            otp_app_password=req.otp_app_password,
            otp_timeout=req.otp_timeout,
            device_id=req.device_id,
            lang=req.lang,
        )
        if retry_token.get("ok"):
            token_info = retry_token
            refreshed = True
            res = nusuk_http_request(
                ep,
                method="POST",
                body_dict=send_body,
                bearer_token=token_info["token"],
                device_id=req.device_id,
                lang=req.lang,
                extra_headers=req.extra_headers,
            )

    return {
        "success": res["ok"],
        "endpoint": ep,
        "encrypted": req.encrypt_body,
        "refreshed_token": refreshed,
        "token_source": token_info.get("source"),
        "otp_id": token_info.get("otp_id"),
        "response_code": _nusuk_response_code(res.get("data")),
        "response_desc": _nusuk_envelope(res.get("data")).get("ResponseDesc", _nusuk_envelope(res.get("data")).get("responseDesc")),
        "error_hint": nusuk_error_hint(res.get("data")),
        "sent_request": raw_body,
        **res,
    }


class RawdahPermitsRequest(BaseModel):
    bearer_token: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    otp: Optional[str] = None
    otp_email: Optional[str] = None
    otp_app_password: Optional[str] = None
    otp_timeout: int = 90
    reservation_id: int
    user_id: Optional[int] = None
    is_notification_group: bool = False
    notification_group_id: Optional[int] = None
    device_id: Optional[str] = None
    lang: str = "ar"


@app.post("/api/rawdah/permits")
def rawdah_permits_api(req: RawdahPermitsRequest):
    """جلب تصاريح الروضة لحجز معيّن (rawdah/v2/getRawdahPermits) — لاستخراج permit_ids قبل الإلغاء."""
    token_info = resolve_nusuk_bearer_token(
        bearer_token=req.bearer_token,
        email=req.email,
        password=req.password,
        otp=req.otp,
        otp_email=req.otp_email,
        otp_app_password=req.otp_app_password,
        otp_timeout=req.otp_timeout,
        device_id=req.device_id,
        lang=req.lang,
    )
    if not token_info.get("ok"):
        return {"success": False, "stage": token_info.get("stage"),
                "error": token_info.get("error") or "تعذر الحصول على Bearer Token"}

    auto_uid = token_info.get("user_id")
    if auto_uid is None:
        auto_uid = _nusuk_user_id_from_jwt(token_info.get("token"))
        if auto_uid is not None:
            log.info("👤 تم استخراج UserID من التوكن: %s", auto_uid)
    if auto_uid is not None:
        if req.user_id is not None and int(req.user_id) != int(auto_uid):
            log.info("👤 تجاهل UserID المكتوب يدويًا (%s) واستخدام UserID الصحيح (%s)", req.user_id, auto_uid)
        uid = auto_uid
    else:
        uid = req.user_id
    inner: Dict[str, object] = {
        "UserId": uid,
        "ReservationId": req.reservation_id,
        "IsNotificationGroupId": bool(req.is_notification_group),
        "NotificationGroupId": req.notification_group_id,
    }
    if uid is None:
        log.warning("⚠️ UserID غير معروف لهذا التوكن — لو رجع -9999 املأ خانة UserId يدويًا أو استخدم الدخول التلقائي")

    refreshed = False
    endpoints_try = ["rawdah/v2/getRawdahPermits", "umrah/v2/getUmrahPermitsByResId"]
    log.info("📋 جلب تصاريح الروضة للحجز %s (UserID=%s, token_source=%s)...",
             req.reservation_id, uid, token_info.get("source"))

    def _attempt_all():
        results = []
        for ep_try in endpoints_try:
            res_try = nusuk_http_request(
                ep_try,
                method="POST",
                body_dict={"Request": inner},
                bearer_token=token_info["token"],
                device_id=req.device_id,
                lang=req.lang,
            )
            upstream_try = res_try.get("data")
            code_try = _nusuk_response_code(upstream_try)
            ids_try = nusuk_extract_permit_ids(upstream_try)
            try:
                log.info("📋 [%s] ids=%s | code=%s | %s", ep_try, len(ids_try), code_try,
                         json.dumps(upstream_try, ensure_ascii=False)[:600])
            except Exception:
                pass
            results.append({"endpoint": ep_try, "res": res_try, "upstream": upstream_try,
                            "code": code_try, "ids": ids_try})
        return results

    attempts = _attempt_all()

    if all(_nusuk_is_session_error(a["upstream"]) for a in attempts) and req.email and req.password:
        log.warning("🔁 توكن نسك منتهي — إعادة تسجيل دخول تلقائي ثم إعادة المحاولة...")
        _nusuk_drop_cached_token(req.email)
        retry_token = resolve_nusuk_bearer_token(
            bearer_token=None,
            email=req.email,
            password=req.password,
            otp=req.otp,
            otp_email=req.otp_email,
            otp_app_password=req.otp_app_password,
            otp_timeout=req.otp_timeout,
            device_id=req.device_id,
            lang=req.lang,
        )
        if retry_token.get("ok"):
            token_info = retry_token
            refreshed = True
            attempts = _attempt_all()

    best = None
    for a in attempts:
        if a["ids"] or a["code"] == 200:
            best = a
            break
    if best is None:
        best = attempts[-1]

    res = best["res"]
    upstream = best["upstream"]
    permit_ids = best["ids"]
    env = _nusuk_envelope(upstream)
    response_code = env.get("ResponseCode", env.get("responseCode"))
    response_desc = env.get("ResponseDesc", env.get("responseDesc"))
    top_keys = list(upstream.keys())[:12] if isinstance(upstream, dict) else []

    return {
        "success": res["ok"],
        "permit_ids": permit_ids,
        "response_code": response_code,
        "response_desc": response_desc,
        "error_hint": nusuk_error_hint(upstream),
        "top_keys": top_keys,
        "used_endpoint": best["endpoint"],
        "attempts": [{"endpoint": a["endpoint"], "code": a["code"], "ids": len(a["ids"]),
                      "http_status": a["res"].get("http_status")} for a in attempts],
        "used_user_id": uid,
        "user_id_missing": uid is None,
        "refreshed_token": refreshed,
        "token_source": token_info.get("source"),
        "otp_id": token_info.get("otp_id"),
        "sent_request": inner,
        **res,
    }


class ActivePermitsRequest(BaseModel):
    bearer_token: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    otp: Optional[str] = None
    otp_email: Optional[str] = None
    otp_app_password: Optional[str] = None
    otp_timeout: int = 90
    device_id: Optional[str] = None
    lang: str = "ar"


@app.post("/api/nusuk/active-permits")
def nusuk_active_permits_api(req: ActivePermitsRequest):
    """جلب كل الحجوزات والتصاريح النشطة للحساب (manasik/ActivePermits) للاختيار والإلغاء."""
    token_info = resolve_nusuk_bearer_token(
        bearer_token=req.bearer_token,
        email=req.email,
        password=req.password,
        otp=req.otp,
        otp_email=req.otp_email,
        otp_app_password=req.otp_app_password,
        otp_timeout=req.otp_timeout,
        device_id=req.device_id,
        lang=req.lang,
    )
    if not token_info.get("ok"):
        return {"success": False, "stage": token_info.get("stage"),
                "error": token_info.get("error") or "تعذر الحصول على Bearer Token"}

    def _fetch_both():
        r_active = nusuk_http_request(
            "manasik/ActivePermits",
            method="GET",
            body_dict=None,
            bearer_token=token_info["token"],
            device_id=req.device_id,
            lang=req.lang,
        )
        r_cert = nusuk_http_request(
            "manasik/getPermitsForCertificate",
            method="GET",
            body_dict=None,
            bearer_token=token_info["token"],
            device_id=req.device_id,
            lang=req.lang,
        )
        return r_active, r_cert

    res, res_cert = _fetch_both()

    refreshed = False
    if _nusuk_is_session_error(res.get("data")) and req.email and req.password:
        log.warning("🔁 توكن نسك منتهي — إعادة تسجيل دخول تلقائي ثم إعادة المحاولة...")
        _nusuk_drop_cached_token(req.email)
        retry_token = resolve_nusuk_bearer_token(
            bearer_token=None, email=req.email, password=req.password, otp=req.otp,
            otp_email=req.otp_email, otp_app_password=req.otp_app_password,
            otp_timeout=req.otp_timeout, device_id=req.device_id, lang=req.lang,
        )
        if retry_token.get("ok"):
            token_info = retry_token
            refreshed = True
            res, res_cert = _fetch_both()

    upstream = res.get("data")
    summary = nusuk_summarize_active_permits(upstream)
    history_permits = nusuk_summarize_certificate_permits(res_cert.get("data"))
    env = _nusuk_envelope(upstream)
    env_cert = _nusuk_envelope(res_cert.get("data"))

    active_permit_ids = [str(x) for x in summary.get("permit_ids", [])]
    history_ids: List[str] = []
    for p in history_permits:
        pid = p.get("permit_id")
        if pid is not None and str(pid) not in history_ids:
            history_ids.append(str(pid))
    all_ids = active_permit_ids + [pid for pid in history_ids if pid not in active_permit_ids]

    log.info("📋 ActivePermits: reservations=%s | active=%s | history=%s | code=%s",
             len(summary.get("reservations", [])), len(active_permit_ids), len(history_ids),
             env.get("ResponseCode", env.get("responseCode")))
    try:
        log.info("📋 رد ActivePermits: %s", json.dumps(upstream, ensure_ascii=False)[:600])
        log.info("📋 رد PermitsForCertificate: %s", json.dumps(res_cert.get("data"), ensure_ascii=False)[:600])
    except Exception:
        pass

    return {
        "success": res["ok"],
        **summary,
        "response_code": env.get("ResponseCode", env.get("responseCode")),
        "response_desc": env.get("ResponseDesc", env.get("responseDesc")),
        "error_hint": nusuk_error_hint(upstream),
        "history_response_code": env_cert.get("ResponseCode", env_cert.get("responseCode")),
        "history_response_desc": env_cert.get("ResponseDesc", env_cert.get("responseDesc")),
        "history_error_hint": nusuk_error_hint(res_cert.get("data")),
        "refreshed_token": refreshed,
        "token_source": token_info.get("source"),
        "otp_id": token_info.get("otp_id"),
        "used_user_id": token_info.get("user_id"),
        "http_status": res.get("http_status"),
        "data": upstream,
        "history_data": res_cert.get("data"),
        "history_permits": history_permits,
        "active_permit_ids": active_permit_ids,
        "history_permit_ids": history_ids,
        "permit_ids": all_ids,
    }


# ==========================================
# Rawdah Booking API — المواعيد المتاحة + حجز تصريح + تأكيد
# ==========================================
class RawdahSlotsRequest(BaseModel):
    date: str
    to_date: Optional[str] = None
    count: int = 1
    service_id: int = 20          # RAWDAH_MALE=20 / RAWDAH_FEMALE=21
    queue_type: int = 0           # 0=REGULAR, 1=INSTANT, 2=ALL
    date_type: int = 1
    latitude: str = "24.4672"
    longitude: str = "39.6111"
    bearer_token: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    otp: Optional[str] = None
    otp_id: Optional[int] = None
    otp_email: Optional[str] = None
    otp_app_password: Optional[str] = None
    otp_timeout: int = 90
    device_id: Optional[str] = None
    lang: str = "ar"


def _norm_date(value: str) -> str:
    s = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def summarize_rawdah_slots(payload) -> dict:
    data = nusuk_extract_data(payload)
    dates = []
    if isinstance(data, dict):
        for d in (data.get("AvailableDates") or []):
            if not isinstance(d, dict):
                continue
            slots = []
            for itv in (d.get("Intervals") or []):
                if not isinstance(itv, dict):
                    continue
                gender = itv.get("Gender")
                timing = itv.get("Timing")
                for s in (itv.get("Timeslots") or []):
                    if not isinstance(s, dict):
                        continue
                    slots.append({
                        "timeslot_id": s.get("TimeslotID"),
                        "time_ar": s.get("TimeAr"),
                        "time_la": s.get("TimeLa"),
                        "percentage": s.get("Percentage"),
                        "is_instant": s.get("IsInstant"),
                        "gender": gender,
                        "timing": timing,
                        "service_id": s.get("ServiceId"),
                        "slot_state": s.get("SlotState"),
                        "ap_id": s.get("apId"),
                    })
            dates.append({
                "date": d.get("Date"),
                "date_type": d.get("DateType"),
                "percentage": d.get("Percentage"),
                "percentage_color": d.get("PercentageColor"),
                "instant_ineligibility": d.get("InstantInEligibilityReason"),
                "slots": slots,
            })
    return {
        "dates": dates,
        "total_slots": sum(len(x["slots"]) for x in dates),
        "server_date_time": data.get("DateTime") if isinstance(data, dict) else None,
    }


@app.post("/api/rawdah/available-slots")
def rawdah_available_slots_api(req: RawdahSlotsRequest):
    """جلب المواعيد المتاحة للروضة (rawdah/v2/availableSlotDays — جسم مشفّر AES)."""
    token_info = resolve_nusuk_bearer_token(
        bearer_token=req.bearer_token, email=req.email, password=req.password, otp=req.otp,
        otp_email=req.otp_email, otp_app_password=req.otp_app_password,
        otp_timeout=req.otp_timeout, device_id=req.device_id, lang=req.lang, otp_id=getattr(req, "otp_id", None),
    )
    if not token_info.get("ok"):
        return {"success": False, "stage": token_info.get("stage"),
                "error": token_info.get("error") or "تعذر الحصول على Bearer Token"}

    def _to_float(v, default):
        try:
            return float(str(v).strip())
        except (TypeError, ValueError):
            return default

    lat = _to_float(req.latitude, 24.4672)
    lng = _to_float(req.longitude, 39.6111)
    d_iso = _norm_date(req.date)
    t_iso = _norm_date(req.to_date or req.date)

    def _fmt_dmy(iso: str) -> str:
        try:
            return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return iso

    service_ids = [req.service_id]
    if 1 not in service_ids:
        service_ids.append(1)
    variants = []
    for svc in service_ids:
        for fmt in ("iso", "dmy"):
            variants.append({
                "service_id": svc,
                "date_format": fmt,
                "inner": {"Request": {
                    "Count": req.count,
                    "Date": d_iso if fmt == "iso" else _fmt_dmy(d_iso),
                    "DateType": req.date_type,
                    "Location": {"Latitude": lat, "Longitude": lng},
                    "QueueType": req.queue_type,
                    "ServiceID": svc,
                    "ToDate": t_iso if fmt == "iso" else _fmt_dmy(t_iso),
                }},
            })

    res = None
    used_variant = variants[0]
    attempts = []
    for v in variants:
        enc_data, _key = encrypt_rawdah(v["inner"])
        res_try = nusuk_http_request(
            "rawdah/v2/availableSlotDays",
            method="POST",
            body_dict={"data": enc_data},
            bearer_token=token_info["token"],
            device_id=req.device_id,
            lang=req.lang,
        )
        code_try = _nusuk_response_code(res_try.get("data"))
        slots_try = summarize_rawdah_slots(res_try.get("data"))["total_slots"]
        attempts.append({"service_id": v["service_id"], "date_format": v["date_format"],
                         "code": code_try, "slots": slots_try})
        res = res_try
        used_variant = v
        try:
            log.info("📅 محاولة Slots: service=%s fmt=%s → code=%s slots=%s",
                     v["service_id"], v["date_format"], code_try, slots_try)
        except Exception:
            pass
        if _nusuk_is_session_error(res_try.get("data")):
            break
        if code_try in (200, "200") or slots_try:
            break

    if res is not None and _nusuk_is_session_error(res.get("data")) and req.email and req.password:
        _nusuk_drop_cached_token(req.email)
        retry_token = resolve_nusuk_bearer_token(
            bearer_token=None, email=req.email, password=req.password, otp=req.otp,
            otp_email=req.otp_email, otp_app_password=req.otp_app_password,
            otp_timeout=req.otp_timeout, device_id=req.device_id, lang=req.lang, otp_id=getattr(req, "otp_id", None),
        )
        if retry_token.get("ok"):
            token_info = retry_token
            enc_data, _key = encrypt_rawdah(used_variant["inner"])
            res = nusuk_http_request(
                "rawdah/v2/availableSlotDays",
                method="POST",
                body_dict={"data": enc_data},
                bearer_token=token_info["token"],
                device_id=req.device_id,
                lang=req.lang,
            )

    if _nusuk_is_session_error(res.get("data")):
        return {
            "success": False,
            "stage": "session",
            "dates": [],
            "total_slots": 0,
            "response_code": _nusuk_response_code(res.get("data")),
            "response_desc": _nusuk_envelope(res.get("data")).get(
                "ResponseDesc", _nusuk_envelope(res.get("data")).get("responseDesc")),
            "error_hint": "انتهت الجلسة — اضغط زر (دخول وجلب التوكن) تاني واكتب OTP الجديد",
            "error": "انتهت الجلسة — أعد تسجيل الدخول (OTP جديد)",
            "http_status": res.get("http_status"),
            "token_source": token_info.get("source"),
            "used_user_id": token_info.get("user_id"),
            "data": res.get("data"),
        }

    upstream = res.get("data")
    summary = summarize_rawdah_slots(upstream)
    env = _nusuk_envelope(upstream)
    log.info("📅 availableSlotDays: dates=%s | slots=%s | code=%s",
             len(summary["dates"]), summary["total_slots"],
             env.get("ResponseCode", env.get("responseCode")))
    try:
        log.info("📅 رد availableSlotDays: %s", json.dumps(upstream, ensure_ascii=False)[:500])
    except Exception:
        pass

    return {
        "success": res["ok"],
        **summary,
        "response_code": env.get("ResponseCode", env.get("responseCode")),
        "response_desc": env.get("ResponseDesc", env.get("responseDesc")),
        "error_hint": nusuk_error_hint(upstream),
        "http_status": res.get("http_status"),
        "token_source": token_info.get("source"),
        "used_user_id": token_info.get("user_id"),
        "used_variant": {"service_id": used_variant["service_id"],
                         "date_format": used_variant["date_format"]},
        "attempts": attempts,
        "sent_request": used_variant["inner"],
        "data": upstream,
    }


class RawdahIssueRequest(BaseModel):
    timeslot_ids: List[str]
    count: int = 1
    service_id: int = 20
    assembly_point_id: int = 20
    is_instant: bool = False
    issue_rawda_permit: Optional[str] = None     # "1" عادي / "3" فوري
    user_type: Optional[str] = None              # citizen_resident | external_visitor
    latitude: str = "24.4672"
    longitude: str = "39.6111"
    location_desc: str = ""
    family_friends_ids: List[int] = []
    relatives_ids: List[int] = []
    muatamer_list: List[dict] = []
    user_identification: Optional[int] = None
    bearer_token: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    otp: Optional[str] = None
    otp_id: Optional[int] = None
    otp_email: Optional[str] = None
    otp_app_password: Optional[str] = None
    otp_timeout: int = 90
    device_id: Optional[str] = None
    lang: str = "ar"


@app.post("/api/rawdah/issue-permit")
def rawdah_issue_permit_api(req: RawdahIssueRequest):
    """إرسال طلب حجز تصريح روضة (issuePermit: instant-track / citizen-resident / external-visitor)."""
    token_info = resolve_nusuk_bearer_token(
        bearer_token=req.bearer_token, email=req.email, password=req.password, otp=req.otp,
        otp_email=req.otp_email, otp_app_password=req.otp_app_password,
        otp_timeout=req.otp_timeout, device_id=req.device_id, lang=req.lang, otp_id=getattr(req, "otp_id", None),
    )
    if not token_info.get("ok"):
        return {"success": False, "stage": token_info.get("stage"),
                "error": token_info.get("error") or "تعذر الحصول على Bearer Token"}

    uid = req.user_identification or token_info.get("user_id")
    if uid is None:
        uid = _nusuk_user_id_from_jwt(token_info.get("token"))
    identification = uid if uid is not None else -1

    is_instant = bool(req.is_instant)
    issue_flag = req.issue_rawda_permit or ("3" if is_instant else "1")
    if is_instant:
        candidates = ["rawdah/v2/issuePermit/instant-track"]
    elif req.user_type:
        ut = req.user_type.strip().lower()
        candidates = ["rawdah/v2/issuePermit/citizen-resident" if "citizen" in ut
                      else "rawdah/v2/issuePermit/external-visitor"]
    else:
        candidates = ["rawdah/v2/issuePermit/citizen-resident", "rawdah/v2/issuePermit/external-visitor"]

    inner = {
        "AssemblyPointID": req.assembly_point_id,
        "Count": req.count,
        "FamilyAndFriendsIDS": req.family_friends_ids or [],
        "IssueRawdaPermit": issue_flag,
        "MainUserDeviceID": req.device_id or NUSUK_DEVICE_ID,
        "MainUserIdentification": identification,
        "MainUserLatitude": req.latitude,
        "MainUserLocationDesc": req.location_desc or "",
        "MainUserLongitude": req.longitude,
        "MuatamerList": req.muatamer_list or [],
        "RelativesIDS": req.relatives_ids or [],
        "ServiceID": req.service_id,
        "TimeslotID": [str(x) for x in (req.timeslot_ids or [])],
        "WaitingListRequestId": 0,
    }

    def _run_candidates():
        results = []
        for ep_try in candidates:
            log.info("🎫 إرسال حجز على %s ...", ep_try)
            res_try = nusuk_http_request(
                ep_try, method="POST", body_dict={"Request": inner},
                bearer_token=token_info["token"], device_id=req.device_id, lang=req.lang,
            )
            env_try = _nusuk_envelope(res_try.get("data"))
            code_try = env_try.get("ResponseCode", env_try.get("responseCode"))
            results.append({
                "endpoint": ep_try, "res": res_try, "code": code_try,
                "desc": env_try.get("ResponseDesc", env_try.get("responseDesc")),
                "session": _nusuk_is_session_error(res_try.get("data")),
            })
            try:
                log.info("🎫 [%s] code=%s | %s", ep_try, code_try,
                         json.dumps(res_try.get("data"), ensure_ascii=False)[:500])
            except Exception:
                pass
            if not results[-1]["session"] and (
                    code_try in (200, "200", 0, "0") or nusuk_extract_permit_ids(res_try.get("data"))):
                break
        return results

    results = _run_candidates()
    if results and all(r["session"] for r in results) and req.email and req.password:
        log.warning("🔁 توكن نسك منتهي — إعادة تسجيل دخول تلقائي ثم إعادة المحاولة...")
        _nusuk_drop_cached_token(req.email)
        retry_token = resolve_nusuk_bearer_token(
            bearer_token=None, email=req.email, password=req.password, otp=req.otp,
            otp_email=req.otp_email, otp_app_password=req.otp_app_password,
            otp_timeout=req.otp_timeout, device_id=req.device_id, lang=req.lang, otp_id=getattr(req, "otp_id", None),
        )
        if retry_token.get("ok"):
            token_info = retry_token
            results = _run_candidates()

    if results and all(r["session"] for r in results):
        return {
            "success": False, "stage": "session", "permit_ids": [],
            "attempts": [{"endpoint": r["endpoint"], "code": r["code"], "desc": r["desc"]} for r in results],
            "response_code": results[-1]["code"],
            "response_desc": results[-1]["desc"],
            "error_hint": "انتهت الجلسة — اضغط زر (دخول وجلب التوكن) تاني واكتب OTP الجديد",
            "error": "انتهت الجلسة — أعد تسجيل الدخول (OTP جديد)",
            "http_status": results[-1]["res"].get("http_status"),
            "used_user_id": uid,
            "sent_request": inner,
            "data": results[-1]["res"].get("data"),
        }

    chosen = None
    for r in results:
        if not r["session"] and (
                r["code"] in (200, "200", 0, "0") or nusuk_extract_permit_ids(r["res"].get("data"))):
            chosen = r
            break
    if chosen is None and results:
        chosen = results[-1]

    res = chosen["res"] if chosen else None
    used_endpoint = chosen["endpoint"] if chosen else None
    attempts = [{"endpoint": r["endpoint"], "http_status": r["res"].get("http_status"),
                 "code": r["code"], "desc": r["desc"]} for r in results]

    upstream = res.get("data") if res else None
    env = _nusuk_envelope(upstream)
    permit_ids = nusuk_extract_permit_ids(upstream)
    return {
        "success": bool(res and res.get("ok")),
        "endpoint": used_endpoint,
        "attempts": attempts,
        "permit_ids": permit_ids,
        "response_code": env.get("ResponseCode", env.get("responseCode")),
        "response_desc": env.get("ResponseDesc", env.get("responseDesc")),
        "error_hint": nusuk_error_hint(upstream),
        "http_status": res.get("http_status") if res else None,
        "used_user_id": uid,
        "sent_request": inner,
        "data": upstream,
    }


class RawdahConfirmRequest(BaseModel):
    permit_ids: List[str]
    bearer_token: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    otp: Optional[str] = None
    otp_email: Optional[str] = None
    otp_app_password: Optional[str] = None
    otp_timeout: int = 90
    device_id: Optional[str] = None
    lang: str = "ar"


@app.post("/api/rawdah/confirm-permit")
def rawdah_confirm_permit_api(req: RawdahConfirmRequest):
    """تأكيد التصاريح بعد الحجز (rawdah/v2/confirmPermit — {PermitsIds})."""
    token_info = resolve_nusuk_bearer_token(
        bearer_token=req.bearer_token, email=req.email, password=req.password, otp=req.otp,
        otp_email=req.otp_email, otp_app_password=req.otp_app_password,
        otp_timeout=req.otp_timeout, device_id=req.device_id, lang=req.lang,
    )
    if not token_info.get("ok"):
        return {"success": False, "stage": token_info.get("stage"),
                "error": token_info.get("error") or "تعذر الحصول على Bearer Token"}

    ids = []
    for pid in (req.permit_ids or []):
        ids.append(int(pid) if str(pid).strip().isdigit() else pid)
    inner = {"PermitsIds": ids}
    log.info("✅ تأكيد التصاريح: %s", ids)
    res = nusuk_http_request(
        "rawdah/v2/confirmPermit", method="POST", body_dict={"Request": inner},
        bearer_token=token_info["token"], device_id=req.device_id, lang=req.lang,
    )
    env = _nusuk_envelope(res.get("data"))
    try:
        log.info("✅ رد confirmPermit: %s", json.dumps(res.get("data"), ensure_ascii=False)[:500])
    except Exception:
        pass
    return {
        "success": bool(res.get("ok")),
        "response_code": env.get("ResponseCode", env.get("responseCode")),
        "response_desc": env.get("ResponseDesc", env.get("responseDesc")),
        "error_hint": nusuk_error_hint(res.get("data")),
        "http_status": res.get("http_status"),
        "sent_request": inner,
        "data": res.get("data"),
    }


@app.get("/")
def serve_index():
    """تقديم واجهة التحكم (index.html) من نفس مجلد السيرفر."""
    if os.path.isfile(INDEX_FILE):
        return FileResponse(INDEX_FILE, media_type="text/html")
    return {
        "success": False,
        "error": "index.html غير موجود بجوار server.py",
        "hint": "ضع ملف الواجهة باسم index.html في مجلد السيرفر، أو حدد مساره في NUSUK_INDEX_FILE",
    }


if __name__ == "__main__":
    import uvicorn

    log.info(f"تشغيل السيرفر على {HOST}:{PORT} | Origins: {ALLOWED_ORIGINS}")
    uvicorn.run(app, host=HOST, port=PORT)
