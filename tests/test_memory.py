"""Tests for AgentMemory — engagement tracking, preference learning, source scoring."""
import json
import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from compound_agent.memory import AgentMemory, KST


def make_memory(tmp_path, **kwargs) -> AgentMemory:
    path = str(tmp_path / "memory.json")
    return AgentMemory(memory_path=path, **kwargs)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestAgentMemoryInit:
    def test_default_path_expanded(self, tmp_path):
        m = make_memory(tmp_path)
        assert os.path.isabs(m._path)

    def test_custom_path(self, tmp_path):
        path = str(tmp_path / "custom.json")
        m = AgentMemory(memory_path=path)
        assert m._path == path

    def test_default_ema_alpha(self, tmp_path):
        m = make_memory(tmp_path)
        assert m._alpha == 0.2

    def test_custom_ema_alpha(self, tmp_path):
        m = make_memory(tmp_path, ema_alpha=0.5)
        assert m._alpha == 0.5

    def test_initial_engagement_log_empty(self, tmp_path):
        m = make_memory(tmp_path)
        assert m.engagement_log == []

    def test_initial_source_scores_empty(self, tmp_path):
        m = make_memory(tmp_path)
        assert m.source_scores == {}

    def test_initial_preferences_structure(self, tmp_path):
        m = make_memory(tmp_path)
        assert "preferred_categories" in m.preferences
        assert "reading_times" in m.preferences

    def test_has_lock(self, tmp_path):
        m = make_memory(tmp_path)
        assert isinstance(m._lock, type(threading.Lock()))


# ---------------------------------------------------------------------------
# Engagement tracking
# ---------------------------------------------------------------------------

class TestLogEngagement:
    def test_log_positive_reaction(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 100, "positive")
        assert len(m.engagement_log) == 1
        assert m.engagement_log[0]["reaction"] == "positive"
        assert m.engagement_log[0]["briefing_type"] == "trend"
        assert m.engagement_log[0]["message_id"] == 100

    def test_all_reaction_types(self, tmp_path):
        m = make_memory(tmp_path)
        for reaction in ("positive", "negative", "bookmark", "ignored"):
            m.log_engagement("trend", 1, reaction)
        reactions = [e["reaction"] for e in m.engagement_log]
        assert set(reactions) == {"positive", "negative", "bookmark", "ignored"}

    def test_item_id_included_when_provided(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 1, "positive", item_id="abc123")
        assert m.engagement_log[0]["item_id"] == "abc123"

    def test_item_id_absent_when_not_provided(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 1, "positive")
        assert "item_id" not in m.engagement_log[0]

    def test_reacted_at_is_set(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 1, "positive")
        assert "reacted_at" in m.engagement_log[0]

    def test_engagement_log_capped_at_1000(self, tmp_path):
        m = make_memory(tmp_path)
        for i in range(1005):
            m.log_engagement("trend", i, "positive")
        assert len(m.engagement_log) == 1000

    def test_engagement_log_cap_keeps_newest(self, tmp_path):
        m = make_memory(tmp_path)
        for i in range(1005):
            m.log_engagement("trend", i, "positive")
        # The last entry should have message_id 1004
        assert m.engagement_log[-1]["message_id"] == 1004


class TestGetEngagementStats:
    def test_counts_reactions_correctly(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 1, "positive")
        m.log_engagement("trend", 2, "positive")
        m.log_engagement("trend", 3, "negative")
        m.log_engagement("trend", 4, "bookmark")
        m.log_engagement("trend", 5, "ignored")
        stats = m.get_engagement_stats()
        assert stats["total"] == 5
        assert stats["positive"] == 2
        assert stats["negative"] == 1
        assert stats["bookmark"] == 1
        assert stats["ignored"] == 1

    def test_engagement_rate_calculation(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 1, "positive")
        m.log_engagement("trend", 2, "ignored")
        stats = m.get_engagement_stats()
        # active = 1 (positive), total = 2 → rate = 0.5
        assert stats["engagement_rate"] == 0.5

    def test_filter_by_briefing_type(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 1, "positive")
        m.log_engagement("knowledge", 2, "positive")
        stats = m.get_engagement_stats(briefing_type="trend")
        assert stats["total"] == 1

    def test_empty_stats_on_no_entries(self, tmp_path):
        m = make_memory(tmp_path)
        stats = m.get_engagement_stats()
        assert stats["total"] == 0
        assert stats["engagement_rate"] == 0.0


# ---------------------------------------------------------------------------
# Preference model
# ---------------------------------------------------------------------------

class TestCategoryPreference:
    def test_new_category_starts_at_0_5(self, tmp_path):
        m = make_memory(tmp_path)
        m.update_category_preference("ai-eng", positive=True)
        cats = m.preferences["preferred_categories"]
        # After first update from prior 0.5: (1-0.2)*0.5 + 0.2*1.0 = 0.6
        assert "ai-eng" in cats

    def test_new_category_prior_is_half(self, tmp_path):
        """Verify prior is 0.5 by checking score after one positive update."""
        m = make_memory(tmp_path, ema_alpha=0.2)
        m.update_category_preference("ai-eng", positive=True)
        score = m.preferences["preferred_categories"]["ai-eng"]["score"]
        expected = (1 - 0.2) * 0.5 + 0.2 * 1.0
        assert abs(score - expected) < 1e-9

    def test_positive_updates_increase_score(self, tmp_path):
        m = make_memory(tmp_path)
        m.update_category_preference("ai-eng", positive=True)
        score_after_1 = m.preferences["preferred_categories"]["ai-eng"]["score"]
        m.update_category_preference("ai-eng", positive=True)
        score_after_2 = m.preferences["preferred_categories"]["ai-eng"]["score"]
        assert score_after_2 > score_after_1

    def test_negative_updates_decrease_score(self, tmp_path):
        m = make_memory(tmp_path)
        # Start at 0.5, push up a bit
        m.update_category_preference("ai-eng", positive=True)
        score_before = m.preferences["preferred_categories"]["ai-eng"]["score"]
        m.update_category_preference("ai-eng", positive=False)
        score_after = m.preferences["preferred_categories"]["ai-eng"]["score"]
        assert score_after < score_before

    def test_ema_convergence_to_1(self, tmp_path):
        m = make_memory(tmp_path, ema_alpha=0.2)
        for _ in range(50):
            m.update_category_preference("ai-eng", positive=True)
        score = m.preferences["preferred_categories"]["ai-eng"]["score"]
        assert score > 0.95

    def test_interaction_count_increments(self, tmp_path):
        m = make_memory(tmp_path)
        m.update_category_preference("ai-eng", positive=True)
        m.update_category_preference("ai-eng", positive=False)
        interactions = m.preferences["preferred_categories"]["ai-eng"]["interactions"]
        assert interactions == 2

    def test_get_preferred_categories_sorted(self, tmp_path):
        m = make_memory(tmp_path, ema_alpha=0.5)
        # Push "ai-eng" high, "business" low
        for _ in range(10):
            m.update_category_preference("ai-eng", positive=True)
        for _ in range(10):
            m.update_category_preference("business", positive=False)
        result = m.get_preferred_categories(top_n=2)
        assert result[0][0] == "ai-eng"
        assert result[1][0] == "business"
        assert result[0][1] > result[1][1]

    def test_get_preferred_categories_respects_top_n(self, tmp_path):
        m = make_memory(tmp_path)
        for cat in ("a", "b", "c", "d", "e", "f"):
            m.update_category_preference(cat, positive=True)
        result = m.get_preferred_categories(top_n=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Reading time
# ---------------------------------------------------------------------------

class TestReadingTime:
    def test_first_reading_time_recorded(self, tmp_path):
        m = make_memory(tmp_path)
        m.update_reading_time("trend", 9.0)
        entry = m.preferences["reading_times"]["trend"]
        assert entry["avg_read_hour"] == 9.0
        assert entry["samples"] == 1

    def test_running_average_correct(self, tmp_path):
        m = make_memory(tmp_path)
        m.update_reading_time("trend", 8.0)
        m.update_reading_time("trend", 10.0)
        avg = m.preferences["reading_times"]["trend"]["avg_read_hour"]
        assert abs(avg - 9.0) < 1e-9

    def test_samples_increments(self, tmp_path):
        m = make_memory(tmp_path)
        for _ in range(3):
            m.update_reading_time("trend", 9.0)
        assert m.preferences["reading_times"]["trend"]["samples"] == 3

    def test_get_optimal_send_time_returns_none_below_5_samples(self, tmp_path):
        m = make_memory(tmp_path)
        for _ in range(4):
            m.update_reading_time("trend", 9.0)
        assert m.get_optimal_send_time("trend") is None

    def test_get_optimal_send_time_returns_value_at_5_samples(self, tmp_path):
        m = make_memory(tmp_path)
        for _ in range(5):
            m.update_reading_time("trend", 9.0)
        assert m.get_optimal_send_time("trend") == 9.0

    def test_get_optimal_send_time_returns_none_for_unknown_type(self, tmp_path):
        m = make_memory(tmp_path)
        assert m.get_optimal_send_time("nonexistent") is None


# ---------------------------------------------------------------------------
# Source scores
# ---------------------------------------------------------------------------

class TestSourceScores:
    def test_new_source_initialised(self, tmp_path):
        m = make_memory(tmp_path)
        m.update_source_score("Hacker News", positive=True)
        assert "Hacker News" in m.source_scores

    def test_quality_calculation_positive(self, tmp_path):
        m = make_memory(tmp_path)
        for _ in range(7):
            m.update_source_score("HN", positive=True)
        for _ in range(3):
            m.update_source_score("HN", positive=False)
        assert abs(m.source_scores["HN"]["quality"] - 0.7) < 1e-9

    def test_total_shown_increments(self, tmp_path):
        m = make_memory(tmp_path)
        m.update_source_score("HN", positive=True)
        m.update_source_score("HN", positive=False)
        assert m.source_scores["HN"]["total_shown"] == 2

    def test_get_source_rankings_sorted(self, tmp_path):
        m = make_memory(tmp_path)
        for _ in range(10):
            m.update_source_score("Good Source", positive=True)
        for _ in range(5):
            m.update_source_score("Bad Source", positive=True)
        for _ in range(5):
            m.update_source_score("Bad Source", positive=False)
        rankings = m.get_source_rankings(min_shown=1)
        assert rankings[0][0] == "Good Source"

    def test_get_source_rankings_filters_by_min_shown(self, tmp_path):
        m = make_memory(tmp_path)
        for _ in range(5):
            m.update_source_score("Rare Source", positive=True)
        rankings = m.get_source_rankings(min_shown=10)
        assert all(src != "Rare Source" for src, _ in rankings)

    def test_get_source_rankings_includes_at_min_shown(self, tmp_path):
        m = make_memory(tmp_path)
        for _ in range(10):
            m.update_source_score("Exact Source", positive=True)
        rankings = m.get_source_rankings(min_shown=10)
        assert any(src == "Exact Source" for src, _ in rankings)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_creates_file(self, tmp_path):
        m = make_memory(tmp_path)
        m.save()
        assert os.path.exists(m._path)

    def test_save_and_reload_engagement(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 42, "positive")
        m.save()

        m2 = AgentMemory(memory_path=m._path)
        assert len(m2.engagement_log) == 1
        assert m2.engagement_log[0]["message_id"] == 42

    def test_save_and_reload_preferences(self, tmp_path):
        m = make_memory(tmp_path)
        m.update_category_preference("ai-eng", positive=True)
        m.save()

        m2 = AgentMemory(memory_path=m._path)
        assert "ai-eng" in m2.preferences["preferred_categories"]

    def test_save_and_reload_source_scores(self, tmp_path):
        m = make_memory(tmp_path)
        for _ in range(5):
            m.update_source_score("HN", positive=True)
        m.save()

        m2 = AgentMemory(memory_path=m._path)
        assert "HN" in m2.source_scores
        assert m2.source_scores["HN"]["total_shown"] == 5

    def test_save_writes_version(self, tmp_path):
        m = make_memory(tmp_path)
        m.save()
        with open(m._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 1

    def test_load_missing_file_returns_empty(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        m = AgentMemory(memory_path=path)
        assert m.engagement_log == []
        assert m.source_scores == {}

    def test_load_corrupted_file_returns_empty(self, tmp_path):
        path = str(tmp_path / "corrupt.json")
        with open(path, "w") as f:
            f.write("{NOT VALID JSON[[")
        m = AgentMemory(memory_path=path)
        assert m.engagement_log == []
        assert m.source_scores == {}


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

class TestCleanup:
    def test_cleanup_removes_old_entries(self, tmp_path):
        m = make_memory(tmp_path)
        old_ts = (datetime.now(KST) - timedelta(days=100)).isoformat()
        m.engagement_log.append({
            "briefing_type": "trend",
            "message_id": 1,
            "reaction": "positive",
            "reacted_at": old_ts,
        })
        m.log_engagement("trend", 2, "positive")
        m.cleanup_old(days=90)
        assert len(m.engagement_log) == 1
        assert m.engagement_log[0]["message_id"] == 2

    def test_cleanup_keeps_recent_entries(self, tmp_path):
        m = make_memory(tmp_path)
        m.log_engagement("trend", 1, "positive")
        m.cleanup_old(days=90)
        assert len(m.engagement_log) == 1


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_log_engagement_no_crash(self, tmp_path):
        m = make_memory(tmp_path)
        errors = []

        def worker(n):
            try:
                for i in range(50):
                    m.log_engagement("trend", n * 50 + i, "positive")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert len(m.engagement_log) <= AgentMemory.MAX_ENGAGEMENT_LOG

    def test_concurrent_update_category_no_crash(self, tmp_path):
        m = make_memory(tmp_path)
        errors = []

        def worker():
            try:
                for _ in range(100):
                    m.update_category_preference("ai-eng", positive=True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        assert "ai-eng" in m.preferences["preferred_categories"]
