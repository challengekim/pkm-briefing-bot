import argparse
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from briefing_composer import compose_linkedin_draft, compose_meta_review_telegram, compose_trend_digest, compose_weekly_knowledge, escape_html
from config import Config
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


def _validate_config(config):
    if not all([config.gemini_api_key, config.telegram_bot_token, config.telegram_chat_id]):
        logger.error("Missing required config. Check environment variables.")
        return False
    return True


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

    tg_message = compose_meta_review_telegram(meta_summary, stats)
    telegram.send_message(tg_message)
    logger.info(f"Meta review sent to Telegram ({stats['total_notes']} notes)")


_BRIEFING_TYPES = {
    "trend": process_trend_digest,
    "knowledge": process_weekly_knowledge,
    "linkedin": process_linkedin_draft,
    "meta": process_meta_review,
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
        briefing_type = os.getenv("BRIEFING_TYPE", "trend").lower()
    else:
        briefing_type = None

    if briefing_type:
        handler = _BRIEFING_TYPES.get(briefing_type, process_trend_digest)
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
