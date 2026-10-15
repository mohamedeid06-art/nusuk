import uiautomator2 as u2
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')
print("--- All elements below 900 ---")
for e in d(classNameMatches='.*(Button|TextView).*'):
    b = e.info.get("bounds", {})
    if b.get("top", 0) > 900:
        print(f"[{e.info.get('className')}] text='{e.info.get('text')}' bounds={b}")
