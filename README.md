# 🏠 Home LLM — Personal Assistant

Voice-first personal assistant รัน **100% local** บน Apple Silicon Mac  
ไม่มีข้อมูลออกไปยัง internet เลย (ยกเว้น SearXNG web search ที่ self-host)

---

## Stack

| Layer | Technology |
|---|---|
| LLM | Ollama + llama3.2:3b / mistral:7b (Metal GPU) |
| STT | faster-whisper (int8, รองรับภาษาไทย) |
| TTS | macOS `say` (built-in) หรือ Kokoro ONNX |
| Wake Word | openwakeword + energy fallback |
| Speaker ID | Resemblyzer (cosine similarity) |
| Memory | deque (short-term) + ChromaDB (long-term) |
| Security | Fernet encryption + lockout |
| Config | Pydantic-Settings v2 |

---

## Quick Start

```bash
# 1. Setup ทุกอย่างครั้งเดียว
chmod +x setup.sh && ./setup.sh

# 2. ลงทะเบียนเสียง
source .venv/bin/activate
python main.py enroll

# 3. เปิดใช้งาน (voice mode)
python main.py start

# 4. ทดสอบแบบ text (ไม่ใช้ mic)
python main.py start --text

# 5. ดู microphone ที่มี
python main.py devices
```

---

## Project Structure

```
home-llm/
├── main.py                  # Entry point + CLI
├── setup.sh                 # One-shot installer
├── .env.example             # Config template
├── pyproject.toml           # Dependencies
│
├── config/
│   ├── settings.py          # Pydantic v2 settings (flat keys)
│   └── prompts.py           # System prompts (TH/EN)
│
├── core/
│   ├── audio.py             # Mic recording + VAD
│   ├── logger.py            # Structured logging
│   ├── memory.py            # Short-term + ChromaDB
│   └── security.py          # Speaker ID + Fernet encryption
│
├── services/
│   ├── llm.py               # Ollama + LangChain agent
│   ├── stt.py               # faster-whisper
│   ├── tts.py               # macOS say / Kokoro
│   └── wake_word.py         # openwakeword / energy fallback
│
├── tools/
│   └── registry.py          # LangChain tools (Calendar, Gmail, Search, Time)
│
├── integrations/
│   └── gmail.py             # Gmail OAuth2 client
│
├── scripts/
│   └── enroll.py            # Speaker enrollment CLI
│
└── tests/
    ├── test_settings.py
    ├── test_memory.py
    └── test_security.py
```

---

## Environment Variables (`.env`)

ดู `.env.example` สำหรับ key ทั้งหมด  
Key สำคัญ:

```
LLM_MODEL=llama3.2:3b
WAKE_WORD_ENABLED=true
SECURITY_VERIFY_SPEAKER=true
TTS_ENGINE=macos          # macos | kokoro
LANGUAGE=th
```

---

## Security

- Speaker embedding เข้ารหัสด้วย **Fernet** ก่อนบันทึกลง disk
- `data/security/` มี chmod 600
- ไม่บันทึก raw audio ลง disk
- `.env` และ `data/` อยู่ใน `.gitignore`
- Lockout หลัง failed attempts เกินกำหนด

---

## Gmail Integration (Optional)

1. ไปที่ [Google Cloud Console](https://console.cloud.google.com)
2. สร้าง OAuth2 credentials (Desktop app)
3. Download `credentials.json` ไว้ใน project root
4. ตั้ง `GMAIL_CREDENTIALS_PATH=credentials.json` ใน `.env`
5. รันครั้งแรก → browser เปิด authorize

---

## Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

---

## Next Steps

- [ ] Home Assistant integration (smart home control)
- [ ] Notification push (นัดหมายล่วงหน้า)
- [ ] Multi-user profiles
- [ ] Web dashboard (FastAPI)
