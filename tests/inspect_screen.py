import sys, io
import uiautomator2 as u2

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = u2.connect('127.0.0.1:5555')
print("App current:", d.app_current())
for el in d(className="android.widget.TextView"):
    t = el.info.get("text")
    if t:
        print(f"TextView: {t} -> {el.info.get('bounds')}")

for el in d(className="android.widget.Button"):
    t = el.info.get("text")
    print(f"Button: {t} -> {el.info.get('bounds')}")
