"""EventLog — append-only JSONL event storage for agent cycle tracking."""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class EventLog:
    """Thread-safe append-only JSONL event log."""

    def __init__(self, log_dir: str):
        self._path = Path(log_dir) / "events.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def append(
        self,
        event_type: str,
        agent: str = "system",
        task: dict = None,
        result: dict = None,
    ) -> str:
        """Append an event and return its uuid4 event_id."""
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "agent": agent,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "task": task or {},
            "result": result or {},
        }
        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        return event_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _read_all(self) -> list[dict]:
        """Read all events from disk."""
        if not self._path.exists():
            return []
        events = []
        with self._lock:
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            logger.warning("Skipping malformed event line")
            except OSError:
                return []
        return events

    def get_last_cycle(self) -> list[dict]:
        """Return events since the last cycle_start event (inclusive)."""
        events = self._read_all()
        # Find the index of the last cycle_start
        last_start = -1
        for i, ev in enumerate(events):
            if ev.get("event_type") == "cycle_start":
                last_start = i
        if last_start == -1:
            return events  # No cycle_start found — return everything
        return events[last_start:]

    def get_events(
        self,
        since: datetime = None,
        event_type: str = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return filtered events, newest last, up to limit."""
        events = self._read_all()
        if since is not None:
            since_str = since.isoformat()
            events = [
                e for e in events
                if e.get("timestamp", "") >= since_str
            ]
        if event_type is not None:
            events = [e for e in events if e.get("event_type") == event_type]
        return events[-limit:]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def rotate(self, max_lines: int = 10_000):
        """Truncate log to last max_lines entries."""
        with self._lock:
            if not self._path.exists():
                return
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                return
            if len(lines) <= max_lines:
                return
            keep = lines[-max_lines:]
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(keep)
            tmp.replace(self._path)
            logger.info(
                "EventLog rotated: kept %d of %d lines", max_lines, len(lines)
            )
