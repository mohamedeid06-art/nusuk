import email
import imaplib
import re
import time
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uiautomator2 as u2

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

d = u2.connect("127.0.0.1:5557")


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


def fetch_nusuk_otp(client_email, client_pass, timeout=60):
    print(f"[*] مراقبة كود OTP على: {client_email}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(client_email, client_pass.replace(" ", ""))
            mail.select("inbox")
            status, messages = mail.search(None, "UNSEEN")
            mail_ids = messages[0].split()
            for mid in reversed(mail_ids):
                status, data = mail.fetch(mid, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                sender = msg.get("From", "").lower()
                subject = msg.get("Subject", "").lower()
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body += part.get_payload(decode=True).decode(
                                "utf-8", errors="ignore"
                            )
                else:
                    body = msg.get_payload(decode=True).decode(
                        "utf-8", errors="ignore"
                    )

                if any(
                    k in sender or k in subject or k in body.lower()
                    for k in ["nusuk", "نسك", "verification", "رمز", "otp"]
                ):
                    matches = re.findall(r"\b\d{4}\b", body)
                    valid_codes = [c for c in matches if c != "2026"]
                    if valid_codes:
                        otp = valid_codes[0]
                        mail.store(mid, "+FLAGS", "\\Seen")
                        mail.logout()
                        print(f"[✓] تم استخراج OTP: {otp}")
                        return otp
            mail.logout()
        except Exception:
            pass
        time.sleep(2)
    return None


def perform_safe_logout(w, h):
    print("[*] في الرئيسية.. سحب القائمة لأسفل لتسجيل الخروج...")
    time.sleep(1.5)

    # سحب الشاشة لأسفل مرتين للوصول لزر تسجيل الخروج
    d.swipe(0.5, 0.85, 0.5, 0.15, steps=25)
    time.sleep(1)
    d.swipe(0.5, 0.85, 0.5, 0.15, steps=25)
    time.sleep(1.2)

    # النقر على تسجيل الخروج
    print("[*] النقر على تسجيل الخروج (540, 1730)...")
    d.shell("input tap 540 1730")
    time.sleep(1.5)

    # تأكيد الخروج
    for txt in ["نعم", "تأكيد", "ديكأت", "موافق", "Yes", "Confirm", "Logout"]:
        btn_confirm = d(textContains=txt)
        if btn_confirm.exists:
            btn_confirm.click()
            break
    time.sleep(3)


def extract_field(p, keys):
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
            if clean_k == clean_s:
                return str(v).strip()
    return ""


@app.get("/api/status")
def get_status():
    return {"status": "ready"}


@app.post("/api/register")
def execute_workflow(req: RegisterRequest):
    p = req.pilgrim

    # حرفين فقط للاسم
    dummy_name = "Ab"

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
        or req.client_email
    )
    password_val = (
        extract_field(
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

    w, h = d.window_size()
    print(f"\n{'='*50}\n[+] بدء المعالجة بالاسم الرمزي: {dummy_name}")
    print(f"[*] الجواز: {passport_val} | التأشيرة: {visa_val}")

    try:
        # 1. شاشة الدخول والضغط على زر أنشئ حسابًا جديدًا بالإحداثيات
        print("[*] النقر على أنشئ حسابًا جديدًا بالإحداثيات...")
        d.shell("input tap 540 1767")
        time.sleep(1.2)
        d.shell("input tap 540 1725")
        time.sleep(2.5)

        # 2. ملء البيانات الأساسية
        inputs = d(className="android.widget.EditText")
        if len(inputs) < 3:
            d.shell("input tap 540 1725")
            time.sleep(2)
            inputs = d(className="android.widget.EditText")

        if len(inputs) >= 3:
            print("[*] كتابة البيانات الأساسية...")
            inputs[0].set_text(dummy_name)
            time.sleep(0.3)
            inputs[1].set_text(email_val)
            time.sleep(0.3)
            inputs[2].set_text(password_val)
            time.sleep(0.5)

            # إغلاق لوحة المفاتيح
            d.shell("input keyevent 111")
            time.sleep(0.8)

            # النقر على زر إنشاء الحساب
            print("[*] النقر على زر إنشاء الحساب (540, 1298)...")
            d.shell("input tap 540 1298")
            time.sleep(3.5)
        else:
            print("[!] خطأ: لم تظهر شاشة التسجيل!")
            return {"success": False, "status": "error", "error": "لم تظهر شاشة التسجيل"}

        # 3. إدخال كود OTP
        otp = fetch_nusuk_otp(req.client_email, req.client_pass, timeout=50)
        if not otp:
            return {
                "success": False,
                "status": "error",
                "error": "لم يتم استلام كود OTP",
            }

        # كتابة الكود
        d.shell("input tap 160 462")
        time.sleep(0.3)
        for _ in range(4):
            d.shell("input keyevent 67")
            time.sleep(0.1)

        for digit in str(otp):
            d.shell(f"input text {digit}")
            time.sleep(0.25)

        d.shell("input keyevent 111")

        # 4. انتظار 3 ثواني ثم 3 نقرات تنظيف أعلى اليمين
        print("[*] انتظار 3 ثواني بعد كتابة الـ OTP...")
        time.sleep(3)

        print("[*] تنفيذ 3 نقرات أعلى اليمين للتنظيف (1000, 100)...")
        for _ in range(3):
            d.shell("input tap 1000 100")
            time.sleep(0.6)

        # 5. الدخول للملف الشخصي ثم Active Permits ثم Complete Profile
        print("[*] النقر على الأفاتار أعلى اليسار (65, 101)...")
        d.shell("input tap 65 101")
        time.sleep(2.5)

        print("[*] النقر على Active Permits أسفل اليمين (807, 1786)...")
        d.shell("input tap 807 1786")
        time.sleep(2)

        print("[*] النقر على زر Complete Profile بالأسفل (540, 1793)...")
        d.shell("input tap 540 1793")
        time.sleep(2)

        # 6. اختيار نوع المستخدم: زائر دولي
        print("[*] اختيار زائر دولي (540, 886)...")
        d.shell("input tap 540 886")
        time.sleep(2)

        # 7. حقل الجنسية والبحث (يدعم الإعدادات من الواجهة أو الافتراضي تايلاند 195)
        nat_text = (
            req.nationality
            or req.nationality_text
            or req.search_text
            or p.get("nationality")
            or p.get("search_text")
            or "تايلاند"
        )
        nat_y = (
            req.nationality_y
            or req.option_y
            or req.choice_y
            or p.get("nationality_y")
            or p.get("option_y")
            or 195
        )
        nat_y = int(nat_y)

        print(f"[*] فتح حقل الجنسية والبحث عن ({nat_text}) ثم اختيار Y={nat_y}...")
        d.shell("input tap 540 491")
        time.sleep(1.8)

        # تحديد مربع البحث العلوي بدقة
        search_box = d(className="android.widget.EditText", textContains="بحث")
        if not search_box.exists:
            search_box = d(className="android.widget.EditText", textContains="Search")

        if search_box.exists:
            search_box.click()
            time.sleep(0.3)
            search_box.set_text(nat_text)
        else:
            edits = d(className="android.widget.EditText")
            if len(edits) > 0:
                top_edit = min(
                    edits, key=lambda el: el.info.get("bounds", {}).get("top", 9999)
                )
                top_edit.click()
                time.sleep(0.3)
                top_edit.set_text(nat_text)

        time.sleep(1.2)

        d.shell("input keyevent 111")
        time.sleep(0.8)

        print(f"[*] اختيار الخيار عند (540, {nat_y})...")
        d.shell(f"input tap 540 {nat_y}")
        time.sleep(0.8)

        d.shell("input tap 540 1850")  # زر التأكيد بالأسفل
        time.sleep(2)

        # 8. كتابة بيانات الجواز والتأشيرة
        all_inputs = d(className="android.widget.EditText")
        if len(all_inputs) >= 2:
            all_inputs[0].set_text(passport_val)
            time.sleep(0.4)
            all_inputs[1].set_text(visa_val)
            time.sleep(0.4)

        d.shell("input keyevent 111")
        time.sleep(0.8)

        # 9. الضغط على زر الحفظ النهائي
        print("[*] الضغط على زر الحفظ (540, 1040)...")
        d.shell("input tap 540 1040")
        time.sleep(3)

        # فحص رسائل الخطأ والتسجيل المسبق
        already_registered = False
        for _ in range(6):
            time.sleep(0.7)
            screen_dump = d.dump_hierarchy().lower()
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
            d.shell("input tap 540 1711")
            time.sleep(1.5)

            # نقرة تنظيف في الربع العلوي الآمن
            print("[*] نقرة تنظيف في الربع العلوي...")
            d.shell("input tap 540 300")
            time.sleep(1)

            return {
                "success": False,
                "status": "already_registered",
                "message": "البيانات مسجلة مسبقاً",
            }

        # 10. الحالة الناجحة: زر Continue Exploring ثم سهم الرجوع
        print("[*] الضغط على Continue Exploring (540, 1793)...")
        d.shell("input tap 540 1793")
        time.sleep(2)

        print("[*] الضغط على السهم أعلى اليمين للرجوع للرئيسية (1019, 91)...")
        d.shell("input tap 1019 91")
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

    uvicorn.run(app, host="127.0.0.1", port=8000)
