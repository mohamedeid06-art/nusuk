import uiautomator2 as u2
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')
print("--- Clickable Views ---")
for e in d(clickable=True):
    print(f"[{e.info.get('className')}] text=\"{e.info.get('text')}\" desc=\"{e.info.get('contentDescription')}\" bounds={e.info.get('bounds')}")
