import email
import imaplib
<<<<<<< HEAD
import json
import os
import re
import shutil
import sys
import threading
import time
from typing import Optional
from fastapi import FastAPI, Request, Response
=======
import re
import time
from typing import Any, Dict, Optional
import adbutils
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
>>>>>>> 02518e383d09fdbfc50efddb3d32625ab7147308
from pydantic import BaseModel
import uiautomator2 as u2
import uvicorn

<<<<<<< HEAD
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
=======
app = FastAPI()
>>>>>>> 02518e383d09fdbfc50efddb3d32625ab7147308

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

<<<<<<< HEAD
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
=======
>>>>>>> 02518e383d09fdbfc50efddb3d32625ab7147308
d = None

<<<<<<< HEAD
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
=======

def get_device():
  """الاتصال التلقائي بالمحاكي المفتوح عليه تطبيق نسك من بين الأجهزة المتصلة"""
  global d
  try:
    if d is not None and d.info.get("screenOn") is not None:
      return d
  except Exception:
    d = None

  # فحص كل المحاكيات المتصلة حالياً عبر adbutils
  try:
    devices = adbutils.adb.device_list()
    for dev_info in devices:
      try:
        dev = u2.connect(dev_info.serial)
        curr_app = str(dev.app_current()).lower()
        if (
            "nusuk" in curr_app
            or dev(textContains="أنشئ حسابك").exists
            or len(dev(className="android.widget.EditText")) > 0
        ):
          d = dev
          print(f"[✓] تم الاتصال بالمحاكي النشط: {d.serial}")
          return d
        if d is None:
          d = dev
      except Exception:
        pass
  except Exception:
    pass

  # محاولة احتياطية على البورتات المعتادة
  for target in [
      "127.0.0.1:16384",
      "127.0.0.1:5555",
      "127.0.0.1:7555",
      "127.0.0.1:5557",
  ]:
    try:
      dev = u2.connect(target)
      if dev and dev.info.get("screenOn") is not None:
        d = dev
        return d
    except Exception:
      pass

  return d


class RegisterRequest(BaseModel):
  client_email: str
  client_pass: str
  pilgrim: Dict[str, Any]
  nationality_mode: Optional[str] = "egypt"
  nationality_search: Optional[str] = "مصر"


def fetch_nusuk_otp(
    imap_user: str, imap_pass: str, target_to_email: str, max_wait: int = 45
) -> Optional[str]:
  """سحب كود OTP من البريد الإلكتروني عبر IMAP"""
  print(f"[*] مراقبة كود OTP على {imap_user}...")
  start_time = time.time()
  clean_pass = imap_pass.replace(" ", "")

  while time.time() - start_time < max_wait:
    try:
      mail = imaplib.IMAP4_SSL("imap.gmail.com")
      mail.login(imap_user, clean_pass)
      mail.select("inbox")

      status, messages = mail.search(None, "ALL")
      if status == "OK" and messages[0]:
        msg_ids = messages[0].split()
        # فحص أحدث 5 رسائل
        for num in reversed(msg_ids[-5:]):
          res, msg_data = mail.fetch(num, "(RFC822)")
          if res != "OK":
            continue
          for response_part in msg_data:
            if isinstance(response_part, tuple):
              msg = email.message_from_bytes(response_part[1])
              subj = str(msg.get("Subject", "")).lower()
              from_hdr = str(msg.get("From", "")).lower()

              body = ""
              if msg.is_multipart():
                for part in msg.walk():
                  if part.get_content_type() in ["text/plain", "text/html"]:
                    payload = part.get_payload(decode=True)
                    if payload:
                      body += payload.decode(errors="ignore")
              else:
                payload = msg.get_payload(decode=True)
                if payload:
                  body = payload.decode(errors="ignore")

              if (
                  "nusuk" in from_hdr
                  or "نسك" in body
                  or "nusuk" in body.lower()
                  or "otp" in subj
                  or "verification" in subj
              ):
                codes = re.findall(r"\b(\d{4})\b", body)
                if codes:
                  otp_code = codes[0]
                  mail.logout()
                  return otp_code
      mail.logout()
    except Exception as e:
      print(f"[!] تنبيه أثناء فحص الإيميل: {e}")

    time.sleep(3)

  return None


def safe_set_text(
    d_inst, edit_el, text_val: str, tap_coords: Optional[tuple] = None
):
  """كتابة النص بأمان مع ضمان التفعيل"""
  try:
    edit_el.click()
    time.sleep(0.2)
    edit_el.set_text(text_val)
  except Exception:
    if tap_coords:
      d_inst.shell(f"input tap {tap_coords[0]} {tap_coords[1]}")
      time.sleep(0.2)
      d_inst.send_keys(text_val)


def execute_workflow(req: RegisterRequest) -> Dict[str, Any]:
  d = get_device()
  if not d:
    return {
        "success": False,
        "status": "error",
        "error": "لا يوجد محاكي متصل حالياً",
    }

  p = req.pilgrim
  passport_no = str(p.get("passport", "")).strip()
  visa_no = str(p.get("visa", "")).strip()
  email_val = str(p.get("email", "")).strip()
  password_val = str(p.get("password", "") or "Msamy2006**").strip()
  dummy_name = "صى"

  print("\n" + "=" * 50)
  print(f"[*] جواز: {passport_no} | تأشيرة: {visa_no}")

  try:
    # 1. فتح شاشة أنشئ حساباً جديداً إذا لم تكن مفتوحة
    inputs = d(className="android.widget.EditText")
    if len(inputs) < 3:
      print("[*] النقر على أنشئ حساباً جديداً بالإحداثيات...")
      d.shell("input tap 540 1725")
      time.sleep(2.5)
      inputs = d(className="android.widget.EditText")

    # 2. كتابة البيانات الأساسية (الاسم، البريد، كلمة المرور)
    if len(inputs) >= 3:
      print("[*] كتابة البيانات الأساسية...")
      safe_set_text(d, inputs[0], dummy_name)
      time.sleep(0.3)
      safe_set_text(d, inputs[1], email_val)
      time.sleep(0.3)
      safe_set_text(d, inputs[2], password_val)
      time.sleep(0.4)

      # إغلاق الكيبورد والانتظار لحظة لظهور الزر الأسود بالأسفل
      d.shell("input keyevent 111")
      time.sleep(1.0)

      # النقر المضمون على زر "أنشئ حسابك" السفلي
      print("[*] النقر على زر إنشاء الحساب...")
      if d(textContains="أنشئ حسابك").exists:
        d(textContains="أنشئ حسابك")[-1].click()
      elif d(textContains="أنشئ حساب").exists:
        d(textContains="أنشئ حساب")[-1].click()
      else:
        d.shell("input tap 540 1760")
        time.sleep(0.4)
        d.shell("input tap 540 1298")

      time.sleep(3.5)
    else:
      print("[!] خطأ: لم تظهر شاشة التسجيل!")
      return {
          "success": False,
          "status": "error",
          "error": "لم تظهر شاشة التسجيل",
      }

    # 3. سحب وإدخال كود الـ OTP
    otp_code = fetch_nusuk_otp(req.client_email, req.client_pass, email_val)
    if not otp_code:
      return {
          "success": False,
          "status": "error",
          "error": "لم يصل كود التحقق OTP إلى الإيميل",
      }

    print(f"[✓] تم استخراج OTP: {otp_code}")
    d.shell("input tap 540 850")
    time.sleep(0.3)
    d.shell(f"input text {otp_code}")
    print("[*] انتظار 3 ثواني بعد كتابة الـ OTP...")
    time.sleep(3.5)

    # 4. تنظيف الشاشة والدخول للملف الشخصي وتصاريح نسك
    print("[*] تنفيذ 3 نقرات أعلى اليمين للتنظيف (1000, 100)...")
    for _ in range(3):
      d.shell("input tap 1000 100")
      time.sleep(0.4)

    print("[*] النقر على الأفاتار أعلى اليسار (65, 101)...")
    d.shell("input tap 65 101")
    time.sleep(2.5)

    print("[*] النقر على Active Permits أسفل اليمين (807, 1786)...")
    d.shell("input tap 807 1786")
    time.sleep(2.5)

    print("[*] النقر على زر Complete Profile بالأسفل (540, 1793)...")
    if d(textContains="Complete Profile").exists:
      d(textContains="Complete Profile").click()
    elif d(textContains="إكمال الملف").exists:
      d(textContains="إكمال الملف").click()
    else:
      d.shell("input tap 540 1793")
    time.sleep(2.5)

    # 5. اختيار زائر دولي والجنسية
    print("[*] اختيار زائر دولي (540, 886)...")
    d.shell("input tap 540 886")
    time.sleep(1.5)

    nat_text = req.nationality_search or "مصر"
    print(f"[*] فتح حقل الجنسية والبحث عن ({nat_text}) ثم اختيار Y=275...")
    d.shell("input tap 540 491")
    time.sleep(1.2)

    search_box = d(className="android.widget.EditText")
    if search_box.exists:
      search_box[0].click()
      time.sleep(0.3)
      search_box[0].set_text(nat_text)
    else:
      edits = d(className="android.widget.EditText")
      if len(edits) > 0:
        top_edit = min(edits, key=lambda el: el.info["bounds"]["top"])
        top_edit.click()
        time.sleep(0.3)
        top_edit.set_text(nat_text)

    time.sleep(1.2)
    print("[*] اختيار الخيار عند (540, 275)...")
    d.shell("input tap 540 275")
    time.sleep(1.2)

    # 6. إدخال رقم التأشيرة ورقم الجواز
    all_inputs = d(className="android.widget.EditText")
    if len(all_inputs) >= 2:
      # ترتيب الحقول من الأعلى للأسفل
      sorted_inputs = sorted(
          all_inputs, key=lambda el: el.info["bounds"]["top"]
      )
      sorted_inputs[-2].click()
      time.sleep(0.2)
      sorted_inputs[-2].set_text(visa_no)
      time.sleep(0.3)

      sorted_inputs[-1].click()
      time.sleep(0.2)
      sorted_inputs[-1].set_text(passport_no)
      time.sleep(0.3)

    d.shell("input keyevent 111")
    time.sleep(0.8)

    # 7. الضغط على زر الحفظ والمتابعة
    print("[*] الضغط على زر الحفظ (540, 1040)...")
    d.shell("input tap 540 1040")
    time.sleep(3.5)

    # فحص ما إذا كان الحساب مسجلاً مسبقاً
    already_reg = False
    if (
        d(textContains="مسجل").exists
        or d(textContains="already").exists
        or d(textContains="مستخدم").exists
    ):
      already_reg = True
      print("[!] المعتمر مسجل مسبقاً، جاري التجاوز...")
      d.shell("input tap 540 1711")
      time.sleep(1.5)
      d.shell("input tap 1019 91")
      time.sleep(1.5)
    else:
      print("[*] الضغط على زر Continue Exploring (540, 1793)...")
      if d(textContains="Continue Exploring").exists:
        d(textContains="Continue Exploring").click()
      else:
        d.shell("input tap 540 1793")
      time.sleep(2.5)

    # 8. الرجوع للرئيسية وتسجيل الخروج للدورة التالية
    print("[*] الضغط على السهم أعلى اليمين للرجوع للرئيسية (1019, 91)...")
    d.shell("input tap 1019 91")
    time.sleep(2.0)

    print("[*] في الرئيسية.. سحب القائمة لأسفل لتسجيل الخروج...")
    d.swipe(540, 1500, 540, 400, 0.3)
    time.sleep(1.2)

    print("[*] تسجيل الخروج (540, 1730)...")
    if d(textContains="تسجيل الخروج").exists:
      d(textContains="تسجيل الخروج").click()
    elif d(textContains="Logout").exists or d(textContains="Log out").exists:
      d(textContains="Log").click()
    else:
      d.shell("input tap 540 1730")
    time.sleep(1.5)

    # تأكيد تسجيل الخروج إن ظهر مربع حوار
    if (
        d(textContains="نعم").exists
        or d(textContains="تأكيد").exists
        or d(textContains="Yes").exists
    ):
      for confirm_txt in ["نعم", "تأكيد", "Yes", "Confirm", "تسجيل الخروج"]:
        if d(text=confirm_txt).exists:
          d(text=confirm_txt)[-1].click()
          break
      time.sleep(1.5)

    status_label = "already_registered" if already_reg else "registered"
    print(f"[✓] تمت العملية بنجاح للحساب: {email_val}")
    return {"success": True, "status": status_label, "email": email_val}

  except Exception as e:
    print(f"[!] حدث خطأ أثناء التنفيذ: {e}")
    return {"success": False, "status": "error", "error": str(e)}


@app.get("/api/status")
def api_status():
  dev = get_device()
  connected = dev is not None
  return {
      "status": "ready" if connected else "disconnected",
      "device_connected": connected,
      "serial": dev.serial if connected else None,
  }

>>>>>>> 02518e383d09fdbfc50efddb3d32625ab7147308

# 8. تنفيذ الأتمتة الأصلي المعتمد بالكامل
@app.post("/api/register")
<<<<<<< HEAD
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
=======
def api_register(req: RegisterRequest):
  return execute_workflow(req)


if __name__ == "__main__":
  print("🚀 جاري تشغيل سيرفر أتمتة نسك...")
  get_device()
  uvicorn.run(app, host="127.0.0.1", port=7410)
>>>>>>> 02518e383d09fdbfc50efddb3d32625ab7147308
