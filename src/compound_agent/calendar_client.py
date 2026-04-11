import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
MAX_EVENTS = 8


class CalendarClient:
    def __init__(self, refresh_token, client_id, client_secret, calendar_id="primary"):
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        self.service = build("calendar", "v3", credentials=creds)
        self.calendar_id = calendar_id

    def get_today_events(self):
        now = datetime.now(KST)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._fetch_events(start, end)

    def get_tomorrow_events(self):
        now = datetime.now(KST)
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._fetch_events(start, end)

    def get_week_events(self, start_date, end_date):
        start = datetime.combine(start_date, datetime.min.time(), tzinfo=KST)
        end = datetime.combine(end_date, datetime.min.time(), tzinfo=KST) + timedelta(days=1)
        return self._fetch_events(start, end, max_results=50)

    def get_next_meeting(self):
        now = datetime.now(KST)
        try:
            result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=now.isoformat(),
                maxResults=1,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = result.get("items", [])
            if not events:
                return None
            return self._parse_event(events[0])
        except Exception as e:
            logger.error(f"Failed to get next meeting: {e}")
            return None

    def _fetch_events(self, start, end, max_results=MAX_EVENTS + 10):
        try:
            result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            all_events = [self._parse_event(e) for e in result.get("items", [])]
            total_count = len(all_events)
            return {
                "events": all_events[:MAX_EVENTS],
                "total_count": total_count,
            }
        except Exception as e:
            logger.error(f"Failed to fetch calendar events: {e}")
            return {"events": [], "total_count": 0}

    def _parse_event(self, event):
        start = event.get("start", {})
        end = event.get("end", {})
        attendees = event.get("attendees", [])
        return {
            "summary": event.get("summary", "(제목 없음)"),
            "start": start.get("dateTime") or start.get("date", ""),
            "end": end.get("dateTime") or end.get("date", ""),
            "all_day": "date" in start and "dateTime" not in start,
            "location": event.get("location", ""),
            "description": event.get("description", ""),
            "attendees": [a.get("email", "") for a in attendees if not a.get("self", False)],
            "meet_link": event.get("hangoutLink", ""),
        }
