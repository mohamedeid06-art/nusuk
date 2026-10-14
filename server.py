import email
import imaplib
import json
import os
import re
import shutil
import socket
import sys
import threading
import time
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
import uiautomator2 as u2
import adbutils

# ضبط مخرجات النظام على ترميز UTF-8 لتجنب انهيار السيرفر في ويندوز CMD
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

app = FastAPI(title="Nusuk ERP & Automation Pro Server")

# 1. ضبط مسار ADB تلقائياً ليعمل بسلاسة في النظام ومن أي مجلد
def ensure_adb_in_path():
    try:
        adb_exe = adbutils.adb_path()
        if adb_exe and os.path.exists(adb_exe):
            adb_dir = os.path.dirname(adb_exe)
            if adb_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")
                print(f"[OK] ADB Path set: {adb_exe}")
            return adb_exe
    except Exception as e:
        print(f"[WARN] ADB Path initialization warning: {e}")
    return shutil.which("adb") or "adb"

ADB_PATH = ensure_adb_in_path()

# 2. ميدلوير شامل لدعم CORS و Private Network Access لجميع المتصفحات (بما فيها Chrome عبر HTTPS / GitHub Pages)
@app.middleware("http")
async def cors_and_pna_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response

# 3. إدارة اتصال المحاكي بمرونة وأمان بدون تعطيل السيرفر
EMULATOR_PORTS = [5557, 5555, 5554, 5556, 5558, 62001, 62025, 21503, 7555, 16384]
d = None
device_lock = threading.Lock()

def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.15) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False

def is_device_alive(device) -> bool:
    if device is None:
        return False
    try:
        return bool(device.serial and device.info and device.info.get("screenOn") is not None)
    except Exception:
        return False

def connect_to_any_emulator(force: bool = False):
    """
    الاتصال المرن بأي محاكي متاح:
    1. تجربة 127.0.0.1:5557
    2. تجربة 127.0.0.1:5555 أو البورتات المفتوحة
    3. تجربة u2.connect() لجلب أي جهاز متصل تلقائياً
    4. فحص adb devices والاتصال بأول جهاز متاح
    """
    global d
    with device_lock:
        if not force and is_device_alive(d):
            return d

        # محاولة 1: البورت المفضل 5557
        if is_port_open(5557):
            try:
                new_dev = u2.connect("127.0.0.1:5557")
                if is_device_alive(new_dev):
                    d = new_dev
                    print(f"[OK] Connected to emulator: [127.0.0.1:5557]")
                    return d
            except Exception:
                pass

        # محاولة 2: فحص أجهزة ADB المتصلة حالياً
        adb = adbutils.adb
        online_devices = []
        try:
            online_devices = [dev for dev in adb.device_list() if dev.get_state() == "device"]
        except Exception as e:
            print(f"[WARN] adb.device_list() check: {e}")

        # محاولة 3: فحص البورتات الشائعة وربطها بـ ADB إذا لم تكن هناك أجهزة نشطة
        if not online_devices:
            for port in EMULATOR_PORTS:
                if is_port_open(port):
                    try:
                        adb.connect(f"127.0.0.1:{port}", timeout=1.0)
                    except Exception:
                        pass
            try:
                online_devices = [dev for dev in adb.device_list() if dev.get_state() == "device"]
            except Exception:
                online_devices = []

        # اختيار السيريال
        target_serial = ""
        for dev in online_devices:
            s = dev.serial
            if s and (s.startswith("127.0.0.1:") or s.startswith("emulator-")):
                target_serial = s
                break
        if not target_serial and online_devices:
            target_serial = online_devices[0].serial

        if target_serial:
            try:
                new_dev = u2.connect(target_serial)
                if is_device_alive(new_dev):
                    d = new_dev
                    print(f"[OK] Connected to emulator: [{target_serial}]")
                    return d
            except Exception as e:
                print(f"[WARN] Failed connecting to {target_serial}: {e}")

        # محاولة 4: الاتصال الافتراضي بدون سيريال
        try:
            new_dev = u2.connect()
            if is_device_alive(new_dev):
                d = new_dev
                print(f"[OK] Connected to default emulator via u2.connect()")
                return d
        except Exception:
            pass

        d = None
        return None

def get_device(max_retries: int = 1, retry_delay: float = 1.0):
    """الحصول على كائن المحاكي مع آلية إعادة المحاولة لتجنب انهيار السيرفر"""
    global d
    if is_device_alive(d):
        return d

    for attempt in range(max_retries):
        dev = connect_to_any_emulator(force=True)
        if dev:
            return dev
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
    return None

# خيط خلفي للاتصال عند بدء تشغيل السيرفر
def background_emulator_connector():
    print("[INFO] Server started. Searching for active emulators in background...")
    for _ in range(15):
        dev = connect_to_any_emulator(force=True)
        if dev:
            return
        time.sleep(2)
    print("[INFO] Server is running. Waiting for emulator to start...")

threading.Thread(target=background_emulator_connector, daemon=True).start()

# 4. دوال التفاعل مع شاشة المحاكي (المنطق الأصلي)
PACKAGE_NUSUK = "com.moh.nusukapp"

def fill_field(device, index, value, offset_y=45):
    """الدالة الأصلية لتعبئة الحقول بحسب الإحداثيات وترتيب TextView"""
    labels = device(className="android.widget.TextView")
    if len(labels) > index:
        label = labels[index]
        b = label.info["bounds"]
        device.click(b["left"] + 50, b["bottom"] + offset_y)
        try:
            device.clear_text()
        except Exception:
            pass
        device.send_keys(str(value))
    else:
        device.send_keys(str(value))

def fill_registration_fields(device, name: str, email: str, password: str):
    """تعبئة حقول الاسم الكامل، البريد، وكلمة المرور بأعلى دقة"""
    edits = device(className="android.widget.EditText")
    if len(edits) >= 3:
        # الحقل 0: الاسم
        edits[0].click()
        time.sleep(0.15)
        edits[0].set_text(name)
        time.sleep(0.2)
        # الحقل 1: الإيميل
        edits[1].click()
        time.sleep(0.15)
        edits[1].set_text(email)
        time.sleep(0.2)
        # الحقل 2: كلمة المرور
        edits[2].click()
        time.sleep(0.15)
        try:
            device.clear_text()
        except Exception:
            pass
        edits[2].set_text(password)
        time.sleep(0.2)
        return True
    else:
        # الطريقة الأصلية عبر fill_field
        fill_field(device, 2, name)
        time.sleep(0.2)
        fill_field(device, 3, email)
        time.sleep(0.2)
        fill_field(device, 4, password)
        time.sleep(0.2)
        return True

def navigate_to_register_screen(device):
    """
    التنقل الذكي لشاشة إنشاء الحساب:
    - إذا كان التطبيق مغلقاً أو في الخلفية، يفتحه
    - يتجاوز شاشة الترحيب بالضغط على 'تسجيل الدخول أو إنشاء حساب'
    - يضغط على 'أنشئ حسابًا جديدًا'
    - إذا كان التطبيق مفتوحاً على الشاشة الرئيسية (من معتمر سابق)، يرجع لشاشة التسجيل
    """
    try:
        cur = device.app_current()
        if not cur or cur.get("package") != PACKAGE_NUSUK:
            print(f"[NAV] Launching {PACKAGE_NUSUK}...")
            device.app_start(PACKAGE_NUSUK)
            time.sleep(2.5)

        for _ in range(6):
            # هل شاشة النموذج جاهزة؟
            if len(device(className="android.widget.EditText")) >= 3 or device(text="الاسم الكامل").exists:
                print("[NAV] Registration form ready.")
                return True

            # شاشة البداية
            if device(text="تسجيل الدخول أو إنشاء حساب").exists:
                print("[NAV] Step 1: Clicking 'تسجيل الدخول أو إنشاء حساب'")
                device(text="تسجيل الدخول أو إنشاء حساب").click()
                time.sleep(1.5)
                continue

            # زر أنشئ حسابًا جديدًا
            if device(text="أنشئ حسابًا جديدًا").exists:
                print("[NAV] Step 2: Clicking 'أنشئ حسابًا جديدًا'")
                device(text="أنشئ حسابًا جديدًا").click()
                time.sleep(1.5)
                continue
            elif device(textContains="أنشئ حساب").exists and not device(className="android.widget.EditText").exists:
                device(textContains="أنشئ حساب").click()
                time.sleep(1.5)
                continue

            # إذا كان التطبيق على الشاشة الرئيسية أو في الداخل
            if device(text="الرئيسية").exists or device(text="الروضة").exists or device(text="المحفظة").exists:
                # الضغط على أيقونة الملف الشخصي بالأعلى يسار
                device.click(65, 101)
                time.sleep(1.5)
                if device(text="أنشئ حسابًا جديدًا").exists:
                    device(text="أنشئ حسابًا جديدًا").click()
                    time.sleep(1.5)
                    continue
                elif device(text="تسجيل الخروج").exists:
                    device(text="تسجيل الخروج").click()
                    time.sleep(1.0)
                    if device(text="تسجيل الخروج").exists:
                        device(text="تسجيل الخروج").click()
                    time.sleep(1.5)
                    continue

            # تجاوز شاشات أذونات النظام
            if device(text="WHILE USING THE APP").exists:
                device(text="WHILE USING THE APP").click()
            if device(text="ALLOW").exists:
                device(text="ALLOW").click()

            time.sleep(1.0)

        return len(device(className="android.widget.EditText")) >= 1 or device(text="الاسم الكامل").exists
    except Exception as ex:
        print(f"[WARN] Navigation error: {ex}")
        return False

# 5. سحب رمز التحقق OTP تلقائياً من بريد Gmail عبر IMAP
def get_latest_email_id(email_user: str, app_password: str) -> int:
    """معرفة رقم آخر رسالة في البريد لضمان عدم قراءة كود قديم"""
    try:
        clean_pass = app_password.replace(" ", "").strip()
        clean_user = email_user.strip()
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=7)
        mail.login(clean_user, clean_pass)
        mail.select("INBOX")
        status, messages = mail.search(None, "ALL")
        if status == "OK" and messages and messages[0]:
            ids = messages[0].split()
            if ids:
                last_id = int(ids[-1])
                try:
                    mail.logout()
                except Exception:
                    pass
                return last_id
        try:
            mail.logout()
        except Exception:
            pass
    except Exception:
        pass
    return 0

def fetch_nusuk_otp(email_user: str, app_password: str, baseline_id: int = 0, max_wait_seconds: int = 40) -> str:
    """الاتصال بـ Gmail وسحب كود OTP المكون من 4 أرقام"""
    if not email_user or not app_password:
        return ""

    clean_pass = app_password.replace(" ", "").strip()
    clean_user = email_user.strip()
    start_time = time.time()

    print(f"[OTP] Checking Gmail IMAP for {clean_user} (baseline_id={baseline_id}, timeout={max_wait_seconds}s)...")

    while time.time() - start_time < max_wait_seconds:
        mail = None
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=10)
            mail.login(clean_user, clean_pass)
            mail.select("INBOX")

            status, messages = mail.search(None, "ALL")
            if status == "OK" and messages and messages[0]:
                msg_ids = messages[0].split()
                candidates = []
                for mid in reversed(msg_ids[-6:]):
                    mid_num = int(mid)
                    if baseline_id == 0 or mid_num > baseline_id:
                        candidates.append(mid)

                for msg_id in candidates:
                    res, data = mail.fetch(msg_id, "(RFC822)")
                    if res != "OK" or not data or not data[0]:
                        continue
                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    subject = str(msg.get("Subject", ""))
                    sender = str(msg.get("From", ""))

                    if ("nusuk" in sender.lower() or 
                        "nusuk" in subject.lower() or 
                        "verification" in subject.lower() or 
                        "تحقق" in subject or 
                        "رمز" in subject):
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() in ["text/plain", "text/html"]:
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body += payload.decode("utf-8", errors="ignore")
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body += payload.decode("utf-8", errors="ignore")

                        # البحث عن النمط [ 1234 ] أولاً
                        exact_match = re.search(r'\[\s*(\d{4})\s*\]', body)
                        if exact_match:
                            otp = exact_match.group(1)
                            print(f"[OTP] Successfully retrieved OTP: [{otp}] from email {msg_id.decode()}")
                            try:
                                mail.logout()
                            except Exception:
                                pass
                            return otp

                        codes = re.findall(r'\b\d{4}\b', body)
                        if codes:
                            otp = codes[0]
                            print(f"[OTP] Successfully retrieved OTP: [{otp}] from email {msg_id.decode()}")
                            try:
                                mail.logout()
                            except Exception:
                                pass
                            return otp

            try:
                mail.logout()
            except Exception:
                pass

        except Exception as ex:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

        time.sleep(2.0)

    print("[OTP] Timeout: could not retrieve OTP within allocated time.")
    return ""

def enter_otp_on_screen(device, otp: str):
    """إدخال كود التحقق في المربعات على الشاشة وتأكيده"""
    print(f"[OTP] Entering 4-digit code {otp} on screen...")
    edits = device(className="android.widget.EditText")
    if len(edits) == 4:
        boxes_ltr = sorted(edits, key=lambda e: e.info['bounds']['left'])
        for i, digit in enumerate(otp[:4]):
            try:
                boxes_ltr[i].click()
                time.sleep(0.1)
                boxes_ltr[i].set_text(digit)
            except Exception:
                device.shell(f"input text {digit}")
            time.sleep(0.1)
    else:
        device.shell(f"input text {otp}")

    time.sleep(1.0)
    # الضغط على زر التأكيد
    for txt in ["تأكيد البريد الإلكتروني", "تحديث الملف الشخصي", "تأكيد", "تحقق"]:
        if device(text=txt).exists:
            device(text=txt).click()
            print(f"[OTP] Clicked '{txt}' button")
            break
    else:
        device.click(540, 714)
        print("[OTP] Clicked confirmation coordinates (540, 714)")

    time.sleep(2.5)

# 6. مسارات الـ API
@app.get("/api/status")
@app.head("/api/status")
@app.options("/api/status")
def check_status():
    device = get_device()
    serial = device.serial if device else None
    return {
        "status": "ready" if device else "waiting_for_device",
        "ok": True,
        "online": True,
        "device_connected": device is not None,
        "device_serial": serial,
        "message": f"السيرفر متصل بالمحاكي ({serial})" if device else "السيرفر يعمل وفي انتظار اتصال المحاكي..."
    }

@app.get("/api/reconnect")
def reconnect():
    device = connect_to_any_emulator(force=True)
    return {
        "success": device is not None,
        "device_connected": device is not None,
        "device_serial": device.serial if device else None,
        "message": f"تم الاتصال بالمحاكي ({device.serial})" if device else "لم يتم العثور على محاكي نشط."
    }

@app.get("/api/devices")
def list_devices():
    adb = adbutils.adb
    devices_info = []
    try:
        for dev in adb.device_list():
            devices_info.append({"serial": dev.serial, "state": dev.get_state()})
    except Exception as e:
        devices_info.append({"error": str(e)})

    return {
        "connected_serial": d.serial if (d and is_device_alive(d)) else None,
        "detected_devices": devices_info
    }

@app.get("/")
def home():
    return {
        "status": "online",
        "app": "Nusuk ERP & Automation Pro Local Server",
        "version": "2.3",
        "device_connected": d is not None and is_device_alive(d)
    }

@app.post("/api/sync_queue")
async def sync_queue(request: Request):
    try:
        body = await request.json()
        with open("active_queue.json", "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        count = len(body.get("pilgrimsList") or body.get("pilgrims") or [])
        print(f"[SYNC] Received queue with {count} pilgrims. Saved to active_queue.json")
        return {"success": True, "count": count, "message": f"تم استلام وتحديث الكشف بنجاح ({count} معتمر)"}
    except Exception as e:
        print(f"[SYNC ERROR] {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/sync_queue")
def get_sync_queue():
    if os.path.exists("active_queue.json"):
        with open("active_queue.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {"pilgrimsList": [], "credentials": {}}


@app.post("/api/register")
def register(data: dict):
    # استخراج بيانات المعتمر
    p = data.get("pilgrim", data)
    client_email = data.get("client_email") or ""
    client_pass = data.get("client_pass") or ""
    nationality = data.get("nationality") or "تايلاند"
    nationality_y = data.get("nationality_y", 195)

    name = p.get("الاسم") or p.get("Name") or "معتمر نسك"
    email = p.get("البريد الإلكتروني") or p.get("Email") or p.get("email") or client_email
    nusuk_fixed_pass = data.get("nusuk_password") or p.get("الباسورد") or p.get("Password") or "Msamy2006**"
    password = str(nusuk_fixed_pass).strip() or "Msamy2006**"
    passport = p.get("رقم الجواز") or p.get("Passport") or p.get("passport") or ""
    visa = p.get("رقم التأشيرة") or p.get("Visa") or p.get("visa") or ""

    # الاتصال التلقائي بالمحاكي قبل بدء تسجيل المعتمر
    device = get_device(max_retries=3, retry_delay=1.0)
    if not device:
        return {
            "success": False,
            "status": "error",
            "error": "محاكي أندرويد غير متصل! يرجى تشغيل المحاكي (LDPlayer / BlueStacks / Nox) والتأكد من ظهوره في النظام."
        }

    try:
        print(f"[PROCESS] Starting registration for: {name} ({email}) - Passport: {passport}")

        # 1. التنقل لشاشة إنشاء الحساب
        nav_ok = navigate_to_register_screen(device)
        if not nav_ok:
            # محاولة أخيرة عبر فتح التطبيق مباشرة
            device.app_start(PACKAGE_NUSUK)
            time.sleep(2.0)

        # 2. تعبئة بيانات الحساب (الاسم، الإيميل، الباسورد)
        fill_registration_fields(device, name, email, password)

        # تسجيل رقم آخر رسالة في البريد قبل الضغط على الزر لضمان عدم قراءة كود قديم
        baseline_msg_id = get_latest_email_id(client_email, client_pass)

        # 3. الضغط على زر "أنشئ حسابك"
        time.sleep(0.5)
        items = device(text="أنشئ حسابك")
        if len(items) >= 2:
            # الزر السفلي (وليس عنوان الصفحة العلوي)
            b = items[len(items) - 1].info["bounds"]
            device.click((b["left"] + b["right"]) // 2, (b["top"] + b["bottom"]) // 2)
            print("[PROCESS] Clicked bottom 'أنشئ حسابك' button")
        elif len(items) == 1:
            items[0].click()
            print("[PROCESS] Clicked 'أنشئ حسابك'")
        elif len(device(className="android.widget.TextView")) > 6:
            device(className="android.widget.TextView")[6].click()
            print("[PROCESS] Clicked TextView[6] button")
        else:
            device.click(540, 1140)
            print("[PROCESS] Clicked fallback coordinates (540, 1140)")

        time.sleep(2.5)

        # 4. فحص هل ظهر تنبيه "مسجل مسبقاً"
        if (device(textContains="مسجل مسبق").exists or 
            device(textContains="مسجل مسبقا").exists or 
            device(textContains="موجود مسبق").exists or
            device(textContains="already exists").exists):
            print(f"[STATUS] Pilgrim already registered: {email}")
            return {
                "success": False,
                "status": "already_registered",
                "message": "الحساب مسجل مسبقاً في نٌسك"
            }

        # 5. خطوة التحقق OTP تلقائياً من Gmail
        otp_code = ""
        is_otp_screen = False
        for _ in range(8):
            if (device(textContains="رمز التحقق").exists or 
                device(textContains="البريد الإلكتروني").exists or 
                len(device(className="android.widget.EditText")) == 4):
                is_otp_screen = True
                break
            time.sleep(1.0)

        if is_otp_screen:
            print("[PROCESS] OTP verification screen detected.")
            otp_code = fetch_nusuk_otp(client_email, client_pass, baseline_id=baseline_msg_id, max_wait_seconds=45)
            if otp_code:
                print(f"[PROCESS] Entering fetched OTP: {otp_code}")
                enter_otp_on_screen(device, otp_code)
            else:
                print("[WARN] Could not fetch OTP automatically, waiting 15s...")
                time.sleep(15.0)

        # تجاوز أي نوافذ أذونات تظهر بعد التحقق (الموقع، الإشعارات)
        for _ in range(8):
            if device(text="WHILE USING THE APP").exists:
                device(text="WHILE USING THE APP").click()
            elif device(text="أثناء استخدام التطبيق").exists:
                device(text="أثناء استخدام التطبيق").click()
            elif device(text="ALLOW").exists:
                device(text="ALLOW").click()
            elif device(text="لاحقًا").exists:
                device(text="لاحقًا").click()
            elif device(text="لاحقا").exists:
                device(text="لاحقا").click()
            elif device(text="الروضة").exists or device(text="أكمل الملف الشخصي").exists:
                break
            time.sleep(1.0)

        # 6. الخطوات التكميلية الأصلية (الروضة، استكمال الملف الشخصي، الجواز والتأشيرة)
        if device(text="الروضة").exists:
            print("[PROCESS] Selecting Rawdah...")
            device(text="الروضة").click()
            time.sleep(1.5)

        # اختيار رجال أو نساء ثم المتابعة في شاشة الروضة إن ظهرت
        if device(text="رجال").exists:
            device(text="رجال").click()
            time.sleep(0.5)
        if device(text="المتابعة").exists:
            device(text="المتابعة").click()
            time.sleep(1.5)

        if device(text="أكمل الملف الشخصي").exists:
            print("[PROCESS] Complete profile prompt...")
            device(text="أكمل الملف الشخصي").click()
            time.sleep(1.5)
        elif device(textContains="أكمل الملف").exists:
            device(textContains="أكمل الملف").click()
            time.sleep(1.5)

        if device(textContains="زائر دولي").exists:
            print("[PROCESS] Selecting International Visitor...")
            device(textContains="زائر دولي").click()
            time.sleep(1.5)

        if device(text="الجنسية").exists:
            print(f"[PROCESS] Selecting nationality: {nationality}...")
            device(text="الجنسية").click()
            time.sleep(0.5)
            device.send_keys(nationality)
            time.sleep(0.5)
            if device(text=nationality).exists:
                device(text=nationality).click()
            else:
                device.click(200, nationality_y)
            time.sleep(0.5)

        if passport and device(textContains="جواز السفر").exists:
            print(f"[PROCESS] Entering passport: {passport}...")
            device(textContains="جواز السفر").click()
            time.sleep(0.3)
            device.send_keys(passport)

        if visa and device(textContains="رقم التأشيرة").exists:
            print(f"[PROCESS] Entering visa: {visa}...")
            device(textContains="رقم التأشيرة").click()
            time.sleep(0.3)
            device.send_keys(visa)

        if device(text="تحقّق من حسابك").exists:
            device(text="تحقّق من حسابك").click()
            time.sleep(2.0)

        print(f"[PROCESS] Registration completed successfully for: {name} (OTP: {otp_code or 'N/A'})")

        # إعادة تشغيل التطبيق لضمان جاهزية المحاكي للمعتمر التالي في الطابور
        try:
            device.app_stop(PACKAGE_NUSUK)
            time.sleep(0.8)
            device.app_start(PACKAGE_NUSUK)
        except Exception:
            pass

        return {
            "success": True,
            "status": "completed",
            "otp": otp_code,
            "message": "تم التسجيل والتحقق بنجاح"
        }

    except Exception as e:
        print(f"[ERROR] Registration exception: {e}")
        return {"success": False, "status": "error", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    print("[SERVER] Starting Nusuk ERP & Automation Pro server on http://127.0.0.1:8000 ...")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
