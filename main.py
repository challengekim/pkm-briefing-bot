import argparse
import logging
import os
import re
from collections import OrderedDict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from briefing_composer import compose_evening, compose_linkedin_draft, compose_morning, compose_meta_review_email, compose_meta_review_telegram, compose_trend_digest, compose_weekly, compose_weekly_knowledge, compose_weekly_knowledge_email, escape_html
from calendar_client import CalendarClient
from config import Config
from gmail_client import GmailClient
from email_sender import EmailSender
from knowledge_scanner import analyze_tag_connections, load_previous_weekly_report, save_project_ideas, save_weekly_report, scan_all_notes, scan_recent_notes
from meta_reviewer import collect_monthly_stats
from summarizer import Summarizer
from telegram_sender import TelegramSender
from trend_fetcher import fetch_all_trends

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Default timezone; overridden in main() from config.schedule_timezone
KST = ZoneInfo("Asia/Seoul")

def _get_action_re(config):
    return re.compile(config.action_pattern)

def _get_calendar_accounts_resolved(config):
    """Return (label, token_value, calendar_id) tuples resolved from config."""
    raw = [
        (config.work_display_name, "work_gmail_refresh_token", "work_calendar_id"),
        (config.personal_display_name, "personal_gmail_refresh_token", "personal_calendar_id"),
    ]
    return [
        (label, getattr(config, token_attr), getattr(config, cal_attr))
        for label, token_attr, cal_attr in raw
    ]


def _validate_config(config):
    if not all([config.gemini_api_key, config.telegram_bot_token, config.telegram_chat_id]):
        logger.error("Missing required config. Check environment variables.")
        return False
    return True


def _format_email_part(subject, sender, summary_text, email_count=1):
    """Format a single email/thread summary as HTML. All inputs are raw (unescaped)."""
    count_label = f" ({email_count}건)" if email_count > 1 else ""
    return (
        f"\n<b>{escape_html(subject)}{count_label}</b>\n"
        f"<i>{escape_html(sender)}</i>\n\n"
        f"{escape_html(summary_text)}\n"
    )


def _normalize_subject(subject):
    """Remove Re:/Fwd:/FW: prefixes (including chained) and extra whitespace."""
    s = subject
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"^(?:Re|Fwd|FW|Fw)\s*:\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def _group_by_thread(emails):
    """Group emails by threadId, then merge single-email threads with the same subject.

    Gmail assigns different threadIds to notification-style emails (e.g. incident
    updates) even when they share the same subject. This two-pass approach groups
    by threadId first, then consolidates single-message threads that share a
    normalized subject line.

    Emails within each group are sorted chronologically (oldest first)."""
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
            # Multi-email thread (real Gmail thread) — keep as-is
            merged[tid] = thread_emails
        else:
            norm = _normalize_subject(thread_emails[0]["subject"])
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


def _fetch_email_summaries(config, summarizer):
    summaries = []
    action_items = []
    status = {"gmail": True}
    action_re = _get_action_re(config)

    # Personal newsletters
    if config.personal_gmail_refresh_token:
        try:
            gmail = GmailClient(
                config.personal_gmail_refresh_token,
                config.google_client_id,
                config.google_client_secret,
            )
            emails = gmail.get_unread_from_senders(config.personal_senders)
            if emails:
                personal_parts = []
                processed_ids = []
                threads = _group_by_thread(emails)
                for thread_emails in threads.values():
                    try:
                        if len(thread_emails) == 1:
                            e = thread_emails[0]
                            summary = summarizer.summarize_newsletter(
                                e["subject"], e["body"], e["from"]
                            )
                        else:
                            summary = summarizer.summarize_newsletter_thread(
                                thread_emails[0]["subject"], thread_emails
                            )
                        senders = ", ".join(dict.fromkeys(
                            e["from"] for e in thread_emails
                        ))
                        personal_parts.append(
                            _format_email_part(
                                thread_emails[0]["subject"], senders,
                                summary, len(thread_emails),
                            )
                        )
                        # Extract action items from personal emails too
                        match = action_re.search(summary)
                        if match:
                            action_text = match.group(1).strip()
                            if action_text != config.none_value:
                                action_items.append({
                                    "subject": thread_emails[0]["subject"],
                                    "action": action_text,
                                })
                        processed_ids.extend(e["id"] for e in thread_emails)
                    except Exception as e:
                        tid = thread_emails[0].get("threadId", "unknown")
                        logger.error(f"Summarize failed [thread={tid}, subject={thread_emails[0]['subject']}]: {e}")
                        processed_ids.extend(em["id"] for em in thread_emails)
                gmail.mark_processed(processed_ids)
                logger.info(f"Processed {len(processed_ids)} personal emails ({len(threads)} threads)")
                summaries.append({"account": f"Newsletter ({config.personal_display_name})", "summaries": personal_parts})
        except Exception as e:
            logger.error(f"Personal Gmail error: {e}")
            status["gmail"] = False

    # Work BD emails
    if config.work_gmail_refresh_token:
        try:
            gmail = GmailClient(
                config.work_gmail_refresh_token,
                config.google_client_id,
                config.google_client_secret,
            )
            emails = gmail.get_unread_by_label(config.work_label)
            skip = config.work_skip_keywords
            emails = [
                e for e in emails
                if not any(kw.lower() in e["subject"].lower() for kw in skip)
            ]
            if emails:
                work_parts = []
                processed_ids = []
                threads = _group_by_thread(emails)
                for thread_emails in threads.values():
                    try:
                        if len(thread_emails) == 1:
                            e = thread_emails[0]
                            summary = summarizer.summarize_business_email(
                                e["subject"], e["body"], e["from"]
                            )
                        else:
                            summary = summarizer.summarize_business_thread(
                                thread_emails[0]["subject"], thread_emails
                            )
                        senders = ", ".join(dict.fromkeys(
                            e["from"] for e in thread_emails
                        ))
                        work_parts.append(
                            _format_email_part(
                                thread_emails[0]["subject"], senders,
                                summary, len(thread_emails),
                            )
                        )
                        # Extract action items
                        match = action_re.search(summary)
                        if match:
                            action_text = match.group(1).strip()
                            if action_text != config.none_value:
                                action_items.append({
                                    "subject": thread_emails[0]["subject"],
                                    "action": action_text,
                                })
                        processed_ids.extend(e["id"] for e in thread_emails)
                    except Exception as e:
                        tid = thread_emails[0].get("threadId", "unknown")
                        logger.error(f"Summarize failed [thread={tid}, subject={thread_emails[0]['subject']}]: {e}")
                        processed_ids.extend(em["id"] for em in thread_emails)
                gmail.mark_processed(processed_ids)
                logger.info(f"Processed {len(processed_ids)} work emails ({len(threads)} threads)")
                summaries.append({"account": f"BD ({config.work_display_name})", "summaries": work_parts})
        except Exception as e:
            logger.error(f"Work Gmail error: {e}")
            status["gmail"] = False

    return summaries, action_items, status




def _fetch_calendar_events(config, method):
    allowed = {"get_today_events", "get_tomorrow_events"}
    if method not in allowed:
        raise ValueError(f"Unknown calendar method: {method}")

    events_list = []
    status = {"calendar": True}

    for label, token, cal_id in _get_calendar_accounts_resolved(config):
        if not token:
            continue
        try:
            cal = CalendarClient(token, config.google_client_id, config.google_client_secret, cal_id)
            result = getattr(cal, method)()
            events_list.append((label, result))
        except Exception as e:
            logger.error(f"Calendar error ({label}): {e}")
            status["calendar"] = False

    return events_list, status


def _fetch_week_events(config, start_date, end_date):
    events_list = []
    status = {"calendar": True}

    for label, token, cal_id in _get_calendar_accounts_resolved(config):
        if not token:
            continue
        try:
            cal = CalendarClient(token, config.google_client_id, config.google_client_secret, cal_id)
            result = cal.get_week_events(start_date, end_date)
            events_list.append((label, result))
        except Exception as e:
            logger.error(f"Calendar error ({label}): {e}")
            status["calendar"] = False

    return events_list, status


def _get_next_meeting_within_hours(config, hours=3):
    now = datetime.now(KST)
    soonest = None
    for label, token, cal_id in _get_calendar_accounts_resolved(config):
        if not token:
            continue
        try:
            cal = CalendarClient(token, config.google_client_id, config.google_client_secret, cal_id)
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


def process_morning():
    config = Config()
    if not _validate_config(config):
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    email_summaries, action_items, email_status = _fetch_email_summaries(config, summarizer)
    calendar_events, cal_status = _fetch_calendar_events(config, "get_today_events")

    next_meeting = _get_next_meeting_within_hours(config, hours=3)
    meeting_prep = None
    if next_meeting:
        meeting_prep = summarizer.summarize_meeting_prep(next_meeting)

    data_source_status = {**email_status, **cal_status}

    has_content = email_summaries or any(
        d.get("total_count", 0) > 0 for _, d in calendar_events
    )
    if not has_content:
        logger.info("No content for morning briefing — skipping")
        return

    message = compose_morning(
        calendar_events=calendar_events,
        email_summaries=email_summaries,
        next_meeting=next_meeting,
        meeting_prep=meeting_prep,
        action_items=action_items,
        data_source_status=data_source_status,
    )
    telegram.send_message(message)
    logger.info("Morning briefing sent")


def process_evening():
    config = Config()
    if not _validate_config(config):
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    email_summaries, _, email_status = _fetch_email_summaries(config, summarizer)
    tomorrow_events, cal_status = _fetch_calendar_events(config, "get_tomorrow_events")

    data_source_status = {**email_status, **cal_status}

    has_content = email_summaries or any(
        d.get("total_count", 0) > 0 for _, d in tomorrow_events
    )
    if not has_content:
        logger.info("No content for evening review — skipping")
        return

    message = compose_evening(
        email_summaries=email_summaries,
        tomorrow_events=tomorrow_events,
        data_source_status=data_source_status,
    )
    telegram.send_message(message)
    logger.info("Evening review sent")


def process_trend_digest():
    config = Config()
    if not _validate_config(config):
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    items = fetch_all_trends(config)
    if not items:
        logger.info("No trend items collected — skipping digest")
        return

    source_counts = {}
    for item in items:
        src = item["source"]
        source_counts[src] = source_counts.get(src, 0) + 1

    trend_summary = summarizer.summarize_trend_digest(items, config.project_context)

    # Translate English titles to Korean
    translations = summarizer.translate_titles(items)
    for item in items:
        if item["title"] in translations:
            item["title_ko"] = translations[item["title"]]

    message = compose_trend_digest(
        trend_summary=trend_summary,
        source_counts=source_counts,
        data_source_status={"trends": True},
        all_items=items,
    )
    telegram.send_message(message)
    logger.info(f"Trend digest sent ({len(items)} items)")


def process_weekly_knowledge():
    config = Config()
    if not _validate_config(config):
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    notes = scan_recent_notes(config, days=7)
    if not notes:
        logger.info("No knowledge notes this week — skipping report")
        return

    # Compound learning: load previous week's report
    previous_report = ""
    if config.vault_path:
        previous_report = load_previous_weekly_report(config.vault_path)

    # Tag co-occurrence analysis
    tag_data = analyze_tag_connections(notes)
    tag_analysis_parts = []
    for conn in tag_data["connections"]:
        tag_analysis_parts.append(f"- \"{conn['note1']}\" ↔ \"{conn['note2']}\" (공통 태그: {', '.join(conn['shared_tags'])})")
    for tag, titles in tag_data["popular_tags"]:
        tag_analysis_parts.append(f"- 태그 '{tag}': {', '.join(titles[:3])}{'...' if len(titles) > 3 else ''}")
    tag_analysis = "\n".join(tag_analysis_parts) if tag_analysis_parts else ""

    knowledge_summary = summarizer.summarize_weekly_knowledge(
        notes, config.project_context, previous_report=previous_report, tag_analysis=tag_analysis,
    )

    message = compose_weekly_knowledge(
        knowledge_summary=knowledge_summary,
        notes=notes,
        data_source_status={"knowledge": True},
    )
    telegram.send_message(message)
    logger.info(f"Weekly knowledge report sent to Telegram ({len(notes)} notes)")

    # Send email report
    if config.personal_gmail_refresh_token and config.knowledge_email_to:
        try:
            email = EmailSender(
                config.personal_gmail_refresh_token,
                config.google_client_id,
                config.google_client_secret,
            )
            now = datetime.now(KST)
            email_html = compose_weekly_knowledge_email(knowledge_summary, notes)
            email.send_html(
                to=config.knowledge_email_to,
                subject=f"Weekly Knowledge Report — {now.strftime('%Y-%m-%d')}",
                html_body=email_html,
            )
        except Exception as e:
            logger.error(f"Knowledge email failed: {e}")

    # Save weekly report for compound learning
    if knowledge_summary and config.vault_path:
        try:
            now = datetime.now(KST)
            save_weekly_report(config.vault_path, knowledge_summary, now.strftime("%Y-%m-%d"))
        except Exception as e:
            logger.error(f"Weekly report save failed: {e}")

    # Save project ideas to Obsidian
    if knowledge_summary and config.vault_path:
        try:
            now = datetime.now(KST)
            save_project_ideas(
                config.vault_path,
                knowledge_summary,
                now.strftime("%Y-%m-%d"),
                ideas_file=config.ideas_file,
            )
        except Exception as e:
            logger.error(f"Project ideas save failed: {e}")


def process_linkedin_draft():
    config = Config()
    if not _validate_config(config):
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    # Collect all vault notes (no date cutoff)
    notes = scan_all_notes(config)
    if not notes:
        logger.info("No notes in vault — skipping LinkedIn draft")
        return

    # Get today's trend digest for cross-referencing
    trend_summary = None
    try:
        items = fetch_all_trends(config)
        if items:
            trend_summary = summarizer.summarize_trend_digest(items, config.project_context)
    except Exception as e:
        logger.warning(f"Trend fetch for LinkedIn draft failed (continuing without): {e}")

    draft = summarizer.generate_linkedin_draft(notes, trend_summary, config.project_context)

    has_trends = trend_summary is not None
    message = compose_linkedin_draft(
        draft_text=draft,
        note_count=len(notes),
        has_trends=has_trends,
        data_source_status={"vault": True, "trends": has_trends},
    )
    telegram.send_message(message)
    logger.info(f"LinkedIn draft sent ({len(notes)} notes used)")


def process_meta_review():
    config = Config()
    if not _validate_config(config):
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    stats = collect_monthly_stats(config, days=30)
    if stats["total_notes"] == 0:
        logger.info("No notes in last 30 days — skipping meta review")
        return

    meta_summary = summarizer.summarize_meta_review(stats, config.project_context)

    # Telegram
    tg_message = compose_meta_review_telegram(meta_summary, stats)
    telegram.send_message(tg_message)
    logger.info(f"Meta review sent to Telegram ({stats['total_notes']} notes)")

    # Email
    if config.personal_gmail_refresh_token and config.knowledge_email_to:
        try:
            email = EmailSender(
                config.personal_gmail_refresh_token,
                config.google_client_id,
                config.google_client_secret,
            )
            now = datetime.now(KST)
            email_html = compose_meta_review_email(meta_summary, stats)
            email.send_html(
                to=config.knowledge_email_to,
                subject=f"Monthly Meta Review — {now.strftime('%Y-%m')}",
                html_body=email_html,
            )
        except Exception as e:
            logger.error(f"Meta review email failed: {e}")


def process_weekly():
    config = Config()
    if not _validate_config(config):
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    now = datetime.now(KST)
    monday = (now - timedelta(days=now.weekday())).date()
    friday = monday + timedelta(days=4)
    next_monday = monday + timedelta(days=7)
    next_friday = next_monday + timedelta(days=4)

    # This week's meetings
    week_meetings, cal_status = _fetch_week_events(config, monday, friday)

    # Email stats
    email_stats = {"personal": 0, "work": 0}
    email_status = {"gmail": True}
    monday_str = monday.strftime("%Y/%m/%d")
    for key, token in [("personal", config.personal_gmail_refresh_token),
                       ("work", config.work_gmail_refresh_token)]:
        if not token:
            continue
        try:
            gmail = GmailClient(token, config.google_client_id, config.google_client_secret)
            query = f"label:digest-processed after:{monday_str}"
            email_stats[key] = gmail.count_by_query(query)
        except Exception as e:
            logger.error(f"Weekly email stats error ({key}): {e}")
            email_status["gmail"] = False

    # Next week's events
    next_week_events, _ = _fetch_week_events(config, next_monday, next_friday)

    # Gemini weekly summary
    meeting_count = sum(d.get("total_count", 0) for _, d in week_meetings)
    all_next_week = []
    for _, data in next_week_events:
        all_next_week.extend(data.get("events", []))
    weekly_summary = summarizer.summarize_weekly(email_stats, meeting_count, all_next_week)

    data_source_status = {**email_status, **cal_status}

    message = compose_weekly(
        week_meetings=week_meetings,
        email_stats=email_stats,
        next_week_events=next_week_events,
        weekly_summary=weekly_summary,
        data_source_status=data_source_status,
    )
    telegram.send_message(message)
    logger.info("Weekly digest sent")


_BRIEFING_TYPES = {
    "morning": process_morning,
    "evening": process_evening,
    "weekly": process_weekly,
    "trend": process_trend_digest,
    "knowledge": process_weekly_knowledge,
    "meta": process_meta_review,
    "linkedin": process_linkedin_draft,
}


def main():
    parser = argparse.ArgumentParser(description="PKM Briefing Bot")
    parser.add_argument(
        "--test",
        choices=list(_BRIEFING_TYPES.keys()),
        help="Run a single briefing type immediately for testing",
    )
    args = parser.parse_args()

    logger.info("Productivity Briefing Bot starting...")

    # --test flag takes priority, then RUN_NOW env var
    if args.test:
        briefing_type = args.test
    elif os.getenv("RUN_NOW", "").lower() in ("1", "true"):
        briefing_type = os.getenv("BRIEFING_TYPE", "morning").lower()
    else:
        briefing_type = None

    if briefing_type:
        handler = _BRIEFING_TYPES.get(briefing_type, process_morning)
        handler()
        return

    global KST
    config = Config()
    KST = ZoneInfo(config.schedule_timezone)

    scheduler = BlockingScheduler(timezone=KST)
    scheduled_names = []
    for name, func in _BRIEFING_TYPES.items():
        cron_kwargs = config.schedule.get(name)
        if cron_kwargs:
            scheduler.add_job(func, "cron", **cron_kwargs)
            scheduled_names.append(name)
    logger.info(f"Scheduled jobs: {', '.join(scheduled_names)} (tz={config.schedule_timezone})")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopped")


if __name__ == "__main__":
    main()
