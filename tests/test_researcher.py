"""Tests for ResearcherAgent."""
import pytest
from unittest.mock import MagicMock, patch

from compound_agent.agents.researcher import ResearcherAgent


SAMPLE_ARTICLES = [
    {"title": "AI breakthrough in 2024", "url": "http://a.com", "score": 10, "source": "HN"},
    {"title": "Python 3.13 released", "url": "http://b.com", "score": 5, "source": "HN"},
    {"title": "Machine learning trends", "url": "http://c.com", "score": 8, "source": "HN"},
]


@pytest.fixture
def agent():
    config = MagicMock()
    summarizer = MagicMock()
    summarizer._generate.return_value = "AI breakthrough in 2024, Machine learning trends"
    return ResearcherAgent(config, summarizer)


class TestResearcherValidateTask:
    def test_fill_gap_requires_category(self, agent):
        assert agent.validate_task({"type": "fill_gap", "category": "ai"}) is True
        assert agent.validate_task({"type": "fill_gap"}) is False

    def test_deep_dive_requires_topic(self, agent):
        assert agent.validate_task({"type": "deep_dive", "topic": "llm"}) is True
        assert agent.validate_task({"type": "deep_dive"}) is False

    def test_trending_relevant_no_required(self, agent):
        assert agent.validate_task({"type": "trending_relevant"}) is True

    def test_unknown_type_invalid(self, agent):
        assert agent.validate_task({"type": "unknown_task"}) is False


class TestFillGap:
    def test_returns_articles_and_category(self, agent):
        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=SAMPLE_ARTICLES):
            result = agent.run({"type": "fill_gap", "category": "ai"})
        assert result.success is True
        assert result.agent == "researcher"
        assert result.task_type == "fill_gap"
        assert "articles" in result.data
        assert result.data["category"] == "ai"

    def test_llm_called_once(self, agent):
        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=SAMPLE_ARTICLES):
            result = agent.run({"type": "fill_gap", "category": "ai"})
        assert result.llm_calls == 1
        agent.summarizer._generate.assert_called_once()

    def test_empty_trends_returns_empty_articles(self, agent):
        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=[]):
            result = agent.run({"type": "fill_gap", "category": "ai"})
        assert result.success is True
        assert result.data["articles"] == []
        assert result.llm_calls == 0

    def test_invalid_task_returns_error(self, agent):
        result = agent.run({"type": "fill_gap"})  # missing category
        assert result.success is False
        assert result.error is not None


class TestDeepDive:
    def test_returns_brief_and_articles(self, agent):
        agent.summarizer._generate.return_value = "Brief summary text"
        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=SAMPLE_ARTICLES):
            result = agent.run({"type": "deep_dive", "topic": "AI"})
        assert result.success is True
        assert result.task_type == "deep_dive"
        assert "brief" in result.data
        assert "articles" in result.data
        assert result.data["topic"] == "AI"

    def test_llm_called_once(self, agent):
        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=SAMPLE_ARTICLES):
            result = agent.run({"type": "deep_dive", "topic": "AI"})
        assert result.llm_calls == 1

    def test_invalid_task_returns_error(self, agent):
        result = agent.run({"type": "deep_dive"})  # missing topic
        assert result.success is False


class TestTrendingRelevant:
    def test_returns_articles_and_interests(self, agent):
        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=SAMPLE_ARTICLES):
            result = agent.run({"type": "trending_relevant", "interests": ["ai", "ml"]})
        assert result.success is True
        assert result.task_type == "trending_relevant"
        assert "articles" in result.data

    def test_uses_memory_preferred_categories(self):
        config = MagicMock()
        summarizer = MagicMock()
        summarizer._generate.return_value = "AI breakthrough in 2024"
        memory = MagicMock()
        memory.preferred_categories = ["ai", "python"]
        agent = ResearcherAgent(config, summarizer, memory)

        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=SAMPLE_ARTICLES):
            result = agent.run({"type": "trending_relevant"})
        assert result.success is True

    def test_empty_trends_no_llm_call(self, agent):
        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=[]):
            result = agent.run({"type": "trending_relevant"})
        assert result.llm_calls == 0
        assert result.data["articles"] == []

    def test_duration_ms_set(self, agent):
        with patch("compound_agent.agents.researcher.fetch_all_trends", return_value=SAMPLE_ARTICLES):
            result = agent.run({"type": "trending_relevant"})
        assert result.duration_ms >= 0
