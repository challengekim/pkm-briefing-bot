"""Hands — callable tool wrappers for the Brain agent.

Each method maps to an existing process_*() pipeline in main.py,
exposing its core logic as a structured dict result.
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


class Hands:
    def __init__(self, config, memory=None, channel=None):
        self.config = config
        self.memory = memory
        self._channel = channel
        self._summarizer = None
        self._telegram = None
        self._email_sender = None
        self._email_svc = None
        self._cal_svc = None

    # ------------------------------------------------------------------
    # Lazy-initialized service accessors
    # ------------------------------------------------------------------

    @property
    def summarizer(self):
        if self._summarizer is None:
            from .summarizer import Summarizer
            self._summarizer = Summarizer(config=self.config, lang=self.config.language)
        return self._summarizer

    @property
    def channel(self):
        if self._channel is None:
            from .notifications import create_channel
            self._channel = create_channel(self.config)
        return self._channel

    @property
    def telegram(self):
        if self._telegram is None:
            from .telegram_sender import TelegramSender
            self._telegram = TelegramSender(
                self.config.telegram_bot_token, self.config.telegram_chat_id
            )
        return self._telegram

    @property
    def email_sender(self):
        if self._email_sender is None:
            from .email_sender import EmailSender
            self._email_sender = EmailSender(
                self.config.personal_gmail_refresh_token,
                self.config.google_client_id,
                self.config.google_client_secret,
            )
        return self._email_sender

    @property
    def email_svc(self):
        if self._email_svc is None:
            from .services import EmailService
            self._email_svc = EmailService(self.config, self.summarizer)
        return self._email_svc

    @property
    def cal_svc(self):
        if self._cal_svc is None:
            from .services import CalendarService
            self._cal_svc = CalendarService(self.config)
        return self._cal_svc

    # ------------------------------------------------------------------
    # Briefing send helper
    # ------------------------------------------------------------------

    def _send_briefing(self, message: str, briefing_type: str):
        """Send a briefing via the notification channel.

        Returns message_id (int) if the channel supports it, else None.
        """
        return self.channel.send_briefing(message, briefing_type, self.config.agent_mode)

    # ------------------------------------------------------------------
    # Pipeline wrappers
    # ------------------------------------------------------------------

    def run_morning_briefing(self) -> dict:
        """Execute morning briefing pipeline (calendar + email + meeting prep)."""
        try:
            from .briefing_composer import compose_morning

            email_summaries, action_items, email_status = self.email_svc.fetch_summaries()
            calendar_events, cal_status = self.cal_svc.fetch_events("get_today_events")
            next_meeting = self.cal_svc.get_next_meeting_within_hours(hours=3)
            meeting_prep = None
            if next_meeting:
                meeting_prep = self.summarizer.summarize_meeting_prep(next_meeting)

            data_source_status = {**email_status, **cal_status}

            has_content = email_summaries or any(
                d.get("total_count", 0) > 0 for _, d in calendar_events
            )
            if not has_content:
                return {"success": True, "message": "No content for morning briefing — skipped"}

            message = compose_morning(
                calendar_events=calendar_events,
                email_summaries=email_summaries,
                next_meeting=next_meeting,
                meeting_prep=meeting_prep,
                action_items=action_items,
                data_source_status=data_source_status,
            )
            msg_id = self._send_briefing(message, "morning")
            return {
                "success": True,
                "message": "Morning briefing sent",
                "message_id": msg_id,
                "email_accounts": len(email_summaries),
                "calendar_accounts": len(calendar_events),
                "has_meeting_prep": meeting_prep is not None,
            }
        except Exception as e:
            logger.error(f"run_morning_briefing failed: {e}")
            return {"success": False, "error": str(e)}

    def run_evening_review(self) -> dict:
        """Execute evening review pipeline (email + tomorrow's calendar)."""
        try:
            from .briefing_composer import compose_evening

            email_summaries, _, email_status = self.email_svc.fetch_summaries()
            tomorrow_events, cal_status = self.cal_svc.fetch_events("get_tomorrow_events")
            data_source_status = {**email_status, **cal_status}

            has_content = email_summaries or any(
                d.get("total_count", 0) > 0 for _, d in tomorrow_events
            )
            if not has_content:
                return {"success": True, "message": "No content for evening review — skipped"}

            message = compose_evening(
                email_summaries=email_summaries,
                tomorrow_events=tomorrow_events,
                data_source_status=data_source_status,
            )
            msg_id = self._send_briefing(message, "evening")
            return {
                "success": True,
                "message": "Evening review sent",
                "message_id": msg_id,
                "email_accounts": len(email_summaries),
            }
        except Exception as e:
            logger.error(f"run_evening_review failed: {e}")
            return {"success": False, "error": str(e)}

    def run_trend_digest(self) -> dict:
        """Execute trend digest pipeline (HN/Reddit/GeekNews → summarize → Telegram + vault save)."""
        try:
            from .briefing_composer import compose_trend_digest
            from .knowledge_scanner import save_url_to_vault
            from .trend_fetcher import fetch_all_trends

            items = fetch_all_trends(self.config)
            if not items:
                return {"success": True, "message": "No trend items collected — skipped", "items_count": 0}

            source_counts = {}
            for item in items:
                src = item["source"]
                source_counts[src] = source_counts.get(src, 0) + 1

            trend_summary = self.summarizer.summarize_trend_digest(items, self.config.project_context)

            translations = self.summarizer.translate_titles(items)
            for item in items:
                if item["title"] in translations:
                    item["title_ko"] = translations[item["title"]]

            message = compose_trend_digest(
                trend_summary=trend_summary,
                source_counts=source_counts,
                data_source_status={"trends": True},
                all_items=items,
            )
            msg_id = self._send_briefing(message, "trend")

            saved_count = 0
            if self.config.vault_path and items:
                items_sorted = sorted(items, key=lambda x: x.get("score", 0), reverse=True)
                for item in items_sorted[:3]:
                    try:
                        save_url_to_vault(item["url"], self.config.vault_path, self.config.knowledge_scan_paths)
                        saved_count += 1
                    except Exception as e:
                        logger.warning(f"Auto-save failed for {item['url']}: {e}")

            return {
                "success": True,
                "message": f"Trend digest sent ({len(items)} items)",
                "message_id": msg_id,
                "items_count": len(items),
                "source_counts": source_counts,
                "vault_saved": saved_count,
            }
        except Exception as e:
            logger.error(f"run_trend_digest failed: {e}")
            return {"success": False, "error": str(e)}

    def run_weekly_knowledge(self) -> dict:
        """Execute weekly knowledge pipeline (vault scan → tag analysis → report → Telegram + email)."""
        try:
            from .briefing_composer import compose_weekly_knowledge, compose_weekly_knowledge_email
            from .knowledge_scanner import (
                analyze_tag_connections,
                load_previous_weekly_reports,
                save_project_ideas,
                save_weekly_report,
                scan_recent_notes,
            )

            notes = scan_recent_notes(self.config, days=7)
            if not notes:
                return {"success": True, "message": "No knowledge notes this week — skipped", "notes_count": 0}

            previous_report = ""
            if self.config.vault_path:
                previous_report = load_previous_weekly_reports(self.config.vault_path, weeks=4)

            tag_data = analyze_tag_connections(notes)
            tag_analysis_parts = []
            for conn in tag_data["connections"]:
                tag_analysis_parts.append(
                    f"- \"{conn['note1']}\" \u2194 \"{conn['note2']}\" "
                    f"(\uacf5\ud1b5 \ud0dc\uadf8: {', '.join(conn['shared_tags'])})"
                )
            for tag, titles in tag_data["popular_tags"]:
                tag_analysis_parts.append(
                    f"- \ud0dc\uadf8 '{tag}': {', '.join(titles[:3])}{'...' if len(titles) > 3 else ''}"
                )
            tag_analysis = "\n".join(tag_analysis_parts) if tag_analysis_parts else ""

            knowledge_summary = self.summarizer.summarize_weekly_knowledge(
                notes, self.config.project_context,
                previous_report=previous_report, tag_analysis=tag_analysis,
            )

            message = compose_weekly_knowledge(
                knowledge_summary=knowledge_summary,
                notes=notes,
                data_source_status={"knowledge": True},
            )
            msg_id = self._send_briefing(message, "knowledge")

            email_sent = False
            if self.config.personal_gmail_refresh_token and self.config.knowledge_email_to:
                try:
                    now = datetime.now(KST)
                    email_html = compose_weekly_knowledge_email(knowledge_summary, notes)
                    self.email_sender.send_html(
                        to=self.config.knowledge_email_to,
                        subject=f"Weekly Knowledge Report \u2014 {now.strftime('%Y-%m-%d')}",
                        html_body=email_html,
                    )
                    email_sent = True
                except Exception as e:
                    logger.error(f"Knowledge email failed: {e}")

            if knowledge_summary and self.config.vault_path:
                try:
                    now = datetime.now(KST)
                    save_weekly_report(self.config.vault_path, knowledge_summary, now.strftime("%Y-%m-%d"))
                except Exception as e:
                    logger.error(f"Weekly report save failed: {e}")

            if knowledge_summary and self.config.vault_path:
                try:
                    now = datetime.now(KST)
                    save_project_ideas(
                        self.config.vault_path,
                        knowledge_summary,
                        now.strftime("%Y-%m-%d"),
                        ideas_file=self.config.ideas_file,
                    )
                except Exception as e:
                    logger.error(f"Project ideas save failed: {e}")

            return {
                "success": True,
                "message": f"Weekly knowledge report sent ({len(notes)} notes)",
                "message_id": msg_id,
                "notes_count": len(notes),
                "email_sent": email_sent,
            }
        except Exception as e:
            logger.error(f"run_weekly_knowledge failed: {e}")
            return {"success": False, "error": str(e)}

    def run_linkedin_draft(self) -> dict:
        """Execute LinkedIn draft pipeline (all vault notes + optional trends → draft → Telegram)."""
        try:
            from .briefing_composer import compose_linkedin_draft
            from .knowledge_scanner import scan_all_notes
            from .trend_fetcher import fetch_all_trends

            notes = scan_all_notes(self.config)
            if not notes:
                return {"success": True, "message": "No notes in vault — skipped", "notes_count": 0}

            trend_summary = None
            try:
                items = fetch_all_trends(self.config)
                if items:
                    trend_summary = self.summarizer.summarize_trend_digest(items, self.config.project_context)
            except Exception as e:
                logger.warning(f"Trend fetch for LinkedIn draft failed (continuing without): {e}")

            draft = self.summarizer.generate_linkedin_draft(notes, trend_summary, self.config.project_context)

            has_trends = trend_summary is not None
            message = compose_linkedin_draft(
                draft_text=draft,
                note_count=len(notes),
                has_trends=has_trends,
                data_source_status={"vault": True, "trends": has_trends},
            )
            msg_id = self._send_briefing(message, "linkedin")
            return {
                "success": True,
                "message": f"LinkedIn draft sent ({len(notes)} notes used)",
                "message_id": msg_id,
                "notes_count": len(notes),
                "has_trends": has_trends,
            }
        except Exception as e:
            logger.error(f"run_linkedin_draft failed: {e}")
            return {"success": False, "error": str(e)}

    def run_meta_review(self) -> dict:
        """Execute monthly meta review pipeline (stats → summarize → Telegram + email)."""
        try:
            from .briefing_composer import compose_meta_review_email, compose_meta_review_telegram
            from .meta_reviewer import collect_monthly_stats

            stats = collect_monthly_stats(self.config, days=30)
            if stats["total_notes"] == 0:
                return {"success": True, "message": "No notes in last 30 days — skipped", "total_notes": 0}

            meta_summary = self.summarizer.summarize_meta_review(stats, self.config.project_context)

            tg_message = compose_meta_review_telegram(meta_summary, stats)
            msg_id = self._send_briefing(tg_message, "meta")

            email_sent = False
            if self.config.personal_gmail_refresh_token and self.config.knowledge_email_to:
                try:
                    now = datetime.now(KST)
                    email_html = compose_meta_review_email(meta_summary, stats)
                    self.email_sender.send_html(
                        to=self.config.knowledge_email_to,
                        subject=f"Monthly Meta Review \u2014 {now.strftime('%Y-%m')}",
                        html_body=email_html,
                    )
                    email_sent = True
                except Exception as e:
                    logger.error(f"Meta review email failed: {e}")

            return {
                "success": True,
                "message": f"Meta review sent ({stats['total_notes']} notes)",
                "message_id": msg_id,
                "total_notes": stats["total_notes"],
                "email_sent": email_sent,
            }
        except Exception as e:
            logger.error(f"run_meta_review failed: {e}")
            return {"success": False, "error": str(e)}

    def run_weekly(self) -> dict:
        """Execute weekly digest pipeline (meetings + email stats + next week preview)."""
        try:
            from .briefing_composer import compose_weekly
            from .gmail_client import GmailClient

            now = datetime.now(KST)
            monday = (now - timedelta(days=now.weekday())).date()
            friday = monday + timedelta(days=4)
            next_monday = monday + timedelta(days=7)
            next_friday = next_monday + timedelta(days=4)

            week_meetings, cal_status = self.cal_svc.fetch_week_events(monday, friday)

            email_stats = {"personal": 0, "work": 0}
            email_status = {"gmail": True}
            monday_str = monday.strftime("%Y/%m/%d")
            for key, token in [
                ("personal", self.config.personal_gmail_refresh_token),
                ("work", self.config.work_gmail_refresh_token),
            ]:
                if not token:
                    continue
                try:
                    gmail = GmailClient(token, self.config.google_client_id, self.config.google_client_secret)
                    query = f"label:digest-processed after:{monday_str}"
                    email_stats[key] = gmail.count_by_query(query)
                except Exception as e:
                    logger.error(f"Weekly email stats error ({key}): {e}")
                    email_status["gmail"] = False

            next_week_events, _ = self.cal_svc.fetch_week_events(next_monday, next_friday)

            meeting_count = sum(d.get("total_count", 0) for _, d in week_meetings)
            all_next_week = []
            for _, data in next_week_events:
                all_next_week.extend(data.get("events", []))
            weekly_summary = self.summarizer.summarize_weekly(email_stats, meeting_count, all_next_week)

            data_source_status = {**email_status, **cal_status}

            message = compose_weekly(
                week_meetings=week_meetings,
                email_stats=email_stats,
                next_week_events=next_week_events,
                weekly_summary=weekly_summary,
                data_source_status=data_source_status,
            )
            msg_id = self._send_briefing(message, "weekly")
            return {
                "success": True,
                "message": "Weekly digest sent",
                "message_id": msg_id,
                "meeting_count": meeting_count,
                "email_stats": email_stats,
            }
        except Exception as e:
            logger.error(f"run_weekly failed: {e}")
            return {"success": False, "error": str(e)}

    def run_topic_summary(self, category: str, notes: list) -> dict:
        """Generate a focused analysis for a topic cluster.

        Called when 3+ articles are saved in the same category within a day.
        Uses the focused_topic.txt prompt template.
        """
        try:
            notes_lines = []
            for n in notes:
                title = n.get("title", "")
                desc = n.get("description", "")
                notes_lines.append(f"- {title}: {desc}" if desc else f"- {title}")
            notes_text = "\n".join(notes_lines)

            from .briefing_composer import compose_focused_analysis

            summary = self.summarizer.generate_from_template(
                "focused_topic",
                topic=category,
                notes_text=notes_text,
                note_count=len(notes),
            )

            message = compose_focused_analysis(category, summary, notes)
            msg_id = self._send_briefing(message, "topic")
            return {
                "success": True,
                "category": category,
                "notes_count": len(notes),
                "message": "Topic summary sent",
                "message_id": msg_id,
            }
        except Exception as e:
            logger.error(f"run_topic_summary failed: {e}")
            return {"success": False, "error": str(e)}

    def run_article_suggestions(self, weak_categories: list, category_stats: dict) -> dict:
        """Suggest articles to fill knowledge gaps in weak categories.

        Called when knowledge report is skipped due to empty week.
        Fetches current trends and recommends relevant articles.
        """
        try:
            from .trend_fetcher import fetch_all_trends

            trends = fetch_all_trends(self.config)

            trend_lines = []
            for item in trends:
                trend_lines.append(f"- [{item.get('source', '')}] {item['title']}")
            trend_items_text = "\n".join(trend_lines) if trend_lines else "수집된 트렌드 없음"

            weak_text = ", ".join(weak_categories) if weak_categories else "없음"
            stats_lines = [f"- {cat}: {count}건" for cat, count in category_stats.items()]
            stats_text = "\n".join(stats_lines) if stats_lines else "데이터 없음"

            from .briefing_composer import compose_article_suggestions

            suggestion = self.summarizer.generate_from_template(
                "article_suggestions",
                weak_categories=weak_text,
                trend_items=trend_items_text,
                category_stats=stats_text,
            )

            message = compose_article_suggestions(suggestion, weak_categories)
            msg_id = self._send_briefing(message, "article_suggestions")
            return {
                "success": True,
                "message_id": msg_id,
                "suggestions_count": len(trends),
                "weak_categories": weak_categories,
            }
        except Exception as e:
            logger.error(f"run_article_suggestions failed: {e}")
            return {"success": False, "error": str(e)}

    def send_skip_notification(self, reason: str, details: str = None) -> dict:
        """Notify user that a scheduled action was skipped and why.

        Reasons: "no_new_notes", "no_trends", "consecutive_failures"
        """
        try:
            reason_messages = {
                "no_new_notes": "📋 이번 주 새로운 노트가 없어 주간 지식 보고서를 건너뛰었습니다.",
                "no_trends": "📰 트렌드 항목을 가져오지 못해 트렌드 다이제스트를 건너뛰었습니다.",
                "consecutive_failures": f"⚠️ {details}에서 연속 3회 실패가 발생했습니다.",
            }
            message = reason_messages.get(reason, f"⚠️ 알 수 없는 이유로 작업을 건너뛰었습니다: {reason}")
            if details and reason != "consecutive_failures":
                message += f"\n\n상세: {details}"

            self.channel.send_plain(message)
            return {"success": True, "reason": reason}
        except Exception as e:
            logger.error(f"send_skip_notification failed: {e}")
            return {"success": False, "error": str(e)}

    def check_duplicate_url(self, url: str) -> dict | None:
        """Check if a URL has already been saved to the vault.

        Scans vault files' frontmatter for matching source URL.
        Returns save info if duplicate found, None otherwise.
        """
        try:
            import os
            from .knowledge_scanner import _detect_category

            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            category = _detect_category(domain, "", "")

            category_paths = {
                "ai-eng": "10_Knowledge/References/AI Engineering",
                "ai-tool": "10_Knowledge/References/AI Tools",
                "business": "10_Knowledge/References/Business",
                "engineering": "10_Knowledge/References/Engineering",
                "marketing": "10_Knowledge/References/Marketing",
            }
            rel_path = category_paths.get(category, "00_Inbox/Read Later")
            scan_dir = os.path.join(self.config.vault_path, rel_path)

            if not os.path.isdir(scan_dir):
                return None

            for filename in os.listdir(scan_dir):
                if not filename.endswith(".md"):
                    continue
                filepath = os.path.join(scan_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        head = [next(f) for _ in range(10)]
                except (StopIteration, OSError):
                    continue

                saved_date = None
                found = False
                for line in head:
                    if line.strip() == f"source: {url}":
                        found = True
                    if line.startswith("saved:"):
                        saved_date = line.partition(":")[2].strip()
                if found:
                    logger.debug(f"Duplicate URL found: {url} in {filepath}")
                    return {"duplicate": True, "saved_date": saved_date, "file_path": filepath}

            return None
        except Exception as e:
            logger.error(f"check_duplicate_url failed: {e}")
            return None

    def get_related_notes(self, category: str, exclude_url: str = None, limit: int = 3) -> list:
        """Find related notes in the vault for a given category.

        Used for context-aware Telegram responses after URL save.
        Returns list of {title, saved_date} dicts.
        """
        try:
            from .knowledge_scanner import scan_recent_notes

            notes = scan_recent_notes(self.config, days=7)
            results = []
            for note in notes:
                if note.get("category") != category:
                    continue
                if exclude_url and note.get("source") == exclude_url:
                    continue
                results.append({
                    "title": note.get("title", ""),
                    "saved_date": note.get("saved", ""),
                })
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            logger.error(f"get_related_notes failed: {e}")
            return []

    def run_proactive_suggestion(self, suggestion: dict) -> dict:
        """Generate and send a proactive suggestion based on user preferences."""
        try:
            category = suggestion.get("category", "general")
            days_without = suggestion.get("days_without", 7)

            # Get preference info for prompt
            preferred_text = "N/A"
            recent_positive_text = "N/A"
            if self.memory:
                prefs = self.memory.get_preferred_categories(top_n=5)
                preferred_text = ", ".join(f"{cat} ({score:.1f})" for cat, score in prefs)

            # Get current trends
            current_trends_text = "수집된 트렌드 없음"
            try:
                from .trend_fetcher import fetch_all_trends
                trends = fetch_all_trends(self.config)
                if trends:
                    # Filter trends relevant to the category
                    relevant = [t for t in trends if category.lower() in t.get("title", "").lower()
                               or category.lower() in t.get("source", "").lower()]
                    if not relevant:
                        relevant = trends[:10]  # Fall back to top trends
                    current_trends_text = "\n".join(
                        f"- [{t.get('source', '')}] {t['title']} | {t.get('url', '')}"
                        for t in relevant[:10]
                    )
            except Exception as e:
                logger.warning(f"Trend fetch for proactive suggestion failed: {e}")

            # Generate suggestion using LLM
            suggestion_text = self.summarizer.generate_from_template(
                "proactive_suggestion",
                category=category,
                days_without=days_without,
                preferred_categories=preferred_text,
                recent_positive=recent_positive_text,
                current_trends=current_trends_text,
            )

            # Format and send
            from .briefing_composer import compose_proactive_suggestion
            suggestion_type = suggestion.get("type", "suggest_articles")
            message = compose_proactive_suggestion(suggestion_type, suggestion_text, category)
            msg_id = self._send_briefing(message, "suggestion")

            return {
                "success": True,
                "message": f"Proactive suggestion sent for {category}",
                "message_id": msg_id,
                "category": category,
            }
        except Exception as e:
            logger.error(f"run_proactive_suggestion failed: {e}")
            return {"success": False, "error": str(e)}

    def send_evolution_report(self, results: list) -> dict:
        """Send a summary of self-improvement actions to Telegram."""
        try:
            lines = ["🧬 <b>Evolution Report</b>\n"]

            for r in results:
                rtype = r.get("type", "unknown")
                if not r.get("success"):
                    lines.append(f"❌ {rtype}: {r.get('error', 'unknown error')}")
                    continue

                if rtype == "evolution_config":
                    changes = r.get("changes", [])
                    lines.append(f"⚙️ <b>Config Adjustments</b> ({len(changes)} changes)")
                    for c in changes[:5]:
                        lines.append(f"  • {c.get('action')}: {c.get('reason', '')}")

                elif rtype == "evolution_prompts":
                    actions = r.get("actions", [])
                    for a in actions:
                        action = a.get("action", "")
                        name = a.get("prompt_name", "")
                        if action == "start_experiment":
                            lines.append(f"🧪 Started prompt experiment: {name}")
                        elif action == "promote_variant":
                            lines.append(f"✅ Promoted new prompt: {name} (avg rating: {a.get('avg_rating', 0):.1f})")
                        elif action == "keep_original":
                            lines.append(f"↩️ Kept original prompt: {name} (avg rating: {a.get('avg_rating', 0):.1f})")

                elif rtype == "evolution_ideas":
                    matches = r.get("matches", [])
                    lines.append(f"💡 <b>Ideas Implemented</b> ({len(matches)} matched)")
                    for m in matches[:3]:
                        lines.append(f"  • {m.get('idea_text', '')[:60]}... → {m.get('project', '')}")

            message = "\n".join(lines)
            msg_id = self._send_briefing(message, "evolution")
            return {"success": True, "message_id": msg_id}
        except Exception as e:
            logger.error(f"send_evolution_report failed: {e}")
            return {"success": False, "error": str(e)}
