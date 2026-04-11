"""Tests for WriterAgent."""
import pytest
from unittest.mock import MagicMock, patch

from compound_agent.agents.writer import WriterAgent


SAMPLE_NOTES = [
    {"title": "Python async patterns", "description": "Notes on async/await usage", "category": "python", "saved": "2026-04-01", "tags": ["python", "async"], "source": "vault"},
    {"title": "AI agent architecture", "description": "Multi-agent system design", "category": "ai", "saved": "2026-04-02", "tags": ["ai", "agents"], "source": "vault"},
    {"title": "Machine learning basics", "description": "Intro to ML algorithms", "category": "ml", "saved": "2026-04-03", "tags": ["ml"], "source": "vault"},
]


@pytest.fixture
def agent():
    config = MagicMock()
    summarizer = MagicMock()
    summarizer._generate.return_value = "Generated LLM response"
    return WriterAgent(config, summarizer)


class TestActionPlan:
    def test_action_plan_with_related_notes(self, agent):
        notes_with_topic = [
            {"title": "Python tips", "description": "Python productivity tips", "category": "dev", "saved": "2026-04-01", "tags": [], "source": "vault"},
            {"title": "Other topic", "description": "Unrelated content", "category": "misc", "saved": "2026-04-01", "tags": [], "source": "vault"},
        ]
        with patch("compound_agent.agents.writer.scan_recent_notes", return_value=notes_with_topic):
            result = agent.run({"type": "action_plan", "topic": "Python"})

        assert result.success is True
        assert result.agent == "writer"
        assert result.task_type == "action_plan"
        assert result.llm_calls == 1
        assert "actions" in result.data
        assert result.data["actions"] == "Generated LLM response"
        agent.summarizer._generate.assert_called_once()

    def test_action_plan_no_related_notes(self, agent):
        notes_no_match = [
            {"title": "Unrelated topic A", "description": "Some description", "category": "misc", "saved": "2026-04-01", "tags": [], "source": "vault"},
            {"title": "Unrelated topic B", "description": "Another description", "category": "other", "saved": "2026-04-01", "tags": [], "source": "vault"},
        ]
        with patch("compound_agent.agents.writer.scan_recent_notes", return_value=notes_no_match):
            result = agent.run({"type": "action_plan", "topic": "Python"})

        assert result.success is True
        assert result.llm_calls == 1
        assert "actions" in result.data
        # Falls back to all notes
        assert result.data["note_count"] == len(notes_no_match)

    def test_action_plan_missing_topic_rejected(self, agent):
        with patch("compound_agent.agents.writer.scan_recent_notes", return_value=SAMPLE_NOTES):
            result = agent.run({"type": "action_plan"})

        assert result.success is False
        assert result.error is not None


class TestSummary:
    def test_summary_with_notes(self, agent):
        result = agent.run({"type": "summary", "notes": SAMPLE_NOTES})

        assert result.success is True
        assert result.agent == "writer"
        assert result.task_type == "summary"
        assert result.llm_calls == 1
        assert "summary" in result.data
        assert result.data["summary"] == "Generated LLM response"
        assert result.data["input_count"] == len(SAMPLE_NOTES)
        agent.summarizer._generate.assert_called_once()

    def test_summary_empty_notes(self, agent):
        result = agent.run({"type": "summary", "notes": []})

        assert result.success is True
        assert result.llm_calls == 0
        assert result.data["summary"] == ""
        assert result.data["input_count"] == 0
        agent.summarizer._generate.assert_not_called()


class TestValidateTask:
    def test_validate_task_rejects_unknown(self, agent):
        assert agent.validate_task({"type": "linkedin_draft", "topic": "ai"}) is False
        assert agent.validate_task({"type": "unknown_type"}) is False
        assert agent.validate_task({"type": "action_plan", "topic": "test"}) is True
        assert agent.validate_task({"type": "summary", "notes": []}) is True
