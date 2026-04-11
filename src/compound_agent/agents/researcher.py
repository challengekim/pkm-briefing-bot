"""ResearcherAgent — fetches and filters trending content."""
import logging
import time

from .base import BaseAgent, AgentResult
from ..trend_fetcher import fetch_all_trends

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    name = "researcher"
    description = "Fetches and filters trending articles by topic or category"

    TASK_TYPES = {
        "fill_gap": {"required": ["category"]},
        "deep_dive": {"required": ["topic"]},
        "trending_relevant": {"required": []},
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
            if task_type == "fill_gap":
                data, llm_calls = self._fill_gap(task["category"])
            elif task_type == "deep_dive":
                data, llm_calls = self._deep_dive(task["topic"])
            else:  # trending_relevant
                interests = task.get("interests", [])
                data, llm_calls = self._trending_relevant(interests)
        except Exception as e:
            logger.error("ResearcherAgent error (%s): %s", task_type, e)
            return self._make_result(task_type, {}, error=str(e))

        duration_ms = int((time.time() - start) * 1000)
        return self._make_result(task_type, data, llm_calls=llm_calls, duration_ms=duration_ms)

    # ------------------------------------------------------------------
    # Task implementations
    # ------------------------------------------------------------------

    def _fill_gap(self, category: str) -> tuple[dict, int]:
        """Fetch trends and filter by category relevance using LLM."""
        articles = fetch_all_trends(self.config)
        if not articles:
            return {"articles": [], "category": category}, 0

        titles = "\n".join(f"- {a['title']}" for a in articles[:30])
        prompt = (
            f"Category: {category}\n\n"
            f"Articles:\n{titles}\n\n"
            f"Return a comma-separated list of article titles most relevant to the category '{category}'. "
            f"Return only titles, no explanation."
        )
        response = self._generate(prompt)
        llm_calls = 1

        relevant_titles = {t.strip().lower() for t in response.split(",") if t.strip()}
        filtered = [
            a for a in articles
            if a["title"].lower() in relevant_titles
        ]
        # Fallback: if LLM returned nothing useful, include all
        if not filtered:
            filtered = articles[:10]

        return {"articles": filtered, "category": category}, llm_calls

    def _deep_dive(self, topic: str) -> tuple[dict, int]:
        """Fetch trends filtered by topic; produce a structured research brief."""
        articles = fetch_all_trends(self.config)
        topic_lower = topic.lower()
        relevant = [
            a for a in articles
            if topic_lower in a["title"].lower()
        ][:20]

        if not relevant:
            relevant = articles[:10]

        titles = "\n".join(f"- {a['title']}" for a in relevant)
        prompt = (
            f"Topic: {topic}\n\n"
            f"Recent articles:\n{titles}\n\n"
            f"Write a concise research brief (3-5 bullet points) summarising the current state of '{topic}' "
            f"based on these articles. Focus on key developments and implications."
        )
        brief = self._generate(prompt)
        llm_calls = 1

        return {
            "topic": topic,
            "articles": relevant,
            "brief": brief,
        }, llm_calls

    def _trending_relevant(self, interests: list) -> tuple[dict, int]:
        """Fetch trends and filter by memory preferred_categories."""
        articles = fetch_all_trends(self.config)

        # Combine explicit interests with memory preferred categories
        preferred = list(interests)
        if self.memory is not None:
            mem_cats = getattr(self.memory, "preferred_categories", None)
            if isinstance(mem_cats, list):
                preferred.extend(mem_cats)
            elif isinstance(mem_cats, dict):
                preferred.extend(mem_cats.keys())

        if not preferred or not articles:
            return {"articles": articles[:10], "interests": preferred}, 0

        prefs_str = ", ".join(preferred)
        titles = "\n".join(f"- {a['title']}" for a in articles[:30])
        prompt = (
            f"User interests: {prefs_str}\n\n"
            f"Articles:\n{titles}\n\n"
            f"Return a comma-separated list of article titles most relevant to the user's interests. "
            f"Return only titles, no explanation."
        )
        response = self._generate(prompt)
        llm_calls = 1

        relevant_titles = {t.strip().lower() for t in response.split(",") if t.strip()}
        filtered = [
            a for a in articles
            if a["title"].lower() in relevant_titles
        ]
        if not filtered:
            filtered = articles[:10]

        return {"articles": filtered, "interests": preferred}, llm_calls
