#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# setup.sh — Home LLM one-shot setup สำหรับ Apple Silicon Mac
# รัน: chmod +x setup.sh && ./setup.sh
# ─────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}ℹ ${NC}$*"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠️  $*${NC}"; }
error()   { echo -e "${RED}❌ $*${NC}"; exit 1; }
step()    { echo -e "\n${BOLD}── $* ──${NC}"; }

echo -e "${BOLD}"
echo "╔══════════════════════════════════════╗"
echo "║   🏠 Home LLM Setup — Apple Silicon  ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

# ── Check macOS + Apple Silicon ───────────────────────────────────────────
step "ตรวจสอบ system"

if [[ "$(uname)" != "Darwin" ]]; then
    error "script นี้ใช้กับ macOS เท่านั้น"
fi

ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    warn "ตรวจพบ Intel Mac — ประสิทธิภาพ LLM จะต่ำกว่า Apple Silicon"
else
    success "Apple Silicon detected ($ARCH)"
fi

# Python version check
PYTHON_MIN="3.11"
if ! command -v python3 &>/dev/null; then
    error "ไม่พบ Python 3 — ติดตั้งจาก https://python.org"
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"; then
    success "Python $PY_VER"
else
    error "ต้องการ Python $PYTHON_MIN+ (ปัจจุบัน: $PY_VER)"
fi

# ── Homebrew ──────────────────────────────────────────────────────────────
step "Homebrew"

if ! command -v brew &>/dev/null; then
    info "ติดตั้ง Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    success "Homebrew พร้อมแล้ว"
fi

# ── Ollama ────────────────────────────────────────────────────────────────
step "Ollama (Local LLM runtime)"

if ! command -v ollama &>/dev/null; then
    info "ติดตั้ง Ollama..."
    brew install ollama
else
    success "Ollama พร้อมแล้ว"
fi

# เลือก model ตาม RAM
TOTAL_RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
info "RAM ที่ตรวจพบ: ${TOTAL_RAM_GB}GB"

if [[ $TOTAL_RAM_GB -ge 16 ]]; then
    DEFAULT_MODEL="llama3.2:3b"
    ALT_MODEL="mistral:7b"
    info "แนะนำ: $DEFAULT_MODEL (เร็ว) หรือ $ALT_MODEL (แม่นกว่า)"
else
    DEFAULT_MODEL="llama3.2:1b"
    warn "RAM น้อยกว่า 16GB — ใช้ model ขนาดเล็ก: $DEFAULT_MODEL"
fi

# Start ollama service และ pull model
info "เริ่ม Ollama service..."
brew services start ollama 2>/dev/null || true
sleep 2

info "Downloading model: $DEFAULT_MODEL (อาจใช้เวลาสักครู่)"
ollama pull "$DEFAULT_MODEL" || warn "ไม่สามารถ pull model ได้ (ลองใหม่ทีหลัง)"

# ── PortAudio (ต้องใช้กับ sounddevice) ───────────────────────────────────
step "Audio dependencies"

brew install portaudio 2>/dev/null || true
success "PortAudio พร้อมแล้ว"

# ── Python Virtual Environment ────────────────────────────────────────────
step "Python virtual environment"

if [[ ! -d ".venv" ]]; then
    python3 -m venv .venv
    success "สร้าง .venv แล้ว"
else
    info ".venv มีอยู่แล้ว"
fi

source .venv/bin/activate
pip install --upgrade pip --quiet

# ── Python Dependencies ───────────────────────────────────────────────────
step "Python dependencies"

pip install -e ".[dev]" --quiet
success "Core dependencies ติดตั้งแล้ว"

# Optional: Kokoro TTS
read -rp $'\n🔊 ติดตั้ง Kokoro TTS (คุณภาพสูงกว่า macOS say, ~200MB)? [y/N] ' install_kokoro
if [[ "$install_kokoro" =~ ^[Yy]$ ]]; then
    pip install -e ".[tts-kokoro]" --quiet
    success "Kokoro TTS ติดตั้งแล้ว"
fi

# Optional: Wake word
read -rp $'\n🎤 ติดตั้ง OpenWakeWord (wake word detection, ~50MB)? [y/N] ' install_ww
if [[ "$install_ww" =~ ^[Yy]$ ]]; then
    pip install -e ".[wake-word]" --quiet
    success "OpenWakeWord ติดตั้งแล้ว"
fi

# ── Environment Config ────────────────────────────────────────────────────
step "Environment configuration"

if [[ ! -f ".env" ]]; then
    cp .env.example .env
    # อัปเดต model ให้ตรงกับที่เลือก
    sed -i '' "s/LLM__MODEL=.*/LLM__MODEL=$DEFAULT_MODEL/" .env
    success ".env สร้างแล้ว จาก .env.example"
    info "แก้ไขค่าใน .env ตามต้องการก่อนรัน"
else
    warn ".env มีอยู่แล้ว — ไม่ได้ override"
fi

# ── Data Directories ──────────────────────────────────────────────────────
step "สร้าง directories"

mkdir -p data/{security,memory,logs}
chmod 700 data/security
success "directories พร้อมแล้ว"

# ── Faster Whisper Model Pre-download ────────────────────────────────────
step "Pre-download Whisper model"

info "โหลด faster-whisper 'small' model (ใช้ครั้งแรกเท่านั้น)..."
python3 -c "
from faster_whisper import WhisperModel
m = WhisperModel('small', device='cpu', compute_type='int8')
print('Whisper model ready')
" && success "Whisper model ready" || warn "Whisper model จะ download อัตโนมัติตอนรันครั้งแรก"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║   ✅ Setup เสร็จสมบูรณ์!                  ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"
echo "ขั้นตอนถัดไป:"
echo ""
echo "  1. ลงทะเบียนเสียง:"
echo "     ${CYAN}source .venv/bin/activate && python main.py enroll${NC}"
echo ""
echo "  2. เริ่มใช้งาน:"
echo "     ${CYAN}python main.py start${NC}"
echo ""
echo "  3. ทดสอบแบบ text mode (ไม่ใช้ mic):"
echo "     ${CYAN}python main.py start --text${NC}"
echo ""
echo "  4. ดู microphone ที่มี:"
echo "     ${CYAN}python main.py devices${NC}"
echo ""
echo -e "${YELLOW}หมายเหตุ: แก้ไขค่าต่างๆ ใน .env ก่อนเริ่มใช้งาน${NC}"
