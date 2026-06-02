"""
tools/registry.py — LangChain tools: Calendar, Email, Web Search, Time, Notes, Reminder
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta

from langchain_core.tools import tool

from config.settings import Settings, settings as _global_settings
from core.logger import get_logger

log = get_logger(__name__)

# Reminder service inject จาก main ตอน runtime
_reminder_service = None

from services.reminder import ReminderService as _RS

def set_reminder_service(svc: "_RS") -> None:
    global _reminder_service
    _reminder_service = svc


# ── Time ──────────────────────────────────────────────────────────────────

@tool
def get_current_time() -> str:
    """บอกวันที่และเวลาปัจจุบัน"""
    now  = datetime.now()
    days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
    return f"วัน{days[now.weekday()]}ที่ {now.day}/{now.month}/{now.year + 543} เวลา {now.strftime('%H:%M')} น."


# ── Calendar ──────────────────────────────────────────────────────────────

@tool
def get_calendar_events(days_ahead: int = 1) -> str:
    """ดูนัดหมายใน Apple Calendar วันนี้และวันข้างหน้า"""
    try:
        end    = datetime.now() + timedelta(days=days_ahead)
        script = f"""
        set output to ""
        tell application "Calendar"
            set today to current date
            set endDate to current date
            set time of endDate to 86399
            set day of endDate to {end.day}
            set month of endDate to {end.month}
            set year of endDate to {end.year}
            repeat with c in calendars
                set evts to (events of c whose start date >= today and start date <= endDate)
                repeat with e in evts
                    set output to output & (summary of e) & " | " & ((start date of e) as string) & "\\n"
                end repeat
            end repeat
        end tell
        return output
        """
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "ไม่มีนัดหมายในช่วงเวลานี้"
    except Exception as exc:
        log.error("calendar_fetch_failed", error=str(exc))
        return f"ไม่สามารถดึงข้อมูลปฏิทินได้: {exc}"


@tool
def add_calendar_event(title: str, start_time: str, duration_minutes: int = 60) -> str:
    """เพิ่มนัดหมายใน Apple Calendar, start_time format: 'YYYY-MM-DD HH:MM'"""
    try:
        dt     = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
        end_dt = dt + timedelta(minutes=duration_minutes)
        fmt    = "%A, %B %d, %Y at %I:%M:%S %p"
        script = f"""
        tell application "Calendar"
            tell calendar "Home"
                make new event with properties {{summary: "{title}", start date: date "{dt.strftime(fmt)}", end date: date "{end_dt.strftime(fmt)}"}}
            end tell
        end tell
        return "ok"
        """
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if "ok" in r.stdout or r.returncode == 0:
            log.info("calendar_event_added", title=title)
            return f"เพิ่มนัดหมาย '{title}' เวลา {start_time} เรียบร้อยแล้ว"
        return f"ไม่สามารถเพิ่มนัดหมายได้: {r.stderr}"
    except Exception as exc:
        return f"เกิดข้อผิดพลาด: {exc}"


# ── Reminder ──────────────────────────────────────────────────────────────

@tool
def set_reminder(message: str, delay_minutes: float) -> str:
    """
    ตั้ง reminder แบบ one-shot
    เช่น "เตือนฉันเรื่องประชุมอีก 30 นาที"
    delay_minutes: จำนวนนาทีที่จะรอก่อนแจ้งเตือน
    """
    if _reminder_service is None:
        return "Reminder service ยังไม่พร้อม"
    if delay_minutes <= 0:
        return "กรุณาระบุเวลาที่มากกว่า 0 นาที"
    _reminder_service.add_manual_reminder(message, delay_minutes)
    log.info("reminder_tool_set", message=message[:50], delay_min=delay_minutes)
    return f"ตั้งเตือน '{message}' ไว้แล้ว อีก {int(delay_minutes)} นาทีจะแจ้งเตือนครับ"


# ── Apple Notes ───────────────────────────────────────────────────────────

@tool
def create_note(title: str, content: str) -> str:
    """
    สร้าง note ใหม่ใน Apple Notes
    ใช้เมื่อผู้ใช้บอกว่า 'จดไว้ให้หน่อย' หรือ 'บันทึกเรื่องนี้'
    """
    try:
        from integrations.apple_notes import AppleNotesClient
        ok = AppleNotesClient().create_note(title=title, body=content)
        if ok:
            return f"จดโน้ต '{title}' เรียบร้อยแล้วครับ"
        return "ไม่สามารถสร้างโน้ตได้ กรุณาตรวจสอบว่าเปิดแอป Notes ไว้"
    except Exception as exc:
        return f"เกิดข้อผิดพลาด: {exc}"


@tool
def append_to_note(title: str, text: str) -> str:
    """
    เพิ่มข้อความต่อท้าย note ที่มีอยู่แล้ว
    ถ้าไม่พบ note ชื่อนั้น จะสร้างใหม่ให้อัตโนมัติ
    """
    try:
        from integrations.apple_notes import AppleNotesClient
        ok = AppleNotesClient().append_to_note(title=title, text=text)
        if ok:
            return f"เพิ่มข้อความใน '{title}' เรียบร้อยแล้วครับ"
        return "ไม่สามารถเพิ่มข้อความได้"
    except Exception as exc:
        return f"เกิดข้อผิดพลาด: {exc}"


@tool
def search_notes(query: str) -> str:
    """ค้นหาโน้ตที่มีคำที่ต้องการ"""
    try:
        from integrations.apple_notes import AppleNotesClient
        notes = AppleNotesClient().search_notes(query, max_results=5)
        if not notes:
            return f"ไม่พบโน้ตที่เกี่ยวกับ '{query}'"
        return "\n".join(
            f"- {n.title}: {n.body[:100]}{'...' if len(n.body) > 100 else ''}"
            for n in notes
        )
    except Exception as exc:
        return f"ค้นหาไม่สำเร็จ: {exc}"


@tool
def get_recent_notes() -> str:
    """ดูโน้ตล่าสุด 5 รายการ"""
    try:
        from integrations.apple_notes import AppleNotesClient
        notes = AppleNotesClient().get_recent_notes(max_results=5)
        if not notes:
            return "ไม่พบโน้ต"
        return "\n".join(f"- {n.title} (แก้ไขล่าสุด: {n.modified})" for n in notes)
    except Exception as exc:
        return f"เกิดข้อผิดพลาด: {exc}"


# ── Email ─────────────────────────────────────────────────────────────────

@tool
def get_unread_emails(max_results: int = 5) -> str:
    """ดูอีเมลที่ยังไม่ได้อ่าน (ต้องตั้งค่า Gmail API ก่อน)"""
    try:
        from integrations.gmail import GmailClient
        emails = GmailClient().get_unread(max_results=max_results)
        if not emails:
            return "ไม่มีอีเมลใหม่"
        return "\n".join(f"- จาก: {e['from']} | เรื่อง: {e['subject']}" for e in emails)
    except ImportError:
        return "Gmail integration ยังไม่ได้ตั้งค่า"
    except Exception as exc:
        return f"ไม่สามารถดึงอีเมลได้: {exc}"


# ── Web Search ────────────────────────────────────────────────────────────

@tool
def web_search(query: str) -> str:
    """ค้นหาข้อมูลจากอินเทอร์เน็ตผ่าน SearXNG (self-hosted)"""
    try:
        import httpx
        r = httpx.get(
            f"{_global_settings.searxng_url}/search",
            params={"q": query, "format": "json", "language": "th"},
            timeout=10,
        )
        results = r.json().get("results", [])[:3]
        if not results:
            return "ไม่พบผลการค้นหา"
        return "\n".join(
            f"- {res.get('title', '')}: {res.get('content', '')[:150]}" for res in results
        )
    except Exception as exc:
        return f"ค้นหาไม่สำเร็จ: {exc}"


# ── Registry ──────────────────────────────────────────────────────────────

def get_all_tools(settings: Settings) -> list:
    """Return tools ที่พร้อมใช้ตาม config"""
    tools = [
        get_current_time,
        get_calendar_events,
        add_calendar_event,
        set_reminder,
        create_note,
        append_to_note,
        search_notes,
        get_recent_notes,
        web_search,
    ]
    if settings.gmail_credentials_path and settings.gmail_credentials_path.exists():
        tools.append(get_unread_emails)
        log.info("tool_gmail_enabled")

    log.info("tools_registered", count=len(tools), names=[t.name for t in tools])
    return tools
