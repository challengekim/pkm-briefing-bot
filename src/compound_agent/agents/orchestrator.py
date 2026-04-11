"""Orchestrator — LLM-planned agent cycle execution."""
import json
import logging
import re

import jsonschema

from .base import AgentResult, _sanitize
from . import AgentRegistry

logger = logging.getLogger(__name__)

# Pipeline actions handled directly by Hands
_PIPELINE_ACTIONS = {"morning", "evening", "meta", "weekly", "trend", "knowledge", "linkedin"}

PLAN_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["agent", "task"],
        "properties": {
            "agent": {"type": "string"},
            "task": {"type": "object", "required": ["type"]},
            "depends_on": {"type": "integer", "minimum": 0},
        },
    },
}

# Default cost cap per cycle
_DEFAULT_MAX_LLM_CALLS = 6


class Orchestrator:
    def __init__(self, config, memory, event_log, registry: AgentRegistry, hands, summarizer):
        self.config = config
        self.memory = memory
        self.event_log = event_log
        self.registry = registry
        self.hands = hands
        self.summarizer = summarizer

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_cycle(self, scheduled_action: str = None) -> list[AgentResult]:
        """Main entry. Log cycle, handle pipeline tasks, or plan+execute."""
        cycle_llm_calls = 0
        self.event_log.append("cycle_start", agent="orchestrator", task={"scheduled_action": scheduled_action})

        # Pipeline actions delegate directly to Hands
        if scheduled_action in _PIPELINE_ACTIONS:
            results = self._run_pipeline(scheduled_action)
            self.event_log.append(
                "cycle_end",
                agent="orchestrator",
                result={"pipeline": scheduled_action, "count": len(results)},
            )
            self.event_log.rotate()
            return results

        # LLM-planned execution
        context = self._build_context(scheduled_action)
        plan, cycle_llm_calls = self._plan(context, cycle_llm_calls)
        results, cycle_llm_calls = self._execute_plan(plan, cycle_llm_calls)

        self.event_log.append(
            "cycle_end",
            agent="orchestrator",
            result={"plan_steps": len(plan), "executed": len(results)},
        )
        self.event_log.rotate()
        return results

    # ------------------------------------------------------------------
    # Pipeline delegation
    # ------------------------------------------------------------------

    def _run_pipeline(self, action: str) -> list[AgentResult]:
        """Delegate simple pipeline tasks to Hands."""
        method_map = {
            "morning": "run_morning_briefing",
            "evening": "run_evening_review",
            "meta": "run_meta_review",
            "weekly": "run_weekly",
            "trend": "run_trend_digest",
            "knowledge": "run_weekly_knowledge",
            "linkedin": "run_linkedin_draft",
        }
        method_name = method_map.get(action)
        if method_name is None:
            logger.warning("Orchestrator: unknown pipeline action '%s'", action)
            return []

        try:
            method = getattr(self.hands, method_name)
            raw = method()
            result = AgentResult(
                success=raw.get("success", True) if isinstance(raw, dict) else True,
                agent="hands",
                task_type=action,
                data=raw if isinstance(raw, dict) else {"raw": str(raw)},
            )
        except Exception as e:
            logger.error("Pipeline action '%s' failed: %s", action, e)
            result = AgentResult(success=False, agent="hands", task_type=action, error=str(e))

        return [result]

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _plan(self, context: dict, cycle_llm_calls: int = 0) -> tuple[list[dict], int]:
        """LLM planning with 3-stage fallback: JSON parse -> regex extract -> rule-based."""
        max_calls = getattr(self.config, "orchestrator_max_llm_calls", _DEFAULT_MAX_LLM_CALLS)

        # Issue #3: respect orchestrator_planning_mode config
        planning_mode = getattr(self.config, "orchestrator_planning_mode", None)
        if planning_mode == "rules":
            return self._rule_based_plan(context), cycle_llm_calls

        if cycle_llm_calls >= max_calls:
            logger.warning("Orchestrator: cost guard hit before planning, using rule-based plan")
            return self._rule_based_plan(context), cycle_llm_calls

        prompt = self._build_planning_prompt(context)
        try:
            raw = self.summarizer._generate(prompt)
            cycle_llm_calls += 1
        except Exception as e:
            logger.error("Orchestrator: LLM planning failed: %s", e)
            return self._rule_based_plan(context), cycle_llm_calls

        try:
            return self._parse_and_validate_plan(raw), cycle_llm_calls
        except Exception as e:
            logger.warning("Orchestrator: plan parse/validate failed (%s), using rule-based", e)
            return self._rule_based_plan(context), cycle_llm_calls

    def _parse_and_validate_plan(self, raw: str) -> list[dict]:
        """Extract JSON, validate schema, validate agent names and capabilities."""
        # Stage 1: direct JSON parse
        plan = None
        try:
            plan = json.loads(raw.strip())
        except json.JSONDecodeError:
            pass

        # Stage 2: regex extract ```json ... ```
        if plan is None:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if match:
                try:
                    plan = json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass

        if plan is None:
            raise ValueError("No valid JSON found in LLM response")

        # Validate against schema
        jsonschema.validate(plan, PLAN_SCHEMA)

        # Validate agent names, task types, and depends_on references
        available = self.registry.list_capabilities()
        for i, step in enumerate(plan):
            agent_name = step["agent"]
            task_type = step["task"].get("type")
            if agent_name not in available:
                raise ValueError(f"Unknown agent: {agent_name}")
            if task_type not in available.get(agent_name, []):
                raise ValueError(f"Agent '{agent_name}' cannot handle task type '{task_type}'")
            dep_idx = step.get("depends_on")
            if dep_idx is not None and dep_idx >= i:
                raise ValueError(
                    f"Step {i}: depends_on={dep_idx} is a forward or self reference (must be < {i})"
                )

        return plan

    def _rule_based_plan(self, context: dict) -> list[dict]:
        """Fallback mirroring Brain.decide() logic."""
        scheduled = context.get("scheduled_action")
        action_map = {
            "trend": [{"agent": "researcher", "task": {"type": "trending_relevant"}}],
            "knowledge": [{"agent": "analyst", "task": {"type": "compound_analysis"}}],
            "suggest_articles": [{"agent": "researcher", "task": {"type": "fill_gap", "category": "general"}}],
            "topic_summary": [{"agent": "analyst", "task": {"type": "trend_intersection"}}],
            "curator_audit": [{"agent": "curator", "task": {"type": "quality_audit"}}],
            "curator_connect": [{"agent": "curator", "task": {"type": "connect_notes"}}],
        }
        if scheduled and scheduled in action_map:
            return action_map[scheduled]

        # Default: alternate between (researcher+analyst) and (curator+analyst) to ensure vault maintenance
        recent_events = context.get("recent_event_count", 0)
        if recent_events % 2 == 1:
            return [
                {"agent": "curator", "task": {"type": "quality_audit"}},
                {"agent": "analyst", "task": {"type": "compound_analysis"}},
            ]
        return [
            {"agent": "researcher", "task": {"type": "trending_relevant"}},
            {"agent": "analyst", "task": {"type": "compound_analysis"}},
        ]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute_plan(self, plan: list[dict], cycle_llm_calls: int = 0) -> tuple[list[AgentResult], int]:
        """Execute sequentially with depends_on chaining and cost guard."""
        max_calls = getattr(self.config, "orchestrator_max_llm_calls", _DEFAULT_MAX_LLM_CALLS)
        results: list[AgentResult] = []

        for i, step in enumerate(plan):
            if cycle_llm_calls >= max_calls:
                logger.warning(
                    "Orchestrator: cost guard — stopping after %d steps (limit=%d llm calls)",
                    i, max_calls,
                )
                break

            agent_name = step["agent"]
            task = dict(step["task"])  # copy so we can inject depends_on data

            # Inject upstream result data if depends_on is set
            dep_idx = step.get("depends_on")
            if dep_idx is not None:
                if 0 <= dep_idx < len(results):
                    task["input"] = results[dep_idx].data
                else:
                    logger.warning(
                        "Orchestrator: step %d depends_on=%d but only %d results available — skipping injection",
                        i, dep_idx, len(results),
                    )

            agent = self.registry.get(agent_name)
            if agent is None:
                logger.error("Orchestrator: agent '%s' not found in registry", agent_name)
                results.append(AgentResult(
                    success=False,
                    agent=agent_name,
                    task_type=task.get("type", "unknown"),
                    error=f"Agent '{agent_name}' not found",
                ))
                continue

            self.event_log.append("task_start", agent=agent_name, task=task)
            try:
                result = agent.run(task)
                cycle_llm_calls += result.llm_calls
            except Exception as e:
                logger.error("Orchestrator: agent '%s' raised: %s", agent_name, e)
                result = AgentResult(
                    success=False,
                    agent=agent_name,
                    task_type=task.get("type", "unknown"),
                    error=str(e),
                )

            self.event_log.append(
                "task_end",
                agent=agent_name,
                result={"success": result.success, "error": result.error},
            )
            results.append(result)

        return results, cycle_llm_calls

    # ------------------------------------------------------------------
    # Context & prompt building
    # ------------------------------------------------------------------

    def _build_context(self, scheduled_action: str = None) -> dict:
        """Gather: scheduled_action, enabled agents, recent events, vault stats, engagement."""
        context: dict = {
            "scheduled_action": scheduled_action,
            "available_agents": self.registry.list_capabilities(),
        }

        # Recent event summary
        try:
            last_cycle = self.event_log.get_last_cycle()
            context["recent_event_count"] = len(last_cycle)
        except Exception:
            context["recent_event_count"] = 0

        # Vault stats from memory
        if self.memory is not None:
            try:
                context["preferred_categories"] = self.memory.get_preferred_categories()
                context["engagement_stats"] = {}
                if hasattr(self.memory, "get_engagement_stats"):
                    context["engagement_stats"] = self.memory.get_engagement_stats(days=7)
            except Exception:
                pass

        return context

    def _build_planning_prompt(self, context: dict) -> str:
        """Prompt asking LLM to produce a JSON task array."""
        agents_desc = "\n".join(
            f"  - {name}: {', '.join(caps)}"
            for name, caps in context.get("available_agents", {}).items()
        )
        scheduled = context.get("scheduled_action") or "none"
        preferred = context.get("preferred_categories", [])
        safe_preferred = [f"{_sanitize(cat)} ({score:.1f})" for cat, score in preferred] if preferred else []

        engagement = context.get("engagement_stats", {})
        eng_summary = (
            f"Engagement rate: {engagement.get('engagement_rate', 0):.0%}, total: {engagement.get('total', 0)}"
            if engagement
            else "No engagement data"
        )

        return (
            f"You are planning tasks for a compound learning agent.\n\n"
            f"Scheduled action: {scheduled}\n"
            f"User preferred categories: {', '.join(safe_preferred) if safe_preferred else 'unknown'}\n"
            f"Engagement stats: {eng_summary}\n\n"
            f"Available agents and their task types:\n{agents_desc}\n\n"
            f"Return a JSON array of task steps to execute. Each step must have:\n"
            f'  - "agent": agent name (must be one of: {list(context.get("available_agents", {}).keys())})\n'
            f'  - "task": object with "type" (must match the agent\'s task types) and any extra fields\n'
            f'  - "depends_on": (optional) integer index of a previous step whose output to inject\n\n'
            f"Choose 1-3 steps that are most useful given the scheduled action and user interests.\n"
            f"Return ONLY the JSON array, no explanation.\n"
        )
