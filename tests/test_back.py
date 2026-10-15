import uiautomator2 as u2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')

print("Clicking Back Arrow (1019, 91)...")
d.shell("input tap 1019 91")
time.sleep(2)

print("--- Screen after Back Arrow ---")
for e in d(classNameMatches='.*(TextView|Button).*'):
    t = e.info.get("text")
    b = e.info.get("bounds")
    if t:
        print(f"[{e.info.get('className')}] text='{t}' bounds={b}")
