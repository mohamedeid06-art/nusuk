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

app = FastAPI(title="Nusuk ERP & Automation Pro Server")

# 1. ضبط مسار ADB تلقائياً ليعمل بسلاسة في النظام ومن أي مجلد
def ensure_adb_in_path():
    try:
        adb_exe = adbutils.adb_path()
        if adb_exe and os.path.exists(adb_exe):
            adb_dir = os.path.dirname(adb_exe)
            if adb_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")
                print(f"✅ تم تفعيل مسار ADB التلقائي: {adb_exe}")
            return adb_exe
    except Exception as e:
        print(f"⚠️ تنبيه إعداد مسار ADB: {e}")
    return shutil.which("adb") or "adb"

ADB_PATH = ensure_adb_in_path()

# 2. ميدلوير شامل لدعم CORS و Private Network Access لجميع المتصفحات (بما فيها Chrome عبر HTTPS / GitHub Pages)
@app.middleware("http")
async def cors_and_pna_middleware(request: Request, call_next):
    # معالجة طلب الفحص المسبق Preflight OPTIONS
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
        return bool(device.info and device.info.get("screenOn") is not None)
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
            print(f"⚠️ خطأ أثناء فحص adb.device_list(): {e}")

        # 2. إذا لم تكن هناك أجهزة نشطة، مسح سريع للبورتات الشائعة والاتصال بها
        if not online_devices:
            for port in EMULATOR_PORTS:
                if is_port_open(port):
                    try:
                        res = adb.connect(f"127.0.0.1:{port}", timeout=1.0)
                        print(f"🔄 محاولة ربط ADB مع 127.0.0.1:{port} -> {res}")
                    except Exception:
                        pass
            try:
                online_devices = [dev for dev in adb.device_list() if dev.get_state() == "device"]
            except Exception:
                online_devices = []

        if not online_devices:
            d = None
            return None

        # 3. اختيار أنسب سيريال (تفضيل emulator-* أو 127.0.0.1:*)
        target_serial = None
        for dev in online_devices:
            s = dev.serial
            if s.startswith("emulator-") or s.startswith("127.0.0.1:"):
                target_serial = s
                break
        if not target_serial:
            target_serial = online_devices[0].serial

        # 4. الاتصال عبر uiautomator2 بالسيريال المحدد لمنع AdbError
        try:
            new_device = u2.connect(target_serial)
            if is_device_alive(new_device):
                d = new_device
                prod_name = d.info.get("productName", "")
                print(f"✅ تم الاتصال بنجاح بالمحاكي: [{target_serial}] ({prod_name})")
                return d
        except Exception as e:
            print(f"⚠️ فشل الاتصال بالمحاكي ({target_serial}): {e}")

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
    print("🚀 بدء تشغيل السيرفر.. جاري فحص المحاكيات في الخلفية...")
    max_startup_attempts = 15  # محاولة لمدة 30 ثانية أثناء إقلاع المحاكي
    for i in range(max_startup_attempts):
        dev = connect_to_any_emulator(force=True)
        if dev:
            return
        time.sleep(2)
    print("ℹ️ السيرفر قيد التشغيل وجاهز. بانتظار فتح المحاكي (سيتم الاتصال به تلقائياً فور تشغيله).")

# تشغيل خيط الاتصال الخلفي
threading.Thread(target=background_emulator_connector, daemon=True).start()

def fill_field(index, value, offset_y=45):
    device = get_device(max_retries=3, retry_delay=1.0)
    if not device:
        raise RuntimeError("محاكي أندرويد غير متصل! يرجى فتح المحاكي (LDPlayer / BlueStacks / Nox) أولاً والتأكد من فتح تطبيق نسك.")
    label = device(className="android.widget.TextView")[index]
    b = label.info["bounds"]
    device.click(b["left"] + 50, b["bottom"] + offset_y)
    device.clear_text()
    device.send_keys(str(value))

# 5. مسارات الـ API
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

@app.get("/")
def home():
    return {
        "status": "online",
        "app": "Nusuk ERP & Automation Pro Local Server",
        "version": "2.1"
    }

@app.post("/api/register")
def register(data: dict):
    # دعم البيانات المباشرة أو المغلفة داخل كائن pilgrim
    p = data.get("pilgrim", data)
    client_email = data.get("client_email") or ""
    client_pass = data.get("client_pass") or ""
    nationality = data.get("nationality") or "تايلاند"
    nationality_y = data.get("nationality_y", 195)

    name = p.get("الاسم") or p.get("Name") or ""
    email = p.get("البريد الإلكتروني") or p.get("Email") or p.get("email") or client_email
    password = p.get("الباسورد") or p.get("Password") or client_pass or "Msamy2006**"
    passport = p.get("رقم الجواز") or p.get("Passport") or p.get("passport") or ""
    visa = p.get("رقم التأشيرة") or p.get("Visa") or p.get("visa") or ""

    device = get_device(max_retries=3, retry_delay=1.0)
    if not device:
        return {
            "success": False,
            "status": "error",
            "error": "محاكي أندرويد غير متصل! يرجى تشغيل المحاكي (LDPlayer / BlueStacks / Nox) وإعادة المحاولة."
        }

    try:
        # 1. شاشة إنشاء الحساب
        fill_field(2, name)
        fill_field(3, email)
        fill_field(4, password)
        device(className="android.widget.TextView")[6].click()  # زر أنشئ حسابك
        time.sleep(2)

        # 2. خطوة الـ OTP
        time.sleep(5)

        # 3. الشاشة الرئيسية: الضغط على الروضة
        device(text="الروضة").click()
        time.sleep(1)

        # 4. بوب أب: أكمل الملف الشخصي
        device(text="أكمل الملف الشخصي").click()
        time.sleep(1)

        # 5. نوع الهوية: زائر دولي
        device(textContains="زائر دولي").click()
        time.sleep(1)

        # 6. شاشة استكمال البيانات: الجنسية، الجواز، والتأشيرة
        device(text="الجنسية").click()
        time.sleep(0.5)
        device.send_keys(nationality)
        time.sleep(0.5)
        if device(text=nationality).exists:
            device(text=nationality).click()
        else:
            device.click(200, nationality_y)

        device(textContains="جواز السفر").click()
        device.send_keys(passport)

        device(textContains="رقم التأشيرة").click()
        device.send_keys(visa)

        device(text="تحقّق من حسابك").click()
        time.sleep(2)

        return {"success": True, "status": "completed"}
    except Exception as e:
        print(f"Error during registration: {e}")
        return {"success": False, "status": "error", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
