import uiautomator2 as u2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')

print("Clicking تايلاند...")
if d(text="تايلاند").exists:
    d(text="تايلاند").click()
    time.sleep(1)

print("Clicking أكّد اختيارك...")
if d(text="أكّد اختيارك").exists:
    d(text="أكّد اختيارك").click()
    time.sleep(2)
else:
    d.shell("input tap 540 1850")
    time.sleep(2)

print("--- Screen after selecting nationality ---")
all_inputs = d(className="android.widget.EditText")
print(f"Number of EditTexts: {len(all_inputs)}")
for i, inp in enumerate(all_inputs):
    print(f"EditText #{i}: text='{inp.info.get('text')}' bounds={inp.info.get('bounds')}")

passport_val = "AD3567248"
visa_val = "6175360949"

if len(all_inputs) >= 2:
    print(f"Entering Passport: {passport_val}...")
    all_inputs[0].click()
    all_inputs[0].set_text(passport_val)
    time.sleep(0.4)
    print(f"Entering Visa: {visa_val}...")
    all_inputs[1].click()
    all_inputs[1].set_text(visa_val)
    time.sleep(0.4)

d.shell("input keyevent 111")
time.sleep(0.8)

print("Clicking تحقّق من حسابك / حفظ...")
if d(text="تحقّق من حسابك").exists:
    d(text="تحقّق من حسابك").click()
elif d(className="android.widget.Button", bounds__top=966).exists:
    d(className="android.widget.Button", bounds__top=966).click()
else:
    d.shell("input tap 540 1040")

time.sleep(3)

print("--- Screen After Final Submit ---")
for e in d(classNameMatches='.*(TextView|EditText|Button).*'):
    t = e.info.get("text")
    cls = e.info.get("className")
    b = e.info.get("bounds")
    if t:
        print(f"[{cls}] text='{t}' bounds={b}")
