import base64
import logging

from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
PROCESSED_LABEL = "digest-processed"


class GmailClient:
    def __init__(self, refresh_token, client_id, client_secret):
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        self.service = build("gmail", "v1", credentials=creds)
        self._ensure_label()

    def _ensure_label(self):
        labels = self.service.users().labels().list(userId="me").execute()
        for label in labels.get("labels", []):
            if label["name"] == PROCESSED_LABEL:
                self.label_id = label["id"]
                return

        label_body = {
            "name": PROCESSED_LABEL,
            "labelListVisibility": "labelHide",
            "messageListVisibility": "hide",
        }
        result = self.service.users().labels().create(userId="me", body=label_body).execute()
        self.label_id = result["id"]

    def get_unread_from_senders(self, senders):
        sender_queries = [f'from:"{s}"' for s in senders]
        query = f'is:unread -label:{PROCESSED_LABEL} ({" OR ".join(sender_queries)})'
        return self._fetch_messages(query)

    def get_unread_by_label(self, label_name):
        query = f"is:unread -label:{PROCESSED_LABEL} label:{label_name}"
        return self._fetch_messages(query)

    def _fetch_messages(self, query):
        results = self.service.users().messages().list(
            userId="me", q=query, maxResults=50
        ).execute()
        messages = results.get("messages", [])
        return [self._get_message_detail(m["id"]) for m in messages]

    def _get_message_detail(self, msg_id):
        msg = self.service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body = self._extract_body(msg["payload"])
        return {
            "id": msg_id,
            "threadId": msg.get("threadId", msg_id),
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }

    def _extract_body(self, payload):
        """Recursively extract text from MIME payload."""
        if "parts" in payload:
            # Prefer plain text, fallback to HTML
            plain = ""
            html = ""
            for part in payload["parts"]:
                mime = part.get("mimeType", "")
                if mime == "text/plain" and not plain:
                    data = part["body"].get("data", "")
                    if data:
                        plain = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                elif mime == "text/html" and not html:
                    data = part["body"].get("data", "")
                    if data:
                        raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                        html = self._html_to_text(raw)
                elif "parts" in part:
                    nested = self._extract_body(part)
                    if nested and not plain:
                        plain = nested
            return (plain or html).strip()

        data = payload.get("body", {}).get("data", "")
        if not data:
            return ""
        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        if payload.get("mimeType") == "text/html":
            return self._html_to_text(decoded).strip()
        return decoded.strip()

    def _html_to_text(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "head", "img"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)

    def count_by_query(self, query):
        """Count messages matching a Gmail query. Returns approximate count."""
        results = self.service.users().messages().list(
            userId="me", q=query, maxResults=1
        ).execute()
        return results.get("resultSizeEstimate", 0)

    def mark_processed(self, msg_ids):
        if not msg_ids:
            return
        self.service.users().messages().batchModify(
            userId="me",
            body={"ids": msg_ids, "addLabelIds": [self.label_id]},
        ).execute()
        logger.info(f"Marked {len(msg_ids)} emails as processed")
