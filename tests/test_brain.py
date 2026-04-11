"""Tests for Brain — decision and dispatch layer."""
import pytest
from unittest.mock import MagicMock, patch

from compound_agent.brain import Brain


class TestBrainDecide:
    def setup_method(self):
        self.config = MagicMock()
        self.state = MagicMock()
        self.hands = MagicMock()
        self.brain = Brain(self.config, self.state, self.hands)

    def _base_context(self, overrides=None):
        ctx = {
            "saves_by_category": {},
            "has_notes_this_week": True,
            "vault_recent_notes": [],
            "recent_saves_count": 0,
            "vault_note_count": 0,
            "days_since": {"knowledge": 7, "trend": 1, "linkedin": 14, "meta": 30},
            "failure_counts": {"trend": 0},
        }
        if overrides:
            ctx.update(overrides)
        return ctx

    def test_topic_cluster_triggers_summary_when_three_saves_in_category(self):
        """3+ saves in same category triggers topic_summary action."""
        context = self._base_context({
            "saves_by_category": {"ai-eng": 3},
            "vault_recent_notes": [
                {"title": "Note1", "category": "ai-eng"},
                {"title": "Note2", "category": "ai-eng"},
            ],
        })
        actions = self.brain.decide(context, scheduled_action=None)
        assert any(a["type"] == "topic_summary" for a in actions)

    def test_topic_cluster_action_contains_category_and_notes(self):
        """topic_summary action includes category and matching notes."""
        context = self._base_context({
            "saves_by_category": {"ai-eng": 3},
            "vault_recent_notes": [
                {"title": "Note1", "category": "ai-eng"},
                {"title": "Note2", "category": "ai-eng"},
            ],
        })
        actions = self.brain.decide(context, scheduled_action=None)
        summary = next(a for a in actions if a["type"] == "topic_summary")
        assert summary["category"] == "ai-eng"
        assert len(summary["notes"]) == 2
        assert summary["save_count"] == 3

    def test_topic_cluster_does_not_fire_below_threshold(self):
        """2 saves in same category does not trigger topic_summary."""
        context = self._base_context({
            "saves_by_category": {"ai-eng": 2},
            "vault_recent_notes": [{"title": "Note1", "category": "ai-eng"}],
        })
        actions = self.brain.decide(context, scheduled_action=None)
        assert not any(a["type"] == "topic_summary" for a in actions)

    def test_empty_week_with_knowledge_scheduled_returns_skip(self):
        """No notes this week + knowledge scheduled → skip_knowledge action."""
        context = self._base_context({
            "saves_by_category": {},
            "has_notes_this_week": False,
            "vault_recent_notes": [],
        })
        actions = self.brain.decide(context, scheduled_action="knowledge")
        assert len(actions) == 1
        assert actions[0]["type"] == "skip_knowledge"
        assert actions[0]["reason"] == "no_new_notes"

    def test_empty_week_skip_knowledge_does_not_also_queue_knowledge(self):
        """skip_knowledge short-circuits — no additional knowledge action appended."""
        context = self._base_context({
            "has_notes_this_week": False,
            "vault_recent_notes": [],
        })
        actions = self.brain.decide(context, scheduled_action="knowledge")
        assert not any(a["type"] == "knowledge" for a in actions)

    def test_passthrough_for_scheduled_trend_action(self):
        """Normal scheduled trend action passes through when no rules match."""
        context = self._base_context({
            "vault_recent_notes": [{"title": "Note1", "category": "ai-eng"}],
        })
        actions = self.brain.decide(context, scheduled_action="trend")
        assert actions == [{"type": "trend"}]

    def test_passthrough_for_scheduled_morning_action(self):
        """Normal scheduled morning action passes through unchanged."""
        context = self._base_context()
        actions = self.brain.decide(context, scheduled_action="morning")
        assert actions == [{"type": "morning"}]

    def test_no_actions_when_no_schedule_and_no_triggers(self):
        """No scheduled action and no clustering triggers → empty list."""
        context = self._base_context()
        actions = self.brain.decide(context, scheduled_action=None)
        assert actions == []

    def test_topic_cluster_fires_alongside_scheduled_action(self):
        """topic_summary and a scheduled action can both appear in results."""
        context = self._base_context({
            "saves_by_category": {"ai-eng": 4},
            "vault_recent_notes": [{"title": "Note1", "category": "ai-eng"}],
        })
        actions = self.brain.decide(context, scheduled_action="trend")
        types = [a["type"] for a in actions]
        assert "topic_summary" in types
        assert "trend" in types

    def test_skip_knowledge_includes_weak_categories_from_notes(self):
        """skip_knowledge weak_categories derived from vault notes with low counts."""
        context = self._base_context({
            "has_notes_this_week": False,
            "vault_recent_notes": [
                {"title": "N1", "category": "business"},
                {"title": "N2", "category": "business"},
            ],
        })
        actions = self.brain.decide(context, scheduled_action="knowledge")
        skip = actions[0]
        # business count is 2 < 3, so it should be in weak categories
        assert "business" in skip["weak_categories"]

    def test_skip_knowledge_defaults_to_general_when_no_notes(self):
        """skip_knowledge falls back to 'general' when no note categories exist."""
        context = self._base_context({
            "has_notes_this_week": False,
            "vault_recent_notes": [],
        })
        actions = self.brain.decide(context, scheduled_action="knowledge")
        assert "general" in actions[0]["weak_categories"]


class TestBrainAct:
    def setup_method(self):
        self.config = MagicMock()
        self.state = MagicMock()
        self.hands = MagicMock()
        self.brain = Brain(self.config, self.state, self.hands)

    def test_act_dispatches_trend_to_run_trend_digest(self):
        """act with type=trend calls hands.run_trend_digest."""
        self.hands.run_trend_digest.return_value = {"success": True, "items_count": 5}
        result = self.brain.act({"type": "trend"})
        self.hands.run_trend_digest.assert_called_once()
        assert result["success"] is True

    def test_act_dispatches_knowledge_to_run_weekly_knowledge(self):
        """act with type=knowledge calls hands.run_weekly_knowledge."""
        self.hands.run_weekly_knowledge.return_value = {"success": True}
        result = self.brain.act({"type": "knowledge"})
        self.hands.run_weekly_knowledge.assert_called_once()
        assert result["success"] is True

    def test_act_dispatches_topic_summary_to_run_topic_summary(self):
        """act with type=topic_summary calls hands.run_topic_summary with category and notes."""
        self.hands.run_topic_summary.return_value = {"success": True}
        action = {"type": "topic_summary", "category": "ai-eng", "notes": [{"title": "N1"}]}
        result = self.brain.act(action)
        self.hands.run_topic_summary.assert_called_once_with("ai-eng", [{"title": "N1"}])
        assert result["success"] is True

    def test_act_dispatches_morning_to_run_morning_briefing(self):
        """act with type=morning calls hands.run_morning_briefing."""
        self.hands.run_morning_briefing.return_value = {"success": True}
        result = self.brain.act({"type": "morning"})
        self.hands.run_morning_briefing.assert_called_once()
        assert result["success"] is True

    def test_act_dispatches_evening_to_run_evening_review(self):
        """act with type=evening calls hands.run_evening_review."""
        self.hands.run_evening_review.return_value = {"success": True}
        result = self.brain.act({"type": "evening"})
        self.hands.run_evening_review.assert_called_once()

    def test_act_dispatches_linkedin_to_run_linkedin_draft(self):
        """act with type=linkedin calls hands.run_linkedin_draft."""
        self.hands.run_linkedin_draft.return_value = {"success": True}
        result = self.brain.act({"type": "linkedin"})
        self.hands.run_linkedin_draft.assert_called_once()

    def test_act_dispatches_meta_to_run_meta_review(self):
        """act with type=meta calls hands.run_meta_review."""
        self.hands.run_meta_review.return_value = {"success": True}
        result = self.brain.act({"type": "meta"})
        self.hands.run_meta_review.assert_called_once()

    def test_act_unknown_type_returns_failure_dict(self):
        """Unknown action type returns dict with success=False."""
        result = self.brain.act({"type": "nonexistent_action"})
        assert result["success"] is False
        assert "nonexistent_action" in result["error"]

    def test_act_trend_sends_skip_notification_on_three_consecutive_failures(self):
        """trend act sends skip notification when 3 consecutive failures have occurred."""
        self.hands.run_trend_digest.return_value = {"success": False, "items_count": 0}
        self.state.get_failure_count.return_value = 2  # already 2 failures
        self.brain.act({"type": "trend"})
        self.hands.send_skip_notification.assert_called_once_with(
            "consecutive_failures",
            details="트렌드 다이제스트",
        )

    def test_act_trend_no_skip_notification_below_failure_threshold(self):
        """trend act does not send skip notification when fewer than 3 failures."""
        self.hands.run_trend_digest.return_value = {"success": False, "items_count": 0}
        self.state.get_failure_count.return_value = 1  # only 1 previous failure
        self.brain.act({"type": "trend"})
        self.hands.send_skip_notification.assert_not_called()

    def test_act_skip_knowledge_calls_send_skip_notification_and_article_suggestions(self):
        """act with type=skip_knowledge calls notification and article suggestions."""
        self.hands.send_skip_notification.return_value = {"success": True}
        self.hands.run_article_suggestions.return_value = {"success": True}
        action = {
            "type": "skip_knowledge",
            "reason": "no_new_notes",
            "weak_categories": ["general"],
            "category_stats": {},
        }
        self.brain.act(action)
        self.hands.send_skip_notification.assert_called_once_with("no_new_notes")
        self.hands.run_article_suggestions.assert_called_once_with(["general"], {})

    def test_act_returns_error_dict_when_hands_raises_exception(self):
        """act returns success=False error dict when hands raises an exception."""
        self.hands.run_morning_briefing.side_effect = RuntimeError("boom")
        result = self.brain.act({"type": "morning"})
        assert result["success"] is False
        assert "boom" in result["error"]


class TestBrainTelegramSave:
    def setup_method(self):
        self.config = MagicMock()
        self.state = MagicMock()
        self.hands = MagicMock()
        self.brain = Brain(self.config, self.state, self.hands)

    def test_on_telegram_save_calls_log_save_on_state(self):
        """on_telegram_save calls state.log_save with url, category, title."""
        self.hands.get_related_notes.return_value = []
        self.state.get_saves_by_category.return_value = {"ai-eng": 1}

        self.brain.on_telegram_save("https://test.com", {"title": "Test", "category": "ai-eng"})

        self.state.log_save.assert_called_once_with("https://test.com", "ai-eng", "Test")

    def test_on_telegram_save_calls_state_save(self):
        """on_telegram_save persists state via state.save()."""
        self.hands.get_related_notes.return_value = []
        self.state.get_saves_by_category.return_value = {"ai-eng": 1}

        self.brain.on_telegram_save("https://test.com", {"title": "Test", "category": "ai-eng"})

        self.state.save.assert_called_once()

    def test_on_telegram_save_returns_context_dict(self):
        """on_telegram_save returns dict with is_trigger, category, title."""
        self.hands.get_related_notes.return_value = []
        self.state.get_saves_by_category.return_value = {"ai-eng": 1}

        result = self.brain.on_telegram_save(
            "https://test.com", {"title": "Test", "category": "ai-eng"}
        )
        assert "is_trigger" in result
        assert result["category"] == "ai-eng"
        assert result["title"] == "Test"

    def test_contextualize_save_is_trigger_true_when_three_in_category(self):
        """contextualize_save returns is_trigger=True when saves_by_category >= 3."""
        self.hands.get_related_notes.return_value = []
        self.state.get_saves_by_category.return_value = {"ai-eng": 3}

        result = self.brain.contextualize_save(
            "https://test.com", {"title": "T", "category": "ai-eng"}
        )
        assert result["is_trigger"] is True

    def test_contextualize_save_is_trigger_false_below_threshold(self):
        """contextualize_save returns is_trigger=False when saves_by_category < 3."""
        self.hands.get_related_notes.return_value = []
        self.state.get_saves_by_category.return_value = {"ai-eng": 2}

        result = self.brain.contextualize_save(
            "https://test.com", {"title": "T", "category": "ai-eng"}
        )
        assert result["is_trigger"] is False

    def test_contextualize_save_includes_related_notes(self):
        """contextualize_save includes related_notes from hands.get_related_notes."""
        related = [{"title": "Prior Note", "saved_date": "2026-04-09"}]
        self.hands.get_related_notes.return_value = related
        self.state.get_saves_by_category.return_value = {"ai-eng": 1}

        result = self.brain.contextualize_save(
            "https://test.com", {"title": "T", "category": "ai-eng"}
        )
        assert result["related_notes"] == related

    def test_check_duplicate_returns_none_when_url_not_known(self):
        """check_duplicate returns None when state reports URL is not known."""
        self.state.is_duplicate_url.return_value = False
        result = self.brain.check_duplicate("https://new.com")
        assert result is None
        self.hands.check_duplicate_url.assert_not_called()

    def test_check_duplicate_delegates_to_hands_when_state_knows_url(self):
        """check_duplicate calls hands.check_duplicate_url when state confirms known URL."""
        self.state.is_duplicate_url.return_value = True
        self.hands.check_duplicate_url.return_value = {"duplicate": True, "saved_date": "2026-04-01"}

        result = self.brain.check_duplicate("https://known.com")
        self.hands.check_duplicate_url.assert_called_once_with("https://known.com")
        assert result["duplicate"] is True


class TestBrainTimingGate:
    def setup_method(self):
        self.config = MagicMock()
        self.state = MagicMock()
        self.hands = MagicMock()
        self.brain = Brain(self.config, self.state, self.hands)

    def test_should_defer_returns_false_when_not_proactive(self):
        """_should_defer_for_timing returns False when agent_mode is not proactive."""
        self.config.agent_mode = "reactive"
        self.brain.memory = MagicMock()
        self.brain.memory.get_optimal_send_time.return_value = 23.0
        assert self.brain._should_defer_for_timing("trend") is False

    def test_should_defer_returns_false_when_memory_is_none(self):
        """_should_defer_for_timing returns False when memory is None."""
        self.config.agent_mode = "proactive"
        self.brain.memory = None
        assert self.brain._should_defer_for_timing("trend") is False

    def test_should_defer_returns_false_when_no_optimal_data(self):
        """_should_defer_for_timing returns False when memory has no data for action."""
        self.config.agent_mode = "proactive"
        self.brain.memory = MagicMock()
        self.brain.memory.get_optimal_send_time.return_value = None
        assert self.brain._should_defer_for_timing("trend") is False

    def test_should_defer_returns_true_when_before_optimal_time(self):
        """_should_defer_for_timing returns True when current time is before optimal - 0.25."""
        self.config.agent_mode = "proactive"
        self.brain.memory = MagicMock()
        # Set optimal to a very late hour so current time is always before it
        self.brain.memory.get_optimal_send_time.return_value = 23.9
        # Current time will always be < 23.65, so should defer
        result = self.brain._should_defer_for_timing("trend")
        assert result is True

    def test_should_defer_returns_false_when_at_optimal_time(self):
        """_should_defer_for_timing returns False when current time is at or past optimal."""
        self.config.agent_mode = "proactive"
        self.brain.memory = MagicMock()
        # Set optimal to 0.0 so current time (always > 0) is past optimal - 0.25
        self.brain.memory.get_optimal_send_time.return_value = 0.0
        result = self.brain._should_defer_for_timing("trend")
        assert result is False


class TestBrainDeferredFlow:
    def setup_method(self):
        self.config = MagicMock()
        self.state = MagicMock()
        self.hands = MagicMock()
        self.brain = Brain(self.config, self.state, self.hands)

    def test_check_deferred_with_empty_list_returns_quickly(self):
        """tick with __check_deferred returns [] immediately when no deferred actions."""
        self.state.deferred_actions = []
        result = self.brain.tick(scheduled_action="__check_deferred")
        assert result == []
        self.state.get_ready_deferred.assert_not_called()

    def test_check_deferred_executes_ready_actions(self):
        """tick with __check_deferred executes ready deferred actions."""
        self.state.deferred_actions = [{"type": "trend"}]
        self.state.get_ready_deferred.return_value = [{"type": "trend"}]
        self.hands.run_trend_digest.return_value = {"success": True, "items_count": 3}

        results = self.brain.tick(scheduled_action="__check_deferred")
        assert len(results) == 1
        assert results[0]["success"] is True

    def test_check_deferred_logs_action_on_success(self):
        """tick with __check_deferred calls state.log_action when action succeeds."""
        self.state.deferred_actions = [{"type": "morning"}]
        self.state.get_ready_deferred.return_value = [{"type": "morning"}]
        self.hands.run_morning_briefing.return_value = {"success": True}

        self.brain.tick(scheduled_action="__check_deferred")
        self.state.log_action.assert_called_once_with("morning")

    def test_check_deferred_logs_failure_on_failure(self):
        """tick with __check_deferred calls state.log_failure when action fails."""
        self.state.deferred_actions = [{"type": "morning"}]
        self.state.get_ready_deferred.return_value = [{"type": "morning"}]
        self.hands.run_morning_briefing.return_value = {"success": False, "error": "oops"}

        self.brain.tick(scheduled_action="__check_deferred")
        self.state.log_failure.assert_called_once_with("morning")

    def test_check_deferred_returns_empty_when_no_ready_actions(self):
        """tick with __check_deferred returns [] when deferred list exists but nothing ready."""
        self.state.deferred_actions = [{"type": "trend", "_optimal_hour": 25.0}]
        self.state.get_ready_deferred.return_value = []
        result = self.brain.tick(scheduled_action="__check_deferred")
        assert result == []

    def test_deferred_action_flow_defer_then_get_ready(self):
        """Integration: defer an action via state, then retrieve it when ready."""
        import tempfile, os
        from compound_agent.agent_state import AgentState

        tmpdir = tempfile.mkdtemp()
        real_state = AgentState(os.path.join(tmpdir, "state.json"))
        brain = Brain(self.config, real_state, self.hands)

        # Defer with optimal_hour=0.0 (always ready)
        real_state.defer_action({"type": "morning"}, optimal_hour=0.0)
        assert len(real_state.deferred_actions) == 1

        # Now check_deferred should pick it up
        self.hands.run_morning_briefing.return_value = {"success": True}
        results = brain.tick(scheduled_action="__check_deferred")
        assert len(results) == 1
        assert real_state.deferred_actions == []  # consumed


class TestProactiveDetection:
    def setup_method(self):
        self.config = MagicMock()
        self.config.agent_mode = "proactive"
        self.config.agent_suggestion_cooldown_hours = 24
        self.config.agent_gap_detection_days = 5
        self.config.agent_min_reading_samples = 5
        self.state = MagicMock()
        self.hands = MagicMock()
        self.brain = Brain(self.config, self.state, self.hands)

    def _base_context(self, overrides=None):
        ctx = {
            "saves_by_category": {},
            "has_notes_this_week": True,
            "vault_recent_notes": [],
            "recent_saves_count": 0,
            "vault_note_count": 0,
            "days_since": {"knowledge": 7, "trend": 1, "linkedin": 14, "meta": 30},
            "failure_counts": {"trend": 0},
        }
        if overrides:
            ctx.update(overrides)
        return ctx

    def test_detect_category_gaps_returns_empty_when_no_memory(self):
        """_detect_category_gaps returns [] when memory is None."""
        self.brain.memory = None
        gaps = self.brain._detect_category_gaps(self._base_context())
        assert gaps == []

    def test_detect_category_gaps_returns_gap_for_preferred_category_without_saves(self):
        """_detect_category_gaps returns gap when preferred category has no recent saves/engagement."""
        memory = MagicMock()
        memory.get_preferred_categories.return_value = [("ai-eng", 0.8)]
        memory.get_engagement_stats.return_value = {"total": 0}
        memory.get_engagement_log_snapshot.return_value = []
        self.brain.memory = memory
        self.state.get_saves_by_category.return_value = {}  # no saves

        gaps = self.brain._detect_category_gaps(self._base_context())
        assert len(gaps) == 1
        assert gaps[0]["category"] == "ai-eng"
        assert gaps[0]["type"] == "suggest_articles"

    def test_detect_category_gaps_returns_empty_when_category_has_recent_saves(self):
        """_detect_category_gaps returns [] when preferred category has recent saves."""
        memory = MagicMock()
        memory.get_preferred_categories.return_value = [("ai-eng", 0.8)]
        memory.get_engagement_stats.return_value = {}
        memory.get_engagement_log_snapshot.return_value = []
        self.brain.memory = memory
        self.state.get_saves_by_category.return_value = {"ai-eng": 2}

        gaps = self.brain._detect_category_gaps(self._base_context())
        assert gaps == []

    def test_detect_category_gaps_skips_low_score_categories(self):
        """_detect_category_gaps ignores categories with score < 0.5."""
        memory = MagicMock()
        memory.get_preferred_categories.return_value = [("business", 0.3)]
        memory.get_engagement_stats.return_value = {}
        memory.get_engagement_log_snapshot.return_value = []
        self.brain.memory = memory
        self.state.get_saves_by_category.return_value = {}

        gaps = self.brain._detect_category_gaps(self._base_context())
        assert gaps == []

    def test_detect_category_gaps_limited_to_one(self):
        """_detect_category_gaps returns at most 1 gap even when multiple categories qualify."""
        memory = MagicMock()
        memory.get_preferred_categories.return_value = [
            ("ai-eng", 0.9),
            ("business", 0.8),
            ("engineering", 0.7),
        ]
        memory.get_engagement_stats.return_value = {}
        memory.get_engagement_log_snapshot.return_value = []
        self.brain.memory = memory
        self.state.get_saves_by_category.return_value = {}

        gaps = self.brain._detect_category_gaps(self._base_context())
        assert len(gaps) == 1

    def test_can_send_proactive_returns_false_with_no_engagement_history(self):
        """_can_send_proactive_suggestion returns False when memory has no engagement log."""
        memory = MagicMock()
        memory.get_engagement_log_snapshot.return_value = []
        self.brain.memory = memory
        self.state.last_actions = {}

        result = self.brain._can_send_proactive_suggestion()
        assert result is False

    def test_can_send_proactive_returns_false_when_less_than_3_days_history(self):
        """_can_send_proactive_suggestion returns False when first engagement was < 3 days ago."""
        from datetime import datetime, timezone, timedelta
        KST = timezone(timedelta(hours=9))
        recent_ts = (datetime.now(KST) - timedelta(days=1)).isoformat()

        memory = MagicMock()
        memory.get_engagement_log_snapshot.return_value = [{"reacted_at": recent_ts}]
        self.brain.memory = memory
        self.state.last_actions = {}

        result = self.brain._can_send_proactive_suggestion()
        assert result is False

    def test_can_send_proactive_returns_true_when_3_days_history_and_no_previous(self):
        """_can_send_proactive_suggestion returns True when 3+ days of history and no prior suggestion."""
        from datetime import datetime, timezone, timedelta
        KST = timezone(timedelta(hours=9))
        old_ts = (datetime.now(KST) - timedelta(days=5)).isoformat()

        memory = MagicMock()
        memory.get_engagement_log_snapshot.return_value = [{"reacted_at": old_ts}]
        self.brain.memory = memory
        self.state.last_actions = {}

        result = self.brain._can_send_proactive_suggestion()
        assert result is True

    def test_can_send_proactive_respects_24h_cooldown(self):
        """_can_send_proactive_suggestion returns False when last suggestion was < 24h ago."""
        self.state.last_actions = {"proactive_suggestion": "2026-04-10T10:00:00+09:00"}
        self.state.days_since_action.return_value = 0  # 0 days = less than 24h

        result = self.brain._can_send_proactive_suggestion()
        assert result is False

    def test_can_send_proactive_returns_true_after_24h(self):
        """_can_send_proactive_suggestion returns True when last suggestion was >= 1 day ago."""
        self.state.last_actions = {"proactive_suggestion": "2026-04-09T10:00:00+09:00"}
        self.state.days_since_action.return_value = 1

        result = self.brain._can_send_proactive_suggestion()
        assert result is True

    def test_decide_includes_proactive_suggestion_in_proactive_mode(self):
        """decide() appends suggest_articles action when proactive mode and gap detected."""
        memory = MagicMock()
        memory.get_preferred_categories.return_value = [("ai-eng", 0.8)]
        memory.get_engagement_stats.return_value = {}
        memory.get_engagement_log_snapshot.return_value = []
        self.brain.memory = memory
        self.state.get_saves_by_category.return_value = {}
        self.state.last_actions = {}

        # Mock _can_send_proactive_suggestion to return True
        self.brain._can_send_proactive_suggestion = MagicMock(return_value=True)

        context = self._base_context()
        actions = self.brain.decide(context, scheduled_action=None)
        assert any(a["type"] == "suggest_articles" for a in actions)

    def test_decide_does_not_include_proactive_suggestion_in_reactive_mode(self):
        """decide() does not add suggest_articles when agent_mode is reactive."""
        self.config.agent_mode = "reactive"
        memory = MagicMock()
        memory.get_preferred_categories.return_value = [("ai-eng", 0.8)]
        memory.get_engagement_stats.return_value = {}
        memory.get_engagement_log_snapshot.return_value = []
        self.brain.memory = memory
        self.state.get_saves_by_category.return_value = {}

        context = self._base_context()
        actions = self.brain.decide(context, scheduled_action=None)
        assert not any(a["type"] == "suggest_articles" for a in actions)

    def test_act_dispatches_suggest_articles_to_run_proactive_suggestion(self):
        """act with type=suggest_articles calls hands.run_proactive_suggestion."""
        self.hands.run_proactive_suggestion.return_value = {"success": True, "message_id": 42}
        action = {"type": "suggest_articles", "category": "ai-eng", "days_without": 7}
        result = self.brain.act(action)
        self.hands.run_proactive_suggestion.assert_called_once_with(action)
        assert result["success"] is True

    def test_act_suggest_articles_logs_proactive_suggestion_on_success(self):
        """act with suggest_articles calls state.log_action('proactive_suggestion') on success."""
        self.hands.run_proactive_suggestion.return_value = {"success": True, "message_id": 1}
        action = {"type": "suggest_articles", "category": "ai-eng", "days_without": 7}
        self.brain.act(action)
        self.state.log_action.assert_called_once_with("proactive_suggestion")

    def test_proactive_suggestions_max_one_per_decide(self):
        """decide() produces at most 1 proactive suggestion even with multiple gaps."""
        memory = MagicMock()
        # _detect_category_gaps already limits to 1, but verify at decide() level too
        memory.get_preferred_categories.return_value = [("ai-eng", 0.9), ("business", 0.8)]
        memory.get_engagement_stats.return_value = {}
        memory.get_engagement_log_snapshot.return_value = []
        self.brain.memory = memory
        self.state.get_saves_by_category.return_value = {}
        self.brain._can_send_proactive_suggestion = MagicMock(return_value=True)

        context = self._base_context()
        actions = self.brain.decide(context, scheduled_action=None)
        suggestion_actions = [a for a in actions if a["type"] == "suggest_articles"]
        assert len(suggestion_actions) == 1
