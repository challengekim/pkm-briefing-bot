"""Telegram message handler with context-aware responses.

Extracted from main.py's process_telegram_saves() to support
Brain-enhanced save responses with related notes and topic triggers.
"""
import re
import logging

from .briefing_composer import escape_html

logger = logging.getLogger(__name__)

URL_RE = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')


class TelegramHandler:
    """Handles Telegram messages with Brain-enhanced responses."""

    def __init__(self, config, brain, telegram, state):
        """
        Args:
            config: Config instance
            brain: Brain instance
            telegram: TelegramSender instance
            state: AgentState instance
        """
        self.config = config
        self.brain = brain
        self.telegram = telegram
        self.state = state
        self._last_update_id = 0

    def poll_and_process(self):
        """Poll Telegram for updates and process them.

        Handles both message updates (URL saves) and callback_query updates (button responses).
        """
        updates = self.telegram.get_updates(offset=self._last_update_id + 1 if self._last_update_id else None)
        if not updates:
            return

        for update in updates:
            update_id = update.get("update_id", 0)
            if update_id > self._last_update_id:
                self._last_update_id = update_id

            # Handle callback queries (inline keyboard responses)
            if "callback_query" in update:
                cb = update["callback_query"]
                cb_chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                if cb_chat_id != str(self.config.telegram_chat_id):
                    continue
                self._handle_callback(cb)
                continue

            # Handle regular messages (URL saves)
            message = update.get("message", {})
            chat_id = str(message.get("chat", {}).get("id", ""))
            if chat_id != str(self.config.telegram_chat_id):
                continue

            text = message.get("text", "")
            if not text:
                continue

            urls = URL_RE.findall(text)
            if not urls:
                continue

            self._handle_urls(urls[:3])  # Max 3 URLs per message

    def _handle_urls(self, urls):
        """Process URL saves with context-aware responses."""
        from .knowledge_scanner import save_url_to_vault
        from .briefing_composer import compose_contextual_save

        for url in urls:
            # Check for duplicates first
            dup_info = self.brain.check_duplicate(url)
            if dup_info:
                self.telegram.send_message(
                    f'📌 이미 저장된 URL입니다 (저장일: {dup_info.get("saved_date", "알 수 없음")})'
                )
                continue

            # Save to vault
            try:
                result = save_url_to_vault(
                    url,
                    self.config.vault_path,
                    self.config.knowledge_scan_paths,
                    summarizer=self.brain.hands.summarizer,
                )
            except Exception as e:
                logger.error("Failed to save URL %s: %s", url, e)
                self.telegram.send_message(f"❌ 저장 실패: {escape_html(str(e))}")
                continue

            if not result:
                self.telegram.send_message("❌ URL을 저장하지 못했습니다.")
                continue

            # Get contextual info from Brain
            ctx = self.brain.on_telegram_save(url, result)

            # Compose context-aware response
            response = compose_contextual_save(
                title=ctx["title"],
                category=ctx["category"],
                related_notes=ctx["related_notes"],
                topic_count=ctx["topic_count"],
                is_trigger=ctx["is_trigger"],
            )

            # If this triggers a focused analysis, add inline keyboard
            if ctx["is_trigger"]:
                keyboard = {
                    "inline_keyboard": [[
                        {"text": "✅ 분석 시작", "callback_data": f"analyze_{ctx['category']}"},
                        {"text": "⏭️ 건너뛰기", "callback_data": "skip_analyze"},
                    ]]
                }
                self.telegram.send_message_with_keyboard(response, keyboard)
            else:
                self.telegram.send_message(response)

    def _handle_callback(self, callback_query):
        """Handle inline keyboard button presses."""
        callback_id = callback_query.get("id")
        data = callback_query.get("data", "")

        # Prompt rating feedback (Phase C — self-improving)
        if data.startswith("rate_"):
            self._handle_rating_callback(callback_query)
            return

        # Engagement feedback (Phase B)
        if data.startswith("eng_"):
            self._handle_engagement_callback(callback_query)
            return

        if data.startswith("analyze_"):
            category = data[len("analyze_"):]
            logger.info("User requested focused analysis for category: %s", category)
            self.telegram.answer_callback_query(callback_id, text="분석을 시작합니다...")
            from .knowledge_scanner import scan_recent_notes
            notes = scan_recent_notes(self.config, days=7)
            category_notes = [n for n in notes if category.lower() in str(n.get("category", "")).lower()]
            result = self.brain.hands.run_topic_summary(category, category_notes)
            if not result.get("success"):
                self.telegram.send_message("❌ 분석 실패: " + escape_html(result.get("error", "알 수 없는 오류")))

        elif data == "skip_analyze":
            self.telegram.answer_callback_query(callback_id, text="건너뛰었습니다")

        elif data.startswith("useful_") or data.startswith("skip_"):
            # Legacy Phase A callbacks (retained for backward compat)
            self.telegram.answer_callback_query(callback_id, text="피드백 감사합니다!")

    def _handle_engagement_callback(self, callback_query: dict):
        """Handle engagement feedback buttons (👍/👎/📌)."""
        callback_id = callback_query.get("id")
        data = callback_query.get("data", "")
        message_id = callback_query.get("message", {}).get("message_id", 0)

        parts = data.split("_", 2)  # ["eng", "p", "trend"]
        if len(parts) != 3:
            self.telegram.answer_callback_query(callback_id, text="⚠️")
            return

        reaction_map = {"p": "positive", "n": "negative", "b": "bookmark"}
        reaction = reaction_map.get(parts[1])
        briefing_type = parts[2]

        if not reaction:
            self.telegram.answer_callback_query(callback_id, text="⚠️")
            return

        # Route through Brain (preserves Brain/Hands separation)
        self.brain.log_engagement(briefing_type, message_id, reaction)

        # Resolve pending engagement tracking
        self.state.resolve_pending_engagement(message_id)
        self.state.save()

        response_text = {
            "positive": "👍 감사합니다!",
            "negative": "👎 피드백 반영됩니다",
            "bookmark": "📌 북마크됨!",
        }
        self.telegram.answer_callback_query(callback_id, text=response_text.get(reaction, "✓"))

    def _handle_rating_callback(self, callback_query: dict):
        """Handle prompt quality rating buttons (⭐1-5)."""
        callback_id = callback_query.get("id")
        data = callback_query.get("data", "")

        parts = data.split("_", 2)  # ["rate", "3", "trend"]
        if len(parts) != 3:
            self.telegram.answer_callback_query(callback_id, text="⚠️")
            return

        try:
            score = int(parts[1])
        except ValueError:
            self.telegram.answer_callback_query(callback_id, text="⚠️")
            return

        if not 1 <= score <= 5:
            self.telegram.answer_callback_query(callback_id, text="⚠️")
            return

        briefing_type = parts[2]
        message_id = callback_query.get("message", {}).get("message_id", 0)

        # Route through Brain → Evolution
        self.brain.log_prompt_rating(briefing_type, score)

        # Resolve pending engagement (rating counts as interaction)
        self.state.resolve_pending_engagement(message_id)
        self.state.save()

        stars = "⭐" * score
        self.telegram.answer_callback_query(callback_id, text=f"{stars} 평가 반영!")
