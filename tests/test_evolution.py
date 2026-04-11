"""Tests for Evolution — safety rails, config adjustment, prompt evolution, idea tracking."""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
import yaml

from compound_agent.evolution import EvolutionSafety, Evolution, _now_kst, KST
from compound_agent.memory import AgentMemory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeConfig:
    """Minimal config for testing."""
    def __init__(self, **overrides):
        self.agent_mode = "self-improving"
        self.language = "ko"
        self.vault_path = ""
        self.project_repos = {}
        self.ideas_file = "project-ideas.md"
        self.trend_subreddits = ["artificial", "MachineLearning", "LocalLLaMA"]
        self.trend_hn_limit = 15
        self.trend_reddit_limit = 8
        self.trend_geeknews_limit = 10
        self.schedule = {
            "morning": {"hour": 8, "minute": 0},
            "trend": {"hour": 10, "minute": 0},
            "knowledge": {"hour": 10, "minute": 0, "day_of_week": "sat"},
        }
        self.evolution_max_config_changes_per_month = 3
        self.evolution_max_prompt_mutations_per_week = 1
        self.evolution_engagement_drop_threshold = 0.5
        self.evolution_log_path = ""
        self.evolution_variants_path = ""
        self.llm_provider = "gemini"
        self.llm_model = "gemini-2.5-flash"
        self.llm_api_key = "test-key"
        self.llm_base_url = None
        for k, v in overrides.items():
            setattr(self, k, v)


def make_memory(tmp_path) -> AgentMemory:
    return AgentMemory(memory_path=str(tmp_path / "memory.json"))


def make_safety(tmp_path, memory=None, config=None):
    config = config or FakeConfig(
        evolution_log_path=str(tmp_path / "evo-log.json"),
    )
    config.evolution_log_path = str(tmp_path / "evo-log.json")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("trends:\n  hn_limit: 15\n", encoding="utf-8")
    return EvolutionSafety(config, memory, config_path=str(config_path))


def make_evolution(tmp_path, memory=None, config=None):
    mem = memory or make_memory(tmp_path)
    cfg = config or FakeConfig(
        evolution_log_path=str(tmp_path / "evo-log.json"),
        evolution_variants_path=str(tmp_path / "variants"),
    )
    cfg.evolution_log_path = str(tmp_path / "evo-log.json")
    cfg.evolution_variants_path = str(tmp_path / "variants")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("trends:\n  hn_limit: 15\n  reddit_limit: 8\n", encoding="utf-8")
    return Evolution(cfg, mem, config_path=str(config_path))


# ===========================================================================
# EvolutionSafety
# ===========================================================================

class TestBackup:
    def test_backup_creates_file(self, tmp_path):
        s = make_safety(tmp_path)
        backup = s.backup_config()
        assert os.path.exists(backup)

    def test_backup_content_matches_original(self, tmp_path):
        s = make_safety(tmp_path)
        original = open(s._config_path, "r").read()
        backup = s.backup_config()
        assert open(backup, "r").read() == original

    def test_backup_includes_overrides(self, tmp_path):
        s = make_safety(tmp_path)
        # Create an overrides file
        overrides_path = tmp_path / "evolution-overrides.yaml"
        overrides_path.write_text("trends:\n  hn_limit: 20\n", encoding="utf-8")
        backup = s.backup_config()
        assert os.path.exists(backup)
        # Overrides backup also exists
        overrides_backup = backup.replace("config.yaml", "evolution-overrides.yaml")
        assert os.path.exists(overrides_backup)


class TestAuditLog:
    def test_log_change_creates_file(self, tmp_path):
        s = make_safety(tmp_path)
        s.log_change({"type": "test", "detail": "hello"})
        assert os.path.exists(s._log_path)

    def test_log_change_appends(self, tmp_path):
        s = make_safety(tmp_path)
        s.log_change({"type": "first"})
        s.log_change({"type": "second"})
        with open(s._log_path) as f:
            log = json.load(f)
        assert len(log) == 2
        assert log[0]["type"] == "first"
        assert log[1]["type"] == "second"

    def test_log_includes_timestamp(self, tmp_path):
        s = make_safety(tmp_path)
        s.log_change({"type": "test"})
        with open(s._log_path) as f:
            log = json.load(f)
        assert "timestamp" in log[0]

    def test_get_recent_changes(self, tmp_path):
        s = make_safety(tmp_path)
        s.log_change({"type": "recent"})
        recent = s.get_recent_changes(days=1)
        assert len(recent) == 1


class TestRateLimit:
    def test_config_allows_first_three(self, tmp_path):
        s = make_safety(tmp_path)
        for i in range(3):
            assert s.check_rate_limit("config") is True
            s.log_change({"change_type": "config", "idx": i})

    def test_config_blocks_fourth(self, tmp_path):
        s = make_safety(tmp_path)
        for i in range(3):
            s.log_change({"change_type": "config", "idx": i})
        assert s.check_rate_limit("config") is False

    def test_rollbacks_dont_count(self, tmp_path):
        s = make_safety(tmp_path)
        for i in range(3):
            s.log_change({"change_type": "config", "type": "rollback", "idx": i})
        assert s.check_rate_limit("config") is True

    def test_prompt_allows_first(self, tmp_path):
        s = make_safety(tmp_path)
        assert s.check_rate_limit("prompt") is True

    def test_prompt_blocks_second_same_week(self, tmp_path):
        s = make_safety(tmp_path)
        s.log_change({"change_type": "prompt"})
        assert s.check_rate_limit("prompt") is False


class TestEngagementDrop:
    def test_returns_none_with_no_memory(self, tmp_path):
        s = make_safety(tmp_path, memory=None)
        assert s.check_engagement_drop() is None

    def test_returns_none_insufficient_data(self, tmp_path):
        mem = make_memory(tmp_path)
        # Only 2 entries — below threshold
        for i in range(2):
            mem.log_engagement("trend", i, "positive")
        s = make_safety(tmp_path, memory=mem)
        assert s.check_engagement_drop() is None

    def test_detects_drop(self, tmp_path):
        mem = make_memory(tmp_path)
        now = _now_kst()

        # Add old baseline: 10 positive engagements (30-60 days ago)
        for i in range(10):
            entry = {
                "briefing_type": "trend",
                "message_id": i,
                "reaction": "positive",
                "reacted_at": (now - timedelta(days=40 + i)).isoformat(),
            }
            mem.engagement_log.append(entry)

        # Add recent: 10 ignored engagements (last 21 days)
        for i in range(10):
            entry = {
                "briefing_type": "trend",
                "message_id": 100 + i,
                "reaction": "ignored",
                "reacted_at": (now - timedelta(days=i + 1)).isoformat(),
            }
            mem.engagement_log.append(entry)

        s = make_safety(tmp_path, memory=mem)
        drop = s.check_engagement_drop()
        assert drop is not None
        assert drop["recent_rate"] < drop["baseline_rate"]

    def test_healthy_engagement_returns_none(self, tmp_path):
        mem = make_memory(tmp_path)
        now = _now_kst()

        # All positive, consistent over time
        for i in range(20):
            entry = {
                "briefing_type": "trend",
                "message_id": i,
                "reaction": "positive",
                "reacted_at": (now - timedelta(days=i + 1)).isoformat(),
            }
            mem.engagement_log.append(entry)

        s = make_safety(tmp_path, memory=mem)
        assert s.check_engagement_drop() is None


class TestRollback:
    def test_rollback_removes_overrides_when_no_backup(self, tmp_path):
        s = make_safety(tmp_path)
        # Create overrides
        overrides_path = tmp_path / "evolution-overrides.yaml"
        overrides_path.write_text("trends:\n  hn_limit: 99\n")
        assert overrides_path.exists()

        s.rollback_config(str(tmp_path / "config.yaml.bak.fake"))
        assert not overrides_path.exists()

    def test_rollback_restores_from_backup(self, tmp_path):
        s = make_safety(tmp_path)
        overrides_path = tmp_path / "evolution-overrides.yaml"
        overrides_path.write_text("trends:\n  hn_limit: 99\n")

        # Create backup of overrides
        backup = s.backup_config()
        overrides_path.write_text("trends:\n  hn_limit: 1\n")  # Modified

        s.rollback_config(backup)
        restored = yaml.safe_load(overrides_path.read_text())
        assert restored["trends"]["hn_limit"] == 99


class TestOverrides:
    def test_read_missing_returns_empty(self, tmp_path):
        s = make_safety(tmp_path)
        assert s.read_overrides() == {}

    def test_write_and_read(self, tmp_path):
        s = make_safety(tmp_path)
        s.write_overrides({"trends": {"hn_limit": 20}})
        result = s.read_overrides()
        assert result["trends"]["hn_limit"] == 20

    def test_write_validates_yaml(self, tmp_path):
        s = make_safety(tmp_path)
        s.write_overrides({"key": "value"})
        # Should be valid YAML
        with open(s._overrides_path) as f:
            data = yaml.safe_load(f)
        assert data["key"] == "value"


# ===========================================================================
# Evolution — Config Adjustment
# ===========================================================================

class TestAdjustTrendSources:
    def test_low_quality_source_reduced(self, tmp_path):
        evo = make_evolution(tmp_path)
        # Set up low quality source
        evo.memory.source_scores["Hacker News"] = {
            "quality": 0.015, "total_shown": 60, "positive": 1, "negative": 59,
        }
        changes = evo._adjust_trend_sources()
        assert len(changes) == 1
        assert changes[0]["action"] == "reduce_source"
        assert changes[0]["new_value"] < 15

    def test_very_low_quality_source_minimized(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.memory.source_scores["Hacker News"] = {
            "quality": 0.005, "total_shown": 150, "positive": 0, "negative": 150,
        }
        changes = evo._adjust_trend_sources()
        assert len(changes) == 1
        assert changes[0]["new_value"] == Evolution.SOURCE_MIN_LIMIT

    def test_high_quality_source_boosted(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.memory.source_scores["Hacker News"] = {
            "quality": 0.15, "total_shown": 100, "positive": 15, "negative": 85,
        }
        changes = evo._adjust_trend_sources()
        assert len(changes) == 1
        assert changes[0]["action"] == "boost_source"
        assert changes[0]["new_value"] > 15

    def test_no_change_for_insufficient_data(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.memory.source_scores["Hacker News"] = {
            "quality": 0.01, "total_shown": 10, "positive": 0, "negative": 10,
        }
        changes = evo._adjust_trend_sources()
        assert len(changes) == 0


class TestAdjustSubreddits:
    def test_subreddit_added_for_preferred_category(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.memory.preferences["preferred_categories"] = {
            "marketing": {"score": 0.8, "interactions": 20},
        }
        changes = evo._adjust_subreddits()
        added = [c for c in changes if c["action"] == "add_subreddit"]
        assert len(added) > 0
        assert any(c["subreddit"] == "marketing" for c in added)

    def test_subreddit_not_duplicated(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.config.trend_subreddits = ["artificial", "MachineLearning", "LocalLLaMA", "marketing"]
        evo.memory.preferences["preferred_categories"] = {
            "marketing": {"score": 0.8, "interactions": 20},
        }
        changes = evo._adjust_subreddits()
        added_marketing = [c for c in changes if c.get("subreddit") == "marketing"]
        assert len(added_marketing) == 0

    def test_low_quality_subreddit_removed(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.config.trend_subreddits = ["artificial", "ChatGPT"]
        evo.memory.source_scores["r/ChatGPT"] = {
            "quality": 0.005, "total_shown": 150, "positive": 0, "negative": 150,
        }
        changes = evo._adjust_subreddits()
        removed = [c for c in changes if c["action"] == "remove_subreddit"]
        assert len(removed) == 1
        assert removed[0]["subreddit"] == "ChatGPT"


class TestAdjustSchedule:
    def test_schedule_adjusted_for_significant_drift(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.memory.preferences["reading_times"] = {
            "trend": {"avg_read_hour": 8.5, "samples": 15},  # reads at 8:30, scheduled at 10:00
        }
        changes = evo._adjust_schedule()
        assert len(changes) == 1
        assert changes[0]["action"] == "adjust_schedule"
        assert changes[0]["briefing_type"] == "trend"

    def test_schedule_unchanged_for_small_drift(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.memory.preferences["reading_times"] = {
            "trend": {"avg_read_hour": 10.2, "samples": 15},  # reads at ~10:12, scheduled at 10:00
        }
        changes = evo._adjust_schedule()
        assert len(changes) == 0

    def test_schedule_unchanged_for_few_samples(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo.memory.preferences["reading_times"] = {
            "trend": {"avg_read_hour": 7.0, "samples": 3},
        }
        changes = evo._adjust_schedule()
        assert len(changes) == 0


class TestApplyConfigChanges:
    def test_apply_creates_backup_and_overrides(self, tmp_path):
        evo = make_evolution(tmp_path)
        changes = [{
            "action": "reduce_source",
            "source": "Hacker News",
            "section": "trends",
            "key": "hn_limit",
            "old_value": 15,
            "new_value": 7,
            "reason": "test",
        }]
        evo._apply_config_changes(changes)
        # Backup should exist
        backups = [f for f in os.listdir(tmp_path) if "bak" in f]
        assert len(backups) > 0
        # Overrides should contain the change
        overrides = evo.read_overrides()
        assert overrides["trends"]["hn_limit"] == 7

    def test_apply_respects_rate_limit(self, tmp_path):
        evo = make_evolution(tmp_path)
        # Exhaust rate limit
        for i in range(3):
            evo.log_change({"change_type": "config", "idx": i})
        # evaluate_and_adjust should abort
        result = evo.evaluate_and_adjust()
        assert result == []

    def test_apply_writes_valid_yaml(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo._apply_config_changes([{
            "action": "add_subreddit",
            "subreddit": "devops",
            "section": "trends",
            "key": "subreddits",
            "reason": "test",
        }])
        overrides = evo.read_overrides()
        assert "devops" in overrides["trends"]["subreddits"]


# ===========================================================================
# Prompt Evolution
# ===========================================================================

class TestPromptValidation:
    def test_rejects_missing_vars(self):
        original = "Summarize: {items_text}\nFor: {user_name}"
        variant = "Summarize differently: {items_text}"  # missing user_name
        assert Evolution._validate_prompt(original, variant) is False

    def test_rejects_too_long(self):
        original = "Short prompt {var}"
        variant = "x" * (len(original) * 2 + 100) + " {var}"
        assert Evolution._validate_prompt(original, variant) is False

    def test_accepts_valid(self):
        original = "Summarize these items: {items_text}\nLanguage: {language}"
        variant = "Please provide a summary of: {items_text}\nOutput in: {language}"
        assert Evolution._validate_prompt(original, variant) is True

    def test_rejects_too_short(self):
        original = "A longer prompt with {var} content"
        variant = "{var}"
        assert Evolution._validate_prompt(original, variant) is False


class TestPromptExperiment:
    def test_get_experiment_returns_none_when_missing(self, tmp_path):
        evo = make_evolution(tmp_path)
        assert evo._get_experiment("nonexistent") is None

    def test_save_and_get_experiment(self, tmp_path):
        evo = make_evolution(tmp_path)
        experiment = {
            "prompt_name": "test",
            "status": "running",
            "ratings": [4, 5],
        }
        evo._save_experiment("test", experiment)
        loaded = evo._get_experiment("test")
        assert loaded["status"] == "running"
        assert loaded["ratings"] == [4, 5]

    def test_record_rating(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo._save_experiment("trend_digest", {
            "prompt_name": "trend_digest",
            "status": "running",
            "ratings": [],
            "total_served": 0,
        })
        evo.record_prompt_rating("trend_digest", 4)
        evo.record_prompt_rating("trend_digest", 5)
        exp = evo._get_experiment("trend_digest")
        assert exp["ratings"] == [4, 5]
        assert exp["total_served"] == 2

    def test_get_active_prompt_returns_variant(self, tmp_path):
        evo = make_evolution(tmp_path)
        evo._save_experiment("trend_digest", {
            "prompt_name": "trend_digest",
            "status": "running",
            "variant_text": "New prompt: {items_text}",
            "ratings": [],
        })
        result = evo.get_active_prompt("trend_digest")
        assert result == "New prompt: {items_text}"

    def test_get_active_prompt_returns_none_when_no_experiment(self, tmp_path):
        evo = make_evolution(tmp_path)
        assert evo.get_active_prompt("trend_digest") is None

    def test_evaluate_promotes_high_rated(self, tmp_path):
        evo = make_evolution(tmp_path)
        now = _now_kst()
        experiment = {
            "prompt_name": "trend_digest",
            "original_text": "Original: {items_text}",
            "variant_text": "Better: {items_text}",
            "started_at": (now - timedelta(days=15)).isoformat(),
            "ends_at": (now - timedelta(days=1)).isoformat(),
            "status": "running",
            "ratings": [5, 4, 5, 4, 5],
            "total_served": 5,
        }
        # Create prompt file for promotion
        prompts_dir = tmp_path / "prompts" / "ko"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "trend_digest.txt").write_text("Original: {items_text}")

        with patch.object(type(evo), '_promote_variant') as mock_promote:
            result = evo._evaluate_experiment("trend_digest", experiment)
            assert result is not None
            assert result["action"] == "promote_variant"

    def test_evaluate_keeps_original_low_rated(self, tmp_path):
        evo = make_evolution(tmp_path)
        now = _now_kst()
        experiment = {
            "prompt_name": "trend_digest",
            "original_text": "Original: {items_text}",
            "variant_text": "Worse: {items_text}",
            "started_at": (now - timedelta(days=15)).isoformat(),
            "ends_at": (now - timedelta(days=1)).isoformat(),
            "status": "running",
            "ratings": [2, 1, 2, 3, 2],
            "total_served": 5,
        }
        result = evo._evaluate_experiment("trend_digest", experiment)
        assert result is not None
        assert result["action"] == "keep_original"


# ===========================================================================
# Idea Tracking
# ===========================================================================

class TestParseProjectIdeas:
    def test_parse_basic_ideas(self, tmp_path):
        from compound_agent.knowledge_scanner import parse_project_ideas
        vault = tmp_path / "vault"
        vault.mkdir()
        ideas_file = vault / "ideas.md"
        ideas_file.write_text(
            "# Project Ideas\n\n"
            "## 2026-04-01\n\n"
            "status: proposed\n\n"
            "- Build a RAG pipeline for internal docs\n"
            "- Create authentication system with OAuth\n"
        )
        ideas = parse_project_ideas(str(vault), "ideas.md")
        assert len(ideas) == 2
        assert ideas[0]["date"] == "2026-04-01"
        assert ideas[0]["status"] == "proposed"
        assert len(ideas[0]["keywords"]) > 0

    def test_parse_empty_file(self, tmp_path):
        from compound_agent.knowledge_scanner import parse_project_ideas
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "ideas.md").write_text("# Empty\n")
        ideas = parse_project_ideas(str(vault), "ideas.md")
        assert ideas == []

    def test_parse_missing_file(self, tmp_path):
        from compound_agent.knowledge_scanner import parse_project_ideas
        ideas = parse_project_ideas(str(tmp_path), "missing.md")
        assert ideas == []


class TestExtractKeywords:
    def test_extracts_technical_terms(self):
        from compound_agent.knowledge_scanner import _extract_keywords
        kws = _extract_keywords("Build a RAG pipeline with LLM integration")
        assert "pipeline" in kws
        assert "integration" in kws

    def test_extracts_quoted_terms(self):
        from compound_agent.knowledge_scanner import _extract_keywords
        kws = _extract_keywords('Implement "smart caching" for the API')
        assert "smart caching" in kws

    def test_caps_at_10(self):
        from compound_agent.knowledge_scanner import _extract_keywords
        long_text = " ".join(f"keyword{i}" for i in range(20))
        kws = _extract_keywords(long_text)
        assert len(kws) <= 10


class TestIdeaTracking:
    def test_matches_idea_to_commits(self, tmp_path):
        evo = make_evolution(tmp_path)
        vault = tmp_path / "vault"
        vault.mkdir()
        ideas_file = vault / "project-ideas.md"
        ideas_file.write_text(
            "## 2026-04-01\n\n"
            "status: proposed\n\n"
            "- Build a RAG pipeline for document search\n"
        )
        evo.config.vault_path = str(vault)
        evo.config.ideas_file = "project-ideas.md"
        evo.config.project_repos = {"my-project": str(tmp_path)}

        # Mock git commits (imported in evolution from meta_reviewer)
        with patch("compound_agent.meta_reviewer._git_commits_since", return_value=[
            "abc1234 feat: implement RAG pipeline for docs",
            "def5678 fix: pipeline indexing bug",
        ]):
            matches = evo.track_idea_outcomes()

        assert len(matches) == 1
        assert matches[0]["project"] == "my-project"
        assert len(matches[0]["matched_keywords"]) >= 2

    def test_no_match_stays_pending(self, tmp_path):
        evo = make_evolution(tmp_path)
        vault = tmp_path / "vault"
        vault.mkdir()
        ideas_file = vault / "project-ideas.md"
        ideas_file.write_text(
            "## 2026-04-01\n\n"
            "status: proposed\n\n"
            "- Build quantum teleportation device\n"
        )
        evo.config.vault_path = str(vault)
        evo.config.ideas_file = "project-ideas.md"
        evo.config.project_repos = {"my-project": str(tmp_path)}

        with patch("compound_agent.meta_reviewer._git_commits_since", return_value=[
            "abc1234 fix: login button color",
        ]):
            matches = evo.track_idea_outcomes()

        assert len(matches) == 0


# ===========================================================================
# Integration
# ===========================================================================

class TestEvolutionIntegration:
    def test_evaluate_and_adjust_with_no_data(self, tmp_path):
        evo = make_evolution(tmp_path)
        # No source scores, no reading times → no changes
        result = evo.evaluate_and_adjust()
        assert result == []

    def test_evaluate_aborts_on_engagement_drop(self, tmp_path):
        mem = make_memory(tmp_path)
        now = _now_kst()

        # Old baseline: all positive
        for i in range(10):
            mem.engagement_log.append({
                "briefing_type": "trend", "message_id": i,
                "reaction": "positive",
                "reacted_at": (now - timedelta(days=40 + i)).isoformat(),
            })
        # Recent: all ignored
        for i in range(10):
            mem.engagement_log.append({
                "briefing_type": "trend", "message_id": 100 + i,
                "reaction": "ignored",
                "reacted_at": (now - timedelta(days=i + 1)).isoformat(),
            })

        evo = make_evolution(tmp_path, memory=mem)
        # Set up a source that would normally trigger a change
        mem.source_scores["Hacker News"] = {
            "quality": 0.015, "total_shown": 60, "positive": 1, "negative": 59,
        }
        result = evo.evaluate_and_adjust()
        # Should abort due to engagement drop, not make changes
        assert result == []

    def test_evolution_skipped_when_not_self_improving(self, tmp_path):
        """Brain._run_evolution should be a no-op when mode != self-improving."""
        from compound_agent.brain import Brain
        from compound_agent.agent_state import AgentState

        config = FakeConfig(agent_mode="proactive")
        state = AgentState(state_path=str(tmp_path / "state.json"))
        mem = make_memory(tmp_path)
        from compound_agent.hands import Hands
        hands = Hands(config, memory=mem)
        brain = Brain(config, state, hands, memory=mem)

        results = brain._run_evolution()
        assert results == []
