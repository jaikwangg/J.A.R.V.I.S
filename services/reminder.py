"""
services/reminder.py
────────────────────
Background reminder service — poll calendar ทุก 60 วินาที
แจ้งเตือนด้วย TTS เมื่อนัดหมายใกล้ถึงตาม threshold ที่กำหนด

FIX-A: ย้าย Callable import ขึ้นบน ลบซ้ำ
FIX-D: ย้าย _parse_applescript_date ขึ้นมาก่อน class ที่ใช้
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)

POLL_INTERVAL = 60
NOTIFY_THRESHOLDS_MINUTES = [60, 30, 15, 5]


# ── Helpers (ต้องอยู่ก่อน class ที่ใช้) ──────────────────────────────────

def _parse_applescript_date(raw: str) -> datetime:
    """
    Parse AppleScript date string หลาย format
    เช่น 'Sunday, 1 June 2025 at 14:00:00'
         'Sunday, June 1, 2025 at 2:00:00 PM'
    """
    formats = [
        "%A, %d %B %Y at %H:%M:%S",
        "%A, %B %d, %Y at %I:%M:%S %p",
        "%A, %d %B %Y at %I:%M:%S %p",
        "%A, %B %d, %Y at %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {raw!r}")


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class CalendarEvent:
    title: str
    start: datetime
    event_id: str

    def minutes_until(self) -> float:
        return (self.start - datetime.now()).total_seconds() / 60


@dataclass
class ReminderState:
    fired: set[str] = field(default_factory=set)

    def mark(self, event_id: str, threshold_min: int) -> None:
        self.fired.add(f"{event_id}@{threshold_min}")

    def was_fired(self, event_id: str, threshold_min: int) -> bool:
        return f"{event_id}@{threshold_min}" in self.fired


# ── Service ───────────────────────────────────────────────────────────────

class ReminderService:
    def __init__(self, settings: Settings, tts_speak_fn: Callable[[str], None]) -> None:
        self._settings = settings
        self._speak    = tts_speak_fn
        self._state    = ReminderState()
        self._stop     = threading.Event()
        self._thread: threading.Thread | None = None
        log.info("reminder_service_init", thresholds=NOTIFY_THRESHOLDS_MINUTES)

    def _fetch_upcoming_events(self, hours_ahead: int = 2) -> list[CalendarEvent]:
        try:
            end = datetime.now() + timedelta(hours=hours_ahead)
            script = f"""
            set output to ""
            tell application "Calendar"
                set now to current date
                set endDate to current date
                set hours of endDate to {end.hour}
                set minutes of endDate to {end.minute}
                set day of endDate to {end.day}
                set month of endDate to {end.month}
                set year of endDate to {end.year}
                repeat with c in calendars
                    set evts to (events of c whose start date >= now and start date <= endDate)
                    repeat with e in evts
                        set output to output & (summary of e) & "|" & ((start date of e) as string) & "\\n"
                    end repeat
                end repeat
            end tell
            return output
            """
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=10)
            events: list[CalendarEvent] = []
            for line in r.stdout.strip().splitlines():
                if "|" not in line:
                    continue
                title_part, date_part = line.split("|", 1)
                title = title_part.strip()
                try:
                    start_dt = _parse_applescript_date(date_part.strip())
                    event_id = f"{title}_{start_dt.isoformat()}"
                    events.append(CalendarEvent(title=title, start=start_dt, event_id=event_id))
                except ValueError as exc:
                    log.debug("reminder_date_parse_failed", raw=date_part[:40], error=str(exc))
            log.debug("reminder_fetched_events", count=len(events))
            return events
        except Exception as exc:
            log.error("reminder_fetch_failed", error=str(exc))
            return []

    def _build_message(self, event: CalendarEvent, threshold_min: int) -> str:
        mins     = int(event.minutes_until())
        time_str = event.start.strftime("%H:%M")
        if threshold_min <= 5:
            return f"แจ้งเตือน! {event.title} เริ่มใน {mins} นาทีครับ"
        elif threshold_min <= 15:
            return f"อีก {mins} นาที มีนัด {event.title} เวลา {time_str} นะครับ"
        elif threshold_min <= 30:
            return f"เตือนล่วงหน้า {mins} นาที นัด {event.title} เวลา {time_str} ครับ"
        else:
            return f"วันนี้มีนัด {event.title} เวลา {time_str} นะครับ อีกประมาณ {mins} นาที"

    def _check_and_notify(self) -> None:
        for event in self._fetch_upcoming_events(hours_ahead=2):
            mins_left = event.minutes_until()
            if mins_left < 0:
                continue
            window = POLL_INTERVAL / 60 + 0.5
            for threshold in NOTIFY_THRESHOLDS_MINUTES:
                if threshold <= mins_left <= threshold + window:
                    if not self._state.was_fired(event.event_id, threshold):
                        msg = self._build_message(event, threshold)
                        log.info("reminder_firing", event=event.title,
                                 threshold_min=threshold, mins_left=round(mins_left, 1))
                        try:
                            self._speak(msg)
                        except Exception as exc:
                            log.error("reminder_speak_failed", error=str(exc))
                        self._state.mark(event.event_id, threshold)

    def _run(self) -> None:
        log.info("reminder_thread_started", poll_interval_s=POLL_INTERVAL)
        while not self._stop.is_set():
            try:
                self._check_and_notify()
            except Exception as exc:
                log.error("reminder_loop_error", error=str(exc))
            self._stop.wait(timeout=POLL_INTERVAL)
        log.info("reminder_thread_stopped")

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="reminder-service")
        self._thread.start()
        log.info("reminder_service_started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        log.info("reminder_service_stopped")

    def add_manual_reminder(self, message: str, delay_minutes: float) -> None:
        """ตั้ง one-shot reminder จากคำสั่งเสียง"""
        delay_s = delay_minutes * 60

        def _fire() -> None:
            time.sleep(delay_s)
            if not self._stop.is_set():
                log.info("manual_reminder_fired", message=message[:50])
                self._speak(message)

        threading.Thread(target=_fire, daemon=True, name="manual-reminder").start()
        log.info("manual_reminder_set", message=message[:50], delay_min=delay_minutes)
