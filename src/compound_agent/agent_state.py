"""
AgentState — minimal persistent state for the Reactive Agent (Phase A).
Storage: ~/.compound-brain/state.json (JSON, stdlib only)
"""

import json
import os
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


class AgentState:
    def __init__(self, state_path: str = "~/.compound-brain/state.json"):
        self._path = os.path.expanduser(state_path)
        self._lock = threading.Lock()
        data = self._load()
        self.recent_saves: list = data.get("recent_saves", [])
        self.last_actions: dict = data.get("last_actions", {})
        self.known_urls: set = set(data.get("known_urls", []))
        self.failure_counts: dict = data.get("failure_counts", {})
        self.deferred_actions: list = data.get("deferred_actions", [])
        self.pending_engagements: list = data.get("pending_engagements", [])

    # ------------------------------------------------------------------
    # Mutation methods
    # ------------------------------------------------------------------

    def log_save(self, url: str, category: str, title: str):
        """Add a URL save record and register the URL as known."""
        entry = {
            "url": url,
            "category": category,
            "title": title,
            "saved_at": _now_kst().isoformat(),
        }
        with self._lock:
            self.recent_saves.append(entry)
            self.known_urls.add(url)

    def log_action(self, action_type: str, timestamp=None):
        """Record successful execution of an action; reset its failure count."""
        ts = timestamp if timestamp is not None else _now_kst()
        if isinstance(ts, datetime):
            ts = ts.isoformat()
        with self._lock:
            self.last_actions[action_type] = ts
            self.failure_counts[action_type] = 0

    def log_failure(self, action_type: str):
        """Increment consecutive failure count for an action."""
        with self._lock:
            self.failure_counts[action_type] = self.failure_counts.get(action_type, 0) + 1

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_recent_saves(self, hours: int = 24) -> list:
        """Return saves within the last N hours."""
        cutoff = _now_kst() - timedelta(hours=hours)
        return [
            s for s in self.recent_saves
            if _parse_dt(s["saved_at"]) >= cutoff
        ]

    def get_saves_by_category(self, days: int = 1) -> dict:
        """Return {category: count} for saves within the last N days."""
        cutoff = _now_kst() - timedelta(days=days)
        counts: dict = {}
        for s in self.recent_saves:
            if _parse_dt(s["saved_at"]) >= cutoff:
                cat = s.get("category", "unknown")
                counts[cat] = counts.get(cat, 0) + 1
        return counts

    def days_since_action(self, action_type: str) -> int:
        """Return days since this action last ran, or 999 if never."""
        ts_str = self.last_actions.get(action_type)
        if not ts_str:
            return 999
        delta = _now_kst() - _parse_dt(ts_str)
        return delta.days

    def is_duplicate_url(self, url: str) -> bool:
        """Return True if URL has already been saved."""
        return url in self.known_urls

    def get_failure_count(self, action_type: str) -> int:
        """Return consecutive failure count for an action."""
        return self.failure_counts.get(action_type, 0)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def defer_action(self, action: dict, optimal_hour: float):
        """Store an action to execute at a better time."""
        with self._lock:
            self.deferred_actions.append({
                **action,
                "_optimal_hour": optimal_hour,
                "_deferred_at": _now_kst().isoformat(),
            })

    def get_ready_deferred(self) -> list:
        """Return deferred actions whose optimal time has arrived."""
        with self._lock:
            if not self.deferred_actions:
                return []
            now = _now_kst()
            now_hour = now.hour + now.minute / 60.0
            ready = []
            remaining = []
            for action in self.deferred_actions:
                # Ready if current time >= optimal_hour - 15min (0.25)
                if now_hour >= action["_optimal_hour"] - 0.25:
                    clean = {k: v for k, v in action.items() if not k.startswith("_")}
                    ready.append(clean)
                else:
                    remaining.append(action)
            self.deferred_actions = remaining
            return ready

    def clear_deferred(self, action_type: str):
        """Remove a specific deferred action by type."""
        with self._lock:
            self.deferred_actions = [
                a for a in self.deferred_actions if a.get("type") != action_type
            ]

    def resolve_pending_engagement(self, message_id: int):
        """Remove a pending engagement entry when user responds."""
        with self._lock:
            self.pending_engagements = [
                p for p in self.pending_engagements
                if p.get("message_id") != message_id
            ]

    def cleanup_old(self, days: int = 30):
        """Remove recent_saves entries older than N days and rebuild known_urls."""
        cutoff = _now_kst() - timedelta(days=days)
        with self._lock:
            self.recent_saves = [
                s for s in self.recent_saves
                if _parse_dt(s["saved_at"]) >= cutoff
            ]
            self.known_urls = {s["url"] for s in self.recent_saves}

    def save(self):
        """Persist state to JSON file atomically; create parent directory if needed."""
        import tempfile
        with self._lock:
            payload = {
                "version": 1,
                "recent_saves": list(self.recent_saves),
                "last_actions": dict(self.last_actions),
                "known_urls": list(self.known_urls),
                "failure_counts": dict(self.failure_counts),
                "deferred_actions": list(self.deferred_actions),
                "pending_engagements": self.pending_engagements,
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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        """Read state from JSON file; return empty structure on any error."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
