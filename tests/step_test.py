import time
import sys
import uiautomator2 as u2

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')

if d(text="أنشئ حسابًا جديدًا").exists:
    print("Clicking 'أنشئ حسابًا جديدًا'...")
    d(text="أنشئ حسابًا جديدًا").click()
    time.sleep(2)

print("--- Registration Form Elements ---")
for el in d(classNameMatches=".*(TextView|Button|EditText).*"):
    t = el.info.get("text", "")
    d_desc = el.info.get("contentDescription", "")
    cls = el.info.get("className", "")
    bounds = el.info.get("bounds", "")
    hint = el.info.get("hint", "")
    print(f"[{cls}] text=\"{t}\" desc=\"{d_desc}\" hint=\"{hint}\" bounds={bounds}")
