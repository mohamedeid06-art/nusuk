import time
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
import uiautomator2 as u2

app = FastAPI(title="Nusuk ERP & Automation Pro Server")

# ميدلوير شامل لدعم CORS و Private Network Access لجميع المتصفحات (بما فيها Chrome عبر HTTPS / GitHub Pages)
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

# الاتصال بمحاكي LDPlayer بأمان دون تعطيل السيرفر في حال تأخر تشغيل المحاكي
d = None

def get_device():
    global d
    if d is not None:
        return d
    try:
        d = u2.connect()
        return d
    except Exception as e:
        print(f"⚠️ تنبيه: محاكي LDPlayer غير متصل حالياً: {e}")
        return None

def fill_field(index, value, offset_y=45):
    device = get_device()
    if not device:
        raise RuntimeError("محاكي LDPlayer غير متصل! يرجى تشغيل المحاكي والتأكد من فتح تطبيق نسك.")
    label = device(className="android.widget.TextView")[index]
    b = label.info["bounds"]
    device.click(b["left"] + 50, b["bottom"] + offset_y)
    device.clear_text()
    device.send_keys(str(value))

# نقطة فحص حالة السيرفر للتأكد من اتصاله مع الواجهة
@app.get("/api/status")
@app.head("/api/status")
@app.options("/api/status")
def check_status():
    device = get_device()
    return {
        "status": "ready",
        "online": True,
        "device_connected": device is not None,
        "message": "السيرفر متصل وجاهز لاستقبال طلبات الأتمتة"
    }

@app.get("/")
def home():
    return {
        "status": "online",
        "app": "Nusuk ERP & Automation Pro Local Server",
        "version": "2.0"
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

    device = get_device()
    if not device:
        return {"success": False, "status": "error", "error": "محاكي LDPlayer غير متصل! يرجى فتح المحاكي أولاً."}

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
        device(text=nationality).click()

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
