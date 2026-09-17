import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uiautomator2 as u2

app = FastAPI()

# السماح للواجهة بالاتصال بالسيرفر
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# الاتصال بمحاكي LDPlayer
d = u2.connect()
d.set_fastinput_ime(True)


class Pilgrim(BaseModel):
    الاسم: str = ""
    البريد_الإلكتروني: str = ""
    الباسورد: str = ""
    رقم_الجواز: str = ""
    رقم_التأشيرة: str = ""


def fill_field(index, value, offset_y=45):
    label = d(className="android.widget.TextView")[index]
    b = label.info["bounds"]
    d.click(b["left"] + 50, b["bottom"] + offset_y)
    d.clear_text()
    d.send_keys(str(value))


@app.post("/api/register")
def register(p: dict):
    # تطابق مع أسماء الأعمدة في الإكسيل
    name = p.get("الاسم") or p.get("Name")
    email = p.get("البريد الإلكتروني") or p.get("Email")
    password = p.get("الباسورد") or p.get("Password") or "Msamy2006**"
    passport = p.get("رقم الجواز") or p.get("Passport")
    visa = p.get("رقم التأشيرة") or p.get("Visa")

    try:
        # 1. شاشة إنشاء الحساب
        fill_field(2, name)
        fill_field(3, email)
        fill_field(4, password)
        d(className="android.widget.TextView")[6].click()  # زر أنشئ حسابك
        time.sleep(2)

        # 2. خطوة الـ OTP
        # هنا التطبيق بينتظر الـ OTP أو إدخاله التلقائي
        time.sleep(5)

        # 3. الشاشة الرئيسية: الضغط على الروضة
        d(text="الروضة").click()
        time.sleep(1)

        # 4. بوب أب: أكمل الملف الشخصي
        d(text="أكمل الملف الشخصي").click()
        time.sleep(1)

        # 5. نوع الهوية: زائر دولي
        d(textContains="زائر دولي").click()
        time.sleep(1)

        # 6. شاشة استكمال البيانات: الجنسية مصر، الجواز، والتأشيرة
        # اختيار الجنسية (مصر)
        d(text="الجنسية").click()
        time.sleep(0.5)
        d.send_keys("مصر")
        d(text="مصر").click()

        # كتابة الجواز والتأشيرة
        d(textContains="جواز السفر").click()
        d.send_keys(passport)

        d(textContains="رقم التأشيرة").click()
        d.send_keys(visa)

        # زر تحقق من حسابك
        d(text="تحقّق من حسابك").click()
        time.sleep(2)

        return {"success": True}
    except Exception as e:
        print(f"Error: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
