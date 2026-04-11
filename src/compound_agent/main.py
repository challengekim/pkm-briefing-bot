import argparse
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from .briefing_composer import compose_evening, compose_linkedin_draft, compose_morning, compose_meta_review_email, compose_meta_review_telegram, compose_trend_digest, compose_weekly, compose_weekly_knowledge, compose_weekly_knowledge_email
from .config import Config
from .email_sender import EmailSender
from .gmail_client import GmailClient
from .knowledge_scanner import analyze_tag_connections, load_previous_weekly_reports, save_project_ideas, save_url_to_vault, save_weekly_report, scan_all_notes, scan_recent_notes
from .meta_reviewer import collect_monthly_stats
from .services import CalendarService, EmailService
from .summarizer import Summarizer
from .telegram_sender import TelegramSender, URL_RE
from .trend_fetcher import fetch_all_trends

# Agent imports (Phase A)
from .brain import Brain
from .hands import Hands
from .agent_state import AgentState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Default timezone; overridden in main() from config.schedule_timezone
KST = ZoneInfo("Asia/Seoul")

def _validate_config(config):
    if not all([config.gemini_api_key, config.telegram_bot_token, config.telegram_chat_id]):
        logger.error("Missing required config. Check environment variables.")
        return False
    return True


def process_morning():
    config = Config()
    if not _validate_config(config):
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)
    email_svc = EmailService(config, summarizer)
    cal_svc = CalendarService(config)

    email_summaries, action_items, email_status = email_svc.fetch_summaries()
    calendar_events, cal_status = cal_svc.fetch_events("get_today_events")

    next_meeting = cal_svc.get_next_meeting_within_hours(hours=3)
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
    email_svc = EmailService(config, summarizer)
    cal_svc = CalendarService(config)

    email_summaries, _, email_status = email_svc.fetch_summaries()
    tomorrow_events, cal_status = cal_svc.fetch_events("get_tomorrow_events")

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

    # Auto-save top trend items to vault for compound learning
    if config.vault_path and items:
        items_sorted = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
        saved_count = 0
        for item in items_sorted[:3]:
            try:
                save_url_to_vault(
                    item["url"], config.vault_path, config.knowledge_scan_paths,
                )
                saved_count += 1
            except Exception as e:
                logger.warning(f"Auto-save failed for {item['url']}: {e}")
        if saved_count:
            logger.info(f"Auto-saved {saved_count} trend items to vault")


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
        previous_report = load_previous_weekly_reports(config.vault_path, weeks=4)

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
    cal_svc = CalendarService(config)

    now = datetime.now(KST)
    monday = (now - timedelta(days=now.weekday())).date()
    friday = monday + timedelta(days=4)
    next_monday = monday + timedelta(days=7)
    next_friday = next_monday + timedelta(days=4)

    # This week's meetings
    week_meetings, cal_status = cal_svc.fetch_week_events(monday, friday)

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
    next_week_events, _ = cal_svc.fetch_week_events(next_monday, next_friday)

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


_last_update_id = 0


def process_telegram_saves():
    """Check Telegram for incoming URLs and save them to vault."""
    global _last_update_id
    config = Config()
    if not config.telegram_bot_token or not config.vault_path:
        return

    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)
    updates = telegram.get_updates(offset=_last_update_id + 1 if _last_update_id else None)

    for update in updates:
        _last_update_id = update["update_id"]
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Only process messages from the configured chat
        if chat_id != config.telegram_chat_id:
            continue

        # Extract URLs from message
        urls = URL_RE.findall(text)
        if not urls:
            continue

        for url in urls[:3]:  # max 3 per message
            try:
                result = save_url_to_vault(url, config.vault_path, config.knowledge_scan_paths)
                telegram.send_message(
                    f"✓ <b>{result['title'][:60]}</b>\n"
                    f"→ {result['category']}\n"
                    f"<code>{os.path.basename(result['path'])}</code>",
                )
                logger.info(f"Telegram save: {result['title'][:40]}")
            except Exception as e:
                telegram.send_message(f"✗ Save failed: {str(e)[:100]}")
                logger.error(f"Telegram save failed for {url}: {e}")


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
        "--save", metavar="URL",
        help="Save a URL to your vault as a markdown note",
    )
    parser.add_argument(
        "--test",
        choices=list(_BRIEFING_TYPES.keys()),
        help="Run a single briefing type immediately for testing",
    )
    args = parser.parse_args()

    logger.info("Productivity Briefing Bot starting...")

    # --save: save a URL to the vault and exit
    if args.save:
        config = Config()
        summarizer_instance = None
        if config.llm_api_key or config.llm_provider == "ollama":
            summarizer_instance = Summarizer(config=config, lang=config.language)
        result = save_url_to_vault(
            args.save, config.vault_path, config.knowledge_scan_paths,
            summarizer_instance,
        )
        print(f"Saved: {result['title']}")
        print(f"  Path: {result['path']}")
        print(f"  Category: {result['category']}")
        return

    # --test flag takes priority, then RUN_NOW env var
    if args.test:
        briefing_type = args.test
    elif os.getenv("RUN_NOW", "").lower() in ("1", "true"):
        briefing_type = os.getenv("BRIEFING_TYPE", "morning").lower()
    else:
        briefing_type = None

    if briefing_type:
        config = Config()
        if config.agent_mode == "multi-agent":
            # Route through Orchestrator for multi-agent mode
            from .memory import AgentMemory
            from .session.event_log import EventLog
            from .agents import create_default_registry
            from .agents.orchestrator import Orchestrator

            memory = AgentMemory(
                memory_path=config.agent_memory_path,
                ema_alpha=config.agent_ema_alpha,
                min_reading_samples=config.agent_min_reading_samples,
            )
            summarizer_instance = Summarizer(config=config, lang=config.language)
            hands = Hands(config, memory=memory)
            event_log = EventLog(config.event_log_path)
            registry = create_default_registry(config, summarizer_instance, memory)
            orchestrator = Orchestrator(config, memory, event_log, registry, hands, summarizer_instance)
            results = orchestrator.run_cycle(scheduled_action=briefing_type)
            logger.info("--test multi-agent: %d results from orchestrator", len(results))
        elif config.agent_mode != "disabled":
            # Route through Brain for reactive/proactive/self-improving modes
            state = AgentState(config.agent_state_path)
            memory = None
            if config.agent_mode in ("proactive", "self-improving"):
                from .memory import AgentMemory
                memory = AgentMemory(
                    memory_path=config.agent_memory_path,
                    ema_alpha=config.agent_ema_alpha,
                    min_reading_samples=config.agent_min_reading_samples,
                )
            hands = Hands(config, memory=memory)
            brain = Brain(config, state, hands, memory=memory)
            results = brain.tick(scheduled_action=briefing_type)
            logger.info("--test brain: %s", results)
        else:
            handler = _BRIEFING_TYPES.get(briefing_type, process_morning)
            handler()
        return

    global KST
    config = Config()
    KST = ZoneInfo(config.schedule_timezone)

    scheduler = BlockingScheduler(timezone=KST)

    if not _validate_config(config):
        return

    if config.agent_mode == "multi-agent":
        logger.info("Agent mode: multi-agent (orchestrator)")

        state = AgentState(config.agent_state_path)

        from .memory import AgentMemory
        memory = AgentMemory(
            memory_path=config.agent_memory_path,
            ema_alpha=config.agent_ema_alpha,
            min_reading_samples=config.agent_min_reading_samples,
        )

        hands = Hands(config, memory=memory)
        summarizer_instance = Summarizer(config)

        from .session.event_log import EventLog
        from .agents import create_default_registry
        from .agents.orchestrator import Orchestrator

        event_log = EventLog(config.event_log_path)
        registry = create_default_registry(config, summarizer_instance, memory)
        orchestrator = Orchestrator(config, memory, event_log, registry, hands, summarizer_instance)

        # Schedule the same cycle slots as self-improving mode
        for name in _BRIEFING_TYPES:
            cron_kwargs = config.schedule.get(name)
            if cron_kwargs:
                scheduler.add_job(
                    orchestrator.run_cycle,
                    "cron",
                    kwargs={"scheduled_action": name},
                    id=f"orchestrator_{name}",
                    **cron_kwargs,
                )
        logger.info("Orchestrator scheduled for: %s (tz=%s)", ", ".join(_BRIEFING_TYPES), config.schedule_timezone)

        # Telegram handler uses Brain for backward compat
        brain = Brain(config, state, hands, memory=memory)
        from .telegram_handler import TelegramHandler
        telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)
        handler = TelegramHandler(config, brain, telegram, state)
        scheduler.add_job(handler.poll_and_process, "interval", seconds=30, id="telegram_agent")
        logger.info("Telegram agent handler active (polling every 30s)")

    elif config.agent_mode != "disabled":
        # --- Agent mode: route through Brain ---
        logger.info("Agent mode: %s (autonomy: %s)", config.agent_mode, config.agent_autonomy)

        state = AgentState(config.agent_state_path)

        # Memory for proactive and self-improving modes
        memory = None
        if config.agent_mode in ("proactive", "self-improving"):
            from .memory import AgentMemory
            memory = AgentMemory(
                memory_path=config.agent_memory_path,
                ema_alpha=config.agent_ema_alpha,
                min_reading_samples=config.agent_min_reading_samples,
            )

        hands = Hands(config, memory=memory)
        brain = Brain(config, state, hands, memory=memory)

        # Register briefing jobs through Brain
        scheduled_names = []
        for name in _BRIEFING_TYPES:
            cron_kwargs = config.schedule.get(name)
            if cron_kwargs:
                scheduler.add_job(
                    brain.tick,
                    "cron",
                    kwargs={"scheduled_action": name},
                    id=f"brain_{name}",
                    **cron_kwargs,
                )
                scheduled_names.append(name)
        logger.info(f"Scheduled jobs (agent): {', '.join(scheduled_names)} (tz={config.schedule_timezone})")

        if config.agent_mode in ("proactive", "self-improving"):
            scheduler.add_job(
                brain.tick,
                "interval",
                minutes=15,
                kwargs={"scheduled_action": "__check_deferred"},
                id="brain_deferred_check",
            )
            logger.info("Deferred action check active (every 15 min)")

        if config.agent_mode == "self-improving":
            # Monthly evolution check (2nd of each month, day after meta-review)
            scheduler.add_job(
                brain.tick,
                "cron",
                kwargs={"scheduled_action": "__evolution_check"},
                id="brain_evolution",
                day=2,
                hour=11,
                minute=0,
            )
            logger.info("Evolution check active (2nd of each month at 11:00)")

        # Enhanced Telegram handler
        from .telegram_handler import TelegramHandler
        telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)
        handler = TelegramHandler(config, brain, telegram, state)
        scheduler.add_job(handler.poll_and_process, "interval", seconds=30, id="telegram_agent")
        logger.info("Telegram agent handler active (polling every 30s)")

    else:
        # --- Disabled mode: original behavior ---
        logger.info("Agent mode: disabled (bot mode)")

        scheduled_names = []
        for name, func in _BRIEFING_TYPES.items():
            cron_kwargs = config.schedule.get(name)
            if cron_kwargs:
                scheduler.add_job(func, "cron", **cron_kwargs, id=f"bot_{name}")
                scheduled_names.append(name)
        logger.info(f"Scheduled jobs: {', '.join(scheduled_names)} (tz={config.schedule_timezone})")

        # Check for incoming Telegram URLs every 30 seconds
        scheduler.add_job(process_telegram_saves, "interval", seconds=30, id="telegram_bot")
        logger.info("Telegram save listener active (polling every 30s)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopped")


if __name__ == "__main__":
    main()
