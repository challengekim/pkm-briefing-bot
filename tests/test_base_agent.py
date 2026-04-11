"""Tests for BaseAgent, AgentResult, and AgentRegistry."""
import pytest
from unittest.mock import MagicMock

from compound_agent.agents.base import AgentResult, BaseAgent
from compound_agent.agents import AgentRegistry, create_default_registry


# ------------------------------------------------------------------
# Concrete stub for testing abstract BaseAgent
# ------------------------------------------------------------------

class StubAgent(BaseAgent):
    name = "stub"
    description = "Test stub"
    TASK_TYPES = {
        "task_a": {"required": ["field1"]},
        "task_b": {"required": []},
    }

    def run(self, task: dict) -> AgentResult:
        return self._make_result(task.get("type", "unknown"), {"ran": True})


class TestAgentResult:
    def test_success_true_when_no_error(self):
        r = AgentResult(success=True, agent="stub", task_type="task_a")
        assert r.success is True
        assert r.error is None

    def test_default_fields(self):
        r = AgentResult(success=False, agent="x", task_type="y")
        assert r.data == {}
        assert r.llm_calls == 0
        assert r.duration_ms == 0


class TestBaseAgentCapabilities:
    def setup_method(self):
        self.agent = StubAgent(MagicMock(), MagicMock())

    def test_get_capabilities_returns_task_types(self):
        caps = self.agent.get_capabilities()
        assert set(caps) == {"task_a", "task_b"}

    def test_validate_task_valid(self):
        assert self.agent.validate_task({"type": "task_a", "field1": "x"}) is True

    def test_validate_task_missing_required_field(self):
        assert self.agent.validate_task({"type": "task_a"}) is False

    def test_validate_task_unknown_type(self):
        assert self.agent.validate_task({"type": "unknown"}) is False

    def test_validate_task_no_required_fields(self):
        assert self.agent.validate_task({"type": "task_b"}) is True

    def test_make_result_success(self):
        r = self.agent._make_result("task_a", {"x": 1}, llm_calls=2, duration_ms=100)
        assert r.success is True
        assert r.agent == "stub"
        assert r.task_type == "task_a"
        assert r.data == {"x": 1}
        assert r.llm_calls == 2
        assert r.duration_ms == 100
        assert r.error is None

    def test_make_result_with_error(self):
        r = self.agent._make_result("task_a", {}, error="oops")
        assert r.success is False
        assert r.error == "oops"

    def test_generate_delegates_to_summarizer(self):
        mock_summarizer = MagicMock()
        mock_summarizer._generate.return_value = "response"
        agent = StubAgent(MagicMock(), mock_summarizer)
        result = agent._generate("prompt")
        mock_summarizer._generate.assert_called_once_with("prompt")
        assert result == "response"


class TestAgentRegistry:
    def setup_method(self):
        self.registry = AgentRegistry()
        self.agent = StubAgent(MagicMock(), MagicMock())
        self.registry.register(self.agent)

    def test_register_and_get(self):
        got = self.registry.get("stub")
        assert got is self.agent

    def test_get_missing_returns_none(self):
        assert self.registry.get("nonexistent") is None

    def test_list_agents(self):
        assert "stub" in self.registry.list_agents()

    def test_list_capabilities(self):
        caps = self.registry.list_capabilities()
        assert "stub" in caps
        assert set(caps["stub"]) == {"task_a", "task_b"}

    def test_register_multiple_agents(self):
        class OtherAgent(BaseAgent):
            name = "other"
            TASK_TYPES = {"other_task": {"required": []}}
            def run(self, task): ...

        other = OtherAgent(MagicMock(), MagicMock())
        self.registry.register(other)
        assert set(self.registry.list_agents()) == {"stub", "other"}


class TestCreateDefaultRegistry:
    def test_creates_researcher_and_analyst_by_default(self):
        config = MagicMock()
        config.agents_config = {}
        summarizer = MagicMock()
        registry = create_default_registry(config, summarizer)
        agents = registry.list_agents()
        assert "researcher" in agents
        assert "analyst" in agents

    def test_researcher_disabled_via_config(self):
        config = MagicMock()
        config.agents_config = {"researcher": False}
        registry = create_default_registry(config, MagicMock())
        assert "researcher" not in registry.list_agents()
        assert "analyst" in registry.list_agents()

    def test_analyst_disabled_via_config(self):
        config = MagicMock()
        config.agents_config = {"analyst": False}
        registry = create_default_registry(config, MagicMock())
        assert "analyst" not in registry.list_agents()
        assert "researcher" in registry.list_agents()

    def test_no_agents_config_attr_uses_defaults(self):
        config = MagicMock(spec=[])  # no agents_config attribute
        registry = create_default_registry(config, MagicMock())
        assert "researcher" in registry.list_agents()
        assert "analyst" in registry.list_agents()
