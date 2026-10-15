import requests
import json
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = "http://127.0.0.1:7410/api/register"

payload = {
    "client_email": "agiadmohamedahmed.samymoham2026@gmail.com",
    "client_pass": "bcjo pmeg abds ofuh",
    "nusuk_password": "Msamy2006**",
    "nationality": "تايلاند",
    "nationality_y": 195,
    "pilgrim": {
        "الاسم": "Ab",
        "email": "ag.iad.mohamedahmed.samymoham2026@gmail.com",
        "رقم الجواز": "AD3732542",
        "رقم التأشيرة": "6175360963",
        "nationality": "تايلاند"
    }
}

print(f"[*] Starting Registration Request for Adeelah Denadulmat...")
print(f"    Target Email: {payload['pilgrim']['email']}")
print(f"    Passport: {payload['pilgrim']['رقم الجواز']}")
print(f"    Visa: {payload['pilgrim']['رقم التأشيرة']}")

start = time.time()
try:
    res = requests.post(url, json=payload, timeout=180)
    print(f"\n[RESPONSE {res.status_code}] ({time.time() - start:.1f}s):")
    data = res.json()
    print(json.dumps(data, ensure_ascii=False, indent=2))
except Exception as e:
    print(f"[ERROR] {e}")
