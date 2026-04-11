"""Orchestrator — LLM-planned agent cycle execution."""
import json
import logging
import re

import jsonschema

from .base import AgentResult
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
            "depends_on": {"type": "integer"},
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
        self._cycle_llm_calls = 0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_cycle(self, scheduled_action: str = None) -> list[AgentResult]:
        """Main entry. Log cycle, handle pipeline tasks, or plan+execute."""
        self._cycle_llm_calls = 0
        self.event_log.append("cycle_start", agent="orchestrator", task={"scheduled_action": scheduled_action})

        # Pipeline actions delegate directly to Hands
        if scheduled_action in _PIPELINE_ACTIONS:
            results = self._run_pipeline(scheduled_action)
            self.event_log.append(
                "cycle_end",
                agent="orchestrator",
                result={"pipeline": scheduled_action, "count": len(results)},
            )
            return results

        # LLM-planned execution
        context = self._build_context(scheduled_action)
        plan = self._plan(context)
        results = self._execute_plan(plan)

        self.event_log.append(
            "cycle_end",
            agent="orchestrator",
            result={"plan_steps": len(plan), "executed": len(results)},
        )
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

    def _plan(self, context: dict) -> list[dict]:
        """LLM planning with 3-stage fallback: JSON parse -> regex extract -> rule-based."""
        max_calls = getattr(self.config, "orchestrator_max_llm_calls", _DEFAULT_MAX_LLM_CALLS)
        if self._cycle_llm_calls >= max_calls:
            logger.warning("Orchestrator: cost guard hit before planning, using rule-based plan")
            return self._rule_based_plan(context)

        prompt = self._build_planning_prompt(context)
        try:
            raw = self.summarizer._generate(prompt)
            self._cycle_llm_calls += 1
        except Exception as e:
            logger.error("Orchestrator: LLM planning failed: %s", e)
            return self._rule_based_plan(context)

        try:
            return self._parse_and_validate_plan(raw)
        except Exception as e:
            logger.warning("Orchestrator: plan parse/validate failed (%s), using rule-based", e)
            return self._rule_based_plan(context)

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

        # Validate agent names and task types
        available = self.registry.list_capabilities()
        for step in plan:
            agent_name = step["agent"]
            task_type = step["task"].get("type")
            if agent_name not in available:
                raise ValueError(f"Unknown agent: {agent_name}")
            if task_type not in available.get(agent_name, []):
                raise ValueError(f"Agent '{agent_name}' cannot handle task type '{task_type}'")

        return plan

    def _rule_based_plan(self, context: dict) -> list[dict]:
        """Fallback mirroring Brain.decide() logic."""
        scheduled = context.get("scheduled_action")
        action_map = {
            "trend": [{"agent": "researcher", "task": {"type": "trending_relevant"}}],
            "knowledge": [{"agent": "analyst", "task": {"type": "compound_analysis"}}],
            "suggest_articles": [{"agent": "researcher", "task": {"type": "fill_gap", "category": "general"}}],
            "topic_summary": [{"agent": "analyst", "task": {"type": "trend_intersection"}}],
        }
        if scheduled and scheduled in action_map:
            return action_map[scheduled]

        # Default: researcher trending + analyst compound
        return [
            {"agent": "researcher", "task": {"type": "trending_relevant"}},
            {"agent": "analyst", "task": {"type": "compound_analysis"}},
        ]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute_plan(self, plan: list[dict]) -> list[AgentResult]:
        """Execute sequentially with depends_on chaining and cost guard."""
        max_calls = getattr(self.config, "orchestrator_max_llm_calls", _DEFAULT_MAX_LLM_CALLS)
        results: list[AgentResult] = []

        for i, step in enumerate(plan):
            if self._cycle_llm_calls >= max_calls:
                logger.warning(
                    "Orchestrator: cost guard — stopping after %d steps (limit=%d llm calls)",
                    i, max_calls,
                )
                break

            agent_name = step["agent"]
            task = dict(step["task"])  # copy so we can inject depends_on data

            # Inject upstream result data if depends_on is set
            dep_idx = step.get("depends_on")
            if dep_idx is not None and 0 <= dep_idx < len(results):
                task["input"] = results[dep_idx].data

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
                self._cycle_llm_calls += result.llm_calls
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

        return results

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
                context["preferred_categories"] = getattr(self.memory, "preferred_categories", [])
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

        return (
            f"You are planning tasks for a compound learning agent.\n\n"
            f"Scheduled action: {scheduled}\n"
            f"User preferred categories: {', '.join(preferred) if preferred else 'unknown'}\n\n"
            f"Available agents and their task types:\n{agents_desc}\n\n"
            f"Return a JSON array of task steps to execute. Each step must have:\n"
            f'  - "agent": agent name (must be one of: {list(context.get("available_agents", {}).keys())})\n'
            f'  - "task": object with "type" (must match the agent\'s task types) and any extra fields\n'
            f'  - "depends_on": (optional) integer index of a previous step whose output to inject\n\n'
            f"Choose 1-3 steps that are most useful given the scheduled action and user interests.\n"
            f"Return ONLY the JSON array, no explanation.\n"
        )
