"""Base agent abstractions for the compound agent system."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AgentResult:
    success: bool
    agent: str           # "researcher" | "curator" | "analyst" | "writer"
    task_type: str       # "fill_gap" | "compound_analysis" etc.
    data: dict = field(default_factory=dict)
    error: str | None = None
    llm_calls: int = 0
    duration_ms: int = 0


class BaseAgent(ABC):
    name: str = ""
    description: str = ""

    def __init__(self, config, summarizer, memory=None):
        self.config = config
        self.summarizer = summarizer
        self.memory = memory

    @abstractmethod
    def run(self, task: dict) -> AgentResult: ...

    def get_capabilities(self) -> list[str]:
        """Return list of task types from TASK_TYPES class var."""
        return list(getattr(self, "TASK_TYPES", {}).keys())

    def validate_task(self, task: dict) -> bool:
        """Check task has required fields."""
        task_type = task.get("type")
        if task_type not in self.get_capabilities():
            return False
        schema = self.TASK_TYPES.get(task_type, {})
        return all(k in task for k in schema.get("required", []))

    def _generate(self, prompt: str) -> str:
        return self.summarizer._generate(prompt)

    def _make_result(
        self,
        task_type: str,
        data: dict,
        llm_calls: int = 0,
        duration_ms: int = 0,
        error: str = None,
    ) -> AgentResult:
        return AgentResult(
            success=error is None,
            agent=self.name,
            task_type=task_type,
            data=data,
            error=error,
            llm_calls=llm_calls,
            duration_ms=duration_ms,
        )
