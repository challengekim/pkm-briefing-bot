"""
Evolution — self-modification engine for the Self-Improving Agent (Phase C).

EvolutionSafety provides guardrails: config backup, audit log, rate limiting,
engagement-drop detection, and rollback.

Evolution(EvolutionSafety) adds the actual adjustment logic (config, prompts, ideas).

Config changes are written to evolution-overrides.yaml (overlay pattern)
so the human-maintained config.yaml is never modified programmatically.
"""

import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_OVERRIDES_FILENAME = "evolution-overrides.yaml"


def _now_kst() -> datetime:
    return datetime.now(KST)


class EvolutionSafety:
    """Guardrails for self-modification. All evolution logic inherits from this."""

    MAX_CONFIG_CHANGES_PER_MONTH = 3
    MAX_PROMPT_MUTATIONS_PER_WEEK = 1
    ENGAGEMENT_DROP_THRESHOLD = 0.5  # 50% drop triggers rollback
    MIN_ENGAGEMENT_DATAPOINTS = 5    # min data points before evaluating

    def __init__(self, config, memory, config_path=None):
        self.config = config
        self.memory = memory
        self._config_path = str(config_path or Path(__file__).parent / "config.yaml")
        self._overrides_path = str(
            Path(self._config_path).parent / _OVERRIDES_FILENAME
        )
        self._log_path = os.path.expanduser(
            getattr(config, "evolution_log_path", "~/.compound-brain/evolution-log.json")
        )
        self._lock = threading.Lock()

        # Use config-provided limits if available
        self._max_config_per_month = getattr(
            config, "evolution_max_config_changes_per_month",
            self.MAX_CONFIG_CHANGES_PER_MONTH,
        )
        self._max_prompt_per_week = getattr(
            config, "evolution_max_prompt_mutations_per_week",
            self.MAX_PROMPT_MUTATIONS_PER_WEEK,
        )
        self._drop_threshold = getattr(
            config, "evolution_engagement_drop_threshold",
            self.ENGAGEMENT_DROP_THRESHOLD,
        )

    # ------------------------------------------------------------------
    # Config backup
    # ------------------------------------------------------------------

    def backup_config(self) -> str:
        """Copy config.yaml (and overrides if present) to timestamped backups.

        Returns the backup path for config.yaml.
        """
        timestamp = _now_kst().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self._config_path}.bak.{timestamp}"
        shutil.copy2(self._config_path, backup_path)

        if os.path.exists(self._overrides_path):
            shutil.copy2(
                self._overrides_path,
                f"{self._overrides_path}.bak.{timestamp}",
            )
        return backup_path

    def rollback_config(self, backup_path: str):
        """Restore evolution-overrides.yaml from a backup.

        If the backup was for overrides, restore it.
        Otherwise, remove the overrides file entirely (revert to base config).
        """
        overrides_backup = backup_path.replace("config.yaml", _OVERRIDES_FILENAME)
        if os.path.exists(overrides_backup):
            shutil.copy2(overrides_backup, self._overrides_path)
        elif os.path.exists(self._overrides_path):
            os.remove(self._overrides_path)

        self.log_change({
            "type": "rollback",
            "backup_path": backup_path,
        })

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def log_change(self, change: dict):
        """Append a change record to evolution-log.json atomically."""
        entry = {
            "timestamp": _now_kst().isoformat(),
            **change,
        }
        with self._lock:
            log = self._read_log()
            log.append(entry)
            self._write_log(log)

    def get_recent_changes(self, days: int = 30) -> list:
        """Return changes from the last N days."""
        cutoff = _now_kst() - timedelta(days=days)
        log = self._read_log()
        return [
            e for e in log
            if datetime.fromisoformat(e["timestamp"]) >= cutoff
        ]

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def check_rate_limit(self, change_type: str) -> bool:
        """Return True if the change is allowed within rate limits.

        change_type: "config" | "prompt"
        Rollbacks do not count against the limit.
        """
        recent = self.get_recent_changes(days=31)

        if change_type == "config":
            count = sum(
                1 for c in recent
                if c.get("change_type") == "config"
                and c.get("type") != "rollback"
            )
            return count < self._max_config_per_month

        if change_type == "prompt":
            week_cutoff = _now_kst() - timedelta(days=7)
            count = sum(
                1 for c in recent
                if c.get("change_type") == "prompt"
                and c.get("type") != "rollback"
                and datetime.fromisoformat(c["timestamp"]) >= week_cutoff
            )
            return count < self._max_prompt_per_week

        return True  # Unknown type — allow

    # ------------------------------------------------------------------
    # Engagement health check
    # ------------------------------------------------------------------

    def check_engagement_drop(self, briefing_type: str = None) -> dict | None:
        """Check if engagement dropped significantly.

        Compares 21-day (recent) rate to 60-day (baseline) rate.
        Requires at least MIN_ENGAGEMENT_DATAPOINTS in the recent window.

        Returns None if healthy, or dict with drop details if concerning.
        """
        if self.memory is None:
            return None

        baseline = self.memory.get_engagement_stats(briefing_type, days=60)
        recent = self.memory.get_engagement_stats(briefing_type, days=21)

        if recent["total"] < self.MIN_ENGAGEMENT_DATAPOINTS:
            return None  # Not enough data to judge

        if baseline["total"] < self.MIN_ENGAGEMENT_DATAPOINTS:
            return None  # No baseline either

        baseline_rate = baseline["engagement_rate"]
        recent_rate = recent["engagement_rate"]

        if baseline_rate == 0:
            return None  # Can't divide by zero

        drop_ratio = recent_rate / baseline_rate
        if drop_ratio < self._drop_threshold:
            return {
                "baseline_rate": baseline_rate,
                "recent_rate": recent_rate,
                "drop_ratio": drop_ratio,
                "briefing_type": briefing_type,
                "baseline_total": baseline["total"],
                "recent_total": recent["total"],
            }
        return None

    # ------------------------------------------------------------------
    # Overrides file management
    # ------------------------------------------------------------------

    def read_overrides(self) -> dict:
        """Read current evolution-overrides.yaml, or empty dict if missing."""
        if not os.path.exists(self._overrides_path):
            return {}
        try:
            with open(self._overrides_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as e:
            logger.error("Failed to read overrides: %s", e)
            return {}

    def write_overrides(self, overrides: dict):
        """Write evolution-overrides.yaml atomically."""
        parent = os.path.dirname(self._overrides_path)
        os.makedirs(parent, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write("# Auto-generated by Evolution — do not edit manually\n")
                yaml.dump(overrides, f, default_flow_style=False, allow_unicode=True)

            # Validate before committing
            with open(tmp_path, "r", encoding="utf-8") as f:
                yaml.safe_load(f)

            os.replace(tmp_path, self._overrides_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Internal persistence (evolution-log.json)
    # ------------------------------------------------------------------

    def _read_log(self) -> list:
        try:
            with open(self._log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _write_log(self, entries: list):
        parent = os.path.dirname(self._log_path)
        os.makedirs(parent, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._log_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ======================================================================
# Evolution — config auto-adjustment + source scoring actions
# ======================================================================

# Source name → config key mapping for limit adjustments
_SOURCE_LIMIT_KEYS = {
    "Hacker News": ("trends", "hn_limit"),
    "HN": ("trends", "hn_limit"),
    "GeekNews": ("trends", "geeknews_limit"),
    "Reddit": ("trends", "reddit_limit"),
}

# Category → suggested subreddits
_CATEGORY_SUBREDDITS = {
    "marketing": ["marketing", "growthacking", "SEO"],
    "business": ["startups", "Entrepreneur", "smallbusiness"],
    "engineering": ["devops", "programming", "webdev"],
    "ai": ["artificial", "MachineLearning", "LocalLLaMA"],
    "design": ["web_design", "userexperience"],
    "productivity": ["productivity", "getdisciplined"],
}


class Evolution(EvolutionSafety):
    """Self-modification engine. Evaluates outcomes and adjusts config/prompts."""

    # Source scoring thresholds
    SOURCE_REDUCE_THRESHOLD = 0.02   # <2% save rate → reduce limit 50%
    SOURCE_REMOVE_THRESHOLD = 0.01   # <1% save rate → remove source
    SOURCE_BOOST_THRESHOLD = 0.10    # >10% save rate → increase limit 50%
    SOURCE_MIN_SHOWN = 50            # min impressions before acting
    SOURCE_REMOVE_MIN_SHOWN = 100    # min impressions for removal
    SOURCE_MIN_LIMIT = 3             # floor for reduced limits
    SOURCE_MAX_LIMIT = 30            # ceiling for boosted limits

    SCHEDULE_MIN_SAMPLES = 10        # min reading time samples before adjusting
    SCHEDULE_MIN_DRIFT_MINUTES = 30  # min drift before proposing change

    def evaluate_and_adjust(self) -> list:
        """Main entry point. Run all self-improvement checks.

        Returns list of change dicts applied (empty if nothing changed or blocked).
        """
        # Pre-check: engagement health
        drop = self.check_engagement_drop()
        if drop:
            logger.warning(
                "Evolution: engagement drop detected (%.0f%% → %.0f%%). "
                "Checking for recent changes to rollback.",
                drop["baseline_rate"] * 100,
                drop["recent_rate"] * 100,
            )
            self._maybe_rollback(drop)
            return []  # Don't make new changes when engagement is declining

        # Rate limit check
        if not self.check_rate_limit("config"):
            logger.info("Evolution: config rate limit reached, skipping adjustments")
            return []

        # Collect proposed changes
        changes = []
        changes.extend(self._adjust_trend_sources())
        changes.extend(self._adjust_subreddits())
        changes.extend(self._adjust_schedule())

        if not changes:
            logger.info("Evolution: no config adjustments needed")
            return []

        # Apply with safety
        self._apply_config_changes(changes)
        return changes

    # ------------------------------------------------------------------
    # Source quality → config adjustment
    # ------------------------------------------------------------------

    def _adjust_trend_sources(self) -> list:
        """Propose limit changes for trend sources based on quality scores."""
        if self.memory is None:
            return []

        changes = []
        with self.memory._lock:
            scores = dict(self.memory.source_scores)

        for source, data in scores.items():
            total = data.get("total_shown", 0)
            quality = data.get("quality", 0)
            limit_key = self._get_source_limit_key(source)
            if limit_key is None:
                continue

            section, key = limit_key
            current_limit = getattr(self.config, f"trend_{key}", None)
            if current_limit is None:
                continue

            # Remove: very low quality with enough data
            if quality < self.SOURCE_REMOVE_THRESHOLD and total >= self.SOURCE_REMOVE_MIN_SHOWN:
                changes.append({
                    "action": "reduce_source",
                    "source": source,
                    "section": section,
                    "key": key,
                    "old_value": current_limit,
                    "new_value": self.SOURCE_MIN_LIMIT,
                    "reason": f"Very low save rate {quality:.1%} ({data.get('positive', 0)}/{total})",
                })
            # Reduce: low quality
            elif quality < self.SOURCE_REDUCE_THRESHOLD and total >= self.SOURCE_MIN_SHOWN:
                new_limit = max(self.SOURCE_MIN_LIMIT, current_limit // 2)
                if new_limit < current_limit:
                    changes.append({
                        "action": "reduce_source",
                        "source": source,
                        "section": section,
                        "key": key,
                        "old_value": current_limit,
                        "new_value": new_limit,
                        "reason": f"Low save rate {quality:.1%} ({data.get('positive', 0)}/{total})",
                    })
            # Boost: high quality
            elif quality > self.SOURCE_BOOST_THRESHOLD and total >= self.SOURCE_MIN_SHOWN:
                new_limit = min(self.SOURCE_MAX_LIMIT, int(current_limit * 1.5))
                if new_limit > current_limit:
                    changes.append({
                        "action": "boost_source",
                        "source": source,
                        "section": section,
                        "key": key,
                        "old_value": current_limit,
                        "new_value": new_limit,
                        "reason": f"High save rate {quality:.1%} ({data.get('positive', 0)}/{total})",
                    })

        return changes

    def _adjust_subreddits(self) -> list:
        """Propose subreddit additions for weak categories, removals for low quality."""
        if self.memory is None:
            return []

        changes = []
        current_subs = list(self.config.trend_subreddits)

        # Add subreddits for weak categories (preferred but under-represented)
        preferred = self.memory.get_preferred_categories(top_n=10)
        with self.memory._lock:
            scores = dict(self.memory.source_scores)

        for category, pref_score in preferred:
            if pref_score < 0.5:
                continue
            cat_lower = category.lower()
            suggested = _CATEGORY_SUBREDDITS.get(cat_lower, [])
            for sub in suggested:
                if sub not in current_subs:
                    changes.append({
                        "action": "add_subreddit",
                        "subreddit": sub,
                        "section": "trends",
                        "key": "subreddits",
                        "reason": f"Category '{category}' preferred (score={pref_score:.2f}) but under-represented",
                    })
                    current_subs.append(sub)  # Avoid duplicates within this run

        # Remove subreddits with very low quality
        for source, data in scores.items():
            if not source.startswith("r/"):
                continue
            sub_name = source[2:]
            if sub_name not in current_subs:
                continue
            total = data.get("total_shown", 0)
            quality = data.get("quality", 0)
            if quality < self.SOURCE_REMOVE_THRESHOLD and total >= self.SOURCE_REMOVE_MIN_SHOWN:
                changes.append({
                    "action": "remove_subreddit",
                    "subreddit": sub_name,
                    "section": "trends",
                    "key": "subreddits",
                    "reason": f"r/{sub_name} save rate {quality:.1%} ({data.get('positive', 0)}/{total})",
                })

        return changes

    def _adjust_schedule(self) -> list:
        """Propose schedule changes based on learned reading times."""
        if self.memory is None:
            return []

        changes = []
        with self.memory._lock:
            reading_times = dict(self.memory.preferences.get("reading_times", {}))

        for briefing_type, data in reading_times.items():
            samples = data.get("samples", 0)
            if samples < self.SCHEDULE_MIN_SAMPLES:
                continue

            avg_hour = data.get("avg_read_hour", 0)
            # Optimal send = 15 min before avg read time
            optimal_hour = avg_hour - 0.25
            if optimal_hour < 0:
                optimal_hour += 24

            # Get current scheduled hour
            sched = self.config.schedule.get(briefing_type, {})
            current_hour = sched.get("hour", 0) + sched.get("minute", 0) / 60.0

            drift = abs(optimal_hour - current_hour)
            drift = min(drift, 24 - drift)  # handle midnight wrap
            drift_minutes = drift * 60
            if drift_minutes < self.SCHEDULE_MIN_DRIFT_MINUTES:
                continue

            # Round to nearest 15 min
            optimal_minute_total = int(optimal_hour * 60)
            optimal_minute_total = round(optimal_minute_total / 15) * 15
            new_hour = optimal_minute_total // 60
            new_minute = optimal_minute_total % 60

            changes.append({
                "action": "adjust_schedule",
                "briefing_type": briefing_type,
                "section": "schedule",
                "key": briefing_type,
                "old_value": f"{int(current_hour):02d}:{int((current_hour % 1) * 60):02d}",
                "new_value": f"{new_hour:02d}:{new_minute:02d}",
                "reason": f"User reads at ~{avg_hour:.1f}h (n={samples}), current schedule at {current_hour:.1f}h",
            })

        return changes

    # ------------------------------------------------------------------
    # Apply changes to evolution-overrides.yaml
    # ------------------------------------------------------------------

    def _apply_config_changes(self, changes: list):
        """Write changes to evolution-overrides.yaml with full safety."""
        backup_path = self.backup_config()
        overrides = self.read_overrides()

        for change in changes:
            section = change.get("section")
            key = change.get("key")
            action = change.get("action")

            if action in ("reduce_source", "boost_source"):
                overrides.setdefault(section, {})[key] = change["new_value"]

            elif action == "add_subreddit":
                subs = overrides.setdefault(section, {}).get(
                    "subreddits", list(self.config.trend_subreddits)
                )
                if change["subreddit"] not in subs:
                    subs.append(change["subreddit"])
                overrides[section]["subreddits"] = subs

            elif action == "remove_subreddit":
                subs = overrides.setdefault(section, {}).get(
                    "subreddits", list(self.config.trend_subreddits)
                )
                if change["subreddit"] in subs:
                    subs.remove(change["subreddit"])
                overrides[section]["subreddits"] = subs

            elif action == "adjust_schedule":
                # Preserve qualifier (e.g., "sat", "1st") if present
                original = self.config.schedule.get(change["briefing_type"], {})
                qualifier = ""
                if "day_of_week" in original:
                    qualifier = f"{original['day_of_week']} "
                elif "day" in original:
                    day = original["day"]
                    suffix = {1: "st", 2: "nd", 3: "rd"}.get(day, "th")
                    qualifier = f"{day}{suffix} "
                overrides.setdefault(section, {})[key] = f"{qualifier}{change['new_value']}"

        self.write_overrides(overrides)

        # Log once per batch (not per change) to avoid exhausting rate limit
        self.log_change({
            "change_type": "config",
            "action": "batch_apply",
            "num_changes": len(changes),
            "changes": [{"action": c.get("action"), "reason": c.get("reason")} for c in changes],
            "backup_path": backup_path,
        })
        logger.info("Evolution: applied %d config changes (backup at %s)", len(changes), backup_path)

    # ------------------------------------------------------------------
    # Rollback logic
    # ------------------------------------------------------------------

    def _maybe_rollback(self, drop_info: dict):
        """If there was a recent config change, rollback to the backup."""
        recent = self.get_recent_changes(days=21)
        config_changes = [
            c for c in recent
            if c.get("change_type") == "config"
            and c.get("type") != "rollback"
            and c.get("backup_path")
        ]
        if not config_changes:
            logger.info("Evolution: engagement drop but no recent config changes to rollback")
            return

        # Rollback to the most recent backup
        latest = config_changes[-1]
        backup_path = latest["backup_path"]
        logger.warning("Evolution: rolling back to %s due to engagement drop", backup_path)
        self.rollback_config(backup_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_source_limit_key(source: str):
        """Map a source name to its (section, config_key) tuple, or None."""
        # Direct match
        if source in _SOURCE_LIMIT_KEYS:
            return _SOURCE_LIMIT_KEYS[source]
        # Reddit subreddits map to the global reddit_limit
        if source.startswith("r/"):
            return ("trends", "reddit_limit")
        return None

    # ==================================================================
    # Prompt Evolution — sequential experiment + user rating
    # ==================================================================

    # Eligible prompts for evolution
    EVOLVABLE_PROMPTS = ("trend_digest", "weekly_knowledge", "linkedin_draft")
    EXPERIMENT_DURATION_DAYS = 14
    MIN_RATINGS_FOR_EVAL = 3
    VARIANT_WIN_THRESHOLD = 3.5  # avg rating >= 3.5 to promote variant

    def evolve_prompts(self) -> list:
        """Main prompt evolution entry point.

        1. Evaluate any completed experiments
        2. Start a new experiment if rate limit allows and no experiment is active
        Returns list of actions taken.
        """
        results = []

        # Evaluate completed experiments
        for name in self.EVOLVABLE_PROMPTS:
            experiment = self._get_experiment(name)
            if experiment and experiment.get("status") == "running":
                outcome = self._evaluate_experiment(name, experiment)
                if outcome:
                    results.append(outcome)

        # Start a new experiment if allowed
        if not self.check_rate_limit("prompt"):
            return results

        # Find a prompt without an active experiment
        for name in self.EVOLVABLE_PROMPTS:
            experiment = self._get_experiment(name)
            if experiment and experiment.get("status") == "running":
                continue
            started = self._start_experiment(name)
            if started:
                results.append(started)
                break  # One at a time

        return results

    def get_active_prompt(self, template_name: str) -> str | None:
        """Return variant prompt text if an experiment is active, else None.

        Called by Brain/Hands before generating a briefing.
        """
        experiment = self._get_experiment(template_name)
        if experiment and experiment.get("status") == "running":
            return experiment.get("variant_text")
        return None

    def record_prompt_rating(self, template_name: str, rating: int):
        """Record a user rating (1-5) for the current prompt variant.

        Called when user rates a briefing via Telegram.
        """
        experiment = self._get_experiment(template_name)
        if not experiment or experiment.get("status") != "running":
            return

        experiment.setdefault("ratings", []).append(rating)
        experiment["total_served"] = experiment.get("total_served", 0) + 1
        self._save_experiment(template_name, experiment)

    # ------------------------------------------------------------------
    # Experiment lifecycle
    # ------------------------------------------------------------------

    def _start_experiment(self, prompt_name: str) -> dict | None:
        """Generate a mutated prompt variant and start an experiment."""
        from .summarizer import Summarizer

        # Load original prompt
        prompts_dir = Path(__file__).parent / "prompts"
        lang = getattr(self.config, "language", "ko")
        prompt_file = prompts_dir / lang / f"{prompt_name}.txt"
        if not prompt_file.exists():
            prompt_file = prompts_dir / "ko" / f"{prompt_name}.txt"
        if not prompt_file.exists():
            return None

        original_text = prompt_file.read_text(encoding="utf-8")

        # Generate mutation via LLM
        summarizer = Summarizer(config=self.config)
        mutation_prompt = (
            "You are a prompt engineer. Below is a prompt template used to generate a briefing.\n\n"
            f"---\n{original_text}\n---\n\n"
            "Create a slightly different version that might produce more engaging output.\n"
            "Change ONE thing: tone, structure, emphasis, or level of detail.\n"
            "Keep ALL template variables (anything in {curly_braces}) exactly as they are.\n"
            "Return ONLY the modified prompt template, nothing else."
        )
        variant_text = summarizer.generate(mutation_prompt)

        # Validate
        if not self._validate_prompt(original_text, variant_text):
            logger.warning("Evolution: prompt mutation for '%s' failed validation", prompt_name)
            return None

        now = _now_kst()
        experiment = {
            "prompt_name": prompt_name,
            "original_text": original_text,
            "variant_text": variant_text,
            "started_at": now.isoformat(),
            "ends_at": (now + timedelta(days=self.EXPERIMENT_DURATION_DAYS)).isoformat(),
            "status": "running",
            "ratings": [],
            "total_served": 0,
        }
        self._save_experiment(prompt_name, experiment)

        self.log_change({
            "change_type": "prompt",
            "action": "start_experiment",
            "prompt_name": prompt_name,
        })

        logger.info("Evolution: started prompt experiment for '%s'", prompt_name)
        return {"action": "start_experiment", "prompt_name": prompt_name}

    def _evaluate_experiment(self, prompt_name: str, experiment: dict) -> dict | None:
        """Evaluate a running experiment. Returns action dict or None if ongoing."""
        now = _now_kst()
        ends_at = datetime.fromisoformat(experiment["ends_at"])
        ratings = experiment.get("ratings", [])

        # Check if experiment period is over
        if now < ends_at and len(ratings) < self.MIN_RATINGS_FOR_EVAL:
            return None  # Still running, not enough data

        # Need at least MIN_RATINGS to evaluate
        if len(ratings) < self.MIN_RATINGS_FOR_EVAL:
            if now >= ends_at:
                # Period over but insufficient ratings — extend or archive
                experiment["status"] = "archived_insufficient_data"
                self._save_experiment(prompt_name, experiment)
                return {"action": "archived", "prompt_name": prompt_name, "reason": "insufficient_ratings"}
            return None

        avg_rating = sum(ratings) / len(ratings)
        if avg_rating >= self.VARIANT_WIN_THRESHOLD:
            # Variant wins — promote to original
            self._promote_variant(prompt_name, experiment)
            experiment["status"] = "promoted"
            experiment["avg_rating"] = avg_rating
            self._save_experiment(prompt_name, experiment)

            self.log_change({
                "change_type": "prompt",
                "action": "promote_variant",
                "prompt_name": prompt_name,
                "avg_rating": avg_rating,
                "num_ratings": len(ratings),
            })
            return {"action": "promote_variant", "prompt_name": prompt_name, "avg_rating": avg_rating}
        else:
            # Original wins — archive experiment
            experiment["status"] = "archived_original_wins"
            experiment["avg_rating"] = avg_rating
            self._save_experiment(prompt_name, experiment)

            self.log_change({
                "change_type": "prompt",
                "action": "archived_original_wins",
                "prompt_name": prompt_name,
                "avg_rating": avg_rating,
                "num_ratings": len(ratings),
            })
            return {"action": "keep_original", "prompt_name": prompt_name, "avg_rating": avg_rating}

    def _promote_variant(self, prompt_name: str, experiment: dict):
        """Replace the original prompt file with the winning variant."""
        lang = getattr(self.config, "language", "ko")
        prompt_file = Path(__file__).parent / "prompts" / lang / f"{prompt_name}.txt"

        # Backup original first
        backup_path = prompt_file.with_suffix(f".txt.bak.{_now_kst().strftime('%Y%m%d_%H%M%S')}")
        if prompt_file.exists():
            shutil.copy2(prompt_file, backup_path)

        # Atomic write to prevent corruption on crash
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(prompt_file.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(experiment["variant_text"])
            os.replace(tmp_path, str(prompt_file))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.info("Evolution: promoted variant for '%s' (backup at %s)", prompt_name, backup_path)

    # ------------------------------------------------------------------
    # Prompt validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_prompt(original: str, variant: str) -> bool:
        """Check that variant preserves all template variables and isn't too long."""
        import re

        # Extract all {variable_name} patterns from original
        original_vars = set(re.findall(r"\{(\w+)\}", original))
        variant_vars = set(re.findall(r"\{(\w+)\}", variant))

        # All original variables must exist in variant
        if not original_vars.issubset(variant_vars):
            missing = original_vars - variant_vars
            logger.warning("Prompt validation failed: missing variables %s", missing)
            return False

        # Length check: variant must not be more than 2x original
        if len(variant) > len(original) * 2:
            logger.warning("Prompt validation failed: variant too long (%d > %d * 2)", len(variant), len(original))
            return False

        # Non-empty check
        if len(variant.strip()) < 50:
            logger.warning("Prompt validation failed: variant too short")
            return False

        return True

    # ------------------------------------------------------------------
    # Experiment file I/O
    # ------------------------------------------------------------------

    def _get_experiment(self, prompt_name: str) -> dict | None:
        """Load experiment state from variants directory."""
        variants_dir = getattr(self.config, "evolution_variants_path",
                               os.path.expanduser("~/.compound-brain/prompts/variants"))
        path = os.path.join(variants_dir, f"{prompt_name}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _save_experiment(self, prompt_name: str, experiment: dict):
        """Save experiment state to variants directory atomically."""
        variants_dir = getattr(self.config, "evolution_variants_path",
                               os.path.expanduser("~/.compound-brain/prompts/variants"))
        os.makedirs(variants_dir, exist_ok=True)
        path = os.path.join(variants_dir, f"{prompt_name}.json")
        tmp_fd, tmp_path = tempfile.mkstemp(dir=variants_dir, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(experiment, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ==================================================================
    # Idea-to-Implementation Tracking (C4)
    # ==================================================================

    MIN_KEYWORD_MATCHES = 2  # require 2+ keyword hits for confidence

    def track_idea_outcomes(self) -> list:
        """Match vault project ideas against git commits. Returns list of matches."""
        if not self.config.vault_path or not self.config.project_repos:
            return []

        from .knowledge_scanner import parse_project_ideas, update_idea_status
        from .meta_reviewer import _git_commits_since

        ideas = parse_project_ideas(
            self.config.vault_path,
            getattr(self.config, "ideas_file", "20_Projects/AI Ideas/project-ideas.md"),
        )
        if not ideas:
            return []

        # Only check pending/proposed ideas
        pending = [i for i in ideas if i["status"] in ("proposed", "pending")]
        if not pending:
            return []

        # Collect all commits across tracked repos
        all_commits = {}
        for project_name, repo_path in self.config.project_repos.items():
            if not os.path.isdir(repo_path):
                continue
            commits = _git_commits_since(repo_path, days=30)
            if commits:
                all_commits[project_name] = " ".join(commits).lower()

        if not all_commits:
            return []

        matches = []
        for idea in pending:
            keywords = idea.get("keywords", [])
            if not keywords:
                continue

            for project_name, commit_text in all_commits.items():
                hit_count = sum(1 for kw in keywords if kw in commit_text)
                if hit_count >= self.MIN_KEYWORD_MATCHES:
                    matches.append({
                        "idea_id": idea["id"],
                        "idea_text": idea["text"],
                        "project": project_name,
                        "matched_keywords": [kw for kw in keywords if kw in commit_text],
                        "hit_count": hit_count,
                    })
                    # Update status in vault
                    update_idea_status(
                        self.config.vault_path,
                        idea["id"],
                        "implemented",
                        project_name,
                    )
                    self.log_change({
                        "change_type": "idea_tracking",
                        "action": "mark_implemented",
                        "idea_id": idea["id"],
                        "project": project_name,
                        "matched_keywords": [kw for kw in keywords if kw in commit_text],
                    })
                    break  # One match per idea is enough

        if matches:
            logger.info("Evolution: matched %d ideas to implementations", len(matches))
        return matches
