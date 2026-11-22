import copy
import email
import email.header
import email.utils
import html
import imaplib
import json
import logging
import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import uiautomator2 as u2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ==========================================
# الإعدادات العامة
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "nusuk_engine.log")
STATE_FILE = os.path.join(BASE_DIR, "nusuk_state.json")
SHOTS_DIR = os.path.join(BASE_DIR, "fail_shots")
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
SUCCESS_KEYS = [
    "exploring", "استكشاف", "استكشف", "تابع واستكشف", "نجاح",
    "تم التحقق", "تم انشاء", "تم استعاده",
]
ERROR_BANNER_KEYWORDS = [
    "غير صحيح", "غير صحيحه", "غير صالح", "غير صالحه", "بيانات غير",
    "لا يوجد حساب", "لم يتم العثور", "غير مطابق", "تاشيره غير", "تاشيره منتهيه",
    "منتهي الصلاحيه", "منتهيه الصلاحيه", "البريد الالكتروني مستخدم",
    "الرمز غير صحيح", "كود غير صحيح", "انتهت صلاحيه الرمز",
    "حدث خطا", "تعذر", "حاول مره اخري", "حاول لاحقا", "تم تجاوز الحد",
    "invalid", "incorrect", "not found", "expired", "already in use",
    "wrong code", "something went wrong", "try again", "too many attempts",
]
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
ARABIC_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_AR_DIGITS_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def strip_arabic_diacritics(text: str) -> str:
    return ARABIC_DIACRITICS_RE.sub("", text or "")


def normalize_arabic_digits(text: str) -> str:
    return (text or "").translate(_AR_DIGITS_TRANS)


def normalize_text(text: str) -> str:
    s = strip_arabic_diacritics(normalize_arabic_digits(text))
    return (
        s.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
        .strip()
        .lower()
    )

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
            for attempt in range(3):
                try:
                    os.replace(tmp, STATE_FILE)
                    return
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.06)
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
_devices_lock = threading.RLock()


def get_device(serial: str, timeout: int = 120):
    with _devices_lock:
        cached = _devices_cache.get(serial)
    if cached is not None:
        try:
            info = cached.info
            if info.get("screenOn") is False:
                try:
                    cached.screen_on()
                except Exception:
                    pass
            if info.get("screenOn") is not None:
                return cached
        except Exception:
            with _devices_lock:
                _devices_cache.pop(serial, None)

    start_t = time.time()
    while time.time() - start_t < timeout:
        try:
            dev = u2.connect(serial)
            info = dev.info
            if info.get("screenOn") is False:
                try:
                    dev.screen_on()
                except Exception:
                    pass
            if info.get("screenOn") is not None:
                with _devices_lock:
                    _devices_cache[serial] = dev
                return dev
        except Exception:
            pass
        time.sleep(1.5)
    raise RuntimeError(f"تعذر الاتصال بالمحاكي {serial}")


def smart_sleep(base_seconds: float, mult: float = 1.0):
    time.sleep(max(0.1, base_seconds * mult))


def safe_dump_hierarchy(dev, retries: int = 2, delay: float = 0.35) -> str:
    """قراءة شجرة الواجهة بأمان مع إعادة محاولة فورية ضد أخطاء ADB / UIAutomator العابرة"""
    for attempt in range(retries + 1):
        try:
            xml_str = dev.dump_hierarchy()
            if xml_str:
                return xml_str
        except Exception as e:
            if attempt >= retries:
                log.warning(f"تعذر قراءة واجهة المحاكي بعد {retries + 1} محاولات: {e}")
                return ""
            time.sleep(delay)
    return ""


def wait_for_network_loading(dev, max_wait: float = 12.0) -> bool:
    start_t = time.time()
    time.sleep(0.25)
    while time.time() - start_t < max_wait:
        xml_str = safe_dump_hierarchy(dev, retries=1)
        if xml_str:
            is_loading = (
                "ProgressBar" in xml_str
                or "جاري التحميل" in xml_str
                or "يرجى الانتظار" in xml_str
                or "Loading" in xml_str
                or "Please wait" in xml_str
            )
            if not is_loading:
                return True
        time.sleep(0.6)
    return False


def get_sorted_edits(dev):
    """إرجاع خانات الإدخال مرتبة من الأعلى للأسفل لضمان عدم تبديل الخانات أبداً"""
    try:
        edits = dev(className="android.widget.EditText")
        count = len(edits)
        if count <= 1:
            return [edits[i] for i in range(count)]
        indexed = []
        for i in range(count):
            el = edits[i]
            try:
                top = el.info.get("bounds", {}).get("top", i * 100)
                left = el.info.get("bounds", {}).get("left", 0)
            except Exception:
                top, left = i * 100, 0
            indexed.append((top, left, el))
        indexed.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in indexed]
    except Exception:
        return []


def safe_set_text(dev, el, value: str, mult: float = 1.0, is_password: bool = False):
    """كتابة نص في خانة EditText بموثوقية عالية مع تحقق واحتياط send_keys لو فشل set_text في Compose"""
    text_val = str(value)
    wrote = False
    try:
        el.set_text(text_val)
        wrote = True
    except Exception:
        wrote = False

    if wrote and not is_password and text_val:
        try:
            smart_sleep(0.12, mult)
            cur = (el.get_text() or "").strip()
            if cur == "":
                wrote = False
        except Exception:
            pass

    if not wrote:
        try:
            b = el.info.get("bounds", {})
            cx = (b.get("left", 100) + b.get("right", 980)) // 2
            cy = (b.get("top", 300) + b.get("bottom", 400)) // 2
            dev.click(cx, cy)
            smart_sleep(0.2, mult)
            dev.send_keys(text_val, clear=True)
        except Exception:
            dev.send_keys(text_val, clear=True)


def extract_screen_error(xml_str: str) -> Optional[str]:
    """استخراج نص رسالة الخطأ من الواجهة إن وجدت للفشل السريع بدلاً من الانتظار العشوائي"""
    if not xml_str:
        return None
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
        for node in root.iter():
            if node.attrib.get("class") == "android.widget.EditText":
                continue
            raw_t = (node.attrib.get("text") or "").strip()
            if not raw_t or len(raw_t) < 4:
                continue
            norm_t = normalize_text(raw_t)
            # تجاهل جملة المساعدة العادية "لديك مشكلة في تسجيل الدخول؟"
            if "لديك مشكله" in norm_t or "having trouble" in norm_t:
                continue
            if any(k in norm_t for k in ERROR_BANNER_KEYWORDS):
                return raw_t
    except Exception:
        pass
    return None


def wait_edits(dev, min_count: int, timeout: float = 7.0, interval: float = 0.25):
    end = time.time() + timeout
    while True:
        edits = get_sorted_edits(dev)
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


def launch_nusuk_app(dev, emu_key: str) -> bool:
    """تشغيل تطبيق نسك بأمان مع timeout وتجنب النقر العشوائي على الشاشة لو كان التطبيق مفتوحاً بالفعل"""
    idx = EMUS[emu_key]["index"]
    try:
        subprocess.run(
            [LDCONSOLE, "runapp", "--index", idx, "--packagename", PACKAGE_NAME],
            timeout=25,
            check=False,
        )
    except Exception as e:
        log.warning(f"تعذر تشغيل التطبيق عبر ldconsole ({e}) - محاولة app_start مباشرة...")
        try:
            dev.app_start(PACKAGE_NAME)
        except Exception:
            pass

    if wait_app_foreground(dev, PACKAGE_NAME, 5.0):
        return True

    try:
        dev.app_start(PACKAGE_NAME)
        if wait_app_foreground(dev, PACKAGE_NAME, 4.0):
            return True
    except Exception:
        pass

    try:
        nusuk_icon = dev(text="Nusuk")
        if not nusuk_icon.exists:
            nusuk_icon = dev(text="نسك")
        if nusuk_icon.exists:
            nusuk_icon.click()
        else:
            dev.click(694, 280)
    except Exception:
        pass
    return wait_app_foreground(dev, PACKAGE_NAME, 6.0)


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

    # تحويل إحداثيات القائمة القديمة (195 / 275) إلى الإحداثيات الجديدة (246 / 323)
    mapped_default = 246 if default_y == 195 else (323 if default_y == 275 else default_y)
    final_y = 323 if (ar_ver == "مصر" or en_ver.lower() == "egypt") else mapped_default
    return ar_ver, en_ver, final_y


def visible_text_without_inputs(xml_str: str, min_y: int = 0, max_y: int = 1920) -> str:
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
    except Exception:
        return xml_str.lower()
    parts = []
    for node in root.iter():
        if node.attrib.get("class") == "android.widget.EditText":
            continue
        if min_y > 0 or max_y < 1920:
            bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds") or "")
            if not bm:
                continue
            cy = (int(bm.group(2)) + int(bm.group(4))) // 2
            if not (min_y <= cy <= max_y):
                continue
        t = node.attrib.get("text") or ""
        d = node.attrib.get("content-desc") or ""
        if t:
            parts.append(t)
        if d:
            parts.append(d)
    return " ".join(parts).lower()


def wait_country_picker_open(dev, timeout: float = 5.0, interval: float = 0.25) -> bool:
    """التأكد الفعلي من فتح شاشة اختيار الدولة (وجود مربع البحث العلوي top < 220 أو زر التأكيد السفلي)"""
    end = time.time() + timeout
    while True:
        try:
            for el in dev(className="android.widget.EditText"):
                if el.info.get("bounds", {}).get("top", 9999) < 220:
                    return True
            dump = normalize_text(safe_dump_hierarchy(dev, retries=1))
            if any(k in dump for k in ("اكد اختيارك", "تاكيد الاختيار", "confirm selection", "confirm")):
                return True
        except Exception:
            pass
        if time.time() >= end:
            return False
        time.sleep(interval)


def _is_country_picker_currently_open(dev) -> bool:
    try:
        for el in dev(className="android.widget.EditText"):
            if el.info.get("bounds", {}).get("top", 9999) < 220:
                return True
        dump = normalize_text(safe_dump_hierarchy(dev, retries=1))
        return any(k in dump for k in ("اكد اختيارك", "تاكيد الاختيار", "confirm selection"))
    except Exception:
        return False


def click_nationality_result(dev, ar_ver: str, en_ver: str, fallback_y: int) -> bool:
    """الضغط على نتيجة الجنسية المطابقة من القائمة (مع تجاهل مربع البحث العلوي) ثم الرجوع للإحداثي الجديد كاحتياط"""
    try:
        xml_str = safe_dump_hierarchy(dev)
        root = ET.fromstring(xml_str.encode("utf-8"))
        targets_exact = {normalize_text(v) for v in (ar_ver, en_ver) if v and v.strip()}
        exact_hit = None
        partial_hits = []
        for node in root.iter():
            if node.attrib.get("class") == "android.widget.EditText":
                continue
            if node.attrib.get("enabled") == "false" or node.attrib.get("visible-to-user") == "false":
                continue
            raw_t = (node.attrib.get("text") or "").strip()
            if not raw_t:
                continue
            bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds") or "")
            if not bm:
                continue
            x1, y1, x2, y2 = map(int, bm.groups())
            if x2 <= x1 or y2 <= y1:
                continue
            cy = (y1 + y2) // 2
            if not (170 <= cy <= 1760):
                continue
            norm_t = normalize_text(raw_t)
            if norm_t in targets_exact:
                exact_hit = ((x1 + x2) // 2, cy)
                break
            if any(t in norm_t for t in targets_exact):
                partial_hits.append((len(norm_t), (x1 + x2) // 2, cy))
        if exact_hit:
            dev.click(exact_hit[0], exact_hit[1])
            return True
        if partial_hits:
            partial_hits.sort(key=lambda item: item[0])
            dev.click(partial_hits[0][1], partial_hits[0][2])
            return True
    except Exception:
        pass
    dev.click(540, fallback_y)
    return False


def ensure_visa_radio_selected(dev, mult: float = 1.0):
    """ضمان اختيار راديو (رقم التأشيرة) بدون الضغط بالخطأ على (رقم الحدود)"""
    try:
        xml_str = safe_dump_hierarchy(dev)
        root = ET.fromstring(xml_str.encode("utf-8"))
        for node in root.iter():
            if node.attrib.get("checkable") == "true":
                sub_texts = " ".join((c.attrib.get("text") or "") for c in node.iter())
                sub_clean = normalize_text(sub_texts)
                if "رقم التاشيره" in sub_clean or "visa" in sub_clean:
                    if node.attrib.get("checked") == "true":
                        return
                    bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds") or "")
                    if bm:
                        cx = (int(bm.group(1)) + int(bm.group(3))) // 2
                        cy = (int(bm.group(2)) + int(bm.group(4))) // 2
                        dev.click(cx, cy)
                        smart_sleep(0.4, mult)
                        return
        # في حال لم يُحدد كـ checkable ولكن النص ظاهر فقط، نتحقق إن كان حقل رقم التأشيرة مفتوحاً بالفعل
        if "رقم التاشيره" in normalize_text(xml_str):
            edits = dev(className="android.widget.EditText")
            if len(edits) >= 2:
                return
            if not click_text_in_xml(dev, xml_str, ("رقم التأشيرة", "رقم التاشيرة", "Visa"), min_y=650, max_y=815):
                dev.click(949, 745)
            smart_sleep(0.4, mult)
    except Exception:
        pass


def is_on_otp_screen(dev, xml_str: str = "") -> bool:
    """التحقق هل الشاشة الحالية هي شاشة إدخال رمز التحقق (OTP)"""
    dump = xml_str or safe_dump_hierarchy(dev, retries=1)
    norm = normalize_text(dump)
    try:
        if len(dev(className="android.widget.EditText")) >= 4:
            return True
    except Exception:
        pass
    return any(
        k in norm
        for k in (
            "رمز التحقق", "كود التحقق", "ادخل الرمز", "تحقق من بريدك",
            "verification code", "enter the code", "enter code", "resend code", "اعاده ارسال الرمز",
        )
    )


def enter_otp_code(dev, otp: str, fallback_x: int = 160, fallback_y: int = 458, mult: float = 1.0):
    """كتابة كود الـ OTP في أول خانة (أقصى اليسار) بدقة مع إعادة محاولة لو لم يُقبل الإدخال الأول"""
    clean_otp = re.sub(r"\D", "", normalize_arabic_digits(str(otp)))
    if not clean_otp:
        raise FlowError("كود OTP غير صالح أو فارغ")

    for attempt in range(2):
        clicked = False
        try:
            edits = dev(className="android.widget.EditText")
            if len(edits) >= 4:
                first_box = min(edits, key=lambda el: el.info.get("bounds", {}).get("left", 9999))
                b = first_box.info.get("bounds", {})
                cx = (b.get("left", 69) + b.get("right", 252)) // 2
                cy = (b.get("top", 416) + b.get("bottom", 500)) // 2
                dev.click(cx, cy)
                clicked = True
        except Exception:
            clicked = False
        if not clicked:
            dev.click(fallback_x, fallback_y)
        smart_sleep(0.25, mult)
        dev.shell("input keyevent 67 67 67 67 67 67")
        dev.shell(f"input text {clean_otp}")
        smart_sleep(0.45, mult)
        dev.shell("input keyevent 111")
        smart_sleep(0.8, mult)

        dump_chk = safe_dump_hierarchy(dev, retries=1)
        # لو في زر تحقق/تأكيد يدوي ظاهر على شاشة OTP نضغطه
        if is_on_otp_screen(dev, dump_chk):
            err = extract_screen_error(dump_chk)
            if err and any(k in normalize_text(err) for k in ("الرمز غير صحيح", "كود غير صحيح", "wrong code", "invalid", "انتهت صلاحيه")):
                raise FlowError(f"فشل التحقق من كود OTP: {err}")
            click_text_in_xml(dev, dump_chk, ("تحقق", "تأكيد", "Verify", "Confirm"), min_y=550, max_y=1200)
            smart_sleep(0.9, mult)
            if not is_on_otp_screen(dev):
                return
            if attempt == 0:
                log.warning("شاشة الـ OTP ما زالت مفتوحة - إعادة إدخال الكود مرة أخرى...")
                continue
        else:
            return


def dismiss_post_otp_popups(dev, mult: float = 1.0):
    """إغلاق نافذة تفعيل الموقع (لاحقًا) أو أي نوافذ منبثقة تظهر بعد إدخال OTP"""
    for _ in range(3):
        try:
            dump = safe_dump_hierarchy(dev, retries=1)
            if click_text_in_xml(dev, dump, ("لاحقًا", "لاحقا", "تخطي", "Later", "Skip"), min_y=1500, max_y=1900):
                smart_sleep(0.9, mult)
                continue
            norm = normalize_text(dump)
            if "فعل الموقع" in norm or "اغلاق الورقه" in norm or "enable location" in norm:
                dev.click(540, 1796)
                smart_sleep(0.9, mult)
                continue
            break
        except Exception:
            break
    for _ in range(2):
        dev.click(1000, 100)
        smart_sleep(0.25, mult)


def smart_search_nationality(dev, raw_nat: str, default_y: int, mult: float = 1.0):
    ar_ver, en_ver, final_y = get_both_nat_versions(raw_nat, default_y)
    dump_xml = safe_dump_hierarchy(dev)
    # فحص لغة القائمة من عناصر الدول فقط (y=170..1760) لتجاهل زر التأكيد وأيقونة البحث بالعربية
    list_visible = visible_text_without_inputs(dump_xml, min_y=170, max_y=1760)
    has_latin_countries = bool(re.search(r"[a-z]{4,}", list_visible))
    has_ar_countries = bool(re.search(r"[\u0600-\u06FF]{3,}", list_visible))
    if has_latin_countries and not has_ar_countries:
        is_arabic_screen = False
    elif has_ar_countries and not has_latin_countries:
        is_arabic_screen = True
    else:
        is_arabic_screen = False

    first_try = ar_ver if is_arabic_screen else en_ver
    second_try = en_ver if is_arabic_screen else ar_ver

    target_box = None
    try:
        edits = dev(className="android.widget.EditText")
        if len(edits) > 0:
            target_box = min(edits, key=lambda el: el.info.get("bounds", {}).get("top", 9999))
            target_box.click()
        else:
            dev.click(562, 95)
    except Exception:
        target_box = None
        dev.click(562, 95)

    smart_sleep(0.25, mult)
    wrote = False
    if target_box is not None:
        try:
            target_box.set_text(first_try)
            wrote = True
        except Exception:
            wrote = False
    if not wrote:
        dev.click(562, 95)
        smart_sleep(0.15, mult)
        dev.send_keys(first_try, clear=True)

    smart_sleep(0.65, mult)
    after_dump = safe_dump_hierarchy(dev)
    visible = normalize_text(visible_text_without_inputs(after_dump, min_y=170, max_y=1760))
    no_result_keywords = ["no result", "not found", "no data", "لا توجد", "لا يوجد", "غير موجود"]

    first_prefix = normalize_text(first_try)[:3]
    need_fallback = any(k in visible for k in no_result_keywords) or (first_prefix and first_prefix not in visible)

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
            dev.click(562, 95)
            smart_sleep(0.15, mult)
            dev.send_keys(second_try, clear=True)
        smart_sleep(0.65, mult)

    return final_y


def select_and_confirm_nationality(dev, raw_nat: str, default_y: int, mult: float = 1.0, confirm_fallback_y: int = 1854):
    """البحث عن الجنسية واختيار النتيجة المطابقة ثم الضغط على زر التأكيد مع التحقق من إغلاق القائمة"""
    ar_ver, en_ver, final_y = get_both_nat_versions(raw_nat, default_y)
    nat_y = smart_search_nationality(dev, raw_nat, default_y, mult=mult)
    dev.shell("input keyevent 111")
    smart_sleep(0.4, mult)
    for attempt in range(2):
        click_nationality_result(dev, ar_ver, en_ver, nat_y)
        smart_sleep(0.45, mult)
        dump_c = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_c, ("أكد اختيارك", "أكّد اختيارك", "تأكيد الاختيار", "Confirm"), min_y=1700, max_y=1910):
            dev.click(559, confirm_fallback_y)
        smart_sleep(0.7, mult)
        wait_for_network_loading(dev, max_wait=8.0)
        if not _is_country_picker_currently_open(dev):
            return
        if attempt == 0:
            log.warning("قائمة اختيار الجنسية ما زالت مفتوحة - إعادة اختيار الدولة وتأكيدها...")


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

    with _devices_lock:
        _devices_cache.pop(emu_serial, None)

    try:
        subprocess.run(
            [
                LDCONSOLE, "modify", "--index", emu_index,
                "--androidid", "auto", "--mac", "auto", "--imei", "auto",
            ],
            check=True,
            timeout=30,
        )
        log.info(f"[✓] تم تحديث معرّفات {emu_name} بنجاح.")

        subprocess.run([LDCONSOLE, "reboot", "--index", emu_index], check=True, timeout=45)
        log.info(f"[*] إرسال أمر ريستارت لـ {emu_name}.. في انتظار الإقلاع...")

        time.sleep(15)
        dev = get_device(emu_serial, timeout=180)
        time.sleep(5)

        launch_nusuk_app(dev, emu_key)
        time.sleep(8)
        wait_for_network_loading(dev, max_wait=10.0)
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
_otp_lock = threading.Lock()
_used_otp_ids = deque(maxlen=250)
_OTP_IGNORED_YEARS = {str(y) for y in range(2020, 2036)} | {str(y) for y in range(1440, 1456)}


def _imap_date(dt: datetime) -> str:
    return f"{dt.day:02d}-{MONTHS[dt.month - 1]}-{dt.year}"


def _html_to_text(raw_html: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html or "")
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    return html.unescape(cleaned)


def _extract_otp_from_body(body: str) -> Optional[str]:
    """استخراج كود OTP (4 أرقام) بذكاء بتفضيل الرقم القريب من كلمات التحقق وتجاهل السنوات"""
    norm_body = normalize_arabic_digits(body or "")
    # 1. البحث عن كود 4 أرقام بالقرب من عبارة تحقق صريحة
    ctx_patterns = (
        r"(?:رمز\s*التحقق|كود\s*التحقق|verification\s*code|otp|one[-\s]*time\s*code|passcode|الرمز\s*هو|your\s*code)[^\d]{0,120}\b(\d{4})\b",
        r"\b(\d{4})\b[^\d]{0,80}(?:رمز\s*التحقق|كود\s*التحقق|verification\s*code|otp)",
    )
    for pat in ctx_patterns:
        for m in re.finditer(pat, norm_body, re.IGNORECASE):
            code = m.group(1)
            if code not in _OTP_IGNORED_YEARS:
                return code

    # 2. الاحتياط: أول رقم مكون من 4 خانات ليس سنة ميلادية/هجرية
    codes = [c for c in re.findall(r"\b(\d{4})\b", norm_body) if c not in _OTP_IGNORED_YEARS]
    return codes[0] if codes else None


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
    min_ts = (sent_after - 60) if sent_after is not None else (start_time - 75)
    clean_pass = client_pass.replace(" ", "")
    checked = set()
    mail = None
    last_err_text = None

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
                    with _otp_lock:
                        already_used = key in _used_otp_ids
                    if key in checked or already_used:
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
                        otp = _extract_otp_from_body(body)
                        if otp:
                            try:
                                mail.store(mid, "+FLAGS", "\\Seen")
                            except Exception:
                                pass
                            with _otp_lock:
                                _used_otp_ids.append(key)
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
                if mail is not None:
                    try:
                        mail.logout()
                    except Exception:
                        pass
                mail = None
            except FlowError:
                raise
            except Exception as e:
                text = f"{type(e).__name__}: {e}"
                if text != last_err_text:
                    log.warning(f"خطأ أثناء قراءة البريد: {text}")
                    last_err_text = text
                if mail is not None:
                    try:
                        mail.logout()
                    except Exception:
                        pass
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
def _is_on_profile_xml(xml_str: str, nusuk_id: str = "") -> bool:
    if not xml_str or is_on_friends_show_all_page(xml_str):
        return False
    norm = normalize_text(xml_str)
    if nusuk_id and nusuk_id in xml_str:
        return True
    return any(
        m in norm
        for m in (
            "بطاقاتي", "my cards", "البطاقات والتصاريح", "عرض الكل", "show all",
            "العائله والاصدقاء", "family & friends", "الخدمات والطلبات", "رقم هويه نسك",
        )
    )


def _is_on_home_xml(xml_str: str) -> bool:
    if not xml_str or _is_on_profile_xml(xml_str) or is_on_friends_show_all_page(xml_str):
        return False
    norm = normalize_text(xml_str)
    return any(m in norm for m in ("المحفظه", "العمره", "الروضه", "نسك ai", "حجز تصريح", "wallet", "umrah", "rawdah"))


def _is_on_permits_xml(xml_str: str) -> bool:
    if not xml_str or _is_on_profile_xml(xml_str):
        return False
    norm = normalize_text(xml_str)
    return any(
        m in norm
        for m in (
            "رقم الحجز", "المواعيد", "لا توجد تصاريح", "لا توجد مواعيد", "لا توجد طلبات",
            "تصريح الروضه", "تصاريح", "السابقه", "القادمه", "reservation", "appointments",
            "no permits", "no appointments", "active permits", "rawdah",
        )
    )


def perform_safe_logout(dev, slow: bool = True, mult: float = 1.0) -> bool:
    """تسجيل خروج ذكي يتحقق من الشاشة الحالية، يمرر حتى ظهور زر تسجيل الخروج، يؤكد الحوار، ويتحقق من العودة لشاشة الدخول"""
    if on_login_screen(dev):
        return True

    # 1. التأكد من الوصول لصفحة البروفايل قبل السحب
    for _ in range(3):
        dump = safe_dump_hierarchy(dev)
        if not dump:
            break
        if on_login_screen(dev):
            return True
        if is_add_friend_dialog_open(dev):
            dev.press("back")
            smart_sleep(0.8, mult)
            continue
        if is_on_friends_show_all_page(dump):
            dev.click(52, 103)
            smart_sleep(1.0, mult)
            if is_on_friends_show_all_page(safe_dump_hierarchy(dev, retries=1)):
                dev.press("back")
                smart_sleep(0.9, mult)
            continue
        if _is_on_profile_xml(dump):
            break
        if _is_on_home_xml(dump):
            dev.click(61, 101)
            smart_sleep(1.5, mult)
            wait_for_network_loading(dev, max_wait=6.0)
            continue
        # في أي صفحة فرعية (تصاريح / نافذة منبثقة): نرجع خطوة ثم نفتح البروفايل
        dismiss_post_otp_popups(dev, mult=mult)
        dev.press("back")
        smart_sleep(1.0, mult)

    log.info("سحب القائمة لأسفل لتسجيل الخروج...")
    found_logout = False
    for swipe_idx in range(3):
        dump_lo = safe_dump_hierarchy(dev)
        if click_text_in_xml(dev, dump_lo, ("تسجيل خروج", "تسجيل الخروج", "Log out", "Logout"), min_y=1100, max_y=1895):
            found_logout = True
            break
        dev.swipe(0.5, 0.85, 0.5, 0.15, steps=22 if slow else 16)
        smart_sleep(0.9 if swipe_idx == 0 else 1.0, mult)

    if not found_logout:
        dump_lo = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_lo, ("تسجيل خروج", "تسجيل الخروج", "Log out", "Logout"), min_y=900, max_y=1895):
            log.info("النقر على إحداثيات تسجيل الخروج الاحتياطية (519, 1733)...")
            dev.click(519, 1733)

    smart_sleep(1.3, mult)
    if on_login_screen(dev):
        return True

    # 2. تأكيد نافذة تسجيل الخروج إن ظهرت
    clicked_confirm = False
    for _ in range(4):
        if on_login_screen(dev):
            return True
        dump_cf = safe_dump_hierarchy(dev)
        norm_cf = normalize_text(dump_cf)
        if click_text_in_xml(dev, dump_cf, ("نعم", "تأكيد", "موافق", "Yes", "Confirm"), min_y=800, max_y=1890):
            clicked_confirm = True
            break
        # الضغط على "تسجيل خروج" داخل حوار التأكيد فقط عند وجود نص سؤال تأكيد حتى لا نعيد ضغط زر البروفايل
        if any(q in norm_cf for q in ("هل انت متاكد", "متاكد", "تود تسجيل", "are you sure", "confirm")):
            if click_text_in_xml(dev, dump_cf, ("تسجيل خروج", "تسجيل الخروج", "Log out", "Logout"), min_y=900, max_y=1890):
                clicked_confirm = True
                break
        time.sleep(0.5)

    if not clicked_confirm and not on_login_screen(dev):
        dev.click(540, 1150)

    smart_sleep(2.2, mult)
    wait_for_network_loading(dev, max_wait=6.0)
    return _wait_login_screen(dev, timeout=6.0)


def pass_welcome_screen_if_needed(dev, mult: float = 1.0) -> bool:
    """تخطي الشاشة الترحيبية (هل أنت مستعد لبدء رحلتك؟ -> تسجيل الدخول أو إنشاء حساب) إن وُجدت"""
    try:
        dump = safe_dump_hierarchy(dev, retries=1)
        if "تسجيل الدخول للمتابعة" in dump or "أنشئ حسابًا جديدًا" in dump:
            return True
        if any(m in dump for m in WELCOME_MARKERS):
            log.info("تخطي شاشة البداية الترحيبية (تسجيل الدخول أو إنشاء حساب)...")
            if not click_text_in_xml(dev, dump, ("تسجيل الدخول أو إنشاء حساب", "Login or Sign up", "Log in or Sign up"), min_y=1550, max_y=1900):
                dev.click(540, 1781)
            smart_sleep(1.2, mult)
            wait_for_network_loading(dev, max_wait=6.0)
            return True
    except Exception:
        pass
    return False


def open_registration_form(dev, mult: float = 1.0):
    """يضمن الوصول لشاشة إنشاء الحساب (الـ 3 خانات مرتبة من الأعلى للأسفل) سواء من الشاشة الترحيبية أو النافذة السفلية"""
    for _ in range(3):
        edits = get_sorted_edits(dev)
        if len(edits) >= 3:
            return edits

        dump = safe_dump_hierarchy(dev)

        # لو دخل بالخطأ على شاشة تسجيل الدخول بالبريد (خانتين فقط)، نرجع بالسهم العلوي (1019, 91)
        if len(edits) == 2 or "مرحبًا بعودتك" in dump or "تسجيل الدخول إلى حسابك" in dump:
            dev.click(1019, 91)
            smart_sleep(1.0, mult)
            dump = safe_dump_hierarchy(dev)

        # 1. لو على الشاشة الترحيبية ("هل أنت مستعد لبدء رحلتك؟") نضغط الزر الأسود (540, 1781)
        if ("تسجيل الدخول للمتابعة" not in dump and "أنشئ حسابًا جديدًا" not in dump) and any(
            m in dump for m in WELCOME_MARKERS
        ):
            log.info("الضغط على الزر الأسود (تسجيل الدخول أو إنشاء حساب)...")
            if not click_text_in_xml(dev, dump, ("تسجيل الدخول أو إنشاء حساب", "Login or Sign up", "Log in or Sign up"), min_y=1550, max_y=1900):
                dev.click(540, 1781)
            smart_sleep(1.2, mult)
            dump = safe_dump_hierarchy(dev)

        # 2. الآن على النافذة المنبثقة ("تسجيل الدخول للمتابعة") -> نضغط "أنشئ حسابًا جديدًا" (519, 1714)
        if not click_text_in_xml(dev, dump, tuple(CREATE_MARKERS), min_y=1300, max_y=1900):
            dev.click(519, 1714)

        inputs = wait_edits(dev, 3, timeout=4.5 * mult)
        if inputs is not None:
            return inputs
    return None


def on_login_screen(dev) -> bool:
    try:
        if dev.app_current().get("package") != PACKAGE_NAME:
            return False
        dump = safe_dump_hierarchy(dev, retries=1)
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

    try:
        if on_login_screen(dev):
            return True
    except Exception:
        pass

    log.warning(f"🛡️ [{label}] الشاشة ليست على نقطة البداية! جاري التنظيف الذاتي قبل البدء...")

    try:
        dev.app_stop(PACKAGE_NAME)
        time.sleep(1.0)
        launch_nusuk_app(dev, emu_key)
        time.sleep(5.5)
        wait_for_network_loading(dev, max_wait=8.0)
    except Exception as e:
        log.warning(f"خطأ أثناء إعادة فتح التطبيق: {e}")

    if _wait_login_screen(dev, timeout=5.0):
        log.info(f"[✓] [{label}] تم استعادة شاشة الدخول بنجاح!")
        return True

    log.warning(f"[{label}] يوجد حساب سابق عالق بالداخل.. جاري إخراجه إجبارياً...")
    try:
        dismiss_post_otp_popups(dev, mult=1.0)
        if perform_safe_logout(dev, slow=True):
            log.info(f"[✓] [{label}] تم إخراج الحساب العالق والعودة لشاشة الدخول!")
            return True
    except Exception as e:
        log.warning(f"[{label}] خطأ أثناء محاولة إخراج الحساب العالق: {e}")

    if _wait_login_screen(dev, timeout=5.0):
        log.info(f"[✓] [{label}] تم إخراج الحساب العالق والعودة لشاشة الدخول!")
        return True

    log.error(f"[{label}] تعذر الوصول لشاشة الدخول بعد التنظيف الذاتي")
    return False


def reopen_nusuk_app(dev, emu_key: str, mult: float = 1.0) -> bool:
    """إغلاق تطبيق نسك وإعادة فتحه للوصول النظيف للشاشة الرئيسية بدون لخبطة في التنقل"""
    label = EMUS[emu_key]["label"]
    log.info(f"🔄 [{label}] إعادة تشغيل تطبيق نسك للرجوع للشاشة الرئيسية النظيفة...")
    try:
        dev.app_stop(PACKAGE_NAME)
        time.sleep(1.0)
        launch_nusuk_app(dev, emu_key)
        time.sleep(4.5 * mult)
        wait_for_network_loading(dev, max_wait=8.0)
        smart_sleep(1.0, mult)

        # التأكد من اختفاء أي نوافذ وظهور الشاشة الرئيسية
        for _ in range(10):
            dump = safe_dump_hierarchy(dev)
            norm = normalize_text(dump)
            if "فعل الموقع" in norm or "لاحقا" in norm:
                dismiss_post_otp_popups(dev, mult=mult)
                continue
            if _is_on_home_xml(dump) or _is_on_profile_xml(dump):
                log.info(f"[✓] [{label}] تم فتح تطبيق نسك والوصول للشاشة الرئيسية بنجاح!")
                return True
            if "تابع واستكشف" in norm or "continue exploring" in norm:
                click_text_in_xml(dev, dump, ("تابع واستكشف", "Continue Exploring", "استكشف"), min_y=1600, max_y=1900)
                smart_sleep(1.0, mult)
                continue
            if any(m in dump for m in WELCOME_MARKERS):
                log.warning(f"[{label}] التطبيق فتح على شاشة الترحيب/الدخول (الحساب غير مسجل دخول).")
                return False
            time.sleep(0.8)
        return wait_app_foreground(dev, PACKAGE_NAME, 2.0)
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
def click_text_in_xml(dev, xml_str: str, targets: tuple, min_y: int = 0, max_y: int = 1920, skip_edits: bool = True) -> bool:
    """البحث عن نص داخل XML الملتقط (بتطبيع الهمزات والتشكيل وترتيب أولوية targets وتفضيل التطابق الكامل) والضغط على مركز العنصر"""
    if not xml_str:
        return False
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
        lowered_targets = [normalize_text(t) for t in targets if t]
        candidates = []
        for node in root.iter():
            if skip_edits and node.attrib.get("class") == "android.widget.EditText":
                continue
            if node.attrib.get("enabled") == "false" or node.attrib.get("visible-to-user") == "false":
                continue
            t = normalize_text(node.attrib.get("text") or "")
            d = normalize_text(node.attrib.get("content-desc") or "")
            if not t and not d:
                continue
            bounds = node.attrib.get("bounds") or ""
            bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
            if not bm:
                continue
            x1, y1, x2, y2 = map(int, bm.groups())
            if x2 <= x1 or y2 <= y1:
                continue
            cy = (y1 + y2) // 2
            if min_y <= cy <= max_y:
                candidates.append((t, d, (x1 + x2) // 2, cy))

        # 1. التطابق التام أولاً حسب ترتيب أولوية targets
        for lt in lowered_targets:
            for t, d, cx, cy in candidates:
                if t == lt or d == lt:
                    dev.click(cx, cy)
                    return True

        # 2. الاحتواء الجزئي حسب ترتيب أولوية targets (مع تفضيل النص الأقصر لتجنب الفقرات الوصفية)
        for lt in lowered_targets:
            sub_hits = []
            for t, d, cx, cy in candidates:
                if lt in t or lt in d:
                    matched_len = len(t) if lt in t else len(d)
                    sub_hits.append((matched_len, cx, cy))
            if sub_hits:
                sub_hits.sort(key=lambda item: item[0])
                dev.click(sub_hits[0][1], sub_hits[0][2])
                return True
    except Exception:
        pass
    return False


def is_on_friends_show_all_page(xml_str: str) -> bool:
    """التحقق الصارم أن الشاشة داخل صفحة الأصدقاء (Show All) وليست على صفحة البروفايل الخارجية"""
    if not xml_str:
        return False
    norm = normalize_text(xml_str)
    profile_only_markers = (
        "عرض الكل", "show all", "بطاقاتي", "my cards",
        "البطاقات والتصاريح", "التصاريح الساريه", "active permits", "الحجوزات",
    )
    if any(pm in norm for pm in profile_only_markers):
        return False
    show_all_markers = (
        "جميع الاصدقاء", "all friends", "المفضله", "favorites",
        "اضف للمفضله", "اداره علاقاتك", "manage your",
        "طلبات مرسله", "sent requests", "في انتظار القبول",
    )
    return any(sm in norm for sm in show_all_markers)


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


def has_pending_friend_request_card(dump_xml: str) -> bool:
    """التحقق بدقة من وجود كرت طلب الإضافة المعلق (دون التطابق الخاطئ مع 'الخدمات والطلبات')"""
    norm = normalize_text(dump_xml or "")
    return any(
        k in norm
        for k in ("طلب اضافه", "friend request", "add request")
    )


def click_accept_friend_request(dev2, dump_xml: str = "", mult: float = 1.0) -> bool:
    """الضغط بدقة على علامة الصح (✓) لقبول طلب الصداقة في صفحة البروفايل (المحاكي الثاني)"""
    xml_str = dump_xml or safe_dump_hierarchy(dev2)

    # 1. لو ظهر زر نصي مباشر (قبول / Accept)
    if click_text_in_xml(dev2, xml_str, ("قبول", "موافقة", "Accept", "Approve"), min_y=250, max_y=650):
        return True

    # 2. تحديد زر علامة الصح (✓) ديناميكياً داخل كرت "طلب إضافة" (bounds=[116,362][195,446] -> center 155, 404)
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
        req_cx = None
        req_cy = None
        for node in root.iter():
            t = normalize_text(node.attrib.get("text") or "")
            if any(k in t for k in ("طلب اضافه", "friend request", "add request")):
                bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds") or "")
                if bm:
                    req_cx = (int(bm.group(1)) + int(bm.group(3))) // 2
                    req_cy = (int(bm.group(2)) + int(bm.group(4))) // 2
                    break

        is_ltr = req_cx is not None and req_cx < 540
        band_min = (req_cy - 60) if req_cy is not None else 320
        band_max = (req_cy + 90) if req_cy is not None else 490

        # جمع أزرار الأيقونات (✓ و ×) في نفس صف كرت الطلب (يساراً في العربية x < 320، يميناً في الإنجليزية x > 760)
        icon_btns = []
        for node in root.iter():
            if node.attrib.get("class") == "android.widget.Button":
                bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds") or "")
                if not bm:
                    continue
                x1, y1, x2, y2 = map(int, bm.groups())
                w, h = x2 - x1, y2 - y1
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                in_side = (cx > 760) if is_ltr else (cx < 320)
                if band_min <= cy <= band_max and 30 <= w <= 130 and 30 <= h <= 120 and in_side:
                    icon_btns.append((cx, cy, x1, y1, x2, y2))

        if len(icon_btns) >= 2:
            icon_btns.sort(key=lambda b: b[0])
            # في الواجهة العربية (RTL): × أقصى اليسار (cx≈74) و ✓ يمينه (cx≈153) -> icon_btns[-1]
            # في الواجهة الإنجليزية (LTR): ✓ يسار × -> icon_btns[0]
            check_btn = icon_btns[0] if is_ltr else icon_btns[-1]
            log.info(f"المحاكي الثاني: الضغط على علامة الصح المكتشفة ({check_btn[0]}, {check_btn[1]})...")
            dev2.click(check_btn[0], check_btn[1])
            return True
    except Exception:
        pass

    # 3. احتياطي بالإحداثيات الجديدة الدقيقة لعلامة الصح (155, 404) بدل القديمة (207, 408)
    log.info("المحاكي الثاني: النقر على إحداثيات علامة الصح (155, 404)...")
    dev2.click(155, 404)
    return True


def refresh_and_accept_friend_request(dev2, comp_id: str, leader_name: str = "", mult: float = 1.0) -> bool:
    """تحديث صفحة البروفايل على المحاكي الثاني حتى ظهور طلب الإضافة ثم قبوله والتحقق من اختفاء الكرت"""
    dump_dev2 = safe_dump_hierarchy(dev2)
    req_found = (
        has_pending_friend_request_card(dump_dev2)
        or any(k in dump_dev2 for k in ("قبول", "موافقة", "Accept", "Approve"))
    )

    if not req_found:
        for attempt in range(4):
            log.info(f"المحاكي الثاني: تحديث صفحة البروفايل لاستلام طلب الإضافة (محاولة {attempt + 1}/4)...")
            if _is_on_profile_xml(dump_dev2, comp_id):
                dev2.click(1019, 91)
                smart_sleep(1.0, mult)
            elif not _is_on_home_xml(dump_dev2):
                dismiss_post_otp_popups(dev2, mult=mult)
                dev2.press("back")
                smart_sleep(0.9, mult)

            dev2.click(61, 101)
            smart_sleep(1.8, mult)
            wait_for_network_loading(dev2, max_wait=10.0)

            dump_dev2 = safe_dump_hierarchy(dev2)
            if not _is_on_profile_xml(dump_dev2, comp_id):
                dev2.click(61, 101)
                smart_sleep(1.6, mult)
                wait_for_network_loading(dev2, max_wait=6.0)
                dump_dev2 = safe_dump_hierarchy(dev2)

            if (
                has_pending_friend_request_card(dump_dev2)
                or any(k in dump_dev2 for k in ("قبول", "موافقة", "Accept", "Approve"))
            ):
                req_found = True
                break
            smart_sleep(1.0, mult)

    if not req_found:
        if "تم قبول" in dump_dev2:
            log.info("المحاكي الثاني: الطلب مقبول مسبقاً ✓")
            return True
        save_failure_artifacts(dev2, "emu2_no_friend_request")
        raise FlowError("لم يصل طلب الإضافة إلى المحاكي الثاني بعد 4 محاولات تحديث")

    for click_attempt in range(3):
        click_accept_friend_request(dev2, dump_dev2, mult=mult)
        smart_sleep(1.6, mult)
        wait_for_network_loading(dev2, max_wait=8.0)
        dump_after = safe_dump_hierarchy(dev2)
        if not has_pending_friend_request_card(dump_after):
            log.info("المحاكي الثاني: تم قبول طلب الإضافة وتأكيد اختفاء الكرت ✓")
            return True
        log.warning(f"المحاكي الثاني: طلب الإضافة ما زال ظاهراً - إعادة النقر على علامة الصح ({click_attempt + 2}/3)...")
        dump_dev2 = dump_after

    save_failure_artifacts(dev2, "emu2_accept_stuck")
    raise FlowError("تعذر قبول طلب الإضافة على المحاكي الثاني (ظل الكرت ظاهراً بعد 3 محاولات)")


def ensure_leader_on_friends_page(dev1, mult: float = 1.0) -> bool:
    """ضمان وجود المحاكي الأول داخل صفحة الأصدقاء (Show All) وإعادته إليها تلقائياً لو خرج منها لأي سبب"""
    for attempt in range(4):
        try:
            if dev1.app_current().get("package") != PACKAGE_NAME:
                log.warning("المحاكي الأول خرج من تطبيق نسك - إعادة فتح التطبيق...")
                reopen_nusuk_app(dev1, "emu1", mult=mult)
        except Exception:
            pass

        if is_add_friend_dialog_open(dev1):
            dev1.press("back")
            smart_sleep(1.0, mult)

        dump1 = safe_dump_hierarchy(dev1)
        if is_on_friends_show_all_page(dump1):
            return True

        if attempt > 0:
            log.warning(f"🛡️ المحاكي الأول ليس في صفحة الأصدقاء (محاولة {attempt + 1}/4) - جاري فتح Show All...")
        else:
            log.info("فتح/استعادة صفحة الأصدقاء (Show All) في المحاكي الأول...")

        leader_id_val = (STATE.get("group") or {}).get("leader_id") or ""
        if _is_on_profile_xml(dump1, leader_id_val):
            if not click_text_in_xml(dev1, dump1, ("عرض الكل", "Show All", "Show all"), min_y=650, max_y=1650):
                # لو صفحة البروفايل مسحوبة لأسفل أو لأعلى نرجعها ثم نبحث عن "عرض الكل"
                dev1.swipe(0.5, 0.35, 0.5, 0.80, steps=15)
                smart_sleep(0.6, mult)
                dump_top = safe_dump_hierarchy(dev1)
                if not click_text_in_xml(dev1, dump_top, ("عرض الكل", "Show All", "Show all"), min_y=650, max_y=1650):
                    dev1.click(127, 1021)
            smart_sleep(1.3, mult)
            wait_for_network_loading(dev1, max_wait=6.0)
        elif "نوع الهوية" in dump1:
            dev1.click(58, 91)
            smart_sleep(1.3, mult)
            wait_for_network_loading(dev1, max_wait=6.0)
        elif _is_on_permits_xml(dump1):
            dev1.click(1019, 91)
            smart_sleep(1.3, mult)
            wait_for_network_loading(dev1, max_wait=6.0)
        elif _is_on_home_xml(dump1):
            dev1.click(61, 101)
            smart_sleep(1.5, mult)
            wait_for_network_loading(dev1, max_wait=6.0)
        else:
            dismiss_post_otp_popups(dev1, mult=mult)
            if attempt >= 2:
                reopen_nusuk_app(dev1, "emu1", mult=mult)
            else:
                dev1.press("back")
                smart_sleep(1.0, mult)
                dev1.click(61, 101)
                smart_sleep(1.4, mult)
                wait_for_network_loading(dev1, max_wait=6.0)

    return is_on_friends_show_all_page(safe_dump_hierarchy(dev1))


def _click_add_friend_on_show_all(dev1, comp_num: int, mult: float = 1.0):
    add_labels = ("أضف صديق", "إضافة صديق", "اضف صديق", "Add friend", "Add Friend")
    dump1 = safe_dump_hierarchy(dev1)
    if click_text_in_xml(dev1, dump1, add_labels, min_y=350, max_y=1860):
        return
    # لو القائمة طويلة ونزل الزر لأسفل الشاشة نسحب مرتين كحد أقصى حتى يظهر
    for _ in range(2):
        dev1.swipe(0.5, 0.78, 0.5, 0.30, steps=14)
        smart_sleep(0.5, mult)
        dump2 = safe_dump_hierarchy(dev1)
        if click_text_in_xml(dev1, dump2, add_labels, min_y=300, max_y=1860):
            return
    if comp_num == 1:
        dev1.click(540, 1118)
    elif comp_num == 2:
        dev1.click(804, 943)
    else:
        dev1.click(804, 1106)


def open_add_friend_and_send_request(dev1, comp_id: str, comp_num: int, mult: float = 1.0):
    """فتح نافذة إضافة صديق في المحاكي الأول وكتابة الـ ID وإرسال الطلب بموثوقية عالية مع التحقق من الإرسال"""
    if not comp_id:
        raise FlowError("لا يمكن إرسال طلب إضافة بدون رقم هوية نسك للمرافق")

    id_box = None
    for attempt in range(3):
        on_friends = ensure_leader_on_friends_page(dev1, mult=mult)
        if not on_friends:
            log.warning(f"تعذر تثبيت المحاكي الأول على صفحة الأصدقاء (محاولة {attempt + 1}/3)...")
            continue
        _click_add_friend_on_show_all(dev1, comp_num, mult=mult)
        id_box = wait_add_friend_dialog(dev1, timeout=(3.0 if attempt == 0 else 4.0) * mult)
        if id_box is not None:
            break
        log.warning(f"إعادة محاولة فتح شاشة إضافة صديق في المحاكي الأول ({attempt + 1}/3)...")

    if id_box is None:
        save_failure_artifacts(dev1, "emu1_add_friend_fail")
        raise FlowError("لم تظهر شاشة إضافة صديق في المحاكي الأول")

    smart_sleep(0.25, mult)
    safe_set_text(dev1, id_box, comp_id, mult=mult, is_password=False)
    # تأكيد ظهور الرقم فعلياً داخل الخانة (أحياناً Compose يحتاج input text مباشر)
    if comp_id not in safe_dump_hierarchy(dev1, retries=1):
        try:
            b = id_box.info.get("bounds", {})
            cx = (b.get("left", 100) + b.get("right", 980)) // 2
            cy = (b.get("top", 368) + b.get("bottom", 455)) // 2
            dev1.click(cx, cy)
        except Exception:
            dev1.click(540, 411)
        smart_sleep(0.2, mult)
        dev1.shell(f"input text {re.sub(r'[^0-9]', '', comp_id)}")

    smart_sleep(0.25, mult)
    dev1.shell("input keyevent 111")
    smart_sleep(0.35, mult)

    for send_attempt in range(2):
        dump_af = safe_dump_hierarchy(dev1)
        if not click_text_in_xml(dev1, dump_af, ("أضف صديق", "اضف صديق", "إضافة صديق", "Add friend", "Add Friend"), min_y=1620, max_y=1830):
            dev1.click(540, 1756)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev1, max_wait=10.0)

        if not is_add_friend_dialog_open(dev1):
            return

        dump_still = safe_dump_hierarchy(dev1)
        norm_still = normalize_text(dump_still)
        if any(k in norm_still for k in ("مضاف بالفعل", "صديق بالفعل", "مرسل بالفعل", "already", "pending")):
            log.info("الطلب مرسل أو الصديق مضاف مسبقاً -> إغلاق النافذة والمتابعة ✓")
            dev1.press("back")
            smart_sleep(0.8, mult)
            return

        err = extract_screen_error(dump_still)
        if err:
            save_failure_artifacts(dev1, "emu1_add_friend_error")
            dev1.press("back")
            smart_sleep(0.6, mult)
            raise FlowError(f"فشل إرسال طلب الصداقة من المحاكي الأول: {err}")

        if send_attempt == 0:
            log.warning("نافذة إدخال الصديق ما زالت مفتوحة - إعادة الضغط على زر الإرسال (540, 1756)...")
            dev1.shell("input keyevent 111")
            smart_sleep(0.3, mult)

    save_failure_artifacts(dev1, "emu1_add_friend_stuck")
    dev1.press("back")
    smart_sleep(0.8, mult)
    raise FlowError("تعذر إرسال طلب الصداقة في المحاكي الأول (ظلت نافذة الإضافة مفتوحة)")


def fast_extract_id_and_name(dev, max_wait: float = 4.0) -> Tuple[Optional[str], str]:
    start_t = time.time()
    nusuk_id = None
    profile_name = "معتمر"
    ignore_headers = ("cards", "nusuk", "بطاقاتي", "البطاقات", "نسك", "ملفي", "profile", "طلب اضافه", "طلب إضافة")

    while time.time() - start_t < max_wait:
        xml_str = safe_dump_hierarchy(dev, retries=1)
        norm_digits = normalize_arabic_digits(xml_str)

        m = re.search(r"(?:Nusuk ID|رقم\s*هوية\s*نسك)\s*[:：]?\s*(\d{10,16})", norm_digits, re.IGNORECASE)
        if m:
            nusuk_id = m.group(1)
        else:
            m2 = re.search(r"\b(20\d{2}\d{8,12})\b", norm_digits)
            if m2:
                nusuk_id = m2.group(1)

        if nusuk_id:
            try:
                root = ET.fromstring(xml_str.encode("utf-8"))
                card_name = None
                for node in root.iter():
                    txt = (node.attrib.get("text") or "").strip()
                    bounds = node.attrib.get("bounds") or ""
                    if not txt or len(txt) <= 2 or not bounds:
                        continue
                    norm_t = normalize_text(txt)
                    if any(ig in norm_t for ig in ignore_headers) or re.fullmatch(r"[\d\s:/.-]+", normalize_arabic_digits(txt)):
                        continue
                    bm = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
                    if not bm:
                        continue
                    top_y = int(bm.group(2))
                    if 140 <= top_y <= 270:
                        profile_name = txt
                        break
                    if 900 <= top_y <= 1130 and card_name is None and "هويه نسك" not in norm_t:
                        card_name = txt
                if profile_name == "معتمر" and card_name:
                    profile_name = card_name
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

    for _ in range(2):
        dump = safe_dump_hierarchy(dev)
        dump_low = normalize_text(dump)
        if any(normalize_text(k) in dump_low for k in SUCCESS_KEYS):
            if not click_text_in_xml(dev, dump, ("تابع واستكشف", "Continue Exploring", "استكشف"), min_y=1650, max_y=1880):
                dev.click(540, 1796)
            smart_sleep(1.3, mult)
            wait_for_network_loading(dev, max_wait=6.0)
            dev.click(1019, 91)
            smart_sleep(1.5, mult)
        elif "نوع الهويه" in dump_low:
            dev.click(58, 91)
            smart_sleep(1.5, mult)
        elif _is_on_permits_xml(dump):
            dev.click(1019, 91)
            smart_sleep(1.5, mult)
        elif is_on_friends_show_all_page(dump):
            dev.click(52, 103)
            smart_sleep(1.2, mult)
        else:
            dismiss_post_otp_popups(dev, mult=mult)
            dev.click(61, 101)
            smart_sleep(1.5, mult)

        wait_for_network_loading(dev, max_wait=6.0)
        nid, pname = fast_extract_id_and_name(dev, max_wait=3.5 * mult)
        if nid:
            return nid, pname

    return None, "معتمر"


def open_active_permits_screen(dev, mult: float = 1.0, expect_complete_sheet: bool = False) -> str:
    """فتح شاشة التصاريح السارية من البروفايل مع التمرير التلقائي لو كانت أسفل الشاشة والتحقق من فتحها فعلياً"""
    # 1. ضمان أننا على صفحة البروفايل
    for _ in range(3):
        dump_p = safe_dump_hierarchy(dev)
        if _is_on_profile_xml(dump_p):
            break
        dismiss_post_otp_popups(dev, mult=mult)
        dev.click(61, 101)
        smart_sleep(1.6, mult)
        wait_for_network_loading(dev, max_wait=8.0)

    # 2. البحث عن كرت "التصاريح السارية" مع تمرير خفيف لو لم يكن ظاهراً بعد
    for attempt in range(3):
        dump_cards = safe_dump_hierarchy(dev)
        clicked = click_text_in_xml(dev, dump_cards, ("التصاريح السارية", "Active Permits"), min_y=900, max_y=1905)
        if not clicked:
            if attempt < 2:
                dev.swipe(0.5, 0.78, 0.5, 0.38, steps=15)
                smart_sleep(0.6, mult)
                dump_cards = safe_dump_hierarchy(dev)
                clicked = click_text_in_xml(dev, dump_cards, ("التصاريح السارية", "Active Permits"), min_y=700, max_y=1905)
            if not clicked:
                dev.click(807, 1786)

        smart_sleep(1.6, mult)
        wait_for_network_loading(dev, max_wait=10.0)
        after_xml = safe_dump_hierarchy(dev)
        norm_after = normalize_text(after_xml)

        if expect_complete_sheet:
            if any(k in norm_after for k in ("اكمل الملف الشخصي", "complete profile", "نوع الهويه", "كافه الزوار", "زائر دولي")):
                return after_xml
            if not _is_on_profile_xml(after_xml):
                return after_xml
        else:
            if _is_on_permits_xml(after_xml) or not _is_on_profile_xml(after_xml):
                return after_xml
        log.warning(f"لم تُفتح شاشة التصاريح السارية بعد (محاولة {attempt + 1}/3) - إعادة المحاولة...")

    after_xml = safe_dump_hierarchy(dev)
    if not expect_complete_sheet and _is_on_profile_xml(after_xml):
        save_failure_artifacts(dev, "permits_screen_not_opened")
        raise FlowError("تعذر فتح شاشة التصاريح السارية لفحص أحقية الروضة")
    return after_xml


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
    ok = False
    try:
        if is_add_friend_dialog_open(dev1):
            dev1.press("back")
            time.sleep(0.8)
        for _ in range(2):
            dump1 = safe_dump_hierarchy(dev1)
            if is_on_friends_show_all_page(dump1):
                dev1.click(52, 103)
                time.sleep(1.2)
                if is_on_friends_show_all_page(safe_dump_hierarchy(dev1, retries=1)):
                    dev1.press("back")
                    time.sleep(1.0)
            else:
                break
        ok = perform_safe_logout(dev1, slow=True)
        if not ok and not on_login_screen(dev1):
            ok = force_clean_login_state(dev1, "emu1")
    except Exception as e:
        log.error(f"فشل خروج الحساب الرئيسي: {e}")
        ok = force_clean_login_state(dev1, "emu1")
    reset_group()
    if ok:
        bump_counter("emu1")
    else:
        set_health("emu1", False, "leader_logout_failed")
    return ok


# ==========================================
# فحص تصاريح الروضة ونظام استرجاع الحساب
# ==========================================
def _is_cancelled_permit_status(status: str) -> bool:
    s = normalize_text(status or "")
    return any(k in s for k in ("ملغي", "ملغاه", "الغاء", "cancel"))


def _is_used_or_expired_permit_status(status: str) -> bool:
    if _is_cancelled_permit_status(status):
        return False
    s = normalize_text(status or "")
    # تجاهل عبارة "من قبل المستخدم" حتى لو ظهرت بصيغة أخرى
    s_clean = s.replace("المستخدم", "").strip()
    return any(k in s_clean for k in ("مستخدم", "منتهي", "منته", "used", "expired", "completed"))


def _is_active_permit_status(status: str) -> bool:
    if _is_cancelled_permit_status(status):
        return False
    s = normalize_text(status or "")
    return any(k in s for k in (
        "مؤكد", "موكد", "منتظر التاكيد", "بانتظار التاكيد", "ساري", "قادم", "فعال",
        "confirmed", "active", "pending", "upcoming", "valid",
    ))


def _parse_permit_date(text: str) -> Optional[datetime]:
    """تحليل تاريخ التصريح بعدة صيغ عربية وإنجليزية ورقمية (مع دعم الأرقام العربية الهندية)"""
    t = normalize_arabic_digits((text or "").strip())
    if not t:
        return None
    en_months = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    ar_months_norm = {normalize_text(k): v for k, v in AR_MONTHS.items()}

    m_ar = re.search(r"(\d{1,2})\s+([\u0621-\u064A]+)\s+(\d{4})", t)
    if m_ar:
        day, mon_name, yr = int(m_ar.group(1)), normalize_text(m_ar.group(2)), int(m_ar.group(3))
        mon = ar_months_norm.get(mon_name)
        if mon:
            try:
                return datetime(yr, mon, day)
            except ValueError:
                pass

    m_en = re.search(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", t)
    if m_en:
        day, mon_name, yr = int(m_en.group(1)), m_en.group(2).lower(), int(m_en.group(3))
        mon = en_months.get(mon_name)
        if mon:
            try:
                return datetime(yr, mon, day)
            except ValueError:
                pass

    m_en2 = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", t)
    if m_en2:
        mon_name, day, yr = m_en2.group(1).lower(), int(m_en2.group(2)), int(m_en2.group(3))
        mon = en_months.get(mon_name)
        if mon:
            try:
                return datetime(yr, mon, day)
            except ValueError:
                pass

    m_iso = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", t)
    if m_iso:
        try:
            return datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except ValueError:
            pass

    m_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", t)
    if m_dmy:
        try:
            return datetime(int(m_dmy.group(3)), int(m_dmy.group(2)), int(m_dmy.group(1)))
        except ValueError:
            pass
    return None


def evaluate_rawdah_permits_from_xml(xml_str: str) -> Tuple[bool, str, dict]:
    """
    فحص تصاريح الروضة الشريفة من شاشة المواعيد (عربي وإنجليزي):
    - التصريح الملغي (ملغى من قبل المستخدم / Cancelled) لا يمنع الحجز ويُستثنى تماماً
    - لو حاجز لنفسه حالياً (مؤكد / منتظر التأكيد / ساري) -> مينفعش
    - لو مستخدم أو منتهي:
      - لو عدى 365 يوم على أحدث تصريح مستخدم/منتهي -> ينفع
      - لو لم يمر 365 يوم (أو تعذر قراءة تاريخه) -> مينفعش
    - لو لا توجد أي تصاريح روضة سارية أو مستخدمة -> ينفع
    """
    if xml_str and _is_on_profile_xml(xml_str) and not _is_on_permits_xml(xml_str):
        raise FlowError("تعذر فحص التصاريح: الشاشة ما زالت على البروفايل ولم تُفتح شاشة المواعيد/التصاريح")

    nodes = []
    # دعم دمج أكثر من لقطة XML (قبل/بعد التمرير) إن وُجد فاصل
    for chunk in (xml_str or "").split("\n<!--NEXT_PAGE-->\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            root = ET.fromstring(chunk.encode("utf-8"))
            nodes.extend(n.attrib.get("text", "").strip() for n in root.iter() if n.attrib.get("text"))
        except Exception:
            pass

    status_markers = (
        "ملغي", "ملغاه", "الغاء", "cancel",
        "مستخدم", "منتهي", "ساري", "مؤكد", "موكد", "منتظر التاكيد", "بانتظار التاكيد",
        "used", "expired", "confirmed", "active", "pending", "upcoming", "completed",
    )

    permits = []
    seen_ids = set()
    curr = None
    for t in nodes:
        t_clean = normalize_text(t)
        if "رقم الحجز" in t_clean or "reservation" in t_clean or "booking" in t_clean:
            if curr and curr["id"] not in seen_ids:
                seen_ids.add(curr["id"])
                permits.append(curr)
            curr = {"id": t, "type": "", "status": "", "date_str": "", "time_str": "", "date": None}
        elif curr:
            if "تصريح الروضه" in t_clean or "الروضه" in t_clean or "rawdah" in t_clean or "rawda" in t_clean:
                curr["type"] = t
            elif any(s in t_clean for s in status_markers) and not curr["status"]:
                curr["status"] = t
            elif re.match(r"^\d{1,2}:\d{2}(\s*[APMapm]{2})?$", normalize_arabic_digits(t)):
                curr["time_str"] = normalize_arabic_digits(t)
            elif curr["date"] is None:
                parsed_dt = _parse_permit_date(t)
                if parsed_dt is not None:
                    curr["date_str"] = t
                    curr["date"] = parsed_dt
    if curr and curr["id"] not in seen_ids:
        seen_ids.add(curr["id"])
        permits.append(curr)

    rawdah_permits = [
        p for p in permits
        if any(k in normalize_text(p.get("type", "")) for k in ("الروضه", "rawdah", "rawda"))
    ]

    # 1. هل المعتمر حاجز لنفسه حالياً (مؤكد أو بانتظار التأكيد أو ساري — مع استثناء الملغي تماماً)؟
    active_rawdah = [p for p in rawdah_permits if _is_active_permit_status(p.get("status", ""))]
    if active_rawdah:
        p = active_rawdah[0]
        date_disp = p.get("date_str") or "محدد"
        time_disp = p.get("time_str") or ""
        stat_disp = p.get("status") or "مؤكد"
        reason = f"مينفعش - المعتمر حاجز لنفسه تصريح روضة ({stat_disp}) بتاريخ {date_disp} {time_disp}".strip()
        return False, reason, {"status": stat_disp, "date": date_disp, "time": time_disp, "type": p.get("type"), "cancelled": False}

    # 2. فحص التصاريح السابقة المستخدمة / المنتهية فعلياً (مع استثناء "ملغى من قبل المستخدم" تماماً!)
    used_rawdah_all = [p for p in rawdah_permits if _is_used_or_expired_permit_status(p.get("status", ""))]
    used_rawdah_dated = [p for p in used_rawdah_all if p.get("date")]
    now = datetime.now()
    if used_rawdah_dated:
        latest = max(used_rawdah_dated, key=lambda x: x["date"])
        days_passed = (now - latest["date"]).days
        date_disp = latest.get("date_str") or str(latest["date"].date())
        if days_passed >= 365:
            reason = f"ينفع - عدى أكثر من سنة ({days_passed} يوم) على آخر تصريح روضة بتاريخ {date_disp}"
            return True, reason, {"status": latest.get("status"), "date": date_disp, "days_passed": days_passed, "type": latest.get("type"), "cancelled": False}
        else:
            reason = f"مينفعش - دخل الروضة بتاريخ {date_disp} (مر فقط {days_passed} يوم ولم يكمل سنة)"
            return False, reason, {"status": latest.get("status"), "date": date_disp, "days_passed": days_passed, "type": latest.get("type"), "cancelled": False}
    if used_rawdah_all:
        p = used_rawdah_all[0]
        stat_disp = p.get("status") or "مستخدم"
        reason = f"مينفعش - يوجد تصريح روضة ({stat_disp}) وتعذر التحقق من تاريخه للتأكد من مرور سنة"
        return False, reason, {"status": stat_disp, "date": None, "type": p.get("type"), "cancelled": False}

    # 3. هل يوجد فقط تصاريح ملغاة؟
    cancelled_rawdah = [p for p in rawdah_permits if _is_cancelled_permit_status(p.get("status", ""))]
    if cancelled_rawdah:
        p = cancelled_rawdah[0]
        date_disp = p.get("date_str") or ""
        stat_disp = p.get("status") or "ملغى"
        reason = f"ينفع - الحجز ملغي ({stat_disp}{(' بتاريخ ' + date_disp) if date_disp else ''}) ولا توجد تصاريح سارية أو مستخدمة"
        return True, reason, {"status": stat_disp, "date": date_disp or None, "type": p.get("type"), "cancelled": True}

    # 4. لا توجد تصاريح روضة مستخدمة أو مؤكدة
    reason = "ينفع - لا توجد أي تصاريح روضة سابقة للمعتمر"
    return True, reason, {"status": "none", "date": None, "cancelled": False}


def _record_companion_in_state(name: str, nid: str) -> int:
    """إضافة المرافق لحالة المجموعة مع منع التكرار لو تكرر نفس الرقم"""
    with _state_lock:
        comps = STATE["group"]["companions"]
        if not any(c.get("id") == nid for c in comps):
            comps.append({"name": name, "id": nid})
        group_count = len(comps)
    save_state()
    return group_count


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
    dump = safe_dump_hierarchy(dev)
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
        dump = safe_dump_hierarchy(dev)
        dump_clean = strip_arabic_diacritics(dump)

    # فحص الشاشة الحالية بعد الضغط على الزر الأسود (أو عند البدء اليدوي)
    if "تسجيل الحساب من جديد" in dump_clean or "كافة الزوار" in dump_clean or "زائر دولي" in dump_clean:
        log.info(f"[{label}] تم فتح شاشة 'تسجيل الحساب من جديد' مباشرة ✓")
    elif "استعد حسابك" in dump_clean or "استعادة حسابك" in dump_clean:
        if not click_text_in_xml(dev, dump, ("استعد حسابك", "استعادة حسابك"), min_y=1400, max_y=1850):
            dev.click(943, 1657)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=8.0)
    elif "لديك مشكلة" in dump_clean:
        if not click_text_in_xml(dev, dump, ("لديك مشكلة",), min_y=600, max_y=1200):
            dev.click(540, 846)
        smart_sleep(1.2, mult)
        dump_tr = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_tr, ("استعد حسابك", "استعادة حسابك"), min_y=1400, max_y=1850):
            dev.click(943, 1657)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=8.0)
    else:
        if not (any(m in dump_clean for m in WELCOME_MARKERS) or "تسجيل الدخول أو إنشاء حساب" in dump_clean or "الدخول بواسطة البريد" in dump_clean):
            force_clean_login_state(dev, emu_key)
            dump = safe_dump_hierarchy(dev)
            dump_clean = strip_arabic_diacritics(dump)

        if any(m in dump_clean for m in WELCOME_MARKERS) or "تسجيل الدخول أو إنشاء حساب" in dump_clean:
            if not click_text_in_xml(dev, dump, ("تسجيل الدخول أو إنشاء حساب", "Login or Sign up", "Log in or Sign up"), min_y=1650, max_y=1860):
                dev.click(540, 1781)
            smart_sleep(1.2, mult)

        dump_sheet = safe_dump_hierarchy(dev)
        dump_sheet_clean = strip_arabic_diacritics(dump_sheet)
        if "الدخول بواسطة البريد" in dump_sheet_clean or "البريد الإلكتروني" in dump_sheet_clean:
            if not click_text_in_xml(dev, dump_sheet, ("الدخول بواسطة البريد",), min_y=1200, max_y=1700):
                dev.click(869, 1528)
            smart_sleep(1.2, mult)

        dump_el = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_el, ("لديك مشكلة",), min_y=600, max_y=1200):
            dev.click(540, 846)
        smart_sleep(1.2, mult)
        dump_tr = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_tr, ("استعد حسابك", "استعادة حسابك"), min_y=1400, max_y=1850):
            dev.click(943, 1657)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=8.0)

    # 2. شاشة "تسجيل الحساب من جديد" -> الضغط على "كافة الزوار" (809, 1702)
    picker_opened = False
    for rec_try in range(2):
        dump_rec = safe_dump_hierarchy(dev)
        dump_rec_clean = strip_arabic_diacritics(dump_rec)
        if "كافة الزوار" in dump_rec_clean or "زائر دولي" in dump_rec_clean:
            if not click_text_in_xml(dev, dump_rec, ("كافة الزوار", "زائر دولي", "International"), min_y=1550, max_y=1850):
                dev.click(809, 1702)
        else:
            dev.click(809, 1702)
        smart_sleep(1.2, mult)
        wait_for_network_loading(dev, max_wait=8.0)
        if wait_country_picker_open(dev, timeout=4.5 * mult):
            picker_opened = True
            break
        if rec_try == 0:
            log.warning(f"[{label}] لم تفتح قائمة الدولة بعد الضغط على كافة الزوار - إعادة المحاولة...")

    if not picker_opened:
        raise FlowError("تعذر فتح قائمة اختيار الدولة في مسار استرجاع الحساب")

    # 3. اختيار الجنسية (القائمة الجديدة: صف 1 عند 246، مصر عند 323، تأكيد الاختيار عند 559, 1822)
    select_and_confirm_nationality(dev, raw_nat, default_nat_y, mult=mult, confirm_fallback_y=1822)

    # 4. إدخال الجواز ورقم التأشيرة (رقم التأشيرة محدد افتراضياً على اليمين؛ نتحقق دون النقر على رقم الحدود)
    smart_sleep(0.8, mult)
    ensure_visa_radio_selected(dev, mult=mult)

    rec_inputs = wait_edits(dev, 2, timeout=4.5 * mult)
    if rec_inputs is not None and len(rec_inputs) >= 2:
        safe_set_text(dev, rec_inputs[0], passport_val, mult=mult)
        smart_sleep(0.2, mult)
        safe_set_text(dev, rec_inputs[1], visa_val, mult=mult)
        smart_sleep(0.2, mult)
    else:
        dev.click(540, 576)  # جواز السفر
        smart_sleep(0.3, mult)
        dev.send_keys(passport_val, clear=True)
        smart_sleep(0.3, mult)

        dev.click(540, 859)  # رقم التأشيرة
        smart_sleep(0.3, mult)
        dev.send_keys(visa_val, clear=True)
        smart_sleep(0.3, mult)

    dev.shell("input keyevent 111")
    smart_sleep(0.4, mult)

    # الضغط على زر "التحقق من حسابك" (560, 989) والتأكد من الانتقال الفعلي لشاشة الإيميل وكلمة المرور
    reached_cred_screen = False
    for verify_attempt in range(2):
        dump_vrf = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_vrf, ("التحقق من حسابك", "تحقق من حسابك", "Verify"), min_y=880, max_y=1150):
            dev.click(560, 989)
        smart_sleep(1.5, mult)
        wait_for_network_loading(dev, max_wait=12.0)

        for _ in range(10):
            dump_chk = safe_dump_hierarchy(dev, retries=1)
            norm_chk = normalize_text(dump_chk)
            if (
                any(k in norm_chk for k in ("تاكيد البريد", "البريد الالكتروني", "كلمه المرور", "confirm email", "password"))
                and "رقم جواز" not in norm_chk
                and "رقم التاشيره" not in norm_chk
            ):
                reached_cred_screen = True
                break
            err = extract_screen_error(dump_chk)
            if err:
                raise FlowError(f"فشل التحقق من الجواز والتأشيرة أثناء الاسترجاع: {err}")
            time.sleep(0.5)
        if reached_cred_screen:
            break
        if verify_attempt == 0:
            log.warning(f"[{label}] لم تنتقل شاشة التحقق إلى الإيميل/كلمة المرور بعد - إعادة الضغط على زر التحقق...")

    if not reached_cred_screen:
        raise FlowError("تعذر الانتقال لشاشة البريد الإلكتروني بعد التحقق من الجواز والتأشيرة")

    # 5. إدخال الإيميل وكلمة المرور
    cred_inputs = wait_edits(dev, 2, timeout=4.5 * mult)
    if cred_inputs is not None and len(cred_inputs) >= 2:
        safe_set_text(dev, cred_inputs[0], email_val, mult=mult)
        smart_sleep(0.2, mult)
        safe_set_text(dev, cred_inputs[1], password_val, mult=mult, is_password=True)
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

    # الضغط على زر "تأكيد البريد الإلكتروني" (560, 1041) والتأكد من الوصول لشاشة الـ OTP قبل انتظار البريد
    otp_sent_at = time.time()
    reached_otp = False
    for em_attempt in range(2):
        dump_em = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_em, ("تأكيد البريد الإلكتروني", "تأكيد البريد", "Confirm"), min_y=700, max_y=1250):
            dev.click(560, 1041)
        smart_sleep(1.8, mult)
        wait_for_network_loading(dev, max_wait=12.0)

        for _ in range(8):
            dump_after_em = safe_dump_hierarchy(dev, retries=1)
            if is_on_otp_screen(dev, dump_after_em):
                reached_otp = True
                break
            err = extract_screen_error(dump_after_em)
            if err:
                raise FlowError(f"فشل تأكيد البريد الإلكتروني للاسترجاع: {err}")
            time.sleep(0.5)
        if reached_otp:
            break
        if em_attempt == 0:
            log.warning(f"[{label}] لم تظهر شاشة الـ OTP بعد - إعادة الضغط على تأكيد البريد الإلكتروني...")

    if not reached_otp:
        err = extract_screen_error(safe_dump_hierarchy(dev, retries=1))
        raise FlowError(f"لم تظهر شاشة رمز التحقق (OTP) بعد تأكيد البريد{(': ' + err) if err else ''}")

    # 6. استلام كود OTP
    log.info(f"[{label}] انتظار كود الـ OTP لاسترجاع الحساب من {req.client_email}...")
    otp = fetch_nusuk_otp(req.client_email.strip(), req.client_pass, timeout=55, sent_after=otp_sent_at)
    if not otp:
        raise FlowError("لم يتم استلام كود OTP لاسترجاع الحساب")

    enter_otp_code(dev, otp, fallback_x=160, fallback_y=458, mult=mult)

    # انتظار ظهور نافذة "تم استعادة حسابك بنجاح" والضغط على الزر الأسود (تابع واستكشف)
    log.info(f"[{label}] انتظار نافذة تم استعادة حسابك بنجاح والضغط على الزر الأسود...")
    clicked_explore = False

    for _ in range(25):
        dump_succ = safe_dump_hierarchy(dev, retries=1)
        norm_succ = normalize_text(dump_succ)
        if any(w in norm_succ for w in ("استعاده حسابك بنجاح", "تم استعاده حسابك", "تابع واستكشف", "continue exploring", "account recovered")):
            if not click_text_in_xml(dev, dump_succ, ("تابع واستكشف", "Continue Exploring", "استكشف"), min_y=1650, max_y=1900):
                dev.click(540, 1796)
            log.info(f"[{label}] تم الضغط على الزر الأسود (تابع واستكشف) بنجاح!")
            clicked_explore = True
            break
        if _is_on_home_xml(dump_succ) or _is_on_profile_xml(dump_succ):
            clicked_explore = True
            break
        if "تاكيد البريد الالكتروني" in norm_succ and is_on_otp_screen(dev, dump_succ):
            click_text_in_xml(dev, dump_succ, ("تأكيد البريد الإلكتروني",), min_y=620, max_y=950)
        time.sleep(0.6)

    if not clicked_explore:
        dev.click(540, 1796)

    smart_sleep(1.5, mult)
    # لو نافذة تابع واستكشف ما زالت ظاهرة نضغطها مرة إضافية
    dump_rechk = safe_dump_hierarchy(dev, retries=1)
    if "تابع واستكشف" in normalize_text(dump_rechk):
        if not click_text_in_xml(dev, dump_rechk, ("تابع واستكشف", "Continue Exploring"), min_y=1650, max_y=1900):
            dev.click(540, 1796)
        smart_sleep(1.2, mult)
    dismiss_post_otp_popups(dev, mult=mult)

    # إذا لم يصل للشاشة الرئيسية نعيد فتح التطبيق لضمان الاستقرار والدخول النظيف
    dump_after_exp = safe_dump_hierarchy(dev)
    if not (_is_on_home_xml(dump_after_exp) or _is_on_profile_xml(dump_after_exp)):
        log.info(f"🔄 [{label}] إعادة تشغيل تطبيق نسك بعد الاسترجاع والزر الأسود للوصول النظيف للشاشة الرئيسية...")
        reopen_nusuk_app(dev, emu_key, mult=mult)

    # 7. الدخول للبروفايل واستخراج الاسم والـ Nusuk ID بموثوقية
    if not _is_on_profile_xml(safe_dump_hierarchy(dev, retries=1)):
        dev.click(61, 101)
        smart_sleep(1.8, mult)
        wait_for_network_loading(dev, max_wait=8.0)

    nid, pname = reach_profile_and_extract_id(dev, mult=mult)
    if not nid:
        raise FlowError("تعذر استخراج رقم هوية نسك بعد استرجاع الحساب")

    log.info(f"[{label}] تم استرجاع البروفايل: {pname} | ID: {nid}")

    # 8. فتح شاشة "التصاريح السارية" مع التحقق الفعلي من فتحها (والتمرير التلقائي لو كانت أسفل الشاشة)
    permits_xml = open_active_permits_screen(dev, mult=mult, expect_complete_sheet=False)

    # لو يوجد تصاريح في القائمة، نمرر لأسفل مرة واحدة للتقاط أي تصاريح روضة إضافية خارج الإطار
    if "رقم الحجز" in permits_xml or "reservation" in normalize_text(permits_xml):
        dev.swipe(0.5, 0.80, 0.5, 0.28, steps=16)
        smart_sleep(0.7, mult)
        permits_xml_scrolled = safe_dump_hierarchy(dev, retries=1)
        if permits_xml_scrolled and not _is_on_profile_xml(permits_xml_scrolled):
            permits_xml = permits_xml + "\n<!--NEXT_PAGE-->\n" + permits_xml_scrolled

    # 9. فحص التصاريح (المواعيد) وتقييم الأحقية
    eligible, reason, details = evaluate_rawdah_permits_from_xml(permits_xml)
    log.info(f"📊 [{label}] نتيجة فحص الأحقية لـ {pname}: {reason}")

    # الرجوع لصفحة البروفايل
    dev.press("back")
    smart_sleep(1.2, mult)
    if not _is_on_profile_xml(safe_dump_hierarchy(dev, retries=1), nid):
        dev.click(1019, 91)
        smart_sleep(1.0, mult)

    # 10. تنفيذ القرار
    if not eligible:
        log.warning(f"❌ [{label}] الحساب غير مؤهل ({reason}) -> تسجيل خروج آمن...")
        if not perform_safe_logout(dev, slow=True, mult=mult):
            force_clean_login_state(dev, emu_key)
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
    try:
        if dev1.app_current().get("package") != PACKAGE_NAME:
            log.warning("المحاكي الأول (الرئيسي) خرج من تطبيق نسك - إعادة فتحه قبل إرسال طلب الإضافة...")
            reopen_nusuk_app(dev1, "emu1", mult=mult)
    except Exception:
        pass
    open_add_friend_and_send_request(dev1, nid, comp_num, mult=mult)

    # قبول الطلب على emu2 مع التحقق الصارم من وصول الطلب واختفاء كرته
    leader_name = (STATE.get("group") or {}).get("leader_name") or ""
    refresh_and_accept_friend_request(dev2, nid, leader_name, mult=mult)

    group_count = _record_companion_in_state(pname, nid)

    if not perform_safe_logout(dev2, slow=True, mult=mult):
        force_clean_login_state(dev2, "emu2")
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


def _validate_and_resolve_request(req: RegisterRequest) -> Tuple[Optional[dict], Optional[dict]]:
    """تحقق موحد من صحة مدخلات الطلب وتحديد الدور والمحاكي المستهدف (يُستخدم في /api/register و /api/recover)"""
    p = req.pilgrim or {}
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
    if force_role not in (None, "leader", "companion"):
        problems.append("قيمة force_role غير صحيحة (يجب أن تكون leader أو companion)")
    if problems:
        log.warning("طلب مرفوض: " + " | ".join(problems))
        return None, {"success": False, "status": "invalid_input", "error": " | ".join(problems)}

    with _state_lock:
        leader_active = STATE["group"]["leader_active"]
        comp_count = len(STATE["group"]["companions"])

    role = force_role or ("companion" if leader_active else "leader")
    if role == "companion" and not leader_active:
        return None, {"success": False, "status": "invalid_state", "error": "لا يوجد حساب رئيسي نشط - سجّل الرئيسي أولاً"}
    if role == "leader" and leader_active:
        return None, {"success": False, "status": "invalid_state", "error": "يوجد حساب رئيسي نشط - أنهِ المجموعة أولاً"}

    emu_key = "emu1" if role == "leader" else "emu2"
    comp_num = comp_count + 1
    mult = max(0.8, min(3.0, float(req.speed_multiplier or STATE.get("speed_multiplier", 1.0))))
    return {
        "p": p,
        "email_val": email_val,
        "password_val": password_val,
        "passport_val": passport_val,
        "visa_val": visa_val,
        "role": role,
        "emu_key": emu_key,
        "comp_num": comp_num,
        "mult": mult,
    }, None


@app.post("/api/recover")
def recover_account_api(req: RegisterRequest):
    """استرجاع حساب مسجل مسبقاً وفحص صلاحية تصاريح الروضة يدوياً أو برمجياً"""
    with exclusive(LOCK_WAIT) as got:
        if not got:
            return BUSY_RESPONSE
        ctx, err_resp = _validate_and_resolve_request(req)
        if err_resp is not None:
            return err_resp
        dev = None
        emu_key = ctx["emu_key"]
        role = ctx["role"]
        try:
            dev = get_device(EMUS[emu_key]["serial"])
            return run_account_recovery_flow(dev, req, role, ctx["comp_num"], emu_key, mult=ctx["mult"])
        except Exception as e:
            log.exception("خطأ في /api/recover")
            shot = save_failure_artifacts(dev, f"{emu_key}_{role}_recover")
            if dev is not None:
                try:
                    force_clean_login_state(dev, emu_key)
                except Exception:
                    pass
            return {"success": False, "status": "error", "error": str(e), "screenshot": shot}


def _run_register(req: RegisterRequest) -> dict:
    dummy_name = "Ab"
    ctx, err_resp = _validate_and_resolve_request(req)
    if err_resp is not None:
        return err_resp

    p = ctx["p"]
    email_val = ctx["email_val"]
    password_val = ctx["password_val"]
    passport_val = ctx["passport_val"]
    visa_val = ctx["visa_val"]
    role = ctx["role"]
    emu_key = ctx["emu_key"]
    comp_num = ctx["comp_num"]
    mult = ctx["mult"]
    emu = EMUS[emu_key]
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

        # 2. ملء البيانات الأساسية (مرتبة من الأعلى للأسفل)
        safe_set_text(dev, inputs[0], dummy_name, mult=mult)
        smart_sleep(0.15, mult)
        safe_set_text(dev, inputs[1], email_val, mult=mult)
        smart_sleep(0.15, mult)
        safe_set_text(dev, inputs[2], password_val, mult=mult, is_password=True)
        smart_sleep(0.2, mult)

        dev.shell("input keyevent 111")
        smart_sleep(0.4, mult)

        # الضغط على زر التأكيد النهائي (أنشئ حسابك) والتحقق من الانتقال لشاشة OTP قبل الانتظار
        otp_sent_at = time.time()
        reached_otp = False
        for reg_attempt in range(2):
            dump_reg_submit = safe_dump_hierarchy(dev)
            if not click_text_in_xml(dev, dump_reg_submit, ("أنشئ حسابك", "انشئ حسابك", "Create Account", "Create"), min_y=700, max_y=1400):
                dev.click(559, 1122)
            smart_sleep(1.8, mult)
            wait_for_network_loading(dev, max_wait=12.0)

            for _ in range(8):
                dump_after_sub = safe_dump_hierarchy(dev, retries=1)
                if is_on_otp_screen(dev, dump_after_sub):
                    reached_otp = True
                    break
                err = extract_screen_error(dump_after_sub)
                if err:
                    raise FlowError(f"فشل إنشاء الحساب (الإيميل/كلمة المرور): {err}")
                time.sleep(0.5)
            if reached_otp:
                break
            if reg_attempt == 0:
                log.warning(f"[{label}] لم تظهر شاشة الـ OTP بعد الضغط على أنشئ حسابك - إعادة المحاولة...")

        if not reached_otp:
            err = extract_screen_error(safe_dump_hierarchy(dev, retries=1))
            raise FlowError(f"لم تظهر شاشة رمز التحقق (OTP) بعد التسجيل{(': ' + err) if err else ''}")

        # 3. استلام وإدخال كود OTP
        otp = fetch_nusuk_otp(req.client_email.strip(), req.client_pass, timeout=55, sent_after=otp_sent_at)
        if not otp:
            raise FlowError("لم يتم استلام كود OTP")

        enter_otp_code(dev, otp, fallback_x=160, fallback_y=458, mult=mult)

        # 4. انتظار انتهاء تحميل الـ OTP ثم إغلاق نافذة تفعيل الموقع (لاحقًا) وأي نوافذ منبثقة
        smart_sleep(1.8, mult)
        wait_for_network_loading(dev, max_wait=12.0)
        dismiss_post_otp_popups(dev, mult=mult)

        # 5. الدخول للملف الشخصي ثم التصاريح السارية ثم أكمل الملف الشخصي
        dump_comp_sheet = open_active_permits_screen(dev, mult=mult, expect_complete_sheet=True)
        if not click_text_in_xml(dev, dump_comp_sheet, ("أكمل الملف الشخصي", "اكمل الملف الشخصي", "Complete Profile"), min_y=1600, max_y=1890):
            dev.click(540, 1796)
        smart_sleep(1.3, mult)

        # 6. اختيار زائر دولي / كافة الزوار (540, 852)
        dump_id_type = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_id_type, ("كافة الزوار", "زائر دولي", "International"), min_y=700, max_y=1050):
            dev.click(540, 852)
        smart_sleep(1.3, mult)
        wait_for_network_loading(dev, max_wait=6.0)

        # 7. اختيار الجنسية (الشاشة الموحدة الجديدة: قائمة الدولة عند 540, 457)
        raw_nat = str(req.nationality or req.nationality_text or req.search_text or p.get("nationality") or "مصر").strip()
        default_nat_y = int(req.nationality_y or req.option_y or req.choice_y or 323)

        dev.click(540, 457)
        if not wait_country_picker_open(dev, timeout=4.5 * mult):
            dump_step6 = safe_dump_hierarchy(dev)
            if "نوع الهويه" in normalize_text(dump_step6) or "زائر دولي" in dump_step6 or "International" in dump_step6:
                if not click_text_in_xml(dev, dump_step6, ("كافة الزوار", "زائر دولي", "International"), min_y=700, max_y=1050):
                    dev.click(540, 852)
                smart_sleep(1.2, mult)
            dev.click(540, 457)
            if not wait_country_picker_open(dev, timeout=4.5 * mult):
                raise FlowError("لم تظهر قائمة الجنسية بسبب بطء الاستجابة")
        smart_sleep(0.3, mult)

        select_and_confirm_nationality(dev, raw_nat, default_nat_y, mult=mult, confirm_fallback_y=1854)

        # 8. بيانات الجواز والتأشيرة (على نفس الشاشة الموحدة بعد العودة من قائمة الدولة)
        all_inputs = wait_edits(dev, 2, timeout=6.0 * mult)
        if all_inputs is None:
            dump_retry_nat = safe_dump_hierarchy(dev)
            if not click_text_in_xml(dev, dump_retry_nat, ("أكد اختيارك", "أكّد اختيارك", "تأكيد الاختيار", "Confirm"), min_y=1700, max_y=1910):
                dev.click(560, 1854)
            all_inputs = wait_edits(dev, 2, timeout=5.0 * mult)
        if all_inputs is None:
            raise FlowError("لم تظهر خانات الجواز والتأشيرة")
        smart_sleep(0.2, mult)
        ensure_visa_radio_selected(dev, mult=mult)
        all_inputs = wait_edits(dev, 2, timeout=3.0 * mult) or all_inputs
        safe_set_text(dev, all_inputs[0], passport_val, mult=mult)
        smart_sleep(0.15, mult)
        safe_set_text(dev, all_inputs[1], visa_val, mult=mult)
        smart_sleep(0.15, mult)

        dev.shell("input keyevent 111")
        smart_sleep(0.4, mult)

        # 9. زر الحفظ النهائي (تحقّق من حسابك: 559, 992) وفحص النتيجة
        dump_save = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_save, ("تحقق من حسابك", "التحقق من حسابك", "Verify"), min_y=880, max_y=1150):
            dev.click(559, 992)
        smart_sleep(1.2, mult)
        wait_for_network_loading(dev, max_wait=15.0)

        outcome = None
        last_err = None
        for _ in range(14):
            raw_dump = safe_dump_hierarchy(dev, retries=1)
            screen_dump = normalize_text(raw_dump)
            if any(normalize_text(k) in screen_dump for k in ALREADY_KEYS):
                outcome = "already"
                break
            if any(normalize_text(k) in screen_dump for k in SUCCESS_KEYS):
                outcome = "success"
                break
            err = extract_screen_error(raw_dump)
            if err:
                last_err = err
            time.sleep(0.5)

        if outcome is None and len(dev(className="android.widget.EditText")) >= 2 and not last_err:
            dev.shell("input keyevent 111")
            smart_sleep(0.3, mult)
            dump_save2 = safe_dump_hierarchy(dev)
            if not click_text_in_xml(dev, dump_save2, ("تحقق من حسابك", "التحقق من حسابك", "Verify"), min_y=880, max_y=1150):
                dev.click(559, 992)
            smart_sleep(1.2, mult)
            wait_for_network_loading(dev, max_wait=10.0)
            for _ in range(10):
                raw_dump = safe_dump_hierarchy(dev, retries=1)
                screen_dump = normalize_text(raw_dump)
                if any(normalize_text(k) in screen_dump for k in ALREADY_KEYS):
                    outcome = "already"
                    break
                if any(normalize_text(k) in screen_dump for k in SUCCESS_KEYS):
                    outcome = "success"
                    break
                err = extract_screen_error(raw_dump)
                if err:
                    last_err = err
                    break
                time.sleep(0.5)

        if outcome == "already":
            log.warning("الحساب مسجل مسبقاً! الضغط على الزر الأسود 'سجّل الخروج واستعد حسابك' وبدء مسار استرجاع الحساب تلقائياً...")
            dump_alr = safe_dump_hierarchy(dev)
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

        if outcome is None:
            dump_now = safe_dump_hierarchy(dev, retries=1)
            if not _is_on_profile_xml(dump_now) and not _is_on_home_xml(dump_now):
                err_msg = last_err or extract_screen_error(dump_now) or "لم تظهر رسالة نجاح التحقق من الجواز والتأشيرة"
                raise FlowError(f"فشل التحقق من بيانات الجواز والتأشيرة: {err_msg}")

        # 10. Continue Exploring (تابع واستكشف: 540, 1796) ثم سهم الرجوع للبروفايل (1019, 91)
        dump_exp = safe_dump_hierarchy(dev)
        if not click_text_in_xml(dev, dump_exp, ("تابع واستكشف", "Continue Exploring", "استكشف"), min_y=1650, max_y=1880):
            if any(normalize_text(k) in normalize_text(dump_exp) for k in SUCCESS_KEYS):
                dev.click(540, 1796)
        smart_sleep(1.3, mult)
        wait_for_network_loading(dev, max_wait=8.0)

        if not _is_on_profile_xml(safe_dump_hierarchy(dev, retries=1)):
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
        refresh_and_accept_friend_request(dev2, comp_id, leader_name, mult=mult)

        group_count = _record_companion_in_state(comp_name, comp_id)

        if not perform_safe_logout(dev2, slow=True, mult=mult):
            force_clean_login_state(dev2, "emu2")
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
        with _state_lock:
            keep_leader = (emu_key == "emu1" and STATE["group"]["leader_active"])
        if not keep_leader:
            force_clean_login_state(dev, emu_key)
        return {"success": False, "status": "error", "error": str(e), "screenshot": shot}


if __name__ == "__main__":
    import uvicorn

    log.info(f"تشغيل السيرفر على {HOST}:{PORT} | Origins: {ALLOWED_ORIGINS}")
    uvicorn.run(app, host=HOST, port=PORT)
