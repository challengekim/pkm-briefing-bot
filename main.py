import argparse
import logging
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from config import Config
from core import (
    Summarizer, TelegramSender, URL_RE,
    scan_recent_notes, scan_all_notes, save_project_ideas,
    save_weekly_report, load_previous_weekly_reports,
    analyze_tag_connections, save_url_to_vault, save_thought_to_vault,
    compose_trend_digest, compose_weekly_knowledge,
    compose_linkedin_draft, compose_meta_review_telegram, escape_html,
    collect_monthly_stats, fetch_all_trends,
)

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

    # Brain-first: enrich trend digest with vault topics
    project_context = config.project_context
    if config.brain_first and config.vault_path:
        try:
            vault_notes = scan_recent_notes(config, days=14)
            if vault_notes:
                topics = ", ".join(n["title"] for n in vault_notes[:10])
                project_context = (project_context + f"\n\n[Vault Topics]\n{topics}").strip()
        except Exception as e:
            logger.warning(f"Brain-first vault scan failed (continuing): {e}")

    trend_summary = summarizer.summarize_trend_digest(items, project_context)

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


_last_update_id = 0

_COMMAND_KEYWORDS = {
    "상태": "status", "status": "status",
    "리포트": "report", "report": "report",
    "도움말": "help", "help": "help",
    "트렌드": "trend", "trend": "trend",
}


def _classify_intent(text, summarizer):
    """Classify message intent using LLM with heuristic fallback."""
    if len(text.strip()) < 30:
        return {"intent": "casual", "confidence": 0.8, "topic": ""}
    return summarizer.classify_intent(text)


def _handle_text(text, config, summarizer, telegram):
    """Handle a non-URL Telegram message based on classified intent."""
    # Command detection (keyword-based, fast path)
    text_lower = text.lower().strip()
    for keyword, cmd in _COMMAND_KEYWORDS.items():
        if keyword in text_lower:
            if cmd == "status":
                telegram.send_message("✓ PKM Bot 정상 동작 중")
            elif cmd == "report":
                telegram.send_message("리포트 생성 중...")
                process_weekly_knowledge()
            elif cmd == "help":
                telegram.send_message(
                    "<b>PKM Bot 명령어</b>\n"
                    "• URL 전송 → 노트 저장\n"
                    "• 아이디어/메모 → 생각 저장\n"
                    "• 상태 → 봇 상태 확인\n"
                    "• 리포트 → 주간 리포트\n"
                    "• 트렌드 → 트렌드 다이제스트\n"
                    "• 도움말 → 이 메시지"
                )
            elif cmd == "trend":
                telegram.send_message("트렌드 수집 중...")
                process_trend_digest()
            return

    # Intent classification
    intent_data = _classify_intent(text, summarizer)
    intent = intent_data.get("intent", "casual")

    if intent == "save_thought" and config.thought_capture:
        try:
            result = save_thought_to_vault(text, config.vault_path, summarizer)
            telegram.send_message(
                f"✓ 생각 저장됨\n"
                f"→ {result['category']}\n"
                f"<code>{os.path.basename(result['path'])}</code>"
            )
            logger.info(f"Thought saved: {text[:40]}")
        except Exception as e:
            telegram.send_message(f"✗ 저장 실패: {str(e)[:100]}")
            logger.error(f"Thought save failed: {e}")

    elif intent == "query":
        try:
            notes = scan_recent_notes(config, days=30)
            answer = summarizer.answer_vault_query(text, notes)
            telegram.send_message(f"<b>검색 결과</b>\n\n{answer}")
            logger.info(f"Query answered: {text[:40]}")
        except Exception as e:
            telegram.send_message(f"✗ 검색 실패: {str(e)[:100]}")
            logger.error(f"Query failed: {e}")

    elif intent == "casual":
        logger.debug(f"Casual message ignored: {text[:40]}")

    else:
        logger.debug(f"Unknown intent '{intent}' for: {text[:40]}")


def process_telegram_saves():
    """Check Telegram for incoming messages and handle URLs or text via intent resolver."""
    global _last_update_id
    config = Config()
    if not config.telegram_bot_token or not config.vault_path:
        return

    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)
    updates = telegram.get_updates(offset=_last_update_id + 1 if _last_update_id else None)

    summarizer = None

    for update in updates:
        _last_update_id = update["update_id"]
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Only process messages from the configured chat
        if chat_id != config.telegram_chat_id:
            continue

        if not text:
            continue

        # Extract URLs from message
        urls = URL_RE.findall(text)
        if urls:
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
        elif config.intent_classification:
            # Lazy-init summarizer only when needed
            if summarizer is None:
                try:
                    summarizer = Summarizer(config=config, lang=config.language)
                except Exception as e:
                    logger.warning(f"Summarizer init failed: {e}")
                    continue
            _handle_text(text, config, summarizer, telegram)


def _find_note_path(config, note):
    """Locate a note's file path by scanning vault directories."""
    vault = config.vault_path
    title = note.get("title", "")
    for scan_path in config.knowledge_scan_paths:
        full_path = os.path.join(vault, scan_path)
        if not os.path.isdir(full_path):
            continue
        for filename in os.listdir(full_path):
            if not filename.endswith(".md"):
                continue
            note_title = filename[:-3]
            if note_title == title or note_title.startswith(title[:30]):
                return os.path.join(full_path, filename)
    # Also check Thoughts directory
    thoughts_dir = os.path.join(vault, "00_Inbox", "Thoughts")
    if os.path.isdir(thoughts_dir):
        for filename in os.listdir(thoughts_dir):
            if filename.endswith(".md") and title[:30] in filename:
                return os.path.join(thoughts_dir, filename)
    return None


def process_dream_cycle():
    """Dream cycle: enrich recent notes with Compiled Truth and send morning summary."""
    config = Config()
    if not config.dream_cycle:
        return
    if not config.vault_path:
        logger.info("Dream cycle skipped — no vault_path configured")
        return

    summarizer = Summarizer(config=config, lang=config.language)
    telegram = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    notes = scan_recent_notes(config, days=1)
    enriched_count = 0
    entity_map = {}  # entity -> list of note titles

    for note in notes:
        note_path = note.get("_filepath") or _find_note_path(config, note)
        if not note_path or not os.path.exists(note_path):
            continue

        try:
            with open(note_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        # Skip notes that already have Compiled Truth
        if "## Compiled Truth" in content:
            continue

        # Extract frontmatter + body
        fm_match = re.match(r'^---\n(.*?\n)---\n', content, re.DOTALL)
        if not fm_match:
            continue

        fm_text = fm_match.group(1)
        body = content[fm_match.end():]

        # Extract title/category/description from frontmatter
        title = note.get("title", "")
        category = note.get("category", "")
        description = note.get("description", "")

        try:
            enrich_data = summarizer.enrich_note(title, category, description, body[:4000])
            compiled_truth = enrich_data.get("compiled_truth", "")
            key_takeaways = enrich_data.get("key_takeaways", [])
        except Exception as e:
            logger.debug(f"Enrich failed for {title}: {e}")
            continue

        if not compiled_truth:
            continue

        # Build Compiled Truth section to prepend to body
        ct_section = f"## Compiled Truth\n\n{compiled_truth}\n"
        if key_takeaways and isinstance(key_takeaways, list):
            items_str = "\n".join(f"- {t}" for t in key_takeaways if t)
            ct_section += f"\n## Key Takeaways\n\n{items_str}\n"
        ct_section += "\n---\n\n"

        new_content = f"---\n{fm_text}---\n{ct_section}{body}"

        try:
            with open(note_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            enriched_count += 1
            logger.info(f"Dream enriched: {title}")
        except Exception as e:
            logger.error(f"Write failed for {note_path}: {e}")
            continue

        # Collect entities for cross-reference
        source_entities = note.get("entities", "")
        if source_entities:
            for entity in source_entities.split(","):
                entity = entity.strip().strip("[]")
                if entity:
                    entity_map.setdefault(entity, []).append(title)

    # Find cross-references (entities shared by 2+ notes)
    cross_refs = [(e, titles) for e, titles in entity_map.items() if len(titles) >= 2]
    cross_refs.sort(key=lambda x: len(x[1]), reverse=True)

    if enriched_count > 0 or cross_refs:
        lines = [f"<b>Dream Cycle 완료</b>"]
        if enriched_count:
            lines.append(f"• {enriched_count}개 노트 Compiled Truth 보강")
        if cross_refs:
            lines.append(f"• 교차 참조 {len(cross_refs)}개 발견")
            for entity, titles in cross_refs[:3]:
                lines.append(f"  - <i>{entity}</i>: {', '.join(titles[:3])}")
        telegram.send_message("\n".join(lines))

    logger.info(f"Dream cycle done: {enriched_count} notes enriched, {len(cross_refs)} cross-refs")


_BRIEFING_TYPES = {
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

    logger.info("PKM Briefing Bot starting...")

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
        briefing_type = os.getenv("BRIEFING_TYPE", "trend").lower()
    else:
        briefing_type = None

    if briefing_type:
        handler = _BRIEFING_TYPES.get(briefing_type)
        if handler:
            handler()
        else:
            logger.error(f"Unknown briefing type: {briefing_type}")
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

    # Check for incoming Telegram messages every 30 seconds
    scheduler.add_job(process_telegram_saves, "interval", seconds=30, id="telegram_save")
    logger.info("Telegram save listener active (polling every 30s)")

    # Dream cycle: nightly note enrichment
    if config.dream_cycle:
        scheduler.add_job(process_dream_cycle, "cron", hour=config.dream_hour, minute=0, id="dream_cycle")
        logger.info(f"Dream cycle scheduled at {config.dream_hour:02d}:00")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopped")


if __name__ == "__main__":
    main()
