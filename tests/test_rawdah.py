import uiautomator2 as u2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')

print("Clicking زائر دولي أو خليجي...")
if d(textContains="زائر دولي").exists:
    d(textContains="زائر دولي").click()
elif d(textContains="كافة الزوار").exists:
    d(textContains="كافة الزوار").click()
else:
    d.shell("input tap 540 886")

time.sleep(2)

print("--- Next Screen Elements ---")
for e in d(classNameMatches='.*(TextView|EditText|Button).*'):
    t = e.info.get("text")
    cls = e.info.get("className")
    b = e.info.get("bounds")
    if t:
        print(f"[{cls}] text='{t}' bounds={b}")
