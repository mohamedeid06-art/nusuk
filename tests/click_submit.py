import uiautomator2 as u2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')
print("Clicking submit button at (540, 1138)...")
d.click(540, 1138)
time.sleep(3)
print("--- Screen Elements After Submit ---")
for e in d(classNameMatches='.*(TextView|EditText|Button).*'):
    t = e.info.get("text")
    cls = e.info.get("className")
    if t:
        print(f"[{cls}] {t}")
