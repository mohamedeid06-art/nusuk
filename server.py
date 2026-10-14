import os
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
    # دعم Private Network Access الصريح لحل حظر المتصفحات للشبكة المحلية
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response

# 3. قائمة البورتات الشائعة لمختلف المحاكيات (LDPlayer, BlueStacks, Nox, MEmu, MuMu)
EMULATOR_PORTS = [
    5555,   # LDPlayer الافتراضي / BlueStacks / MEmu
    5554,   # المحاكي القياسي Instance 0
    5556,   # المحاكي القياسي Instance 1
    5557,   # LDPlayer / BlueStacks 64-bit
    5558,   # المحاكي القياسي Instance 2
    62001,  # NoxPlayer الافتراضي
    62025,  # NoxPlayer Multi-Instance 1
    21503,  # MEmu Player
    7555,   # MuMu Player
    16384,  # MuMu Player 12
]

d = None
device_lock = threading.Lock()

def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.12) -> bool:
    """فحص سريع بمهلة 120ms لمعرفة هل بورت المحاكي مفتوح محلياً أم لا"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False

def is_device_alive(device) -> bool:
    """فحص هل الاتصال بالمحاكي ما زال حياً ويستجيب للأوامر"""
    if device is None:
        return False
    try:
        # فحص سريع لخاصية serial أو info
        return bool(device.serial and device.info and device.info.get("screenOn") is not None)
    except Exception:
        return False

def connect_to_any_emulator(force: bool = False):
    """
    اكتشاف والاتصال التلقائي بأي محاكي متصل ومفتوح عبر ADB:
    - يبحث أولاً في قائمة الأجهزة المكتشفة في adb devices
    - إذا لم يجد أجهزة، يفحص بورتات المحاكيات النشطة على 127.0.0.1 ويتصل بها تلقائياً
    - يختار السيريال الصحيح لتجنب خطأ (more than one device/emulator)
    """
    global d
    with device_lock:
        if not force and is_device_alive(d):
            return d

        adb = adbutils.adb

        # 1. فحص الأجهزة المتصلة حالياً في ADB
        online_devices = []
        try:
            online_devices = [dev for dev in adb.device_list() if dev.get_state() == "device"]
        except Exception as e:
            print(f"[WARN] adb.device_list() error: {e}")

        # 2. إذا لم تكن هناك أجهزة نشطة، مسح سريع للبورتات الشائعة والاتصال بها
        if not online_devices:
            for port in EMULATOR_PORTS:
                if is_port_open(port):
                    try:
                        res = adb.connect(f"127.0.0.1:{port}", timeout=1.0)
                        print(f"[ADB] Attempting connection to 127.0.0.1:{port} -> {res}")
                    except Exception:
                        pass
            try:
                online_devices = [dev for dev in adb.device_list() if dev.get_state() == "device"]
            except Exception:
                online_devices = []

        if not online_devices:
            d = None
            return None

        # 3. اختيار أنسب سيريال (تفضيل 127.0.0.1:* أولاً ثم emulator-*)
        target_serial: str = ""
        # أولوية 1: 127.0.0.1:5555 أو أي IP محلي
        for dev in online_devices:
            s = dev.serial
            if s and s.startswith("127.0.0.1:"):
                target_serial = s
                break
        # أولوية 2: emulator-*
        if not target_serial:
            for dev in online_devices:
                s = dev.serial
                if s and s.startswith("emulator-"):
                    target_serial = s
                    break
        # أولوية 3: أول جهاز متاح
        if not target_serial and online_devices:
            first_serial = online_devices[0].serial
            if first_serial:
                target_serial = str(first_serial)

        if not target_serial:
            d = None
            return None

        # 4. الاتصال عبر uiautomator2 بالسيريال المحدد لمنع AdbError
        try:
            new_device = u2.connect(target_serial)
            if is_device_alive(new_device):
                d = new_device
                prod_name = d.info.get("productName", "") if d and d.info else ""
                print(f"[OK] Connected to emulator: [{target_serial}] ({prod_name})")
                return d
        except Exception as e:
            print(f"[WARN] Failed to connect to emulator ({target_serial}): {e}")

        d = None
        return None

def get_device(max_retries: int = 1, retry_delay: float = 1.0):
    """الحصول على كائن المحاكي مع آلية إعادة المحاولة (Retry Mechanism)"""
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

# 4. خيط خلفي (Background Thread) للاتصال وإعادة المحاولة التلقائية عند إقلاع السيرفر
def background_emulator_connector():
    """يحاول الاتصال بالمحاكي في الخلفية عند بدء التشغيل دون تعطيل سيرفر Uvicorn"""
    print("[INFO] Server started. Searching for active emulators in background...")
    max_startup_attempts = 15  # محاولة لمدة 30 ثانية أثناء إقلاع المحاكي
    for i in range(max_startup_attempts):
        dev = connect_to_any_emulator(force=True)
        if dev:
            return
        time.sleep(2)
    print("[INFO] Server is running. Waiting for emulator to start...")

threading.Thread(target=background_emulator_connector, daemon=True).start()

# 5. منطق التنقل التلقائي الذكي داخل تطبيق نُسك
PACKAGE_NUSUK = "com.moh.nusukapp"

def navigate_to_register_screen(device):
    """
    التحقق من مكان التطبيق والتنقل الذكي لشاشة إنشاء الحساب:
    1. فتح التطبيق إن لم يكن مفتوحاً في الواجهة
    2. تجاوز شاشة البداية (تسجيل الدخول أو إنشاء حساب)
    3. تجاوز شاشة اختيار وسيلة الدخول بالضغط على (أنشئ حسابًا جديدًا)
    4. التأكد من الوصول لشاشة النموذج (أنشئ حسابك)
    """
    try:
        # التأكد أن تطبيق نسك في الواجهة
        cur = device.app_current()
        if not cur or cur.get("package") != PACKAGE_NUSUK:
            print(f"[NAV] Launching app: {PACKAGE_NUSUK}")
            device.app_start(PACKAGE_NUSUK)
            time.sleep(2.5)

        # فحص الشاشة الحالية
        for _ in range(5):
            # شاشة البداية والترحيب
            btn_welcome = device(text="تسجيل الدخول أو إنشاء حساب")
            if btn_welcome.exists:
                print("[NAV] Step 1: Clicking 'تسجيل الدخول أو إنشاء حساب'")
                btn_welcome.click()
                time.sleep(1.5)
                continue

            # شاشة اختيار إنشاء حساب جديد
            btn_create = device(text="أنشئ حسابًا جديدًا")
            if not btn_create.exists:
                btn_create = device(textContains="أنشئ حساب")
            if btn_create.exists and not device(className="android.widget.EditText").exists:
                print("[NAV] Step 2: Clicking 'أنشئ حسابًا جديدًا'")
                btn_create.click()
                time.sleep(1.5)
                continue

            # التحقق هل وصلنا لشاشة نموذج التسجيل التي تحتوي على حقول الإدخال
            edit_texts = device(className="android.widget.EditText")
            if len(edit_texts) >= 3 or device(text="الاسم الكامل").exists:
                print("[NAV] Step 3: Registration form is active and ready.")
                return True

            time.sleep(1)

        # محاولة أخيرة: التحقق من وجود الحقول
        return len(device(className="android.widget.EditText")) >= 1
    except Exception as ex:
        print(f"[WARN] Navigation error: {ex}")
        return False

def fill_registration_fields(device, name: str, email: str, password: str):
    """
    تعبئة حقول الاسم الكامل، البريد الإلكتروني، وكلمة المرور
    باستخدام عناصر EditText المباشرة وبأعلى دقة وثبات
    """
    edit_texts = device(className="android.widget.EditText")
    if len(edit_texts) >= 3:
        # الحقل 0: الاسم الكامل
        edit_texts[0].click()
        time.sleep(0.2)
        edit_texts[0].set_text(name)
        time.sleep(0.3)

        # الحقل 1: البريد الإلكتروني
        edit_texts[1].click()
        time.sleep(0.2)
        edit_texts[1].set_text(email)
        time.sleep(0.3)

        # الحقل 2: كلمة المرور
        edit_texts[2].click()
        time.sleep(0.2)
        edit_texts[2].set_text(password)
        time.sleep(0.3)
        return True
    else:
        # طريقة بديلة في حال اختلاف الترتيب: البحث بالنصوص الإرشادية
        if device(text="الاسم الكامل").exists:
            device(text="الاسم الكامل").click()
            device.send_keys(name)
            time.sleep(0.3)
        if device(text="عنوان البريد الإلكتروني").exists:
            device(text="عنوان البريد الإلكتروني").click()
            device.send_keys(email)
            time.sleep(0.3)
        if device(text="كلمة المرور").exists:
            device(text="كلمة المرور").click()
            device.send_keys(password)
            time.sleep(0.3)
        return True

# 6. مسارات الـ API
@app.get("/api/status")
@app.head("/api/status")
@app.options("/api/status")
def check_status():
    device = get_device()
    serial = device.serial if device else None
    return {
        "status": "ready" if device else "waiting_for_device",
        "online": True,
        "device_connected": device is not None,
        "device_serial": serial,
        "message": f"السيرفر متصل بالمحاكي ({serial})" if device else "السيرفر يعمل وفي انتظار اتصال المحاكي..."
    }

@app.get("/api/reconnect")
def reconnect():
    """إعادة فحص وإعادة اتصال فورية بالمحاكي حسب الطلب"""
    device = connect_to_any_emulator(force=True)
    return {
        "success": device is not None,
        "device_connected": device is not None,
        "device_serial": device.serial if device else None,
        "message": f"تم الاتصال بالمحاكي ({device.serial})" if device else "لم يتم العثور على محاكي نشط."
    }

@app.get("/api/devices")
def list_devices():
    """عرض جميع المحاكيات والأجهزة المكتشفة في النظام"""
    adb = adbutils.adb
    devices_info = []
    try:
        for dev in adb.device_list():
            devices_info.append({
                "serial": dev.serial,
                "state": dev.get_state()
            })
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
        "version": "2.2",
        "device_connected": d is not None and is_device_alive(d)
    }

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
    password = p.get("الباسورد") or p.get("Password") or client_pass or "Msamy2006**"
    passport = p.get("رقم الجواز") or p.get("Passport") or p.get("passport") or ""
    visa = p.get("رقم التأشيرة") or p.get("Visa") or p.get("visa") or ""

    device = get_device(max_retries=3, retry_delay=1.0)
    if not device:
        return {
            "success": False,
            "status": "error",
            "error": "محاكي أندرويد غير متصل! يرجى تشغيل المحاكي (LDPlayer / BlueStacks / Nox) والتأكد من ظهوره في النظام."
        }

    try:
        print(f"[PROCESS] Starting registration for: {name} ({email}) - Passport: {passport}")

        # 1. التنقل الذكي لشاشة إنشاء الحساب
        navigate_to_register_screen(device)

        # 2. تعبئة بيانات الحساب (الاسم، الإيميل، الباسورد)
        fill_registration_fields(device, name, email, password)

        # 3. الضغط على زر "أنشئ حسابك"
        time.sleep(0.5)
        btn_submit = device(text="أنشئ حسابك")
        if not btn_submit.exists:
            btn_submit = device(textContains="أنشئ حسابك")
        if btn_submit.exists:
            btn_submit.click()
            print("[PROCESS] Clicked 'أنشئ حسابك'")
        else:
            # محاولة البحث عن زر الإرسال بواسطة XPath
            btns = device.xpath('//android.widget.Button').all()
            if btns:
                btns[-1].click()

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

        # 5. خطوة التحقق OTP (إذا كان مطلوباً، ينتظر التطبيق إدخال الرمز)
        time.sleep(3.0)

        # 6. الخطوات التكميلية (الروضة، استكمال الملف الشخصي، الجواز والتأشيرة) إن وجدت في الشاشة
        if device(text="الروضة").exists:
            print("[PROCESS] Selecting Rawdah...")
            device(text="الروضة").click()
            time.sleep(1.0)

        if device(text="أكمل الملف الشخصي").exists:
            print("[PROCESS] Complete profile prompt...")
            device(text="أكمل الملف الشخصي").click()
            time.sleep(1.0)

        if device(textContains="زائر دولي").exists:
            print("[PROCESS] Selecting International Visitor...")
            device(textContains="زائر دولي").click()
            time.sleep(1.0)

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
            time.sleep(0.2)
            device.send_keys(passport)

        if visa and device(textContains="رقم التأشيرة").exists:
            print(f"[PROCESS] Entering visa: {visa}...")
            device(textContains="رقم التأشيرة").click()
            time.sleep(0.2)
            device.send_keys(visa)

        if device(text="تحقّق من حسابك").exists:
            device(text="تحقّق من حسابك").click()
            time.sleep(2.0)

        print(f"[PROCESS] Registration completed successfully for: {name}")
        return {"success": True, "status": "completed", "message": "تمت العملية بنجاح"}

    except Exception as e:
        print(f"[ERROR] Registration exception: {e}")
        return {"success": False, "status": "error", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    print("[SERVER] Starting Nusuk ERP & Automation Pro server on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
