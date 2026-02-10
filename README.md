# Clawdbot - Secure Browser Automation Bot

Clawdbot เป็น Telegram bot สำหรับ browser automation ที่ออกแบบมาให้ **ปลอดภัย** และ **ปรับแต่งง่าย**

## 🔒 หลักการความปลอดภัย

- **Config-driven**: แก้ไฟล์ config ได้ ไม่ต้องแก้โค้ดบ่อย
- **Allowlist + Least privilege**: มีสิทธิ์เฉพาะคน/เฉพาะคำสั่ง
- **Two-step confirm**: สำหรับ action เสี่ยง (submit/จ่ายเงิน/ลบ)
- **Sandbox profile**: Chrome profile แยก
- **Audit & Logs**: ย้อนดูว่า bot ทำอะไรไป

## 🚀 การติดตั้ง

### 1. สร้าง Virtual Environment
```cmd
mkdir clawdbot
cd clawdbot
python -m venv .venv
.venv\Scripts\activate
```

### 2. ติดตั้ง Dependencies
```cmd
pip install -r requirements.txt
python -m playwright install chromium
```

### 3. ตั้งค่า Bot Token
1. สร้าง bot ใหม่กับ [@BotFather](https://t.me/BotFather)
2. แก้ไข `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_USER_IDS=your_user_id_here
```

### 4. ตั้งค่า User ID
- หา User ID ของคุณจาก [@userinfobot](https://t.me/userinfobot)
- เพิ่มใน `config/settings.yaml`:
```yaml
security:
  allow_user_ids: [123456789]  # ใส่ User ID ของคุณ
```

### 5. รัน Bot
```cmd
python bot.py
```

## 📋 คำสั่งที่ใช้ได้

- `/start` - เริ่มต้นใช้งาน
- `/run <macro>` - รัน macro
- `/list` - ดู macro ที่มี
- `/status` - สถานะ bot
- `/shot` - ถ่าย screenshot
- `/stop` - หยุดงานปัจจุบัน
- `/confirm <job_id>` - ยืนยัน action เสี่ยง

## 🔧 การปรับแต่ง

### เพิ่ม Macro ใหม่
1. สร้างไฟล์ `macros/your_macro.py`
2. เพิ่มใน `config/macros.yaml`
3. Restart bot

### เปลี่ยนเป็น Chrome Profile
แก้ไข `config/settings.yaml`:
```yaml
chrome:
  mode: "profile"
  chrome_exe: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
  user_data_dir: "C:\\Users\\YOURNAME\\AppData\\Local\\Google\\Chrome\\User Data"
  profile_dir: "Profile 2"
```

## 📁 โครงสร้างโปรเจกต์

```
clawdbot/
├── bot.py              # Main bot file
├── config/
│   ├── settings.yaml   # การตั้งค่าหลัก
│   └── macros.yaml     # การตั้งค่า macro
├── engine/
│   ├── runner.py       # Core execution engine
│   └── safety.py       # Security manager
├── macros/
│   └── demo_google.py  # ตัวอย่าง macro
├── utils/
│   ├── logging.py      # Logging utilities
│   └── screenshot.py   # Screenshot utilities
├── out/                # Screenshots, logs
├── .env                # Secrets only
└── requirements.txt
```

## ⚠️ ข้อควรระวัง

1. **อย่าใส่ token ใน git**
2. **ใช้ Chrome profile แยก**
3. **ตรวจสอบ macro ก่อนรัน**
4. **เปิด confirm สำหรับ action เสี่ยง**
5. **เก็บ log ไว้ตรวจสอบ**

## 🛡️ Security Checklist

- [ ] Bot token อยู่ใน `.env` ไม่หลุด git
- [ ] มี allowlist user id แล้ว
- [ ] มี `/stop` ใช้งานได้จริง
- [ ] Macro เสี่ยงทุกตัว require confirm
- [ ] Chrome profile แยกเรียบร้อย
- [ ] Logging + screenshot เก็บลง `out/`

## 📞 การแก้ปัญหา

### Bot ไม่ตอบ
1. ตรวจสอบ token ใน `.env`
2. ตรวจสอบ User ID ใน allowlist
3. ดู log ใน `out/clawdbot.log`

### Browser ไม่เปิด
1. ตรวจสอบ Playwright ติดตั้งแล้ว
2. ลอง `python -m playwright install chromium`
3. เปลี่ยน `headless: false` ใน settings

### Macro ไม่ทำงาน
1. ตรวจสอบ enabled ใน `macros.yaml`
2. ดู error ใน log
3. ลองรัน `/shot` ดู screenshot