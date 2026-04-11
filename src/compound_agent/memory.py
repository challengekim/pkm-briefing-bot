"""
AgentMemory — persistent memory for engagement tracking, preference learning,
and source quality scoring. Used by the Proactive Agent (Phase B).
Storage: ~/.compound-brain/memory.json (JSON, stdlib only)
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _parse_dt(s: str) -> datetime:
    """Parse ISO timestamp, always return timezone-aware datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


class AgentMemory:
    MAX_ENGAGEMENT_LOG = 1000

    def __init__(
        self,
        memory_path: str = "~/.compound-brain/memory.json",
        ema_alpha: float = 0.2,
        min_reading_samples: int = 5,
    ):
        self._path = os.path.expanduser(memory_path)
        self._lock = threading.Lock()
        self._alpha = ema_alpha
        self._min_reading_samples = min_reading_samples
        data = self._load()
        self.engagement_log: list = data.get("engagement_log", [])
        self.preferences: dict = data.get(
            "preferences",
            {
                "preferred_categories": {},
                "reading_times": {},
            },
        )
        self.source_scores: dict = data.get("source_scores", {})

    # ------------------------------------------------------------------
    # Engagement tracking
    # ------------------------------------------------------------------

    def log_engagement(
        self,
        briefing_type: str,
        message_id: int,
        reaction: str,
        item_id: str = None,
    ):
        """
        Record a user engagement event.

        reaction: "positive", "negative", "bookmark", "ignored"
        Auto-prunes engagement_log when it exceeds MAX_ENGAGEMENT_LOG.
        """
        entry = {
            "briefing_type": briefing_type,
            "message_id": message_id,
            "reaction": reaction,
            "reacted_at": _now_kst().isoformat(),
        }
        if item_id is not None:
            entry["item_id"] = item_id

        with self._lock:
            self.engagement_log.append(entry)
            if len(self.engagement_log) > self.MAX_ENGAGEMENT_LOG:
                self.engagement_log = self.engagement_log[-self.MAX_ENGAGEMENT_LOG :]

    def get_engagement_log_snapshot(self) -> list:
        """Return a thread-safe copy of the engagement log."""
        with self._lock:
            return list(self.engagement_log)

    def get_engagement_stats(
        self, briefing_type: str = None, days: int = 30
    ) -> dict:
        """
        Return engagement statistics.

        Filters by briefing_type if provided and by the last N days.
        Returns {total, positive, negative, bookmark, ignored, engagement_rate}.
        """
        cutoff = _now_kst() - timedelta(days=days)
        with self._lock:
            entries = list(self.engagement_log)

        filtered = [
            e
            for e in entries
            if _parse_dt(e["reacted_at"]) >= cutoff
            and (briefing_type is None or e.get("briefing_type") == briefing_type)
        ]

        counts = {"positive": 0, "negative": 0, "bookmark": 0, "ignored": 0}
        for e in filtered:
            reaction = e.get("reaction", "ignored")
            if reaction in counts:
                counts[reaction] += 1

        total = len(filtered)
        active = counts["positive"] + counts["negative"] + counts["bookmark"]
        engagement_rate = active / total if total > 0 else 0.0

        return {
            "total": total,
            "positive": counts["positive"],
            "negative": counts["negative"],
            "bookmark": counts["bookmark"],
            "ignored": counts["ignored"],
            "engagement_rate": engagement_rate,
        }

    # ------------------------------------------------------------------
    # Preference model
    # ------------------------------------------------------------------

    def update_category_preference(self, category: str, positive: bool):
        """
        Update EMA score for a content category.

        New categories start at 0.5 (Bayesian prior).
        EMA: new_score = (1 - alpha) * old_score + alpha * signal
        """
        signal = 1.0 if positive else 0.0
        with self._lock:
            cats = self.preferences.setdefault("preferred_categories", {})
            if category not in cats:
                cats[category] = {
                    "score": 0.5,
                    "interactions": 0,
                    "last_updated": _now_kst().isoformat(),
                }
            entry = cats[category]
            entry["score"] = (1 - self._alpha) * entry["score"] + self._alpha * signal
            entry["interactions"] = entry.get("interactions", 0) + 1
            entry["last_updated"] = _now_kst().isoformat()

    def get_preferred_categories(self, top_n: int = 5) -> list:
        """Return top-N (category, score) pairs sorted by score descending."""
        with self._lock:
            cats = self.preferences.get("preferred_categories", {})
            pairs = [(cat, info["score"]) for cat, info in cats.items()]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[:top_n]

    def update_reading_time(self, briefing_type: str, read_hour: float):
        """
        Update running average of reading hour for a briefing type.

        new_avg = ((old_avg * samples) + read_hour) / (samples + 1)
        """
        with self._lock:
            times = self.preferences.setdefault("reading_times", {})
            if briefing_type not in times:
                times[briefing_type] = {
                    "avg_read_hour": read_hour,
                    "samples": 1,
                    "last_updated": _now_kst().isoformat(),
                }
            else:
                entry = times[briefing_type]
                old_avg = entry["avg_read_hour"]
                samples = entry["samples"]
                entry["avg_read_hour"] = (old_avg * samples + read_hour) / (samples + 1)
                entry["samples"] = samples + 1
                entry["last_updated"] = _now_kst().isoformat()

    def get_optimal_send_time(self, briefing_type: str):
        """
        Return avg_read_hour for briefing_type if samples >= 5, else None.
        """
        with self._lock:
            times = self.preferences.get("reading_times", {})
            entry = times.get(briefing_type)
        if entry is None or entry.get("samples", 0) < self._min_reading_samples:
            return None
        return entry["avg_read_hour"]

    # ------------------------------------------------------------------
    # Source scores
    # ------------------------------------------------------------------

    def update_source_score(self, source: str, positive: bool):
        """
        Record an impression for a source and recalculate quality score.

        quality = positive_count / total_shown
        """
        with self._lock:
            if source not in self.source_scores:
                self.source_scores[source] = {
                    "quality": 0.0,
                    "total_shown": 0,
                    "positive": 0,
                    "negative": 0,
                }
            entry = self.source_scores[source]
            entry["total_shown"] += 1
            if positive:
                entry["positive"] += 1
            else:
                entry["negative"] += 1
            entry["quality"] = entry["positive"] / entry["total_shown"]

    def get_source_rankings(self, min_shown: int = 10) -> list:
        """
        Return (source, quality) pairs sorted by quality descending.

        Only includes sources with total_shown >= min_shown.
        """
        with self._lock:
            pairs = [
                (src, info["quality"])
                for src, info in self.source_scores.items()
                if info.get("total_shown", 0) >= min_shown
            ]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self):
        """Persist memory to JSON file atomically; create parent directory if needed."""
        with self._lock:
            payload = {
                "version": 1,
                "engagement_log": list(self.engagement_log),
                "preferences": {
                    "preferred_categories": dict(
                        self.preferences.get("preferred_categories", {})
                    ),
                    "reading_times": dict(
                        self.preferences.get("reading_times", {})
                    ),
                },
                "source_scores": dict(self.source_scores),
            }

        parent = os.path.dirname(self._path)
        os.makedirs(parent, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def cleanup_old(self, days: int = 90):
        """Prune engagement_log entries older than N days."""
        cutoff = _now_kst() - timedelta(days=days)
        with self._lock:
            self.engagement_log = [
                e
                for e in self.engagement_log
                if _parse_dt(e["reacted_at"]) >= cutoff
            ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        """Read memory from JSON file; return empty dict on any error."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
