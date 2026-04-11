"""Tests for AnalystAgent."""
import pytest
from unittest.mock import MagicMock, patch

from compound_agent.agents.analyst import AnalystAgent


SAMPLE_NOTES = [
    {"title": "LLM paper review", "category": "ai", "saved": "2024-01-10", "description": "", "tags": "", "source": ""},
    {"title": "Python packaging guide", "category": "python", "saved": "2024-01-09", "description": "", "tags": "", "source": ""},
    {"title": "RAG architecture patterns", "category": "ai", "saved": "2024-01-08", "description": "", "tags": "", "source": ""},
]

SAMPLE_TRENDS = [
    {"title": "Rust systems programming", "url": "http://a.com", "score": 10, "source": "HN"},
    {"title": "WebAssembly future", "url": "http://b.com", "score": 8, "source": "HN"},
]


@pytest.fixture
def agent():
    config = MagicMock()
    config.vault_path = "/fake/vault"
    summarizer = MagicMock()
    summarizer._generate.return_value = "Analysis result text"
    return AnalystAgent(config, summarizer)


class TestAnalystValidateTask:
    def test_compound_analysis_valid(self, agent):
        assert agent.validate_task({"type": "compound_analysis"}) is True

    def test_trend_intersection_valid(self, agent):
        assert agent.validate_task({"type": "trend_intersection"}) is True

    def test_blind_spot_detection_valid(self, agent):
        assert agent.validate_task({"type": "blind_spot_detection"}) is True

    def test_unknown_type_invalid(self, agent):
        assert agent.validate_task({"type": "bad_type"}) is False


class TestCompoundAnalysis:
    def test_returns_analysis_and_metadata(self, agent):
        with patch("compound_agent.agents.analyst.load_previous_weekly_reports", return_value="Week 1 report"):
            with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=SAMPLE_NOTES):
                result = agent.run({"type": "compound_analysis"})
        assert result.success is True
        assert result.agent == "analyst"
        assert result.task_type == "compound_analysis"
        assert "analysis" in result.data
        assert "period_weeks" in result.data
        assert "note_count" in result.data

    def test_llm_called_once(self, agent):
        with patch("compound_agent.agents.analyst.load_previous_weekly_reports", return_value=""):
            with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=SAMPLE_NOTES):
                result = agent.run({"type": "compound_analysis"})
        assert result.llm_calls == 1
        agent.summarizer._generate.assert_called_once()

    def test_accepts_period_weeks_param(self, agent):
        with patch("compound_agent.agents.analyst.load_previous_weekly_reports", return_value="") as mock_load:
            with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=[]):
                result = agent.run({"type": "compound_analysis", "period_weeks": 8})
        assert result.data["period_weeks"] == 8
        mock_load.assert_called_once_with(agent.config.vault_path, weeks=8)

    def test_invalid_task_returns_error(self, agent):
        result = agent.run({"type": "nonexistent"})
        assert result.success is False


class TestTrendIntersection:
    def test_returns_intersections(self, agent):
        with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=SAMPLE_NOTES):
            result = agent.run({"type": "trend_intersection"})
        assert result.success is True
        assert result.task_type == "trend_intersection"
        assert "intersections" in result.data
        assert "categories" in result.data

    def test_llm_called_when_notes_exist(self, agent):
        with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=SAMPLE_NOTES):
            result = agent.run({"type": "trend_intersection"})
        assert result.llm_calls == 1

    def test_no_llm_call_when_no_notes(self, agent):
        with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=[]):
            result = agent.run({"type": "trend_intersection"})
        assert result.llm_calls == 0
        assert result.data["note_count"] == 0

    def test_duration_ms_set(self, agent):
        with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=SAMPLE_NOTES):
            result = agent.run({"type": "trend_intersection"})
        assert result.duration_ms >= 0


class TestBlindSpotDetection:
    def test_returns_gaps_and_counts(self, agent):
        with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=SAMPLE_NOTES):
            with patch("compound_agent.agents.analyst.fetch_all_trends", return_value=SAMPLE_TRENDS):
                result = agent.run({"type": "blind_spot_detection"})
        assert result.success is True
        assert result.task_type == "blind_spot_detection"
        assert "gaps" in result.data
        assert "user_note_count" in result.data
        assert "trend_count" in result.data

    def test_llm_called_once(self, agent):
        with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=SAMPLE_NOTES):
            with patch("compound_agent.agents.analyst.fetch_all_trends", return_value=SAMPLE_TRENDS):
                result = agent.run({"type": "blind_spot_detection"})
        assert result.llm_calls == 1

    def test_counts_match_inputs(self, agent):
        with patch("compound_agent.agents.analyst.scan_recent_notes", return_value=SAMPLE_NOTES):
            with patch("compound_agent.agents.analyst.fetch_all_trends", return_value=SAMPLE_TRENDS):
                result = agent.run({"type": "blind_spot_detection"})
        assert result.data["user_note_count"] == len(SAMPLE_NOTES)
        assert result.data["trend_count"] == len(SAMPLE_TRENDS)
