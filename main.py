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

from config.settings import Settings, settings
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


class HomeAssistant:
    def __init__(self, override_settings: Settings | None = None) -> None:
        self._settings = override_settings or settings

        console.print(Panel(
            f"[bold]🏠 {self._settings.assistant_name}[/bold] — Home LLM\n"
            f"Model: [cyan]{self._settings.llm_model}[/cyan]  "
            f"Lang: [cyan]{self._settings.language}[/cyan]  "
            f"Debug: [cyan]{self._settings.debug}[/cyan]",
            border_style="blue"
        ))

        self.audio    = AudioCapture(self._settings)
        self.stt      = STTService(self._settings)
        self.tts      = create_tts(self._settings)
        self.security = SpeakerSecurity(self._settings)
        self.memory   = MemoryManager(self._settings)
        self.llm      = LLMService(self._settings)
        self.tools    = get_all_tools(self._settings)
        self.detector = WakeWordDetector(self._settings)

        self._active   = threading.Event()
        self._shutdown = threading.Event()

    def _check_health(self) -> bool:
        console.print("[yellow]⏳ เชื่อมต่อ Ollama...[/yellow]")
        if not self.llm.health_check():
            console.print(
                "[red]❌ ไม่พบ Ollama หรือ model ที่ระบุ[/red]\n"
                f"   รัน: [bold]ollama serve[/bold]  แล้ว  "
                f"[bold]ollama pull {self._settings.llm_model}[/bold]"
            )
            return False
        console.print(f"[green]✅ Ollama พร้อม ({self._settings.llm_model})[/green]")
        if not self.security.is_enrolled:
            console.print("[yellow]⚠️  ยังไม่ได้ลงทะเบียนเสียง — รัน: python main.py enroll[/yellow]")
        return True

    def _on_wake_word(self) -> None:
        if self._active.is_set():
            return
        self._active.set()
        threading.Thread(target=self._handle_turn, daemon=True).start()

    def _handle_turn(self) -> None:
        try:
            self.tts.speak("ครับ", blocking=False)
            console.print("[cyan]🎤 กำลังฟัง...[/cyan]")
            audio = self.audio.record_utterance(max_duration=20.0)
            if audio is None or len(audio) == 0:
                return

            if not self.security.verify(audio):
                console.print("[red]🔒 ไม่รู้จักเสียง[/red]")
                self.tts.speak("ขออภัย ไม่รู้จักเสียงของคุณ")
                return

            text = self.stt.transcribe(audio)
            if not text:
                return
            console.print(f"[white]👤 คุณ:[/white] {text}")

            context = self.memory.search_similar(text, n_results=2)
            history = self.memory.get_history()

            if self.tools:
                reply = self.llm.chat_with_tools(text, self.tools, history)
            else:
                reply = self.llm.chat(text, history, context)

            console.print(f"[bold blue]🤖 {self._settings.assistant_name}:[/bold blue] {reply}")
            self.tts.speak(reply)
            self.memory.add(text, reply)

        except Exception as exc:
            log.error("turn_error", error=str(exc), exc_info=True)
            self.tts.speak("ขออภัย เกิดข้อผิดพลาด กรุณาลองใหม่")
        finally:
            self._active.clear()

    def run(self, voice_mode: bool = True) -> None:
        if not self._check_health():
            sys.exit(1)

        def _sig_handler(sig: int, frame: object) -> None:
            console.print("\n[yellow]⏹ กำลังปิดระบบ...[/yellow]")
            self._shutdown.set()
            self.detector.stop()
            self.tts.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        if voice_mode and self._settings.wake_word_enabled:
            console.print(
                f"[green]👂 กำลังฟัง wake word: "
                f"[bold]{self._settings.wake_word_phrase}[/bold][/green]"
            )
            self.tts.speak(f"{self._settings.assistant_name} พร้อมแล้วครับ", blocking=False)
            self.detector.start(on_detected=self._on_wake_word)
            self._shutdown.wait()
        else:
            # Text mode — FIX: ไม่ mutate settings object อีกต่อไป
            console.print("[yellow]Text mode — พิมพ์คำถาม หรือ 'quit' เพื่อออก[/yellow]")
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
                    console.print(f"[bold blue]{self._settings.assistant_name}:[/bold blue] {reply}")
                    self.memory.add(text, reply)
                except (EOFError, KeyboardInterrupt):
                    break


# ── CLI ───────────────────────────────────────────────────────────────────

@app.command()
def start(
    text: bool = typer.Option(False, "--text", "-t", help="ใช้ text mode แทน voice"),
) -> None:
    """เริ่ม Home Assistant"""
    HomeAssistant().run(voice_mode=not text)


@app.command()
def enroll() -> None:
    """ลงทะเบียนเสียงเจ้าของบ้าน"""
    from scripts.enroll import run_enrollment
    run_enrollment()


@app.command()
def devices() -> None:
    """แสดง microphone ที่มีทั้งหมด"""
    mics = AudioCapture.list_devices()
    if not mics:
        console.print("[yellow]ไม่พบ microphone[/yellow]")
        return
    for m in mics:
        console.print(f"  [{m['index']}] {m['name']}")


if __name__ == "__main__":
    app()
