"""Tests for CuratorAgent."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from compound_agent.agents.curator import CuratorAgent


def make_note(title="Note", description="A description", category="ai", saved=None, tags="[ai, ml]", source=""):
    if saved is None:
        saved = datetime.now().strftime("%Y-%m-%d")
    return {
        "title": title,
        "description": description,
        "category": category,
        "saved": saved,
        "tags": tags,
        "source": source,
    }


@pytest.fixture
def agent():
    config = MagicMock()
    summarizer = MagicMock()
    summarizer._generate.return_value = "Note A and Note B are connected via machine learning themes."
    return CuratorAgent(config, summarizer)


class TestValidateTask:
    def test_validate_task_rejects_unknown(self, agent):
        assert agent.validate_task({"type": "nonexistent_task"}) is False

    def test_connect_notes_no_required_fields(self, agent):
        assert agent.validate_task({"type": "connect_notes"}) is True

    def test_quality_audit_no_required_fields(self, agent):
        assert agent.validate_task({"type": "quality_audit"}) is True

    def test_archive_stale_requires_days(self, agent):
        assert agent.validate_task({"type": "archive_stale", "days": 30}) is True
        assert agent.validate_task({"type": "archive_stale"}) is False


class TestConnectNotes:
    def test_connect_notes_with_notes(self, agent):
        notes = [
            make_note("AI Agents Overview", category="ai"),
            make_note("Python Best Practices", category="engineering"),
            make_note("Startup Growth Metrics", category="business"),
        ]
        with patch("compound_agent.agents.curator.scan_recent_notes", return_value=notes):
            result = agent.run({"type": "connect_notes"})

        assert result.success is True
        assert result.agent == "curator"
        assert result.task_type == "connect_notes"
        assert result.llm_calls == 1
        agent.summarizer._generate.assert_called_once()
        assert "connections" in result.data
        assert result.data["note_count"] == 3

    def test_connect_notes_empty_vault(self, agent):
        with patch("compound_agent.agents.curator.scan_recent_notes", return_value=[]):
            result = agent.run({"type": "connect_notes"})

        assert result.success is True
        assert result.llm_calls == 0
        agent.summarizer._generate.assert_not_called()
        assert result.data["connections"] == []
        assert result.data["note_count"] == 0


class TestQualityAudit:
    def test_quality_audit_finds_issues(self, agent):
        notes = [
            make_note("Good Note", description="Has description", tags="[ai]"),
            make_note("Bad Note 1", description="", tags=""),
            make_note("Bad Note 2", description="Has desc", tags=""),
        ]
        with patch("compound_agent.agents.curator.scan_recent_notes", return_value=notes):
            result = agent.run({"type": "quality_audit"})

        assert result.success is True
        assert result.llm_calls == 0
        assert result.data["total_audited"] == 3
        issue_titles = [i["title"] for i in result.data["issues"]]
        assert "Bad Note 1" in issue_titles
        assert "Bad Note 2" in issue_titles
        assert "Good Note" not in issue_titles

    def test_quality_audit_clean_notes(self, agent):
        notes = [
            make_note("Note A", description="Good description", tags="[ai, ml]"),
            make_note("Note B", description="Another good description", tags="[engineering]"),
        ]
        with patch("compound_agent.agents.curator.scan_recent_notes", return_value=notes):
            result = agent.run({"type": "quality_audit"})

        assert result.success is True
        assert result.llm_calls == 0
        assert result.data["issues"] == []
        assert result.data["total_audited"] == 2


class TestArchiveStale:
    def test_archive_stale_finds_candidates(self, agent):
        old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        recent_date = datetime.now().strftime("%Y-%m-%d")
        notes = [
            make_note("Old Untagged Note", description="", tags="", saved=old_date),
            make_note("Recent Note", description="Has description", tags="[ai]", saved=recent_date),
        ]
        with patch("compound_agent.agents.curator.scan_recent_notes", return_value=notes):
            result = agent.run({"type": "archive_stale", "days": 30})

        assert result.success is True
        assert result.llm_calls == 0
        assert result.data["threshold_days"] == 30
        candidate_titles = [c["title"] for c in result.data["candidates"]]
        assert "Old Untagged Note" in candidate_titles
        assert "Recent Note" not in candidate_titles

    def test_archive_stale_no_candidates(self, agent):
        recent_date = datetime.now().strftime("%Y-%m-%d")
        notes = [
            make_note("Fresh Note A", description="Has description", tags="[ai]", saved=recent_date),
            make_note("Fresh Note B", description="Has description", tags="[ml]", saved=recent_date),
        ]
        with patch("compound_agent.agents.curator.scan_recent_notes", return_value=notes):
            result = agent.run({"type": "archive_stale", "days": 30})

        assert result.success is True
        assert result.data["candidates"] == []
        assert result.data["threshold_days"] == 30
