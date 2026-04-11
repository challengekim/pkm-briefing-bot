"""AnalystAgent — cross-week pattern analysis and blind spot detection."""
import logging
import time

from .base import BaseAgent, AgentResult
from ..knowledge_scanner import load_previous_weekly_reports, scan_recent_notes
from ..trend_fetcher import fetch_all_trends

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    name = "analyst"
    description = "Analyses compound patterns across weeks and detects knowledge gaps"

    TASK_TYPES = {
        "compound_analysis": {"required": []},
        "trend_intersection": {"required": []},
        "blind_spot_detection": {"required": []},
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
            if task_type == "compound_analysis":
                period_weeks = task.get("period_weeks", 4)
                data, llm_calls = self._compound_analysis(period_weeks)
            elif task_type == "trend_intersection":
                data, llm_calls = self._trend_intersection()
            else:  # blind_spot_detection
                data, llm_calls = self._blind_spot_detection()
        except Exception as e:
            logger.error("AnalystAgent error (%s): %s", task_type, e)
            return self._make_result(task_type, {}, error=str(e))

        duration_ms = int((time.time() - start) * 1000)
        return self._make_result(task_type, data, llm_calls=llm_calls, duration_ms=duration_ms)

    # ------------------------------------------------------------------
    # Task implementations
    # ------------------------------------------------------------------

    def _compound_analysis(self, period_weeks: int = 4) -> tuple[dict, int]:
        """Find evolving patterns across recent weekly reports and recent notes."""
        reports = load_previous_weekly_reports(self.config.vault_path, weeks=period_weeks)
        recent_notes = scan_recent_notes(self.config, days=period_weeks * 7)

        note_titles = "\n".join(f"- {n['title']}" for n in recent_notes[:20])
        prompt = (
            f"Previous {period_weeks} weeks of reports:\n{reports or '(none)'}\n\n"
            f"Recent saved notes:\n{note_titles or '(none)'}\n\n"
            "Identify 3-5 evolving patterns or themes that span multiple weeks. "
            "For each pattern describe: what it is, how it has evolved, and why it matters. "
            "Be concise and specific."
        )
        analysis = self._generate(prompt)
        llm_calls = 1

        return {
            "analysis": analysis,
            "period_weeks": period_weeks,
            "note_count": len(recent_notes),
        }, llm_calls

    def _trend_intersection(self) -> tuple[dict, int]:
        """Find cross-domain connections in recent saved notes."""
        notes = scan_recent_notes(self.config, days=14)
        if not notes:
            return {"intersections": [], "note_count": 0}, 0

        # Group by category
        by_category: dict[str, list[str]] = {}
        for note in notes:
            cat = note.get("category", "unknown")
            by_category.setdefault(cat, []).append(note["title"])

        categories_str = "\n".join(
            f"{cat}: {', '.join(titles[:5])}"
            for cat, titles in by_category.items()
        )
        prompt = (
            f"Recent saved notes by category:\n{categories_str}\n\n"
            "Find 2-4 non-obvious connections or intersections between different domains/categories. "
            "For each intersection: name the domains, describe the connection, and suggest an insight. "
            "Be specific and actionable."
        )
        intersections_text = self._generate(prompt)
        llm_calls = 1

        return {
            "intersections": intersections_text,
            "categories": list(by_category.keys()),
            "note_count": len(notes),
        }, llm_calls

    def _blind_spot_detection(self) -> tuple[dict, int]:
        """Compare user reading patterns with industry trends to find gaps."""
        notes = scan_recent_notes(self.config, days=30)
        trends = fetch_all_trends(self.config)

        user_topics = " ".join(n["title"] for n in notes[:30])
        trend_titles = "\n".join(f"- {t['title']}" for t in trends[:30])

        prompt = (
            f"User's recent reading (last 30 days):\n{user_topics or '(none)'}\n\n"
            f"Current industry trends:\n{trend_titles or '(none)'}\n\n"
            "Identify 3-5 important topics or trends the user appears to be missing or under-reading. "
            "For each gap: name the topic, explain why it matters, and suggest a starting resource or question. "
            "Be constructive and specific."
        )
        gaps_text = self._generate(prompt)
        llm_calls = 1

        return {
            "gaps": gaps_text,
            "user_note_count": len(notes),
            "trend_count": len(trends),
        }, llm_calls
