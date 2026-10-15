import uiautomator2 as u2
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')
d = u2.connect('127.0.0.1:5555')

print("Clicking verify button at (540, 1008)...")
d.click(540, 1008)
time.sleep(3)

print("--- Dump Hierarchy Text ---")
hierarchy = d.dump_hierarchy()
print("Hierarchy length:", len(hierarchy))
for line in hierarchy.splitlines():
    if any(k in line for k in ["text=", "content-desc="]):
        print(line.strip())
