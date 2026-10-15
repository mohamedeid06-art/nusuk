import sys
import uiautomator2 as u2

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')
print("Current app:", d.app_current())
print("--- UI Elements on Screen ---")
for el in d(classNameMatches=".*(TextView|Button|ImageView|EditText).*"):
    info = el.info
    text = info.get("text", "")
    desc = info.get("contentDescription", "")
    rid = info.get("resourceName", "")
    cls = info.get("className", "")
    bounds = info.get("bounds", "")
    if text or desc or rid:
        print(f"[{cls}] text='{text}' desc='{desc}' id='{rid}' bounds={bounds}")
