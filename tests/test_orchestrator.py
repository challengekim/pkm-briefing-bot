"""Tests for Orchestrator."""
import json
import pytest
from unittest.mock import MagicMock, patch, call

from compound_agent.agents.base import AgentResult
from compound_agent.agents import AgentRegistry
from compound_agent.agents.orchestrator import Orchestrator


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_registry(agents=("researcher", "analyst")):
    registry = AgentRegistry()
    for name in agents:
        agent = MagicMock()
        agent.name = name
        agent.get_capabilities.return_value = {
            "researcher": ["fill_gap", "deep_dive", "trending_relevant"],
            "analyst": ["compound_analysis", "trend_intersection", "blind_spot_detection"],
        }.get(name, ["task_x"])
        agent.run.return_value = AgentResult(
            success=True, agent=name, task_type="trending_relevant", data={"items": []}
        )
        registry.register(agent)
    return registry


def _make_orchestrator(scheduled_action=None, max_llm_calls=6):
    config = MagicMock()
    config.orchestrator_max_llm_calls = max_llm_calls
    memory = MagicMock()
    memory.preferred_categories = ["ai"]
    memory.get_engagement_stats.return_value = {}

    event_log = MagicMock()
    event_log.get_last_cycle.return_value = []

    registry = _make_registry()
    hands = MagicMock()
    hands.run_morning_briefing.return_value = {"success": True, "action": "morning"}
    hands.run_trend_digest.return_value = {"success": True, "items_count": 5}
    hands.run_weekly_knowledge.return_value = {"success": True}
    hands.run_meta_review.return_value = {"success": True}
    hands.run_weekly.return_value = {"success": True}
    hands.run_evening_review.return_value = {"success": True}
    hands.run_linkedin_draft.return_value = {"success": True}

    summarizer = MagicMock()
    summarizer._generate.return_value = json.dumps([
        {"agent": "researcher", "task": {"type": "trending_relevant"}}
    ])

    orch = Orchestrator(config, memory, event_log, registry, hands, summarizer)
    return orch


# ------------------------------------------------------------------
# Pipeline delegation
# ------------------------------------------------------------------

class TestPipelineDelegation:
    def test_morning_delegates_to_hands(self):
        orch = _make_orchestrator()
        results = orch.run_cycle("morning")
        orch.hands.run_morning_briefing.assert_called_once()
        assert len(results) == 1
        assert results[0].task_type == "morning"

    def test_trend_delegates_to_hands(self):
        orch = _make_orchestrator()
        results = orch.run_cycle("trend")
        orch.hands.run_trend_digest.assert_called_once()
        assert results[0].success is True

    def test_weekly_delegates_to_hands(self):
        orch = _make_orchestrator()
        results = orch.run_cycle("weekly")
        orch.hands.run_weekly.assert_called_once()

    def test_meta_delegates_to_hands(self):
        orch = _make_orchestrator()
        results = orch.run_cycle("meta")
        orch.hands.run_meta_review.assert_called_once()

    def test_knowledge_delegates_to_hands(self):
        orch = _make_orchestrator()
        results = orch.run_cycle("knowledge")
        orch.hands.run_weekly_knowledge.assert_called_once()

    def test_pipeline_logs_cycle_start_and_end(self):
        orch = _make_orchestrator()
        orch.run_cycle("morning")
        assert orch.event_log.append.call_count >= 2
        first_call = orch.event_log.append.call_args_list[0]
        assert first_call[0][0] == "cycle_start"

    def test_pipeline_hands_failure_returns_error_result(self):
        orch = _make_orchestrator()
        orch.hands.run_morning_briefing.side_effect = RuntimeError("connection failed")
        results = orch.run_cycle("morning")
        assert results[0].success is False
        assert "connection failed" in results[0].error


# ------------------------------------------------------------------
# Planning — JSON parsing
# ------------------------------------------------------------------

class TestPlanParsing:
    def test_parses_valid_json(self):
        orch = _make_orchestrator()
        plan_json = json.dumps([
            {"agent": "researcher", "task": {"type": "trending_relevant"}}
        ])
        orch.summarizer._generate.return_value = plan_json
        plan = orch._plan(orch._build_context())
        assert len(plan) == 1
        assert plan[0]["agent"] == "researcher"

    def test_parses_json_in_code_fence(self):
        orch = _make_orchestrator()
        plan_json = json.dumps([
            {"agent": "analyst", "task": {"type": "compound_analysis"}}
        ])
        orch.summarizer._generate.return_value = f"Here is the plan:\n```json\n{plan_json}\n```"
        plan = orch._plan(orch._build_context())
        assert plan[0]["agent"] == "analyst"

    def test_fallback_on_invalid_json(self):
        orch = _make_orchestrator()
        orch.summarizer._generate.return_value = "not json at all"
        plan = orch._plan(orch._build_context("trend"))
        # Should fall back to rule-based
        assert isinstance(plan, list)
        assert len(plan) >= 1

    def test_fallback_on_unknown_agent_in_plan(self):
        orch = _make_orchestrator()
        bad_plan = json.dumps([{"agent": "nonexistent", "task": {"type": "task_x"}}])
        orch.summarizer._generate.return_value = bad_plan
        plan = orch._plan(orch._build_context())
        # Falls back to rule-based, which uses known agents
        assert all(orch.registry.get(s["agent"]) is not None for s in plan)

    def test_fallback_on_llm_exception(self):
        orch = _make_orchestrator()
        orch.summarizer._generate.side_effect = Exception("API error")
        plan = orch._plan(orch._build_context())
        assert isinstance(plan, list)
        assert len(plan) >= 1


# ------------------------------------------------------------------
# Rule-based planning
# ------------------------------------------------------------------

class TestRuleBasedPlan:
    def test_trend_action_maps_to_researcher_trending(self):
        orch = _make_orchestrator()
        plan = orch._rule_based_plan({"scheduled_action": "trend"})
        assert plan[0]["agent"] == "researcher"
        assert plan[0]["task"]["type"] == "trending_relevant"

    def test_knowledge_action_maps_to_analyst_compound(self):
        orch = _make_orchestrator()
        plan = orch._rule_based_plan({"scheduled_action": "knowledge"})
        assert plan[0]["agent"] == "analyst"
        assert plan[0]["task"]["type"] == "compound_analysis"

    def test_suggest_articles_maps_to_fill_gap(self):
        orch = _make_orchestrator()
        plan = orch._rule_based_plan({"scheduled_action": "suggest_articles"})
        assert plan[0]["agent"] == "researcher"
        assert plan[0]["task"]["type"] == "fill_gap"

    def test_topic_summary_maps_to_trend_intersection(self):
        orch = _make_orchestrator()
        plan = orch._rule_based_plan({"scheduled_action": "topic_summary"})
        assert plan[0]["agent"] == "analyst"
        assert plan[0]["task"]["type"] == "trend_intersection"

    def test_unknown_action_returns_default_plan(self):
        orch = _make_orchestrator()
        plan = orch._rule_based_plan({"scheduled_action": "something_else"})
        assert len(plan) >= 1


# ------------------------------------------------------------------
# Execution
# ------------------------------------------------------------------

class TestExecutePlan:
    def test_executes_all_steps(self):
        orch = _make_orchestrator()
        plan = [
            {"agent": "researcher", "task": {"type": "trending_relevant"}},
            {"agent": "analyst", "task": {"type": "compound_analysis"}},
        ]
        results = orch._execute_plan(plan)
        assert len(results) == 2

    def test_chains_depends_on_result(self):
        orch = _make_orchestrator()
        upstream_data = {"articles": ["a", "b"]}
        orch.registry.get("researcher").run.return_value = AgentResult(
            success=True, agent="researcher", task_type="trending_relevant",
            data=upstream_data
        )
        captured_tasks = []
        def capture_run(task):
            captured_tasks.append(dict(task))
            return AgentResult(success=True, agent="analyst", task_type="compound_analysis", data={})
        orch.registry.get("analyst").run.side_effect = capture_run

        plan = [
            {"agent": "researcher", "task": {"type": "trending_relevant"}},
            {"agent": "analyst", "task": {"type": "compound_analysis"}, "depends_on": 0},
        ]
        orch._execute_plan(plan)
        assert captured_tasks[0].get("input") == upstream_data

    def test_agent_failure_does_not_crash_cycle(self):
        orch = _make_orchestrator()
        orch.registry.get("researcher").run.side_effect = RuntimeError("crash")
        plan = [
            {"agent": "researcher", "task": {"type": "trending_relevant"}},
            {"agent": "analyst", "task": {"type": "compound_analysis"}},
        ]
        results = orch._execute_plan(plan)
        assert results[0].success is False
        assert results[1].success is True  # analyst still ran

    def test_missing_agent_returns_error_result(self):
        orch = _make_orchestrator()
        plan = [{"agent": "ghost_agent", "task": {"type": "task_x"}}]
        results = orch._execute_plan(plan)
        assert results[0].success is False
        assert "ghost_agent" in results[0].error


# ------------------------------------------------------------------
# Cost guard
# ------------------------------------------------------------------

class TestCostGuard:
    def test_cost_guard_stops_execution(self):
        orch = _make_orchestrator(max_llm_calls=1)
        # Each agent.run returns llm_calls=2, exhausting the budget after step 0
        for name in ["researcher", "analyst"]:
            orch.registry.get(name).run.return_value = AgentResult(
                success=True, agent=name, task_type="trending_relevant",
                data={}, llm_calls=2
            )
        plan = [
            {"agent": "researcher", "task": {"type": "trending_relevant"}},
            {"agent": "analyst", "task": {"type": "compound_analysis"}},
        ]
        results = orch._execute_plan(plan)
        # Only first step should execute (llm_calls=2 > limit=1 after step 0)
        assert len(results) == 1

    def test_cost_guard_prevents_planning_llm_call(self):
        orch = _make_orchestrator(max_llm_calls=0)
        context = orch._build_context("trend")
        plan = orch._plan(context)
        # LLM should not be called; falls back to rule-based
        orch.summarizer._generate.assert_not_called()
        assert isinstance(plan, list)


# ------------------------------------------------------------------
# Full cycle integration
# ------------------------------------------------------------------

class TestFullCycleWithMockLlm:
    def test_full_cycle_no_scheduled_action(self):
        orch = _make_orchestrator()
        results = orch.run_cycle()
        assert isinstance(results, list)
        # cycle_start and cycle_end should be logged
        event_types = [c[0][0] for c in orch.event_log.append.call_args_list]
        assert "cycle_start" in event_types
        assert "cycle_end" in event_types

    def test_full_cycle_with_valid_llm_plan(self):
        orch = _make_orchestrator()
        orch.summarizer._generate.return_value = json.dumps([
            {"agent": "researcher", "task": {"type": "trending_relevant"}},
        ])
        results = orch.run_cycle(scheduled_action=None)
        assert len(results) >= 1
        assert results[0].agent == "researcher"

    def test_context_includes_scheduled_action(self):
        orch = _make_orchestrator()
        context = orch._build_context("trend")
        assert context["scheduled_action"] == "trend"

    def test_context_includes_available_agents(self):
        orch = _make_orchestrator()
        context = orch._build_context()
        assert "researcher" in context["available_agents"]
        assert "analyst" in context["available_agents"]
