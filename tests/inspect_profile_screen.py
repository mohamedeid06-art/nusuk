import uiautomator2 as u2
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')
print("--- All Elements on Nationality/Passport Screen ---")
for el in d(classNameMatches=".*"):
    info = el.info
    cls = info.get("className", "")
    t = info.get("text", "")
    desc = info.get("contentDescription", "")
    b = info.get("bounds", "")
    if any(k in cls for k in ["EditText", "Button", "TextView", "Spinner"]):
        print(f"[{cls}] text='{t}' desc='{desc}' bounds={b}")
