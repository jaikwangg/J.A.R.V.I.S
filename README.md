# home-llm

Private local home assistant powered by Ollama, faster-whisper, local TTS,
speaker verification, memory, and LangChain tools.

## Project Layout

```text
home-llm/
├── setup.sh
├── main.py
├── .env.example
├── pyproject.toml
├── config/
│   ├── settings.py
│   └── prompts.py
├── core/
│   ├── security.py
│   ├── audio.py
│   ├── memory.py
│   └── logger.py
├── services/
│   ├── llm.py
│   ├── stt.py
│   ├── tts.py
│   └── wake_word.py
├── tools/
│   └── registry.py
├── integrations/
│   └── gmail.py
└── scripts/
    └── enroll.py
```

## Security Design

- Speaker embedding เข้ารหัสด้วย Fernet ก่อนบันทึก และตั้ง permission เป็น `chmod 600`
- ไม่บันทึก raw audio ลง disk เด็ดขาด
- Lockout หลังยืนยันเสียงผิดครบ 3 ครั้ง
- `.env` และ `data/security/` อยู่ใน `.gitignore`

Runtime data, logs, encryption keys, and speaker embeddings are stored under
`data/` and are ignored by git.

## วิธีเริ่มใช้งาน

```bash
# 1. ตั้งค่า
chmod +x setup.sh && ./setup.sh

# 2. ลงทะเบียนเสียง
source .venv/bin/activate
python main.py enroll

# 3. เปิดใช้งาน
python main.py start

# 4. ทดสอบแบบ text (ไม่มี mic)
python main.py start --text
```

After editable install, the CLI command is also available:

```bash
home-llm enroll
home-llm start --text
```
