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
            if urls:
                self._handle_urls(urls[:3])  # Max 3 URLs per message
            elif text.startswith("/"):
                self._handle_command(text)
            else:
                self._handle_question(text)

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

    def _handle_command(self, text: str):
        """Handle slash commands."""
        cmd = text.split()[0].lower()
        if cmd == "/status":
            status = self._get_status_text()
            self.telegram.send_message(status)
        elif cmd == "/report":
            self.telegram.send_message("📊 분석을 시작합니다...")
            try:
                result = self.brain.hands.run_weekly_knowledge()
                if not result.get("success", True):
                    self.telegram.send_message("❌ 분석 실패")
            except Exception as e:
                self.telegram.send_message(f"❌ 오류: {escape_html(str(e))}")
        elif cmd == "/help":
            help_text = (
                "📋 <b>사용 가능한 명령어</b>\n\n"
                "/status — 에이전트 상태 확인\n"
                "/report — 주간 분석 즉시 실행\n"
                "/help — 이 도움말\n\n"
                "💬 텍스트를 보내면 vault에서 관련 내용을 검색합니다.\n"
                "🔗 URL을 보내면 vault에 저장합니다."
            )
            self.telegram.send_message(help_text)

    def _handle_question(self, text: str):
        """Handle natural language questions by searching vault."""
        from .vault_search import search_vault, synthesize_answer

        try:
            results = search_vault(self.config, text, max_results=5)
            if not results:
                self.telegram.send_message("🔍 관련 노트를 찾지 못했습니다.")
                return

            answer = synthesize_answer(self.brain.hands.summarizer, text, results)

            sources = "\n".join(
                f"  📄 {escape_html(r.get('title', 'Untitled'))}"
                for r in results[:3]
            )
            response = f"💡 {escape_html(answer)}\n\n<b>참고 노트:</b>\n{sources}"
            self.telegram.send_message(response)
        except Exception as e:
            logger.error("Question handling failed: %s", e)
            self.telegram.send_message(f"❌ 질문 처리 실패: {escape_html(str(e))}")

    def _get_status_text(self) -> str:
        """Build agent status text."""
        mode = self.config.agent_mode
        state_name = self.state.current_state if hasattr(self.state, 'current_state') else 'unknown'

        mem_stats = ""
        if hasattr(self.brain, 'memory') and self.brain.memory:
            engagement = self.brain.memory.get_engagement_stats(days=7)
            cats = self.brain.memory.get_preferred_categories(top_n=3)
            cat_text = ", ".join(f"{c}({s:.1f})" for c, s in cats) if cats else "없음"
            mem_stats = (
                f"\n📊 7일 참여: {engagement.get('total', 0)}건 "
                f"(참여율 {engagement.get('engagement_rate', 0):.0%})"
                f"\n🏷️ 관심 카테고리: {cat_text}"
            )

        return (
            f"🤖 <b>Agent Status</b>\n"
            f"모드: {escape_html(mode)}\n"
            f"상태: {escape_html(state_name)}"
            f"{mem_stats}"
        )

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
