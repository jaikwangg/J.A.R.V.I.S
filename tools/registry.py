"""
tools/registry.py
─────────────────
LangChain tool registry — เพิ่ม/ลด tool ได้ง่าย
แต่ละ tool เป็น function ที่ LLM สามารถเรียกใช้ได้
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta

from langchain_core.tools import tool

from config.settings import Settings
from core.logger import get_logger

log = get_logger(__name__)


# ── Calendar (Apple EventKit via osascript) ───────────────────────────────

@tool
def get_calendar_events(days_ahead: int = 1) -> str:
    """ดูนัดหมายใน Apple Calendar วันนี้และวันข้างหน้า"""
    try:
        end_date = datetime.now() + timedelta(days=days_ahead)
        script = f"""
        set output to ""
        tell application "Calendar"
            set today to current date
            set endDate to current date
            set time of endDate to 86399
            set day of endDate to {end_date.day}
            set month of endDate to {end_date.month}
            set year of endDate to {end_date.year}
            repeat with c in calendars
                set evts to (events of c whose start date >= today and start date <= endDate)
                repeat with e in evts
                    set output to output & (summary of e) & " | " & ((start date of e) as string) & "\n"
                end repeat
            end repeat
        end tell
        return output
        """
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        events = result.stdout.strip()
        if not events:
            return "ไม่มีนัดหมายในช่วงเวลานี้"
        log.debug("calendar_fetched", lines=events.count("\n") + 1)
        return events
    except Exception as exc:
        log.error("calendar_fetch_failed", error=str(exc))
        return f"ไม่สามารถดึงข้อมูลปฏิทินได้: {exc}"


@tool
def add_calendar_event(title: str, start_time: str, duration_minutes: int = 60) -> str:
    """
    เพิ่มนัดหมายใน Apple Calendar
    start_time format: "YYYY-MM-DD HH:MM"
    """
    try:
        dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
        script = f"""
        tell application "Calendar"
            tell calendar "Home"
                make new event with properties {{
                    summary: "{title}",
                    start date: date "{dt.strftime('%A, %B %d, %Y at %I:%M:%S %p')}",
                    end date: date "{(dt + timedelta(minutes=duration_minutes)).strftime('%A, %B %d, %Y at %I:%M:%S %p')}"
                }}
            end tell
        end tell
        return "ok"
        """
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        if "ok" in result.stdout or result.returncode == 0:
            log.info("calendar_event_added", title=title, start=start_time)
            return f"เพิ่มนัดหมาย '{title}' เวลา {start_time} เรียบร้อยแล้ว"
        return f"ไม่สามารถเพิ่มนัดหมายได้: {result.stderr}"
    except Exception as exc:
        return f"เกิดข้อผิดพลาด: {exc}"


# ── Email (Gmail API) ─────────────────────────────────────────────────────

@tool
def get_unread_emails(max_results: int = 5) -> str:
    """ดูอีเมลที่ยังไม่ได้อ่าน (ต้องตั้งค่า Gmail API ก่อน)"""
    try:
        from integrations.gmail import GmailClient
        client = GmailClient()
        emails = client.get_unread(max_results=max_results)
        if not emails:
            return "ไม่มีอีเมลใหม่"
        result = "\n".join(
            f"- จาก: {e['from']} | เรื่อง: {e['subject']}" for e in emails
        )
        return result
    except ImportError:
        return "Gmail integration ยังไม่ได้ตั้งค่า"
    except Exception as exc:
        log.error("email_fetch_failed", error=str(exc))
        return f"ไม่สามารถดึงอีเมลได้: {exc}"


# ── Web Search (SearXNG) ──────────────────────────────────────────────────

@tool
def web_search(query: str) -> str:
    """ค้นหาข้อมูลจากอินเทอร์เน็ตผ่าน SearXNG (self-hosted)"""
    try:
        import httpx
        from config.settings import settings

        url = f"{settings.searxng_url}/search"
        r = httpx.get(
            url,
            params={"q": query, "format": "json", "language": "th"},
            timeout=10,
        )
        data = r.json()
        results = data.get("results", [])[:3]
        if not results:
            return "ไม่พบผลการค้นหา"
        summary = "\n".join(
            f"- {res.get('title', '')}: {res.get('content', '')[:150]}"
            for res in results
        )
        log.debug("web_search_done", query=query[:50], results=len(results))
        return summary
    except Exception as exc:
        log.error("web_search_failed", error=str(exc))
        return f"ค้นหาไม่สำเร็จ: {exc}"


# ── Current Time ──────────────────────────────────────────────────────────

@tool
def get_current_time() -> str:
    """บอกวันที่และเวลาปัจจุบัน"""
    now = datetime.now()
    thai_days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
    day = thai_days[now.weekday()]
    return f"วัน{day}ที่ {now.day}/{now.month}/{now.year + 543} เวลา {now.strftime('%H:%M')} น."


# ── Registry ──────────────────────────────────────────────────────────────

def get_all_tools(settings: Settings) -> list:
    """Return list ของ tools ทั้งหมดที่พร้อมใช้"""
    tools = [
        get_current_time,
        get_calendar_events,
        add_calendar_event,
        web_search,
    ]

    # Gmail เพิ่มเฉพาะถ้าตั้งค่าไว้
    if settings.gmail_credentials_path and settings.gmail_credentials_path.exists():
        tools.append(get_unread_emails)
        log.info("tool_gmail_enabled")

    log.info("tools_registered", count=len(tools), names=[t.name for t in tools])
    return tools
