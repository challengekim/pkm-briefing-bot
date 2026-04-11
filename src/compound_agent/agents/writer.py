"""WriterAgent — generates action plans and summaries from vault notes."""
import logging
import time

from .base import BaseAgent, AgentResult, _sanitize
from ..knowledge_scanner import scan_recent_notes

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    name = "writer"
    description = "Generates action plans and summaries from vault notes"

    TASK_TYPES = {
        "action_plan": {"required": ["topic"]},
        "summary": {"required": ["notes"]},
    }

    def run(self, task: dict) -> AgentResult:
        task_type = task.get("type", "unknown")
        start = time.time()

        # Merge injected input from orchestrator depends_on BEFORE validation
        injected = task.get("input")
        if isinstance(injected, dict):
            if "notes" in injected and "notes" not in task:
                task = dict(task, notes=injected["notes"])
            elif "articles" in injected and "notes" not in task:
                task = dict(task, notes=injected["articles"])

        if not self.validate_task(task):
            return self._make_result(
                task_type,
                {},
                error=f"Invalid task: {task}",
            )

        try:
            if task_type == "action_plan":
                data, llm_calls = self._action_plan(task["topic"])
            else:  # summary
                data, llm_calls = self._summary(task["notes"])
        except Exception as e:
            logger.error("WriterAgent error (%s): %s", task_type, e)
            return self._make_result(task_type, {}, error=str(e))

        duration_ms = int((time.time() - start) * 1000)
        return self._make_result(task_type, data, llm_calls=llm_calls, duration_ms=duration_ms)

    # ------------------------------------------------------------------
    # Task implementations
    # ------------------------------------------------------------------

    def _action_plan(self, topic: str) -> tuple[dict, int]:
        """Scan recent vault notes and produce actionable items for the topic."""
        notes = scan_recent_notes(self.config, days=14)
        topic_lower = topic.lower()

        related = [
            n for n in notes
            if topic_lower in n.get("title", "").lower()
            or topic_lower in n.get("description", "").lower()
            or topic_lower in n.get("category", "").lower()
        ]

        if not related:
            related = notes[:20]

        safe_topic = _sanitize(topic)
        note_lines = "\n".join(
            f"- {n.get('title', '')} — {n.get('description', '')}"
            for n in related
        )
        prompt = (
            f"Topic: {safe_topic}\n\n"
            f"Related notes:\n{note_lines}\n\n"
            f"Create 3-5 specific, actionable items based on these notes for the topic '{safe_topic}'."
        )
        actions = self._generate(prompt)
        llm_calls = 1

        return {"topic": topic, "actions": actions, "note_count": len(related)}, llm_calls

    def _summary(self, notes: list) -> tuple[dict, int]:
        """Summarize a list of notes."""
        if not notes:
            return {"summary": "", "input_count": 0}, 0

        note_lines = "\n".join(
            f"- {_sanitize(n.get('title', ''))} — {_sanitize(n.get('description', ''), max_len=200)}"
            for n in notes
        )
        prompt = (
            f"Notes:\n{note_lines}\n\n"
            f"Write a concise summary of these notes."
        )
        summary = self._generate(prompt)
        llm_calls = 1

        return {"summary": summary, "input_count": len(notes)}, llm_calls
