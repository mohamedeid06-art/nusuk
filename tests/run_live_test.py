import requests
import json
import time

url = "http://127.0.0.1:7410/api/register"

# Load active queue
with open("active_queue.json", "r", encoding="utf-8") as f:
    queue_data = json.load(f)

pilgrim = queue_data["pilgrimsList"][0]

payload = {
    "client_email": queue_data.get("nusuk_active_email", "agiadmohamedahmed.samymoham2026@gmail.com"),
    "client_pass": queue_data.get("nusuk_active_pass", "bcjo pmeg abds ofuh"),
    "nusuk_password": queue_data.get("nusuk_account_pass", "Msamy2006**"),
    "nationality": queue_data.get("nusuk_nat_text", "تايلاند"),
    "nationality_y": int(queue_data.get("nusuk_nat_opt", "1")) == 2 and 275 or 195,
    "pilgrim": pilgrim
}

print(f"[*] Sending Registration Request for Pilgrim #1:")
print(f"    Name: {pilgrim.get('name')}")
print(f"    Passport: {pilgrim.get('passport')}")
print(f"    Visa: {pilgrim.get('visa')}")
print(f"    Email: {pilgrim.get('email')}")
print(f"    Client Email: {payload['client_email']}")

start = time.time()
try:
    res = requests.post(url, json=payload, timeout=120)
    print(f"\n[RESPONSE {res.status_code}] ({time.time() - start:.1f}s):")
    print(json.dumps(res.json(), ensure_ascii=False, indent=2))
except Exception as e:
    print(f"[ERROR] {e}")
