import uiautomator2 as u2
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')
edits = d(className='android.widget.EditText')
print(f"Number of EditTexts: {len(edits)}")
for i, e in enumerate(edits):
    print(f"EditText #{i}: text='{e.info.get('text')}' bounds={e.info.get('bounds')}")

buttons = d(className='android.widget.Button')
print(f"Number of Buttons: {len(buttons)}")
for i, b in enumerate(buttons):
    print(f"Button #{i}: text='{b.info.get('text')}' bounds={b.info.get('bounds')}")
