"""Shared email and calendar service logic.

Extracted from main.py and hands.py to eliminate duplication.
"""
import logging
import re
from collections import OrderedDict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .briefing_composer import escape_html

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def normalize_subject(subject):
    """Remove Re:/Fwd:/FW: prefixes (including chained) and extra whitespace."""
    s = subject
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"^(?:Re|Fwd|FW|Fw)\s*:\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def group_by_thread(emails):
    """Group emails by threadId, then merge single-email threads with the same subject.

    Gmail assigns different threadIds to notification-style emails (e.g. incident
    updates) even when they share the same subject. This two-pass approach groups
    by threadId first, then consolidates single-message threads that share a
    normalized subject line.

    Emails within each group are sorted chronologically (oldest first).
    """
    # Pass 1: group by Gmail threadId
    threads = OrderedDict()
    for email in emails:
        tid = email["threadId"]
        if tid not in threads:
            threads[tid] = []
        threads[tid].append(email)

    # Pass 2: merge single-email threads with same normalized subject
    merged = OrderedDict()
    subject_key_map = {}  # normalized_subject -> first key in merged
    for tid, thread_emails in threads.items():
        if len(thread_emails) > 1:
            merged[tid] = thread_emails
        else:
            norm = normalize_subject(thread_emails[0]["subject"])
            if norm and norm in subject_key_map:
                merged[subject_key_map[norm]].extend(thread_emails)
            elif norm:
                subject_key_map[norm] = tid
                merged[tid] = thread_emails
            else:
                merged[tid] = thread_emails

    for key in merged:
        merged[key].sort(key=lambda e: e.get("date", ""))
    return merged


def format_email_part(subject, sender, summary_text, email_count=1):
    """Format a single email/thread summary as HTML. All inputs are raw (unescaped)."""
    count_label = f" ({email_count}건)" if email_count > 1 else ""
    return (
        f"\n<b>{escape_html(subject)}{count_label}</b>\n"
        f"<i>{escape_html(sender)}</i>\n\n"
        f"{escape_html(summary_text)}\n"
    )


# ---------------------------------------------------------------------------
# Service classes
# ---------------------------------------------------------------------------

class EmailService:
    def __init__(self, config, summarizer):
        self.config = config
        self.summarizer = summarizer

    def fetch_summaries(self) -> tuple:
        """Fetch and summarize unread emails from all configured accounts.

        Returns:
            (summaries, action_items, status)
        """
        from .gmail_client import GmailClient

        action_re = re.compile(self.config.action_pattern)
        summaries = []
        action_items = []
        status = {"gmail": True}

        # Personal newsletters
        if self.config.personal_gmail_refresh_token:
            try:
                gmail = GmailClient(
                    self.config.personal_gmail_refresh_token,
                    self.config.google_client_id,
                    self.config.google_client_secret,
                )
                emails = gmail.get_unread_from_senders(self.config.personal_senders)
                if emails:
                    personal_parts = []
                    processed_ids = []
                    threads = group_by_thread(emails)
                    for thread_emails in threads.values():
                        try:
                            if len(thread_emails) == 1:
                                e = thread_emails[0]
                                summary = self.summarizer.summarize_newsletter(
                                    e["subject"], e["body"], e["from"]
                                )
                            else:
                                summary = self.summarizer.summarize_newsletter_thread(
                                    thread_emails[0]["subject"], thread_emails
                                )
                            senders = ", ".join(dict.fromkeys(e["from"] for e in thread_emails))
                            personal_parts.append(
                                format_email_part(
                                    thread_emails[0]["subject"], senders,
                                    summary, len(thread_emails),
                                )
                            )
                            match = action_re.search(summary)
                            if match:
                                action_text = match.group(1).strip()
                                if action_text != self.config.none_value:
                                    action_items.append({
                                        "subject": thread_emails[0]["subject"],
                                        "action": action_text,
                                    })
                            processed_ids.extend(e["id"] for e in thread_emails)
                        except Exception as e:
                            tid = thread_emails[0].get("threadId", "unknown")
                            logger.error(
                                f"Summarize failed [thread={tid}, subject={thread_emails[0]['subject']}]: {e}"
                            )
                            processed_ids.extend(em["id"] for em in thread_emails)
                    gmail.mark_processed(processed_ids)
                    logger.info(
                        f"Processed {len(processed_ids)} personal emails ({len(threads)} threads)"
                    )
                    summaries.append({
                        "account": f"Newsletter ({self.config.personal_display_name})",
                        "summaries": personal_parts,
                    })
            except Exception as e:
                logger.error(f"Personal Gmail error: {e}")
                status["gmail"] = False

        # Work BD emails
        if self.config.work_gmail_refresh_token:
            try:
                gmail = GmailClient(
                    self.config.work_gmail_refresh_token,
                    self.config.google_client_id,
                    self.config.google_client_secret,
                )
                emails = gmail.get_unread_by_label(self.config.work_label)
                skip = self.config.work_skip_keywords
                emails = [
                    e for e in emails
                    if not any(kw.lower() in e["subject"].lower() for kw in skip)
                ]
                if emails:
                    work_parts = []
                    processed_ids = []
                    threads = group_by_thread(emails)
                    for thread_emails in threads.values():
                        try:
                            if len(thread_emails) == 1:
                                e = thread_emails[0]
                                summary = self.summarizer.summarize_business_email(
                                    e["subject"], e["body"], e["from"]
                                )
                            else:
                                summary = self.summarizer.summarize_business_thread(
                                    thread_emails[0]["subject"], thread_emails
                                )
                            senders = ", ".join(dict.fromkeys(e["from"] for e in thread_emails))
                            work_parts.append(
                                format_email_part(
                                    thread_emails[0]["subject"], senders,
                                    summary, len(thread_emails),
                                )
                            )
                            match = action_re.search(summary)
                            if match:
                                action_text = match.group(1).strip()
                                if action_text != self.config.none_value:
                                    action_items.append({
                                        "subject": thread_emails[0]["subject"],
                                        "action": action_text,
                                    })
                            processed_ids.extend(e["id"] for e in thread_emails)
                        except Exception as e:
                            tid = thread_emails[0].get("threadId", "unknown")
                            logger.error(
                                f"Summarize failed [thread={tid}, subject={thread_emails[0]['subject']}]: {e}"
                            )
                            processed_ids.extend(em["id"] for em in thread_emails)
                    gmail.mark_processed(processed_ids)
                    logger.info(
                        f"Processed {len(processed_ids)} work emails ({len(threads)} threads)"
                    )
                    summaries.append({
                        "account": f"BD ({self.config.work_display_name})",
                        "summaries": work_parts,
                    })
            except Exception as e:
                logger.error(f"Work Gmail error: {e}")
                status["gmail"] = False

        return summaries, action_items, status


class CalendarService:
    def __init__(self, config):
        self.config = config

    def _get_accounts(self):
        """Return (label, token_value, calendar_id) tuples resolved from config."""
        raw = [
            (self.config.work_display_name, "work_gmail_refresh_token", "work_calendar_id"),
            (self.config.personal_display_name, "personal_gmail_refresh_token", "personal_calendar_id"),
        ]
        return [
            (label, getattr(self.config, token_attr), getattr(self.config, cal_attr))
            for label, token_attr, cal_attr in raw
        ]

    def fetch_events(self, method: str) -> tuple:
        """Fetch today's or tomorrow's events.

        Args:
            method: 'get_today_events' or 'get_tomorrow_events'

        Returns:
            (events_list, status)
        """
        from .calendar_client import CalendarClient

        allowed = {"get_today_events", "get_tomorrow_events"}
        if method not in allowed:
            raise ValueError(f"Unknown calendar method: {method}")

        events_list = []
        status = {"calendar": True}

        for label, token, cal_id in self._get_accounts():
            if not token:
                continue
            try:
                cal = CalendarClient(
                    token, self.config.google_client_id,
                    self.config.google_client_secret, cal_id,
                )
                result = getattr(cal, method)()
                events_list.append((label, result))
            except Exception as e:
                logger.error(f"Calendar error ({label}): {e}")
                status["calendar"] = False

        return events_list, status

    def fetch_week_events(self, start_date, end_date) -> tuple:
        """Fetch events for a date range.

        Returns:
            (events_list, status)
        """
        from .calendar_client import CalendarClient

        events_list = []
        status = {"calendar": True}

        for label, token, cal_id in self._get_accounts():
            if not token:
                continue
            try:
                cal = CalendarClient(
                    token, self.config.google_client_id,
                    self.config.google_client_secret, cal_id,
                )
                result = cal.get_week_events(start_date, end_date)
                events_list.append((label, result))
            except Exception as e:
                logger.error(f"Calendar error ({label}): {e}")
                status["calendar"] = False

        return events_list, status

    def get_next_meeting_within_hours(self, hours=3) -> "dict | None":
        """Return the soonest upcoming meeting within the given hour window, or None."""
        from .calendar_client import CalendarClient

        now = datetime.now(KST)
        soonest = None

        for label, token, cal_id in self._get_accounts():
            if not token:
                continue
            try:
                cal = CalendarClient(
                    token, self.config.google_client_id,
                    self.config.google_client_secret, cal_id,
                )
                meeting = cal.get_next_meeting()
                if meeting and meeting.get("start") and "T" in meeting["start"]:
                    start_dt = datetime.fromisoformat(meeting["start"])
                    diff = start_dt - now
                    if timedelta(0) <= diff <= timedelta(hours=hours):
                        if soonest is None or start_dt < datetime.fromisoformat(soonest["start"]):
                            soonest = meeting
            except Exception as e:
                logger.error(f"Next meeting error ({label}): {e}")

        return soonest
