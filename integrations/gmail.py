"""
integrations/gmail.py
─────────────────────
Gmail API client
ตั้งค่าครั้งแรก:
  1. ไปที่ Google Cloud Console → สร้าง OAuth2 credentials
  2. Download credentials.json ไปไว้ใน project root
  3. ระบุ path ใน GMAIL_CREDENTIALS_PATH ใน .env
  4. รันครั้งแรก → browser จะเปิดให้ authorize
"""
from __future__ import annotations

from pathlib import Path

from core.logger import get_logger

log = get_logger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    # เพิ่ม gmail.send ถ้าต้องการส่งอีเมล (ไม่แนะนำเว้นแต่จำเป็น)
]


class GmailClient:
    def __init__(
        self,
        credentials_path: str | Path = "credentials.json",
        token_path: str | Path = "data/security/gmail_token.json",
    ) -> None:
        self._creds_path = Path(credentials_path)
        self._token_path = Path(token_path)
        self._service = self._authenticate()

    def _authenticate(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if self._token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self._token_path), _SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._creds_path), _SCOPES
                )
                creds = flow.run_local_server(port=0)

            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(creds.to_json())
            self._token_path.chmod(0o600)
            log.info("gmail_token_saved", path=str(self._token_path))

        service = build("gmail", "v1", credentials=creds)
        log.info("gmail_authenticated")
        return service

    def get_unread(self, max_results: int = 5) -> list[dict[str, str]]:
        """ดึงอีเมลที่ยังไม่ได้อ่าน"""
        try:
            msgs = (
                self._service.users()
                .messages()
                .list(userId="me", q="is:unread", maxResults=max_results)
                .execute()
                .get("messages", [])
            )

            emails = []
            for m in msgs:
                msg = (
                    self._service.users()
                    .messages()
                    .get(userId="me", id=m["id"], format="metadata",
                         metadataHeaders=["From", "Subject", "Date"])
                    .execute()
                )
                headers = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }
                emails.append({
                    "from": headers.get("From", "Unknown"),
                    "subject": headers.get("Subject", "(ไม่มีหัวข้อ)"),
                    "date": headers.get("Date", ""),
                    "id": m["id"],
                })

            log.debug("gmail_fetched", count=len(emails))
            return emails

        except Exception as exc:
            log.error("gmail_fetch_failed", error=str(exc))
            return []
