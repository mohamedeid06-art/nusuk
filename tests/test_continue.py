import uiautomator2 as u2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')

print("Clicking تابع واستكشف...")
if d(textContains="تابع واستكشف").exists:
    d(textContains="تابع واستكشف").click()
elif d(textContains="Continue").exists:
    d(textContains="Continue").click()
else:
    d.shell("input tap 540 1793")

time.sleep(2.5)

print("--- Screen after Continue Exploring ---")
for e in d(classNameMatches='.*(TextView|EditText|Button).*'):
    t = e.info.get("text")
    cls = e.info.get("className")
    b = e.info.get("bounds")
    if t:
        print(f"[{cls}] text='{t}' bounds={b}")
