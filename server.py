import email
import imaplib
import os
import re
import shutil
import socket
import sys
import threading
import time
from fastapi import FastAPI, Request, Response
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

def ensure_adb_in_path():
    try:
        adb_exe = adbutils.adb_path()
        if adb_exe and os.path.exists(adb_exe):
            adb_dir = os.path.dirname(adb_exe)
            if adb_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")
            return adb_exe
    except Exception:
        pass
    return shutil.which("adb") or "adb"

ADB_PATH = ensure_adb_in_path()

# دعم CORS و Private Network Access ليعمل مع GitHub Pages والمحلي بدون حظر
@app.middleware("http")
async def cors_and_pna_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    origin = request.headers.get("origin")
    response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response

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
    global d
    with device_lock:
        if not force and is_device_alive(d):
            return d

        if is_port_open(5557):
            try:
                new_dev = u2.connect("127.0.0.1:5557")
                if is_device_alive(new_dev):
                    d = new_dev
                    print("[OK] Connected to emulator: [127.0.0.1:5557]")
                    return d
            except Exception:
                pass

        adb = adbutils.adb
        online_devices = []
        try:
            online_devices = [dev for dev in adb.device_list() if dev.get_state() == "device"]
        except Exception:
            pass

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
            except Exception:
                pass

        try:
            new_dev = u2.connect()
            if is_device_alive(new_dev):
                d = new_dev
                return d
        except Exception:
            pass

        d = None
        return None

def get_device(max_retries: int = 2, retry_delay: float = 1.0):
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

threading.Thread(target=lambda: connect_to_any_emulator(force=True), daemon=True).start()

PACKAGE_NUSUK = "com.moh.nusukapp"

# الدالة الأصلية الدقيقة للضغط أسفل عنوان الحقل والكتابة بداخله
def fill_field(device, index, value, offset_y=45):
    labels = device(className="android.widget.TextView")
    if len(labels) > index:
        label = labels[index]
        b = label.info["bounds"]
        device.click(b["left"] + 50, b["bottom"] + offset_y)
        time.sleep(0.15)
        try:
            device.clear_text()
        except Exception:
            pass
        device.send_keys(str(value))
    else:
        device.send_keys(str(value))

def click_below_label(device, label_text, value, offset_y=45):
    """الضغط أسفل النص المسمى (مثل جواز السفر أو رقم التأشيرة) والكتابة في المربع"""
    el = device(textContains=label_text)
    if el.exists:
        b = el[0].info["bounds"]
        device.click(b["left"] + 60, b["bottom"] + offset_y)
        time.sleep(0.2)
        try:
            device.clear_text()
        except Exception:
            pass
        device.send_keys(str(value))
        return True
    return False

def navigate_to_register_screen(device) -> bool:
    """
    ضمان الوصول الفعلي لشاشة 'أنشئ حسابك' التي تحتوي على حقول الإدخال الثلاثة:
    إذا كان التطبيق داخل حساب سابق أو في شاشة فرعية، يقوم بالخروج والعودة لشاشة التسجيل.
    """
    try:
        cur = device.app_current()
        if not cur or cur.get("package") != PACKAGE_NUSUK:
            device.app_start(PACKAGE_NUSUK)
            time.sleep(3.0)

        for step in range(10):
            # 1. هل نحن بالفعل داخل صفحة ملء بيانات الحساب الجديد؟
            if device(text="الاسم الكامل").exists or (
                device(text="أنشئ حسابك").exists and len(device(className="android.widget.EditText")) >= 3
            ):
                print("[NAV] Registration screen is ready.")
                return True

            # 2. تجاوز نوافذ الصلاحيات إن ظهرت
            if device(text="WHILE USING THE APP").exists:
                device(text="WHILE USING THE APP").click()
                time.sleep(0.8)
            if device(text="ALLOW").exists:
                device(text="ALLOW").click()
                time.sleep(0.8)

            # 3. هل نحن على شاشة الترحيب الأولى؟
            if device(text="تسجيل الدخول أو إنشاء حساب").exists:
                device(text="تسجيل الدخول أو إنشاء حساب").click()
                time.sleep(1.5)
                continue

            # 4. هل ظهر زر 'أنشئ حسابًا جديدًا'؟
            if device(text="أنشئ حسابًا جديدًا").exists:
                device(text="أنشئ حسابًا جديدًا").click()
                time.sleep(1.5)
                continue
            if device(textContains="أنشئ حساب").exists and not device(text="الاسم الكامل").exists:
                device(textContains="أنشئ حساب").click()
                time.sleep(1.5)
                continue

            # 5. إذا كان التطبيق عالقاً في شاشة OTP قديمة أو شاشة داخلية، نرجع للخلف
            if device(textContains="رمز التحقق").exists or device(text="تأكيد البريد الإلكتروني").exists:
                device.press("back")
                time.sleep(1.2)
                continue

            # 6. إذا كان التطبيق داخل حساب مسجل (الرئيسية / الروضة / الملف الشخصي)
            if device(text="الرئيسية").exists or device(text="الروضة").exists or device(text="الخدمات").exists:
                # الضغط على أيقونة الحساب أعلى اليسار لتسجيل الخروج أو إنشاء حساب
                device.click(65, 101)
                time.sleep(1.5)
                if device(text="أنشئ حسابًا جديدًا").exists:
                    device(text="أنشئ حسابًا جديدًا").click()
                    time.sleep(1.5)
                    continue
                if device(textContains="تسجيل الخروج").exists:
                    device(textContains="تسجيل الخروج").click()
                    time.sleep(1.0)
                    if device(text="نعم").exists:
                        device(text="نعم").click()
                    elif device(textContains="تسجيل الخروج").exists:
                        device(textContains="تسجيل الخروج").click()
                    time.sleep(2.0)
                    continue

            # 7. محاولة الرجوع خطوة للخلف
            device.press("back")
            time.sleep(1.2)

        return device(text="الاسم الكامل").exists or len(device(className="android.widget.EditText")) >= 3
    except Exception as ex:
        print(f"[WARN] Navigation exception: {ex}")
        return False

def get_latest_email_id(email_user: str, app_password: str) -> int:
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
                mail.logout()
                return last_id
        mail.logout()
    except Exception:
        pass
    return 0

def fetch_nusuk_otp(email_user: str, app_password: str, baseline_id: int = 0, max_wait_seconds: int = 45) -> str:
    if not email_user or not app_password:
        return ""
    clean_pass = app_password.replace(" ", "").strip()
    clean_user = email_user.strip()
    start_time = time.time()

    print(f"[OTP] Waiting for new OTP on {clean_user} (after msg #{baseline_id})...")
    while time.time() - start_time < max_wait_seconds:
        mail = None
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=10)
            mail.login(clean_user, clean_pass)
            mail.select("INBOX")
            status, messages = mail.search(None, "ALL")
            if status == "OK" and messages and messages[0]:
                msg_ids = messages[0].split()
                candidates = [mid for mid in reversed(msg_ids[-6:]) if baseline_id == 0 or int(mid) > baseline_id]

                for msg_id in candidates:
                    res, data = mail.fetch(msg_id, "(RFC822)")
                    if res != "OK" or not data or not data[0]:
                        continue
                    msg = email.message_from_bytes(data[0][1])
                    subject = str(msg.get("Subject", ""))
                    sender = str(msg.get("From", ""))

                    if any(k in sender.lower() or k in subject.lower() for k in ["nusuk", "verification", "تحقق", "رمز"]):
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

                        exact_match = re.search(r'\[\s*(\d{4})\s*\]', body)
                        if exact_match:
                            otp = exact_match.group(1)
                            mail.logout()
                            return otp

                        codes = re.findall(r'\b\d{4}\b', body)
                        if codes:
                            otp = codes[0]
                            mail.logout()
                            return otp
            mail.logout()
        except Exception:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
        time.sleep(2.0)
    return ""

def enter_otp_on_screen(device, otp: str):
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
    for txt in ["تأكيد البريد الإلكتروني", "تحديث الملف الشخصي", "تأكيد", "تحقق"]:
        if device(text=txt).exists:
            device(text=txt).click()
            break
    else:
        device.click(540, 714)
    time.sleep(2.5)

@app.get("/api/status")
@app.head("/api/status")
@app.options("/api/status")
def check_status():
    device = get_device(max_retries=1)
    serial = device.serial if device else None
    return {
        "status": "ready" if device else "waiting_for_device",
        "ok": True,
        "online": True,
        "device_connected": device is not None,
        "device_serial": serial
    }

@app.post("/api/register")
def register(data: dict):
    p = data.get("pilgrim", data)
    client_email = (data.get("client_email") or "").strip()
    client_pass = (data.get("client_pass") or "").strip()
    nationality = (data.get("nationality") or "تايلاند").strip()
    nationality_y = int(data.get("nationality_y", 195))

    name = p.get("الاسم") or p.get("Name") or "معتمر نسك"
    email_addr = (p.get("البريد الإلكتروني") or p.get("Email") or p.get("email") or client_email).strip()
    password = str(data.get("nusuk_password") or p.get("الباسورد") or "Msamy2006**").strip()
    passport = str(p.get("رقم الجواز") or p.get("Passport") or p.get("passport") or "").strip()
    visa = str(p.get("رقم التأشيرة") or p.get("Visa") or p.get("visa") or "").strip()

    device = get_device(max_retries=3, retry_delay=1.0)
    if not device:
        return {"success": False, "status": "error", "error": "المحاكي غير متصل"}

    try:
        print(f"\n[START] Pilgrim: {name} | Passport: {passport} | Email: {email_addr}")

        # 1. التأكد الصارم من الوصول لشاشة التسجيل قبل كتابة أي حرف
        if not navigate_to_register_screen(device):
            return {
                "success": False,
                "status": "error",
                "error": "لم تظهر شاشة التسجيل"
            }

        # 2. تعبئة الاسم والإيميل والباسورد بالطريقة الأصلية المضمونة
        fill_field(device, 2, name)
        time.sleep(0.2)
        fill_field(device, 3, email_addr)
        time.sleep(0.2)
        fill_field(device, 4, password)
        time.sleep(0.3)

        # حفظ آخر رسالة في الجيميل قبل الضغط على زر التسجيل مباشرة
        baseline_msg_id = get_latest_email_id(client_email, client_pass)

        # 3. الضغط على زر "أنشئ حسابك"
        items = device(text="أنشئ حسابك")
        if len(items) >= 2:
            b = items[len(items) - 1].info["bounds"]
            device.click((b["left"] + b["right"]) // 2, (b["top"] + b["bottom"]) // 2)
        elif len(device(className="android.widget.TextView")) > 6:
            device(className="android.widget.TextView")[6].click()
        else:
            device.click(540, 1140)

        time.sleep(2.5)

        # 4. فحص هل الحساب مسجل مسبقاً؟
        if (device(textContains="مسجل مسبق").exists or
            device(textContains="مسجل مسبقا").exists or
            device(textContains="موجود مسبق").exists or
            device(textContains="already exists").exists):
            print(f"[ALREADY] {email_addr} is already registered.")
            return {
                "success": False,
                "status": "already_registered",
                "message": "مسجل مسبقاً"
            }

        # 5. انتظار شاشة الـ OTP وسحب الكود (إلزامي لنجاح التسجيل!)
        is_otp_screen = False
        for _ in range(10):
            if (device(textContains="رمز التحقق").exists or
                device(textContains="تأكيد البريد").exists or
                len(device(className="android.widget.EditText")) == 4):
                is_otp_screen = True
                break
            if device(textContains="مسجل مسبق").exists or device(textContains="موجود مسبق").exists:
                return {"success": False, "status": "already_registered", "message": "مسجل مسبقاً"}
            time.sleep(1.0)

        if not is_otp_screen:
            return {
                "success": False,
                "status": "error",
                "error": "لم ينتقل لشاشة رمز التحقق OTP"
            }

        otp_code = fetch_nusuk_otp(client_email, client_pass, baseline_id=baseline_msg_id, max_wait_seconds=45)
        if not otp_code:
            return {
                "success": False,
                "status": "error",
                "error": "لم يصل كود OTP للبريد"
            }

        enter_otp_on_screen(device, otp_code)

        # 6. استكمال بيانات الزائر الدولي (الجنسية، الجواز، التأشيرة)
        for _ in range(8):
            if device(text="WHILE USING THE APP").exists:
                device(text="WHILE USING THE APP").click()
            elif device(text="ALLOW").exists:
                device(text="ALLOW").click()
            elif device(text="لاحقًا").exists:
                device(text="لاحقًا").click()
            elif device(text="الروضة").exists or device(textContains="أكمل الملف").exists:
                break
            time.sleep(1.0)

        if device(text="الروضة").exists:
            device(text="الروضة").click()
            time.sleep(1.5)

        if device(text="رجال").exists:
            device(text="رجال").click()
            time.sleep(0.5)
        if device(text="المتابعة").exists:
            device(text="المتابعة").click()
            time.sleep(1.5)

        if device(textContains="أكمل الملف").exists:
            device(textContains="أكمل الملف").click()
            time.sleep(1.5)

        if device(textContains="زائر دولي").exists:
            device(textContains="زائر دولي").click()
            time.sleep(1.5)

        # اختيار الجنسية بالطريقة الأصلية
        if device(text="الجنسية").exists:
            b = device(text="الجنسية").info["bounds"]
            device.click(b["left"] + 60, b["bottom"] + 45)
            time.sleep(0.6)
            device.send_keys(nationality)
            time.sleep(0.8)
            device.click(200, nationality_y)
            time.sleep(0.6)

        # كتابة الجواز والتأشيرة أسفل العنوان مباشرة
        if passport:
            click_below_label(device, "جواز السفر", passport, offset_y=45)
            time.sleep(0.3)

        if visa:
            click_below_label(device, "رقم التأشيرة", visa, offset_y=45)
            time.sleep(0.3)

        if device(text="تحقّق من حسابك").exists:
            device(text="تحقّق من حسابك").click()
            time.sleep(2.5)

        print(f"[SUCCESS] Completed: {name} | OTP: {otp_code}")
        return {
            "success": True,
            "status": "completed",
            "otp": otp_code,
            "message": "تم التسجيل بنجاح"
        }

    except Exception as e:
        print(f"[ERROR] {e}")
        return {"success": False, "status": "error", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
