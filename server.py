import email
import imaplib
import json
import os
import re
import shutil
import sys
import threading
import time
from typing import Optional
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
import uiautomator2 as u2
import adbutils

# ضبط ترميز الإخراج على UTF-8
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

# 1. ضبط مسار ADB تلقائياً ليعمل في كل مكان
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

# 2. دعم CORS و Private Network Access للمتصفحات (PNA)
@app.middleware("http")
async def cors_and_pna_middleware(request: Request, call_next):
    # معالجة طلبات Preflight (OPTIONS) الخاصة بكروم و PNA فوراً
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        try:
            response = await call_next(request)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            response = Response(
                content=json.dumps({"ok": False, "status": "error", "error": str(exc)}),
                status_code=500,
                media_type="application/json"
            )

    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"

    req_headers = request.headers.get("access-control-request-headers")
    if req_headers:
        response.headers["Access-Control-Allow-Headers"] = req_headers
    else:
        response.headers["Access-Control-Allow-Headers"] = "*"

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD"
    # دعم Private Network Access (PNA) الصريح لكروم لمواقع HTTPS مثل GitHub Pages
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response

# 3. إدارة اتصال المحاكي (يدعم 5557 و 5555 وأي محاكي نشط)
d = None
device_lock = threading.Lock()

def is_device_alive(device) -> bool:
    if device is None:
        return False
    try:
        return bool(device.serial and device.info and device.info.get("screenOn") is not None)
    except Exception:
        return False

def connect_to_emulator(force: bool = False):
    global d
    with device_lock:
        if not force and is_device_alive(d):
            return d

        # 1. فحص الأجهزة المتصلة عبر adbutils أولاً واختيار الجهاز المفتوح عليه تطبيق نسك
        try:
            device_list = [dev for dev in adbutils.adb.device_list() if dev.get_state() == "device"]
            # الأولوية للمحاكي المفتوح عليه تطبيق نسك تلقائياً
            for dev_info in device_list:
                try:
                    s = dev_info.serial
                    dev = u2.connect(s)
                    if is_device_alive(dev):
                        cur = dev.app_current()
                        if cur and cur.get("package") == "com.moh.nusukapp":
                            d = dev
                            print(f"[OK] Connected to emulator running Nusuk: [{s}]")
                            return d
                except Exception:
                    pass

            # إذا لم يكن التطبيق مفتوحاً، نختار أول محاكي نشط
            for dev_info in device_list:
                try:
                    s = dev_info.serial
                    dev = u2.connect(s)
                    if is_device_alive(dev):
                        d = dev
                        print(f"[OK] Connected to emulator via adbutils: [{s}]")
                        return d
                except Exception:
                    pass
        except Exception:
            pass

        # 2. فحص البورتات المتصلة الشائعة (16384, 5555, 7555, إلخ)
        for port in [16384, 5555, 7555, 5557, 5554, 5556, 5558, 62001]:
            try:
                dev = u2.connect(f"127.0.0.1:{port}")
                if is_device_alive(dev):
                    d = dev
                    print(f"[OK] Connected to emulator: [127.0.0.1:{port}]")
                    return d
            except Exception:
                pass

        # 3. الاتصال الافتراضي
        try:
            dev = u2.connect()
            if is_device_alive(dev):
                d = dev
                print("[OK] Connected to default emulator via u2.connect()")
                return d
        except Exception:
            pass

        d = None
        return None

def get_device():
    global d
    if is_device_alive(d):
        return d
    return connect_to_emulator(force=True)

threading.Thread(target=connect_to_emulator, daemon=True).start()

# 4. جلب رمز OTP عبر IMAP
def fetch_nusuk_otp(client_email: str, client_pass: str, timeout: int = 60):
    clean_email = client_email.strip()
    clean_pass = client_pass.replace(" ", "").strip()
    print(f"[*] مراقبة كود OTP على: {clean_email}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        mail = None
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(clean_email, clean_pass)
            mail.select("inbox")
            status, messages = mail.search(None, "UNSEEN")
            if status == "OK" and messages and messages[0]:
                mail_ids = messages[0].split()
                for mid in reversed(mail_ids):
                    status, data = mail.fetch(mid, "(RFC822)")
                    if status != "OK" or not data or not data[0]:
                        continue
                    msg = email.message_from_bytes(data[0][1])
                    sender = msg.get("From", "").lower()
                    subject = msg.get("Subject", "").lower()
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                p = part.get_payload(decode=True)
                                if p:
                                    body += p.decode("utf-8", errors="ignore")
                    else:
                        p = msg.get_payload(decode=True)
                        if p:
                            body += p.decode("utf-8", errors="ignore")

                    if any(
                        k in sender or k in subject or k in body.lower()
                        for k in ["nusuk", "نسك", "verification", "رمز", "otp"]
                    ):
                        matches = re.findall(r"\b\d{4}\b", body)
                        valid_codes = [c for c in matches if c != "2026"]
                        if valid_codes:
                            otp = valid_codes[0]
                            mail.store(mid, "+FLAGS", "\\Seen")
                            try:
                                mail.logout()
                            except Exception:
                                pass
                            print(f"[✓] تم استخراج OTP: {otp}")
                            return otp
            try:
                mail.logout()
            except Exception:
                pass
        except Exception:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass
        time.sleep(2)
    return None

# 5. تسجيل الخروج الآمن
def perform_safe_logout(w=1080, h=1920):
    device = get_device()
    if not device:
        return
    print("[*] في الرئيسية.. سحب القائمة لأسفل لتسجيل الخروج...")
    time.sleep(1.5)
    try:
        # سحب الشاشة لأسفل مرتين للوصول لزر تسجيل الخروج
        device.swipe(0.5, 0.85, 0.5, 0.15, steps=25)
        time.sleep(1)
        device.swipe(0.5, 0.85, 0.5, 0.15, steps=25)
        time.sleep(1.2)

        # النقر على تسجيل الخروج
        print("[*] النقر على تسجيل الخروج (540, 1730)...")
        device.shell("input tap 540 1730")
        time.sleep(1.5)

        # تأكيد الخروج
        for txt in ["نعم", "تأكيد", "ديكأت", "موافق", "Yes", "Confirm", "Logout"]:
            btn_confirm = device(textContains=txt)
            if btn_confirm.exists:
                btn_confirm.click()
                break
        time.sleep(3)
    except Exception as e:
        print(f"[WARN] Error in perform_safe_logout: {e}")

# 6. استخراج الحقول
def extract_field(p, keys):
    if not isinstance(p, dict):
        return ""
    for k, v in p.items():
        clean_k = (
            str(k)
            .strip()
            .replace("أ", "ا")
            .replace("إ", "ا")
            .replace("آ", "ا")
            .replace("ة", "ه")
            .lower()
        )
        for search_k in keys:
            clean_s = (
                str(search_k)
                .strip()
                .replace("أ", "ا")
                .replace("إ", "ا")
                .replace("آ", "ا")
                .replace("ة", "ه")
                .lower()
            )
            if clean_k == clean_s or clean_k in clean_s or clean_s in clean_k:
                if v is not None and str(v).strip():
                    return str(v).strip()
    return ""

# 7. مسارات الـ API الأساسية
@app.get("/")
def home():
    device = get_device()
    return {
        "status": "online",
        "app": "Nusuk ERP & Automation Pro Local Server",
        "version": "3.1",
        "device_connected": device is not None,
        "device_serial": device.serial if device else None
    }

@app.get("/api/status")
@app.head("/api/status")
@app.options("/api/status")
def get_status():
    device = get_device()
    serial = device.serial if device else None
    connected = device is not None
    return {
        "status": "ready" if connected else "waiting_for_device",
        "device_connected": connected,
        "ok": True,
        "online": True,
        "serial": serial,
        "device_serial": serial,
        "message": f"السيرفر متصل بالمحاكي ({serial})" if connected else "السيرفر يعمل وفي انتظار اتصال المحاكي..."
    }

@app.get("/api/reconnect")
def reconnect():
    device = connect_to_emulator(force=True)
    return {
        "success": device is not None,
        "device_connected": device is not None,
        "device_serial": device.serial if device else None,
        "message": f"تم الاتصال بالمحاكي ({device.serial})" if device else "لم يتم العثور على محاكي نشط."
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

# 8. تنفيذ الأتمتة الأصلي المعتمد بالكامل
@app.post("/api/register")
async def execute_workflow(request: Request):
    data = await request.json()
    p = data.get("pilgrim") or data

    # حرفين فقط للاسم
    dummy_name = "Ab"

    client_email = data.get("client_email") or ""
    client_pass = data.get("client_pass") or ""

    email_val = (
        extract_field(
            p,
            [
                "email",
                "البريد الالكتروني",
                "البريد الإلكتروني",
                "Email",
                "الايميل",
            ],
        )
        or client_email
    )
    password_val = (
        data.get("nusuk_password")
        or extract_field(
            p, ["password", "الباسورد", "كلمة المرور", "Password", "pass"]
        )
        or "Msamy2006**"
    )
    passport_val = extract_field(
        p,
        [
            "رقم الجواز",
            "الجواز",
            "passport_number",
            "Passport",
            "passport",
            "رقم وثيقة السفر",
        ],
    )
    visa_val = extract_field(
        p,
        [
            "رقم الفيزا",
            "الفيزا",
            "رقم التاشيره",
            "رقم التأشيرة",
            "التاشيره",
            "التأشيرة",
            "visa_number",
            "Visa",
            "visa",
        ],
    )

    device = get_device()
    if not device:
        return {
            "success": False,
            "status": "error",
            "error": "محاكي أندرويد غير متصل! يرجى تشغيل المحاكي والتأكد من ظهوره."
        }

    w, h = device.window_size()
    print(f"\n{'='*50}\n[+] بدء المعالجة بالاسم الرمزي: {dummy_name}")
    print(f"[*] البريد: {email_val} | الجواز: {passport_val} | التأشيرة: {visa_val}")

    try:
        # التأكد من أن التطبيق مفتوح
        cur = device.app_current()
        if not cur or cur.get("package") != "com.moh.nusukapp":
            device.app_start("com.moh.nusukapp")
            time.sleep(2.5)

        # 1. شاشة الدخول والضغط على زر أنشئ حسابًا جديدًا بالأسفل
        inputs = device(className="android.widget.EditText")
        if len(inputs) < 3:
            print("[*] النقر على زر إنشاء الحساب السفلي...")
            clicked = False
            try:
                btn = device(textContains="أنشئ حسابك")
                if btn.exists:
                    btn[-1].click()
                    clicked = True
            except Exception as e:
                print(f"[!] u2 click failed: {e}")

            if not clicked:
                print("[*] استخدام الإحداثيات الاحتياطية (540, 1760)...")
                device.shell("input tap 540 1760")

            time.sleep(2.5)

            inputs = device(className="android.widget.EditText")
            if len(inputs) < 3:
                try:
                    btn = device(textContains="أنشئ حسابك")
                    if btn.exists:
                        btn[-1].click()
                    else:
                        device.shell("input tap 540 1760")
                except Exception:
                    device.shell("input tap 540 1760")
                time.sleep(2)
                inputs = device(className="android.widget.EditText")

        # 2. ملء البيانات الأساسية
        if len(inputs) >= 3:
            print("[*] كتابة البيانات الأساسية...")
            inputs[0].set_text(dummy_name)
            time.sleep(0.3)
            inputs[1].set_text(email_val)
            time.sleep(0.3)
            inputs[2].set_text(password_val)
            time.sleep(0.5)

            # إغلاق لوحة المفاتيح
            device.shell("input keyevent 111")
            time.sleep(0.8)

            # النقر على زر إنشاء الحساب
            print("[*] النقر على زر إنشاء الحساب...")
            # النقر على زر إنشاء الحساب عبر الزر أو الإحداثيات
            submit_btn = None
            for b in device(className="android.widget.Button"):
                bounds = b.info.get("bounds", {})
                if bounds.get("top", 0) > 800 and bounds.get("bottom", 0) < 1300:
                    submit_btn = b
                    break
            if submit_btn:
                submit_btn.click()
            else:
                device.shell("input tap 540 1138")
                time.sleep(0.3)
                device.shell("input tap 540 1298")
            time.sleep(3.5)
        else:
            print("[!] خطأ: لم تظهر شاشة التسجيل!")
            return {"success": False, "status": "error", "error": "لم تظهر شاشة التسجيل"}

        # فحص فوري هل ظهر خطأ "مسجل مسبقاً" قبل طلب الـ OTP
        screen_check = device.dump_hierarchy().lower()
        if any(k in screen_check for k in ["مسجل", "مسبق", "مسبقا", "مسبقاً", "already"]):
            print("[!] الحساب مسجل مسبقاً في نٌسك!")
            return {
                "success": False,
                "status": "already_registered",
                "message": "البيانات مسجلة مسبقاً في نٌسك"
            }

        # 3. إدخال كود OTP
        otp = fetch_nusuk_otp(client_email, client_pass, timeout=50)
        if not otp:
            return {
                "success": False,
                "status": "error",
                "error": "لم يتم استلام كود OTP",
            }

        # كتابة الكود
        print(f"[*] كتابة كود OTP المستلم: {otp}...")
        device.shell("input tap 160 462")
        time.sleep(0.3)
        for _ in range(4):
            device.shell("input keyevent 67")
            time.sleep(0.1)

        for digit in str(otp):
            device.shell(f"input text {digit}")
            time.sleep(0.25)

        device.shell("input keyevent 111")

        # 4. انتظار 3 ثواني ثم 3 نقرات تنظيف أعلى اليمين
        print("[*] انتظار 3 ثواني بعد كتابة الـ OTP...")
        time.sleep(3)

        print("[*] تنفيذ 3 نقرات أعلى اليمين للتنظيف (1000, 100)...")
        for _ in range(3):
            device.shell("input tap 1000 100")
            time.sleep(0.6)

        # 5. الدخول للملف الشخصي ثم Active Permits ثم Complete Profile
        print("[*] النقر على الأفاتار أعلى اليسار (65, 101)...")
        device.shell("input tap 65 101")
        time.sleep(2.5)

        print("[*] النقر على Active Permits أسفل اليمين (807, 1786)...")
        device.shell("input tap 807 1786")
        time.sleep(2)

        print("[*] النقر على زر Complete Profile بالأسفل (540, 1793)...")
        device.shell("input tap 540 1793")
        time.sleep(2)

        # 6. اختيار نوع المستخدم: زائر دولي
        print("[*] اختيار زائر دولي (540, 886)...")
        device.shell("input tap 540 886")
        time.sleep(2)

        # 7. حقل الجنسية والبحث واختيار الخيار المحدد
        nat_text = (
            data.get("nationality")
            or data.get("nationality_text")
            or p.get("nationality")
            or "تايلاند"
        )
        nat_y = (
            data.get("nationality_y")
            or data.get("option_y")
            or p.get("nationality_y")
            or 195
        )
        nat_y = int(nat_y)

        print(f"[*] فتح حقل الجنسية والبحث عن ({nat_text})...")
        device.shell("input tap 540 491")
        time.sleep(1.5)

        search_box = device(className="android.widget.EditText")
        if search_box.exists:
            search_box.set_text(nat_text)
        else:
            device.send_keys(nat_text)
        time.sleep(1)

        device.shell("input keyevent 111")
        time.sleep(0.5)

        print(f"[*] اختيار الخيار عند (540, {nat_y})...")
        device.shell(f"input tap 540 {nat_y}")  # اختيار الخيار
        time.sleep(0.8)

        device.shell("input tap 540 1850")  # زر التأكيد بالأسفل
        time.sleep(2)

        # 8. كتابة بيانات الجواز والتأشيرة
        all_inputs = device(className="android.widget.EditText")
        if len(all_inputs) >= 2:
            print(f"[*] كتابة الجواز: {passport_val} والتأشيرة: {visa_val}...")
            all_inputs[0].set_text(passport_val)
            time.sleep(0.4)
            all_inputs[1].set_text(visa_val)
            time.sleep(0.4)

        device.shell("input keyevent 111")
        time.sleep(0.8)

        # 9. الضغط على زر الحفظ النهائي
        print("[*] الضغط على زر الحفظ (540, 1040)...")
        device.shell("input tap 540 1040")
        time.sleep(3)

        # فحص رسائل الخطأ والتسجيل المسبق
        already_registered = False
        for _ in range(6):
            time.sleep(0.7)
            screen_dump = device.dump_hierarchy().lower()
            if any(
                k in screen_dump
                for k in [
                    "مسجل",
                    "مسبق",
                    "مسبقا",
                    "مسبقاً",
                    "الهوية",
                    "الهويه",
                    "خطأ",
                    "already",
                    "registered",
                    "exists",
                    "duplicate",
                    "account",
                    "found",
                ]
            ):
                already_registered = True
                break

        # معالجة المسجل مسبقاً
        if already_registered:
            print("[!] مسجل مسبقاً! الضغط على الزرار الأسود (540, 1711)...")
            time.sleep(1)
            device.shell("input tap 540 1711")
            time.sleep(1.5)

            # نقرة تنظيف في الربع العلوي الآمن
            print("[*] نقرة تنظيف في الربع العلوي...")
            device.shell("input tap 540 300")
            time.sleep(1)

            # تسجيل الخروج الآمن ليكون المحاكي جاهزاً للمعتمر التالي
            perform_safe_logout(w, h)

            return {
                "success": False,
                "status": "already_registered",
                "message": "البيانات مسجلة مسبقاً",
            }

        # 10. الحالة الناجحة: زر Continue Exploring ثم سهم الرجوع
        print("[*] الضغط على Continue Exploring (540, 1793)...")
        device.shell("input tap 540 1793")
        time.sleep(2)

        print("[*] الضغط على السهم أعلى اليمين للرجوع للرئيسية (1019, 91)...")
        device.shell("input tap 1019 91")
        time.sleep(2.5)

        # 11. تسجيل الخروج الآمن بالسحب لأسفل في الرئيسية مباشرة
        perform_safe_logout(w, h)
        print(f"[✓] تمت العملية بنجاح للحساب: {email_val}")
        return {
            "success": True,
            "status": "completed",
            "message": "تم التسجيل بنجاح",
            "otp": otp,
        }

    except Exception as e:
        print(f"[X] استثناء أثناء التنفيذ: {str(e)}")
        try:
            perform_safe_logout(w, h)
        except Exception:
            pass
        return {"success": False, "status": "error", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    print("[SERVER] Starting Nusuk server on http://127.0.0.1:7410 ...")
    uvicorn.run("server:app", host="127.0.0.1", port=7410, reload=True)
