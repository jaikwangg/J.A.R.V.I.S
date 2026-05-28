"""
scripts/enroll.py
─────────────────
ลงทะเบียนเสียงเจ้าของบ้าน
รัน: python -m scripts.enroll  หรือ  home-llm enroll
"""
from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config.prompts import ENROLL_SENTENCES
from config.settings import settings
from core.audio import AudioCapture
from core.logger import setup_logging
from core.security import SpeakerSecurity

setup_logging(settings.logs_dir)
console = Console()
app = typer.Typer()


def run_enrollment() -> None:
    audio_cap = AudioCapture(settings)
    security  = SpeakerSecurity(settings)

    if security.is_enrolled:
        overwrite = typer.confirm(
            "⚠️  มีข้อมูลเสียงอยู่แล้ว ต้องการลงทะเบียนใหม่หรือไม่?",
            default=False,
        )
        if not overwrite:
            console.print("[yellow]ยกเลิก[/yellow]")
            return
        security.clear_enrollment()

    console.print("\n[bold]🎤 ลงทะเบียนเสียงเจ้าของบ้าน[/bold]")
    console.print("กรุณาพูดประโยคต่อไปนี้ให้ชัดเจน (ห้องเงียบ ไม่มีเสียง rambo รบกวน)\n")

    samples = []
    sentences = ENROLL_SENTENCES

    for i, sentence in enumerate(sentences, start=1):
        console.print(f"  [{i}/{len(sentences)}] [cyan]{sentence}[/cyan]")
        console.print("  กด Enter เมื่อพร้อม...", end="")
        input()

        console.print("  [green]🔴 กำลังบันทึก...[/green]", end="\r")
        audio = audio_cap.record_utterance(max_duration=10.0)

        if audio is None or len(audio) == 0:
            console.print("  [red]❌ ไม่ได้ยินเสียง กรุณาลองอีกครั้ง[/red]")
            i -= 1
            continue

        duration = len(audio) / settings.audio.sample_rate
        console.print(f"  [green]✅ บันทึกได้ {duration:.1f} วินาที[/green]\n")
        samples.append(audio)
        time.sleep(0.5)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("กำลังประมวลผล embedding...", total=None)
        ok = security.enroll(samples)
        progress.remove_task(task)

    if ok:
        console.print("\n[bold green]✅ ลงทะเบียนสำเร็จ! ระบบพร้อมใช้งานแล้ว[/bold green]")
        console.print("รัน: [bold]python main.py start[/bold]")
    else:
        console.print("\n[red]❌ ลงทะเบียนไม่สำเร็จ กรุณาลองใหม่ในที่เงียบกว่านี้[/red]")


@app.command()
def main() -> None:
    run_enrollment()


if __name__ == "__main__":
    app()
