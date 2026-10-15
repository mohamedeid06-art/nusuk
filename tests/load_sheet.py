import os
import openpyxl
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Search for latest pilgrims excel sheet in Downloads
downloads = os.path.expanduser('~/Downloads')
candidates = [
    os.path.join(downloads, 'بيانات_تأشيرات_العمرة_HYT30_39_معتمر.xlsx'),
    os.path.join(downloads, 'روضة 20 اكتوبر المحلة عدد 45_منسق.xlsx')
]

chosen_file = None
for c in candidates:
    if os.path.exists(c):
        chosen_file = c
        break

if not chosen_file:
    print("[ERROR] No Excel file found in Downloads.")
    sys.exit(1)

print(f"[EXCEL] Reading from: {chosen_file}")
wb = openpyxl.load_workbook(chosen_file, data_only=True)
sheet = wb.active
rows = list(sheet.iter_rows(values_only=True))

# Header is on row index 1 (row 2 in excel)
headers = [str(c).strip() if c is not None else '' for c in rows[1]]
print("[EXCEL] Headers:", headers)

pilgrims = []
for r in rows[2:]:
    if not any(r):
        continue
    d = dict(zip(headers, [str(c).strip() if c is not None else '' for c in r]))
    passport = d.get('رقم الجواز', '')
    visa = d.get('رقم التأشيرة', '')
    name = d.get('الاسم', '')
    email = d.get('البريد الإلكتروني', '')
    if passport or visa:
        pilgrims.append({
            'raw': d,
            'passport': passport,
            'visa': visa,
            'name': name,
            'email': email,
            'status': 'pending',
            'message': 'في الانتظار',
            'otp': '-'
        })

print(f"[OK] Total pilgrims loaded: {len(pilgrims)}")
for i, p in enumerate(pilgrims[:5]):
    print(f"  #{i+1}: {p['name']} | Passport: {p['passport']} | Visa: {p['visa']} | Email: {p['email']}")

active_payload = {
    'nusuk_active_email': 'agiad-ahmedsamy2026@gmail.com',
    'nusuk_active_pass': 'bcjo pmeg abds ofuh',
    'nusuk_account_pass': 'Msamy2006**',
    'nusuk_nat_text': 'تايلاند',
    'nusuk_nat_opt': '1',
    'pilgrimsList': pilgrims
}

with open('active_queue.json', 'w', encoding='utf-8') as out:
    json.dump(active_payload, out, ensure_ascii=False, indent=2)

print(f"[OK] Successfully saved {len(pilgrims)} pilgrims to active_queue.json")
