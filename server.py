import copy
import email
import email.header
import email.utils
import imaplib
import json
import logging
import os
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Dict, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _ensure_runtime_dependencies():
    import glob
    import sys

    try:
        import uiautomator2  # noqa: F401
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get("NUSUK_REEXEC") != "1":
        home = os.path.expanduser("~")
        patterns = [
            os.path.join(home, "AppData", "Local", "Programs", "Python", "Python*", "python.exe"),
            os.path.join(home, "Desktop", "*", "Scripts", "python.exe"),
            os.path.join(home, "*", "Scripts", "python.exe"),
            os.path.join(home, "*venv*", "Scripts", "python.exe"),
            os.path.join(home, "anaconda3", "python.exe"),
            os.path.join(home, "miniconda3", "python.exe"),
            r"C:\Python*\python.exe",
            r"C:\Program Files\Python*\python.exe",
        ]
        seen = {os.path.normcase(os.path.abspath(sys.executable))}
        for pat in patterns:
            for cand in glob.glob(pat):
                norm = os.path.normcase(os.path.abspath(cand))
                if norm in seen or not os.path.isfile(cand):
                    continue
                seen.add(norm)
                try:
                    chk = subprocess.run(
                        [cand, "-c", "import uiautomator2, fastapi, uvicorn"],
                        capture_output=True,
                        timeout=6,
                    )
                    if chk.returncode == 0:
                        print(f"[✓] تحويل التشغيل تلقائياً إلى بيئة البايثون المكتملة: {cand}")
                        env = os.environ.copy()
                        env["NUSUK_REEXEC"] = "1"
                        raise SystemExit(subprocess.call([cand, os.path.abspath(__file__), *sys.argv[1:]], env=env))
                except SystemExit:
                    raise
                except Exception:
                    pass

    print("[⏳] جاري تثبيت المكتبات المطلوبة للسيرفر (uiautomator2, fastapi, uvicorn) لأول مرة...")
    pacman_exe = r"C:\msys64\usr\bin\pacman.exe"
    if "msys64" in sys.executable.lower() and os.path.isfile(pacman_exe):
        subprocess.run(
            [
                pacman_exe,
                "-S",
                "--noconfirm",
                "--needed",
                "mingw-w64-ucrt-x86_64-python-pip",
                "mingw-w64-ucrt-x86_64-python-fastapi",
                "mingw-w64-ucrt-x86_64-python-uvicorn",
                "mingw-w64-ucrt-x86_64-python-pydantic",
                "mingw-w64-ucrt-x86_64-python-pillow",
                "mingw-w64-ucrt-x86_64-python-lxml",
                "mingw-w64-ucrt-x86_64-python-requests",
            ]
        )
    else:
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], capture_output=True)

    pkgs = ["uiautomator2", "fastapi", "uvicorn", "pydantic"]
    res = subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", *pkgs])
    if res.returncode != 0:
        subprocess.run([sys.executable, "-m", "pip", "install", *pkgs])


_ensure_runtime_dependencies()

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
    "مسجل مسبق", "مسجل بالفعل", "موجود مسبق", "مسجلة مسبق",
    "لديك حساب", "already registered", "already exists", "account already",
]
SUCCESS_KEYS = ["exploring", "استكشاف", "نجاح"]
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

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
    with _state_lock:
        live_mult = float(STATE.get("speed_multiplier", mult) or mult)
    time.sleep(max(0.08, base_seconds * live_mult))


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
    """البحث عن نص داخل XML الملتقط والضغط على مركز العنصر فوراً بدون استدعاءات RPC إضافية"""
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
        lowered_targets = [t.lower() for t in targets]
        for node in root.iter():
            t = (node.attrib.get("text") or "").strip().lower()
            d = (node.attrib.get("content-desc") or "").strip().lower()
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
    if "استعد حسابك" in dump:
        click_text_in_xml(dev, dump, ("استعد حسابك", "استعادة حسابك"), min_y=1400, max_y=1800)
    elif "لديك مشكلة" in dump:
        click_text_in_xml(dev, dump, ("لديك مشكلة",), min_y=600, max_y=1200)
        smart_sleep(1.0, mult)
        dev.click(780, 1650)
    else:
        if any(m in dump for m in WELCOME_MARKERS) or "تسجيل الدخول أو إنشاء حساب" in dump:
            dev.click(540, 1768)
            smart_sleep(1.2, mult)

        dump_sheet = dev.dump_hierarchy()
        if "الدخول بواسطة البريد" in dump_sheet or "البريد الإلكتروني" in dump_sheet:
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
    if "كافة الزوار" in dump_rec or "زائر دولي" in dump_rec:
        if not click_text_in_xml(dev, dump_rec, ("كافة الزوار", "زائر دولي"), min_y=1400, max_y=1850):
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


@app.api_route("/api/set-speed", methods=["POST", "GET"])
def set_speed_api(multiplier: float = 1.0):
    mult = max(0.5, min(3.0, float(multiplier)))
    with _state_lock:
        STATE["speed_multiplier"] = mult
    save_state()
    log.info(f"⚡ تم تغيير معامل سرعة المحرك إلى: {mult}x")
    return {"success": True, "speed_multiplier": mult}


@app.api_route("/api/restart-server", methods=["POST", "GET"])
def restart_server_api():
    import sys
    log.info("🔄 طلب إعادة تشغيل السيرفر من الواجهة...")

    def _do_restart():
        time.sleep(0.6)
        server_path = os.path.abspath(__file__)
        ps_cmd = f'powershell.exe -NoExit -ExecutionPolicy Bypass -Command "Set-Location \'{BASE_DIR}\'; & \'{sys.executable}\' \'{server_path}\'"'
        subprocess.Popen(f'start "Nusuk Pro Engine" {ps_cmd}', shell=True)
        os._exit(0)

    threading.Thread(target=_do_restart, daemon=True).start()
    return {"success": True, "message": "جاري إعادة تشغيل السيرفر..."}


@app.api_route("/api/stop-server", methods=["POST", "GET"])
def stop_server_api():
    log.info("⏹️ طلب إيقاف السيرفر من الواجهة...")

    def _do_stop():
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=_do_stop, daemon=True).start()
    return {"success": True, "message": "تم إيقاف السيرفر بنجاح"}


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
            if req.speed_multiplier:
                with _state_lock:
                    STATE["speed_multiplier"] = mult
            dev = get_device(EMUS[emu_key]["serial"])
            return run_account_recovery_flow(dev, req, role, comp_num, emu_key, mult=mult)
        except Exception as e:
            log.exception("خطأ في /api/recover")
            return {"success": False, "status": "error", "error": str(e)}


def _run_register(req: RegisterRequest) -> dict:
    p = req.pilgrim or {}
    dummy_name = "Ab"
    mult = float(req.speed_multiplier or STATE.get("speed_multiplier", 1.0))
    if req.speed_multiplier:
        with _state_lock:
            STATE["speed_multiplier"] = mult

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
            screen_dump = dev.dump_hierarchy().lower()
            if any(k in screen_dump for k in ALREADY_KEYS):
                outcome = "already"
                break
            if any(k in screen_dump for k in SUCCESS_KEYS):
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
                screen_dump = dev.dump_hierarchy().lower()
                if any(k in screen_dump for k in ALREADY_KEYS):
                    outcome = "already"
                    break
                if any(k in screen_dump for k in SUCCESS_KEYS):
                    outcome = "success"
                    break
                time.sleep(0.5)

        if outcome == "already":
            log.warning("الحساب مسجل مسبقاً! بدء مسار استرجاع الحساب وفحص التصاريح تلقائياً...")
            dev.click(540, 1711)
            smart_sleep(1.0, mult)
            dev.click(540, 300)
            smart_sleep(0.7, mult)
            force_clean_login_state(dev, emu_key)
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


def register_browser_protocol():
    """تسجيل بروتوكول nusuk-server:// في ويندوز لتشغيل السيرفر بضغطة زر من المتصفح"""
    try:
        import sys
        import winreg
        python_exe = sys.executable
        server_path = os.path.abspath(__file__)
        cmd_str = f'powershell.exe -NoExit -ExecutionPolicy Bypass -Command "Set-Location \'{BASE_DIR}\'; & \'{python_exe}\' \'{server_path}\'"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\nusuk-server") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Nusuk Local Server Launcher")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\nusuk-server\shell\open\command") as cmd_key:
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_str)
    except Exception as e:
        log.warning(f"تعذر تسجيل بروتوكول التشغيل التلقائي: {e}")


def free_port_before_start(port: int):
    """إغلاق أي نسخة قديمة عالقة على نفس البورت قبل بدء السيرفر"""
    try:
        my_pid = os.getpid()
        out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in line:
                pid = int(parts[-1])
                if pid != my_pid and pid > 0:
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(0.4)
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    register_browser_protocol()
    free_port_before_start(PORT)
    log.info(f"تشغيل السيرفر على {HOST}:{PORT} | Origins: {ALLOWED_ORIGINS}")
    uvicorn.run(app, host=HOST, port=PORT)
