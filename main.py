"""
main.py
───────
Main orchestrator — เชื่อม pipeline ทั้งหมด
Flow: Wake Word → Record → Speaker Verify → STT → LLM → TTS
"""
from __future__ import annotations

import signal
import sys
import threading

import typer
from rich.console import Console
from rich.panel import Panel

from config.settings import settings
from core.audio import AudioCapture
from core.logger import get_logger, setup_logging
from core.memory import MemoryManager
from core.security import SpeakerSecurity
from services.llm import LLMService
from services.stt import STTService
from services.tts import create_tts
from services.wake_word import WakeWordDetector
from tools.registry import get_all_tools

setup_logging(settings.logs_dir, debug=settings.debug)
log = get_logger("main")
console = Console()
app = typer.Typer(help="Home LLM Personal Assistant")


# ── Assistant Core ────────────────────────────────────────────────────────

class HomeAssistant:
    def __init__(self) -> None:
        console.print(Panel(
            f"[bold]🏠 {settings.assistant_name}[/bold] — Home LLM\n"
            f"Model: [cyan]{settings.llm.model}[/cyan]  "
            f"Lang: [cyan]{settings.language}[/cyan]  "
            f"Debug: [cyan]{settings.debug}[/cyan]",
            border_style="blue"
        ))

        # Init components
        self.audio    = AudioCapture(settings)
        self.stt      = STTService(settings)
        self.tts      = create_tts(settings)
        self.security = SpeakerSecurity(settings)
        self.memory   = MemoryManager(settings)
        self.llm      = LLMService(settings)
        self.tools    = get_all_tools(settings)
        self.detector = WakeWordDetector(settings)

        self._active   = threading.Event()  # True = กำลังฟัง utterance
        self._shutdown = threading.Event()

    # ── Health Check ──────────────────────────────────────────────────────

    def _check_health(self) -> bool:
        """ตรวจสอบ Ollama ก่อนเริ่ม"""
        console.print("[yellow]⏳ เชื่อมต่อ Ollama...[/yellow]")
        if not self.llm.health_check():
            console.print(
                "[red]❌ ไม่พบ Ollama หรือ model ที่ระบุ[/red]\n"
                f"   รัน: [bold]ollama serve[/bold]  แล้ว  "
                f"[bold]ollama pull {settings.llm.model}[/bold]"
            )
            return False
        console.print(f"[green]✅ Ollama พร้อม ({settings.llm.model})[/green]")

        if not self.security.is_enrolled:
            console.print(
                "[yellow]⚠️  ยังไม่ได้ลงทะเบียนเสียง — รัน: home-llm enroll[/yellow]"
            )
        return True

    # ── Pipeline ──────────────────────────────────────────────────────────

    def _on_wake_word(self) -> None:
        """Callback เมื่อ wake word ถูกตรวจพบ"""
        if self._active.is_set():
            return  # กำลังประมวลผลอยู่
        self._active.set()
        threading.Thread(target=self._handle_turn, daemon=True).start()

    def _handle_turn(self) -> None:
        """หนึ่ง turn ของการสนทนา"""
        try:
            # 1. เล่นเสียงตอบรับ
            self.tts.speak("ครับ", blocking=False)

            # 2. บันทึกเสียง
            console.print("[cyan]🎤 กำลังฟัง...[/cyan]")
            audio = self.audio.record_utterance(max_duration=20.0)
            if audio is None or len(audio) == 0:
                log.debug("turn_no_audio")
                return

            # 3. ยืนยันเสียงเจ้าของบ้าน
            if not self.security.verify(audio):
                console.print("[red]🔒 ไม่รู้จักเสียง[/red]")
                self.tts.speak("ขออภัย ไม่รู้จักเสียงของคุณ")
                return

            # 4. STT
            text = self.stt.transcribe(audio)
            if not text:
                log.debug("turn_empty_transcription")
                return
            console.print(f"[white]👤 คุณ:[/white] {text}")

            # 5. ค้นหา context จาก long-term memory
            context = self.memory.search_similar(text, n_results=2)

            # 6. LLM
            history = self.memory.get_history()
            if self.tools:
                reply = self.llm.chat_with_tools(text, self.tools, history)
            else:
                reply = self.llm.chat(text, history, context)

            console.print(f"[bold blue]🤖 {settings.assistant_name}:[/bold blue] {reply}")

            # 7. TTS
            self.tts.speak(reply)

            # 8. บันทึก memory
            self.memory.add(text, reply)

        except Exception as exc:
            log.error("turn_error", error=str(exc), exc_info=True)
            self.tts.speak("ขออภัย เกิดข้อผิดพลาด กรุณาลองใหม่")
        finally:
            self._active.clear()

    # ── Run ───────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Main loop"""
        if not self._check_health():
            sys.exit(1)

        # Graceful shutdown
        def _sig_handler(sig, frame):
            console.print("\n[yellow]⏹ กำลังปิดระบบ...[/yellow]")
            self._shutdown.set()
            self.detector.stop()
            self.tts.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        if settings.wake_word.enabled:
            console.print(
                f"[green]👂 กำลังฟัง wake word: "
                f"[bold]{settings.wake_word.phrase}[/bold][/green]"
            )
            self.tts.speak(f"{settings.assistant_name} พร้อมแล้วครับ", blocking=False)
            self.detector.start(on_detected=self._on_wake_word)
            self._shutdown.wait()  # Block until Ctrl+C
        else:
            # Text mode (สำหรับ debug / ไม่มี mic)
            console.print("[yellow]Wake word disabled — Text mode[/yellow]")
            while not self._shutdown.is_set():
                try:
                    text = input("You: ").strip()
                    if text.lower() in ("exit", "quit", "q"):
                        break
                    if not text:
                        continue
                    history = self.memory.get_history()
                    context = self.memory.search_similar(text)
                    reply = self.llm.chat(text, history, context)
                    console.print(f"[bold blue]{settings.assistant_name}:[/bold blue] {reply}")
                    self.memory.add(text, reply)
                except (EOFError, KeyboardInterrupt):
                    break


# ── CLI Commands ──────────────────────────────────────────────────────────

@app.command()
def start(
    text_mode: bool = typer.Option(False, "--text", "-t", help="ใช้ text mode แทน voice"),
) -> None:
    """เริ่ม Home Assistant"""
    if text_mode:
        settings.wake_word.enabled = False
    HomeAssistant().run()


@app.command()
def enroll() -> None:
    """ลงทะเบียนเสียงเจ้าของบ้าน"""
    from scripts.enroll import run_enrollment
    run_enrollment()


@app.command()
def devices() -> None:
    """แสดง microphone ที่มีทั้งหมด"""
    mics = AudioCapture.list_devices()
    for m in mics:
        console.print(f"  [{m['index']}] {m['name']}")


if __name__ == "__main__":
    app()
