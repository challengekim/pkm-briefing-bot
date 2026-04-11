"""Tests for AgentState — JSON persistence layer."""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from compound_agent.agent_state import AgentState, KST


class TestAgentStateInitial:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmpdir, "state.json")
        self.state = AgentState(self.state_path)

    def test_initial_state_has_no_recent_saves(self):
        """Fresh state returns empty list from get_recent_saves."""
        assert self.state.get_recent_saves(hours=24) == []

    def test_initial_state_has_no_saves_by_category(self):
        """Fresh state returns empty dict from get_saves_by_category."""
        assert self.state.get_saves_by_category(days=1) == {}

    def test_initial_state_url_is_not_duplicate(self):
        """Fresh state treats any URL as non-duplicate."""
        assert self.state.is_duplicate_url("https://example.com") is False

    def test_initial_failure_count_is_zero(self):
        """Fresh state returns 0 failure count for any action."""
        assert self.state.get_failure_count("trend") == 0


class TestAgentStateLogSave:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmpdir, "state.json")
        self.state = AgentState(self.state_path)

    def test_log_save_appears_in_recent_saves(self):
        """log_save records data retrievable by get_recent_saves."""
        self.state.log_save("https://example.com", "ai-eng", "Test Article")
        saves = self.state.get_recent_saves(hours=24)
        assert len(saves) == 1
        assert saves[0]["url"] == "https://example.com"
        assert saves[0]["category"] == "ai-eng"
        assert saves[0]["title"] == "Test Article"

    def test_duplicate_url_detected_after_log_save(self):
        """After logging a URL, is_duplicate_url returns True."""
        self.state.log_save("https://example.com", "ai-eng", "Test")
        assert self.state.is_duplicate_url("https://example.com") is True

    def test_different_url_not_duplicate(self):
        """A URL not logged is still treated as non-duplicate."""
        self.state.log_save("https://example.com", "ai-eng", "Test")
        assert self.state.is_duplicate_url("https://other.com") is False

    def test_saves_by_category_counts_correctly(self):
        """get_saves_by_category groups multiple saves in same category."""
        self.state.log_save("https://a.com", "ai-eng", "A")
        self.state.log_save("https://b.com", "ai-eng", "B")
        self.state.log_save("https://c.com", "business", "C")
        by_cat = self.state.get_saves_by_category(days=1)
        assert by_cat["ai-eng"] == 2
        assert by_cat["business"] == 1

    def test_multiple_saves_all_appear_in_recent(self):
        """Multiple log_save calls all appear in get_recent_saves."""
        self.state.log_save("https://a.com", "ai-eng", "A")
        self.state.log_save("https://b.com", "ai-eng", "B")
        saves = self.state.get_recent_saves(hours=24)
        assert len(saves) == 2


class TestAgentStateActions:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmpdir, "state.json")
        self.state = AgentState(self.state_path)

    def test_days_since_action_returns_999_for_never_run(self):
        """days_since_action returns 999 for actions that never ran."""
        assert self.state.days_since_action("knowledge") == 999
        assert self.state.days_since_action("trend") == 999

    def test_log_action_makes_days_since_return_zero(self):
        """After log_action, days_since_action returns 0."""
        self.state.log_action("knowledge")
        assert self.state.days_since_action("knowledge") == 0

    def test_log_action_resets_failure_count(self):
        """log_action resets the failure count for that action type."""
        self.state.log_failure("trend")
        self.state.log_failure("trend")
        self.state.log_action("trend")
        assert self.state.get_failure_count("trend") == 0

    def test_log_failure_increments_count(self):
        """log_failure increments consecutive failure count."""
        self.state.log_failure("trend")
        assert self.state.get_failure_count("trend") == 1
        self.state.log_failure("trend")
        assert self.state.get_failure_count("trend") == 2

    def test_failure_count_independent_per_action(self):
        """Failure counts are tracked independently per action type."""
        self.state.log_failure("trend")
        self.state.log_failure("trend")
        self.state.log_failure("knowledge")
        assert self.state.get_failure_count("trend") == 2
        assert self.state.get_failure_count("knowledge") == 1


class TestAgentStatePersistence:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmpdir, "state.json")

    def test_persistence_save_and_reload_url(self):
        """Saved URL survives save() and reload via new AgentState instance."""
        state = AgentState(self.state_path)
        state.log_save("https://test.com", "ai-eng", "Test Article")
        state.save()

        reloaded = AgentState(self.state_path)
        assert reloaded.is_duplicate_url("https://test.com")

    def test_persistence_save_and_reload_action(self):
        """log_action persists and days_since_action reads correctly after reload."""
        state = AgentState(self.state_path)
        state.log_action("knowledge")
        state.save()

        reloaded = AgentState(self.state_path)
        assert reloaded.days_since_action("knowledge") == 0

    def test_persistence_saves_file_with_version(self):
        """save() writes a JSON file that contains version key."""
        state = AgentState(self.state_path)
        state.save()
        with open(self.state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == 1

    def test_handles_missing_state_file(self):
        """AgentState works when state file does not exist."""
        state = AgentState("/tmp/nonexistent_test_state_xyz.json")
        assert state.get_recent_saves() == []
        assert state.days_since_action("trend") == 999

    def test_handles_corrupt_json_file(self):
        """AgentState returns empty state when JSON file is corrupt."""
        corrupt_path = os.path.join(self.tmpdir, "corrupt.json")
        with open(corrupt_path, "w") as f:
            f.write("{NOT VALID JSON[[")
        state = AgentState(corrupt_path)
        assert state.get_recent_saves() == []
        assert state.is_duplicate_url("https://example.com") is False


class TestAgentStateCleanup:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmpdir, "state.json")
        self.state = AgentState(self.state_path)

    def test_cleanup_old_removes_entries_past_threshold(self):
        """cleanup_old removes saves older than the given days threshold."""
        # Log a save with a timestamp in the past by writing directly
        old_ts = (datetime.now(KST) - timedelta(days=35)).isoformat()
        self.state.recent_saves.append({
            "url": "https://old.com",
            "category": "ai-eng",
            "title": "Old",
            "saved_at": old_ts,
        })
        self.state.log_save("https://new.com", "ai-eng", "New")

        self.state.cleanup_old(days=30)
        remaining = [s["url"] for s in self.state.recent_saves]
        assert "https://old.com" not in remaining
        assert "https://new.com" in remaining

    def test_cleanup_old_keeps_recent_entries(self):
        """cleanup_old keeps entries within the threshold."""
        self.state.log_save("https://recent.com", "ai-eng", "Recent")
        self.state.cleanup_old(days=30)
        assert len(self.state.recent_saves) == 1


class TestAgentStateDeferredActions:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmpdir, "state.json")
        self.state = AgentState(self.state_path)

    def test_defer_action_stores_action(self):
        """defer_action appends action to deferred_actions list."""
        self.state.defer_action({"type": "trend"}, optimal_hour=9.0)
        assert len(self.state.deferred_actions) == 1
        assert self.state.deferred_actions[0]["type"] == "trend"
        assert self.state.deferred_actions[0]["_optimal_hour"] == 9.0

    def test_get_ready_deferred_returns_actions_at_optimal_time(self):
        """get_ready_deferred returns actions when current time >= optimal_hour - 0.25."""
        # Use hour 0.0 so it's always ready (current time is always >= -0.25)
        self.state.defer_action({"type": "trend"}, optimal_hour=0.0)
        ready = self.state.get_ready_deferred()
        assert len(ready) == 1
        assert ready[0]["type"] == "trend"

    def test_get_ready_deferred_strips_internal_fields(self):
        """get_ready_deferred returns clean dicts without _ prefixed keys."""
        self.state.defer_action({"type": "trend"}, optimal_hour=0.0)
        ready = self.state.get_ready_deferred()
        assert len(ready) == 1
        for key in ready[0]:
            assert not key.startswith("_"), f"Internal field leaked: {key}"

    def test_get_ready_deferred_leaves_future_actions(self):
        """get_ready_deferred keeps actions whose optimal time hasn't arrived."""
        # Use hour 25.0 (impossible value) to ensure action is never ready
        self.state.defer_action({"type": "trend"}, optimal_hour=25.0)
        ready = self.state.get_ready_deferred()
        assert ready == []
        assert len(self.state.deferred_actions) == 1  # still in queue

    def test_get_ready_deferred_removes_returned_actions(self):
        """Once returned by get_ready_deferred, actions are removed from deferred_actions."""
        self.state.defer_action({"type": "trend"}, optimal_hour=0.0)
        self.state.get_ready_deferred()
        assert self.state.deferred_actions == []

    def test_clear_deferred_removes_by_type(self):
        """clear_deferred removes actions matching the given type."""
        self.state.defer_action({"type": "trend"}, optimal_hour=9.0)
        self.state.defer_action({"type": "knowledge"}, optimal_hour=10.0)
        self.state.clear_deferred("trend")
        assert all(a["type"] != "trend" for a in self.state.deferred_actions)
        assert any(a["type"] == "knowledge" for a in self.state.deferred_actions)

    def test_deferred_actions_persists_in_save_load(self):
        """deferred_actions survives save() and reload via new AgentState instance."""
        self.state.defer_action({"type": "morning"}, optimal_hour=8.0)
        self.state.save()

        reloaded = AgentState(self.state_path)
        assert len(reloaded.deferred_actions) == 1
        assert reloaded.deferred_actions[0]["type"] == "morning"
        assert reloaded.deferred_actions[0]["_optimal_hour"] == 8.0

    def test_initial_deferred_actions_is_empty(self):
        """Fresh state has empty deferred_actions list."""
        assert self.state.deferred_actions == []
