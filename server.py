import email
import imaplib
import re
import time
from typing import Any, Dict, Optional
import adbutils
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uiautomator2 as u2
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

d = None


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


@app.post("/api/register")
def api_register(req: RegisterRequest):
  return execute_workflow(req)


if __name__ == "__main__":
  print("🚀 جاري تشغيل سيرفر أتمتة نسك...")
  get_device()
  uvicorn.run(app, host="127.0.0.1", port=7410)
