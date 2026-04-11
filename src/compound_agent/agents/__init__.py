"""Agent registry and factory for compound agent system."""
from .base import AgentResult, BaseAgent


class AgentRegistry:
    """Discovers and manages available agents."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    def list_capabilities(self) -> dict[str, list[str]]:
        return {name: agent.get_capabilities() for name, agent in self._agents.items()}


def create_default_registry(config, summarizer, memory=None) -> AgentRegistry:
    """Create registry with built-in agents filtered by config."""
    from .researcher import ResearcherAgent
    from .analyst import AnalystAgent

    registry = AgentRegistry()
    agents_config = getattr(config, "agents_config", {})

    if agents_config.get("researcher", True):
        registry.register(ResearcherAgent(config, summarizer, memory))
    if agents_config.get("analyst", True):
        registry.register(AnalystAgent(config, summarizer, memory))

    return registry


__all__ = ["AgentResult", "BaseAgent", "AgentRegistry", "create_default_registry"]
