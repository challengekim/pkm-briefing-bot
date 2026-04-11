"""Brain — decision layer for the Reactive Agent.

Follows Anthropic's Brain/Hand separation pattern:
- Brain contains decision logic only (no I/O)
- Hands contain execution logic only (no decisions)
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


class Brain:
    def __init__(self, config, state, hands, memory=None):
        """
        Args:
            config: Config instance
            state:  AgentState instance
            hands:  Hands instance
            memory: AgentMemory instance (proactive mode only)
        """
        self.config = config
        self.state = state
        self.hands = hands
        self.memory = memory

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def tick(self, scheduled_action: str = None) -> list:
        """Main entry point — called by scheduler instead of process_*().

        Args:
            scheduled_action: What was originally scheduled to run
                (e.g. "trend", "knowledge", "morning", "evening",
                "linkedin", "meta", "weekly",
                "__check_deferred", "__evolution_check")

        Returns: list of result dicts from executed actions
        """
        # Handle evolution check (self-improving mode)
        if scheduled_action == "__evolution_check":
            return self._run_evolution()

        # Handle deferred check
        if scheduled_action == "__check_deferred":
            self.check_expired_engagements()
            if not self.state.deferred_actions:
                return []  # Guard: skip if nothing deferred
            ready = self.state.get_ready_deferred()
            if not ready:
                return []
            results = []
            for action in ready:
                logger.info("Brain: executing deferred action type=%s", action.get("type"))
                result = self.act(action)
                results.append(result)
                if result.get("success"):
                    self.state.log_action(action["type"])
                    if result.get("message_id"):
                        self.track_sent_briefing(action["type"], result["message_id"])
                else:
                    self.state.log_failure(action.get("type", "unknown"))
            self.state.save()
            return results

        # Normal flow
        context = self.observe()
        actions = self.decide(context, scheduled_action)

        if not actions:
            logger.info("Brain: no actions to take (scheduled=%s)", scheduled_action)
            return []

        results = []
        for action in actions:
            # Timing gate for proactive mode (only defer the scheduled action itself)
            if scheduled_action and action.get("type") == scheduled_action and self._should_defer_for_timing(scheduled_action):
                optimal = self.memory.get_optimal_send_time(scheduled_action)
                logger.info("Brain: deferring %s to optimal hour %.1f", scheduled_action, optimal)
                self.state.defer_action(action, optimal)
                self.state.save()
                continue

            logger.info("Brain: executing action type=%s", action.get("type"))
            result = self.act(action)
            results.append(result)

            if result.get("success"):
                self.state.log_action(action["type"])
                if result.get("message_id"):
                    self.track_sent_briefing(action["type"], result["message_id"])
            else:
                self.state.log_failure(action.get("type", "unknown"))

        self.state.save()
        return results

    def _should_defer_for_timing(self, scheduled_action: str) -> bool:
        """Check if action should be deferred to a better time (proactive/self-improving mode)."""
        if self.config.agent_mode not in ("proactive", "self-improving") or self.memory is None:
            return False

        optimal_hour = self.memory.get_optimal_send_time(scheduled_action)
        if optimal_hour is None:
            return False  # Not enough data

        now = datetime.now(KST)
        current_hour = now.hour + now.minute / 60.0

        # Defer if more than 15 minutes before optimal time
        if current_hour < optimal_hour - 0.25:
            return True
        return False

    # ------------------------------------------------------------------
    # Observe
    # ------------------------------------------------------------------

    def observe(self) -> dict:
        """Gather current state without side effects."""
        from .knowledge_scanner import scan_recent_notes  # lazy import

        recent_notes = []
        try:
            recent_notes = scan_recent_notes(self.config, days=7)
        except Exception as e:
            logger.warning("Brain.observe: vault scan failed: %s", e)

        context = {
            "recent_saves_count": len(self.state.get_recent_saves(hours=24)),
            "saves_by_category": self.state.get_saves_by_category(days=1),
            "days_since": {
                "knowledge": self.state.days_since_action("knowledge"),
                "trend": self.state.days_since_action("trend"),
                "linkedin": self.state.days_since_action("linkedin"),
                "meta": self.state.days_since_action("meta"),
            },
            "vault_recent_notes": recent_notes,
            "vault_note_count": len(recent_notes),
            "has_notes_this_week": len(recent_notes) > 0,
            "failure_counts": {
                "trend": self.state.get_failure_count("trend"),
            },
        }

        # Enrich with memory data (proactive mode)
        if self.memory:
            context["preferred_categories"] = self.memory.get_preferred_categories()
            context["source_rankings"] = self.memory.get_source_rankings()
            context["engagement_stats"] = self.memory.get_engagement_stats(days=7)

        return context

    # ------------------------------------------------------------------
    # Decide
    # ------------------------------------------------------------------

    def decide(self, context: dict, scheduled_action: str = None) -> list:
        """Rule-based decision engine. Returns list of action dicts.

        Rules:
        1. Topic clustering: 3+ saves in the same category today → topic_summary
        2. Empty week: no notes + knowledge day → skip + suggest articles
        3. Proactive suggestions (proactive mode only): category gap detection
        4. Scheduled passthrough: run the scheduled action as-is
        """
        actions = []

        # Rule 1: topic clustering trigger
        for category, count in context["saves_by_category"].items():
            if count >= 3:
                notes = [
                    n for n in context["vault_recent_notes"]
                    if self._note_matches_category(n, category)
                ]
                logger.info(
                    "Brain.decide: topic cluster detected category=%s count=%d notes=%d",
                    category, count, len(notes),
                )
                actions.append({
                    "type": "topic_summary",
                    "category": category,
                    "notes": notes,
                    "save_count": count,
                })

        # Rule 2: empty week → skip knowledge, suggest articles instead
        if scheduled_action == "knowledge" and not context["has_notes_this_week"]:
            category_stats = self._get_category_stats(context["vault_recent_notes"])
            weak_categories = [cat for cat, cnt in category_stats.items() if cnt < 3]
            if not weak_categories:
                weak_categories = ["general"]

            logger.info(
                "Brain.decide: no notes this week — skipping knowledge, suggesting articles "
                "(weak=%s)", weak_categories,
            )
            actions.append({
                "type": "skip_knowledge",
                "reason": "no_new_notes",
                "weak_categories": weak_categories,
                "category_stats": category_stats,
            })
            return actions  # don't also queue the normal knowledge report

        # Rule 3: Proactive suggestions (proactive/self-improving mode)
        if self.config.agent_mode in ("proactive", "self-improving") and self._can_send_proactive_suggestion():
            gaps = self._detect_category_gaps(context)
            if gaps:
                actions.extend(gaps)

        # Rule 4: passthrough scheduled action
        if scheduled_action:
            logger.info("Brain.decide: passthrough scheduled_action=%s", scheduled_action)
            actions.append({"type": scheduled_action})

        return actions

    # ------------------------------------------------------------------
    # Act
    # ------------------------------------------------------------------

    def act(self, action: dict) -> dict:
        """Execute an action via Hands. Returns result dict."""
        action_type = action["type"]

        try:
            # Existing pipeline wrappers
            if action_type == "morning":
                return self.hands.run_morning_briefing()
            elif action_type == "evening":
                return self.hands.run_evening_review()
            elif action_type == "trend":
                result = self.hands.run_trend_digest()
                if not result.get("success") or result.get("items_count", 0) == 0:
                    failures = self.state.get_failure_count("trend") + 1
                    if failures >= 3:
                        self.hands.send_skip_notification(
                            "consecutive_failures",
                            details="트렌드 다이제스트",
                        )
                return result
            elif action_type == "knowledge":
                return self.hands.run_weekly_knowledge()
            elif action_type == "linkedin":
                return self.hands.run_linkedin_draft()
            elif action_type == "meta":
                return self.hands.run_meta_review()
            elif action_type == "weekly":
                return self.hands.run_weekly()

            # New capabilities
            elif action_type == "topic_summary":
                return self.hands.run_topic_summary(
                    action["category"], action.get("notes", [])
                )
            elif action_type == "skip_knowledge":
                self.hands.send_skip_notification(action["reason"])
                return self.hands.run_article_suggestions(
                    action.get("weak_categories", []),
                    action.get("category_stats", {}),
                )
            elif action_type == "suggest_articles":
                result = self.hands.run_proactive_suggestion(action)
                if result.get("success"):
                    self.state.log_action("proactive_suggestion")
                return result

            else:
                logger.warning("Brain.act: unknown action type: %s", action_type)
                return {"success": False, "error": f"Unknown action: {action_type}"}

        except Exception as e:
            logger.error("Brain.act failed for %s: %s", action_type, e)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Telegram save integration
    # ------------------------------------------------------------------

    def on_telegram_save(self, url: str, save_result: dict) -> dict:
        """Called after a URL is saved via Telegram. Updates state and returns context."""
        category = save_result.get("category", "unknown")
        title = save_result.get("title", "")

        self.state.log_save(url, category, title)
        self.state.save()

        return self.contextualize_save(url, save_result)

    def contextualize_save(self, url: str, save_result: dict) -> dict:
        """Generate context-aware information for a Telegram save response.

        Returns dict with related_notes, topic_count, is_trigger, title, category.
        """
        category = save_result.get("category", "unknown")
        title = save_result.get("title", "")

        related_notes = self.hands.get_related_notes(category, exclude_url=url, limit=3)

        saves_by_cat = self.state.get_saves_by_category(days=1)
        topic_count = saves_by_cat.get(category, 0)
        is_trigger = topic_count >= 3

        return {
            "title": title,
            "category": category,
            "related_notes": related_notes,
            "topic_count": topic_count,
            "is_trigger": is_trigger,
        }

    # ------------------------------------------------------------------
    # Engagement tracking (Phase B)
    # ------------------------------------------------------------------

    def log_engagement(self, briefing_type: str, message_id: int, reaction: str):
        """Log user engagement and update preferences. Called by TelegramHandler."""
        if self.memory is None:
            return

        self.memory.log_engagement(briefing_type, message_id, reaction)

        # Update reading time based on when user reacted
        now = datetime.now(KST)
        read_hour = now.hour + now.minute / 60.0
        self.memory.update_reading_time(briefing_type, read_hour)

        self.memory.save()

    def log_prompt_rating(self, briefing_type: str, score: int):
        """Log a user's prompt quality rating. Called by TelegramHandler."""
        if self.config.agent_mode != "self-improving" or self.memory is None:
            return
        from .evolution import Evolution
        evo = Evolution(self.config, self.memory)
        evo.record_prompt_rating(briefing_type, score)

    def track_sent_briefing(self, briefing_type: str, message_id: int):
        """Track that a briefing was sent, for later ignored-detection."""
        if self.memory is None:
            return
        self.state.pending_engagements.append({
            "briefing_type": briefing_type,
            "message_id": message_id,
            "sent_at": datetime.now(KST).isoformat(),
        })
        self.state.save()

    def check_expired_engagements(self):
        """Check for briefings that were sent 24+ hours ago with no response. Log as ignored."""
        if self.memory is None:
            return
        pending = self.state.pending_engagements
        if not pending:
            return

        from .agent_state import _parse_dt

        now = datetime.now(KST)
        still_pending = []
        for p in pending:
            sent_at = _parse_dt(p["sent_at"])
            if (now - sent_at).total_seconds() > 86400:  # 24 hours
                self.memory.log_engagement(p["briefing_type"], p["message_id"], "ignored")
            else:
                still_pending.append(p)

        if len(still_pending) != len(pending):
            self.state.pending_engagements = still_pending
            self.memory.save()
            self.state.save()

    # ------------------------------------------------------------------
    # Duplicate check (called before save)
    # ------------------------------------------------------------------

    def check_duplicate(self, url: str) -> dict | None:
        """Check if URL was already saved. Returns info dict or None."""
        if self.state.is_duplicate_url(url):
            return self.hands.check_duplicate_url(url)
        return None

    # ------------------------------------------------------------------
    # Evolution (self-improving mode)
    # ------------------------------------------------------------------

    def _run_evolution(self) -> list:
        """Run the self-improvement cycle. Only in self-improving mode."""
        if self.config.agent_mode != "self-improving":
            return []
        if self.memory is None:
            return []

        from .evolution import Evolution

        evo = Evolution(self.config, self.memory)
        results = []

        # 1. Config auto-adjustment (source scores, schedules, subreddits)
        try:
            config_changes = evo.evaluate_and_adjust()
            if config_changes:
                results.append({
                    "success": True,
                    "type": "evolution_config",
                    "changes": config_changes,
                })
        except Exception as e:
            logger.error("Evolution config adjustment failed: %s", e)
            results.append({"success": False, "type": "evolution_config", "error": str(e)})

        # 2. Prompt evolution (sequential experiment + rating)
        try:
            prompt_results = evo.evolve_prompts()
            if prompt_results:
                results.append({
                    "success": True,
                    "type": "evolution_prompts",
                    "actions": prompt_results,
                })
        except Exception as e:
            logger.error("Evolution prompt evolution failed: %s", e)
            results.append({"success": False, "type": "evolution_prompts", "error": str(e)})

        # 3. Idea-to-implementation tracking
        try:
            idea_matches = evo.track_idea_outcomes()
            if idea_matches:
                results.append({
                    "success": True,
                    "type": "evolution_ideas",
                    "matches": idea_matches,
                })
        except Exception as e:
            logger.error("Evolution idea tracking failed: %s", e)
            results.append({"success": False, "type": "evolution_ideas", "error": str(e)})

        # Send evolution report if anything happened
        if results:
            try:
                self.hands.send_evolution_report(results)
            except Exception as e:
                logger.error("Failed to send evolution report: %s", e)

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_category_gaps(self, context: dict) -> list:
        """Find categories user likes but hasn't engaged with recently."""
        if self.memory is None:
            return []

        from .agent_state import _parse_dt

        preferred = self.memory.get_preferred_categories(top_n=10)
        gap_days = self.config.agent_gap_detection_days
        saves_by_cat = self.state.get_saves_by_category(days=gap_days)

        # Get a thread-safe snapshot of engagement log
        engagement_snapshot = self.memory.get_engagement_log_snapshot()
        now = datetime.now(KST)

        gaps = []
        for category, score in preferred:
            if score < 0.5:
                continue  # Only suggest for categories with real interest

            has_recent_saves = saves_by_cat.get(category, 0) > 0

            # Check engagement for THIS specific category's briefing type
            has_recent_engagement = False
            for entry in engagement_snapshot:
                if entry.get("reaction") not in ("positive", "bookmark"):
                    continue
                if entry.get("briefing_type") != category:
                    continue
                raw_ts = entry.get("reacted_at", "")
                if not raw_ts:
                    continue
                try:
                    entry_time = _parse_dt(raw_ts)
                    if (now - entry_time).days <= gap_days:
                        has_recent_engagement = True
                        break
                except Exception:
                    continue

            if not has_recent_saves and not has_recent_engagement:
                gaps.append({
                    "type": "suggest_articles",
                    "category": category,
                    "preference_score": score,
                    "days_without": gap_days,
                })

        return gaps[:1]  # Max 1 gap suggestion per check

    def _can_send_proactive_suggestion(self) -> bool:
        """Check if enough time has passed since last proactive suggestion."""
        last = self.state.last_actions.get("proactive_suggestion")
        if not last:
            # First-time check: don't fire immediately on mode switch
            # Require at least 3 days of proactive mode history
            first_engagement = None
            if self.memory:
                snapshot = self.memory.get_engagement_log_snapshot()
                if snapshot:
                    first_engagement = snapshot[0].get("reacted_at")
            if not first_engagement:
                return False  # No engagement history = just switched to proactive

            from .agent_state import _parse_dt, _now_kst
            first_dt = _parse_dt(first_engagement)
            if (_now_kst() - first_dt).days < 3:
                return False  # Less than 3 days of history
            return True

        cooldown_days = max(1, self.config.agent_suggestion_cooldown_hours // 24)
        return self.state.days_since_action("proactive_suggestion") >= cooldown_days

    def _note_matches_category(self, note: dict, category: str) -> bool:
        """Check if a vault note belongs to the given category."""
        note_cat = note.get("category", "")
        if note_cat and category.lower() in note_cat.lower():
            return True
        # Fallback: check source URL or tags
        source = note.get("source", "")
        if source and category.lower().replace("-", " ") in source.lower():
            return True
        return False

    def _get_category_stats(self, notes: list) -> dict:
        """Count notes per category from vault scan results."""
        stats: dict = {}
        for note in notes:
            cat = note.get("category", "uncategorized")
            stats[cat] = stats.get(cat, 0) + 1
        return stats
