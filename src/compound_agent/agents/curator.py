"""CuratorAgent — manages vault note quality, connections, and archival."""
import logging
import time
from datetime import datetime

from .base import BaseAgent, AgentResult, _sanitize
from ..knowledge_scanner import scan_recent_notes

logger = logging.getLogger(__name__)


class CuratorAgent(BaseAgent):
    name = "curator"
    description = "Manages vault note quality, connections, and archival"

    TASK_TYPES = {
        "connect_notes": {"required": []},
        "quality_audit": {"required": []},
        "archive_stale": {"required": ["days"]},
    }

    def run(self, task: dict) -> AgentResult:
        if not self.validate_task(task):
            return self._make_result(
                task.get("type", "unknown"),
                {},
                error=f"Invalid task: {task}",
            )
        task_type = task["type"]
        start = time.time()
        try:
            if task_type == "connect_notes":
                data, llm_calls = self._connect_notes()
            elif task_type == "quality_audit":
                data, llm_calls = self._quality_audit()
            else:  # archive_stale
                data, llm_calls = self._archive_stale(task["days"])
        except Exception as e:
            logger.error("CuratorAgent error (%s): %s", task_type, e)
            return self._make_result(task_type, {}, error=str(e))

        duration_ms = int((time.time() - start) * 1000)
        return self._make_result(task_type, data, llm_calls=llm_calls, duration_ms=duration_ms)

    # ------------------------------------------------------------------
    # Task implementations
    # ------------------------------------------------------------------

    def _connect_notes(self) -> tuple[dict, int]:
        """Find cross-category connections using LLM."""
        notes = scan_recent_notes(self.config, days=14)
        if not notes:
            return {"connections": [], "note_count": 0}, 0

        listing = "\n".join(
            f"- {_sanitize(n['title'])} (category: {_sanitize(n['category'])})"
            for n in notes
        )
        prompt = (
            f"Here are recent vault notes:\n{listing}\n\n"
            f"Identify interesting cross-category connections between these notes. "
            f"Describe which notes could be linked and why, focusing on notes from different categories."
        )
        response = self._generate(prompt)
        return {"connections": response, "note_count": len(notes)}, 1

    def _quality_audit(self) -> tuple[dict, int]:
        """Check notes for missing frontmatter fields."""
        notes = scan_recent_notes(self.config, days=30)
        issues = []
        for note in notes:
            problems = []
            if not note.get("title", "").strip():
                problems.append("missing title")
            if not note.get("description", "").strip():
                problems.append("missing description")
            tags = note.get("tags", "")
            if not tags or (isinstance(tags, str) and not tags.strip()) or tags == "[]":
                problems.append("missing tags")
            if problems:
                issues.append({"title": note.get("title", ""), "problems": problems})
        return {"issues": issues, "total_audited": len(notes)}, 0

    def _archive_stale(self, days: int) -> tuple[dict, int]:
        """Find stale notes older than `days` with no tags or empty description."""
        notes = scan_recent_notes(self.config, days=days * 2)
        today = datetime.now().date()
        candidates = []
        for note in notes:
            saved_str = note.get("saved", "")
            if not saved_str:
                continue
            try:
                saved_date = datetime.strptime(saved_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            age_days = (today - saved_date).days
            if age_days < days:
                continue
            # Stale heuristic: no tags or empty description
            tags = note.get("tags", "")
            desc = note.get("description", "")
            no_tags = not tags or (isinstance(tags, str) and not tags.strip()) or tags == "[]"
            no_desc = not desc or not desc.strip()
            if no_tags or no_desc:
                candidates.append({"title": note.get("title", ""), "saved": saved_str})
        return {"candidates": candidates, "threshold_days": days}, 0
