import uiautomator2 as u2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')

print("Pressing back button...")
d.press("back")
time.sleep(2)

print("--- Screen after Back ---")
for e in d(classNameMatches='.*(TextView|Button).*'):
    t = e.info.get("text")
    if t:
        print(f"[{e.info.get('className')}] text='{t}'")
