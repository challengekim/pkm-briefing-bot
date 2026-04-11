"""Integration tests for multi-agent mode end-to-end flows."""
import json
import pytest
from unittest.mock import MagicMock, patch

from compound_agent.agents.base import AgentResult
from compound_agent.agents import AgentRegistry, create_default_registry
from compound_agent.agents.orchestrator import Orchestrator
from compound_agent.session.event_log import EventLog


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _mock_config(agent_mode="multi-agent"):
    config = MagicMock()
    config.agent_mode = agent_mode
    config.orchestrator_max_llm_calls = 6
    config.orchestrator_planning_mode = None
    config.vault_path = "/tmp/vault"
    config.knowledge_scan_paths = []
    config.project_context = "test"
    config.language = "ko"
    config.telegram_bot_token = "test"
    config.telegram_chat_id = "123"
    config.gemini_api_key = "test"
    config.agent_state_path = "/tmp/state.json"
    config.agent_memory_path = "/tmp/memory.json"
    config.agent_ema_alpha = 0.2
    config.agent_min_reading_samples = 5
    config.agent_autonomy = "medium"
    config.event_log_path = ""  # will be overridden
    config.agents_config = {"researcher": True, "analyst": True}
    config.schedule = {}
    return config


def _mock_summarizer(plan_response=None):
    summarizer = MagicMock()
    if plan_response is None:
        plan_response = json.dumps([
            {"agent": "researcher", "task": {"type": "trending_relevant"}}
        ])
    summarizer._generate.return_value = plan_response
    return summarizer


# ------------------------------------------------------------------
# Test: Orchestrator run_cycle produces results and logs events
# ------------------------------------------------------------------

class TestOrchestratorRunCycleTrend:
    def test_run_cycle_trend_delegates_to_hands(self, tmp_path):
        config = _mock_config()
        memory = MagicMock()
        memory.preferred_categories = ["ai"]
        memory.get_engagement_stats.return_value = {}
        event_log = EventLog(str(tmp_path))
        summarizer = _mock_summarizer()

        registry = AgentRegistry()
        researcher = MagicMock()
        researcher.name = "researcher"
        researcher.get_capabilities.return_value = ["fill_gap", "deep_dive", "trending_relevant"]
        researcher.run.return_value = AgentResult(
            success=True, agent="researcher", task_type="trending_relevant",
            data={"articles": [{"title": "Test"}]}, llm_calls=1,
        )
        registry.register(researcher)

        hands = MagicMock()
        hands.run_trend_digest.return_value = {"success": True, "items_count": 5}

        orch = Orchestrator(config, memory, event_log, registry, hands, summarizer)

        # "trend" is a pipeline action → delegates to Hands
        results = orch.run_cycle("trend")
        assert len(results) == 1
        assert results[0].task_type == "trend"
        hands.run_trend_digest.assert_called_once()

        # Verify EventLog has cycle_start and cycle_end
        events = event_log._read_all()
        event_types = [e["event_type"] for e in events]
        assert "cycle_start" in event_types
        assert "cycle_end" in event_types

    def test_run_cycle_non_pipeline_uses_agents(self, tmp_path):
        """Non-pipeline actions go through LLM planning → agent execution."""
        config = _mock_config()
        memory = MagicMock()
        memory.preferred_categories = ["ai"]
        memory.get_engagement_stats.return_value = {}
        event_log = EventLog(str(tmp_path))

        plan_json = json.dumps([
            {"agent": "researcher", "task": {"type": "trending_relevant"}}
        ])
        summarizer = _mock_summarizer(plan_json)

        registry = AgentRegistry()
        researcher = MagicMock()
        researcher.name = "researcher"
        researcher.get_capabilities.return_value = ["fill_gap", "deep_dive", "trending_relevant"]
        researcher.run.return_value = AgentResult(
            success=True, agent="researcher", task_type="trending_relevant",
            data={"articles": []}, llm_calls=1,
        )
        registry.register(researcher)

        hands = MagicMock()
        orch = Orchestrator(config, memory, event_log, registry, hands, summarizer)

        # "custom_action" is NOT a pipeline action → uses LLM plan
        results = orch.run_cycle("custom_action")
        assert len(results) == 1
        assert results[0].agent == "researcher"
        researcher.run.assert_called_once()

        # EventLog should have task_start, task_end
        events = event_log._read_all()
        event_types = [e["event_type"] for e in events]
        assert "task_start" in event_types
        assert "task_end" in event_types


# ------------------------------------------------------------------
# Test: LLM fallback to rule-based plan
# ------------------------------------------------------------------

class TestLlmFallbackToRules:
    def test_fallback_when_llm_raises(self, tmp_path):
        config = _mock_config()
        memory = MagicMock()
        memory.preferred_categories = []
        memory.get_engagement_stats.return_value = {}
        event_log = EventLog(str(tmp_path))
        summarizer = MagicMock()
        summarizer._generate.side_effect = Exception("No API key")

        registry = AgentRegistry()
        for name in ["researcher", "analyst"]:
            agent = MagicMock()
            agent.name = name
            agent.get_capabilities.return_value = {
                "researcher": ["fill_gap", "deep_dive", "trending_relevant"],
                "analyst": ["compound_analysis", "trend_intersection", "blind_spot_detection"],
            }[name]
            agent.run.return_value = AgentResult(
                success=True, agent=name, task_type="trending_relevant", data={}, llm_calls=0,
            )
            registry.register(agent)

        hands = MagicMock()
        orch = Orchestrator(config, memory, event_log, registry, hands, summarizer)

        # Non-pipeline action triggers LLM planning, which fails → rule-based fallback
        results = orch.run_cycle("suggest_articles")
        # Rule-based plan for "suggest_articles" maps to researcher.fill_gap
        assert len(results) >= 1
        assert any(r.agent == "researcher" for r in results)


# ------------------------------------------------------------------
# Test: Cost guard stops execution
# ------------------------------------------------------------------

class TestCostGuardIntegration:
    def test_cost_guard_limits_execution(self, tmp_path):
        config = _mock_config()
        config.orchestrator_max_llm_calls = 1
        memory = MagicMock()
        memory.preferred_categories = []
        memory.get_engagement_stats.return_value = {}
        event_log = EventLog(str(tmp_path))

        plan_json = json.dumps([
            {"agent": "researcher", "task": {"type": "trending_relevant"}},
            {"agent": "analyst", "task": {"type": "compound_analysis"}},
        ])
        summarizer = _mock_summarizer(plan_json)

        registry = AgentRegistry()
        for name in ["researcher", "analyst"]:
            agent = MagicMock()
            agent.name = name
            agent.get_capabilities.return_value = {
                "researcher": ["fill_gap", "deep_dive", "trending_relevant"],
                "analyst": ["compound_analysis", "trend_intersection", "blind_spot_detection"],
            }[name]
            # Each agent uses 2 LLM calls
            agent.run.return_value = AgentResult(
                success=True, agent=name, task_type="trending_relevant",
                data={}, llm_calls=2,
            )
            registry.register(agent)

        hands = MagicMock()
        orch = Orchestrator(config, memory, event_log, registry, hands, summarizer)

        # max_llm_calls=1, planning uses 1 call, first agent uses 2 → stops
        # But planning call puts us at 1 (= limit), so execution starts at limit
        # and the cost guard in _execute_plan skips all steps
        results = orch.run_cycle("custom_action")
        # At most 1 agent should have run (the one before budget was exceeded)
        assert len(results) <= 1


# ------------------------------------------------------------------
# Test: Reactive mode backward compatibility
# ------------------------------------------------------------------

class TestReactiveModeBackwardCompat:
    @patch("compound_agent.knowledge_scanner.scan_recent_notes", return_value=[])
    def test_brain_tick_trend_delegates_to_hands(self, mock_scan):
        from compound_agent.brain import Brain

        config = _mock_config(agent_mode="reactive")
        config.schedule_timezone = "Asia/Seoul"

        state = MagicMock()
        state.get_recent_saves.return_value = []
        state.get_saves_by_category.return_value = {}
        state.days_since_action.return_value = 999
        state.get_failure_count.return_value = 0
        state.deferred_actions = []

        hands = MagicMock()
        hands.run_trend_digest.return_value = {"success": True, "items_count": 5}

        brain = Brain(config, state, hands, memory=None)
        results = brain.tick(scheduled_action="trend")

        # Brain should have called hands.run_trend_digest
        hands.run_trend_digest.assert_called_once()


# ------------------------------------------------------------------
# Test: Disabled mode uses process_* directly
# ------------------------------------------------------------------

class TestDisabledModeBackwardCompat:
    def test_disabled_mode_uses_briefing_types_map(self):
        """Verify _BRIEFING_TYPES maps to process_* functions."""
        from compound_agent.main import _BRIEFING_TYPES

        assert "morning" in _BRIEFING_TYPES
        assert "trend" in _BRIEFING_TYPES
        assert "evening" in _BRIEFING_TYPES
        assert "knowledge" in _BRIEFING_TYPES
        assert "linkedin" in _BRIEFING_TYPES
        assert "meta" in _BRIEFING_TYPES
        assert "weekly" in _BRIEFING_TYPES

        # All values should be callable functions
        for name, func in _BRIEFING_TYPES.items():
            assert callable(func), f"{name} handler is not callable"
