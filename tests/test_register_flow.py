import time
import sys
import uiautomator2 as u2
import server

sys.stdout.reconfigure(encoding='utf-8')
device = u2.connect('127.0.0.1:5555')

name = "Abibah Chesoh"
# Use a fresh dot alias of agiadmohamedahmed.samymoham2026@gmail.com
email = "ag.iad.mohamed.ahmed.samymoham2026@gmail.com"
password = "Msamy2006**"
passport = "AD3567248"
visa = "6175360949"
nationality = "تايلاند"

print(f"--- Testing Registration for {name} ({email}) ---")

# Step 1: Check form
edits = device(className="android.widget.EditText")
print(f"Found {len(edits)} EditTexts on screen.")
if len(edits) >= 3:
    print("Filling Name...")
    edits[0].click()
    edits[0].set_text(name)
    time.sleep(0.3)
    
    print("Filling Email...")
    edits[1].click()
    edits[1].set_text(email)
    time.sleep(0.3)
    
    print("Filling Password...")
    edits[2].click()
    try:
        device.clear_text()
    except Exception:
        pass
    edits[2].set_text(password)
    time.sleep(0.5)

print("Clicking Submit ('أنشئ حسابك')...")
submit_btn = None
for btn in device(className="android.widget.Button"):
    b = btn.info["bounds"]
    if b["top"] > 700:
        submit_btn = btn
        break

if submit_btn:
    submit_btn.click()
    print("Clicked submit button via Button element.")
else:
    device(text="أنشئ حسابك").click()
    print("Clicked submit button via text.")

time.sleep(3)

print("--- Screen After Submit ---")
for el in device(classNameMatches=".*(TextView|Button|EditText).*"):
    t = el.info.get("text", "")
    cls = el.info.get("className", "")
    b = el.info.get("bounds", "")
    if t:
        print(f"[{cls}] text=\"{t}\" bounds={b}")
