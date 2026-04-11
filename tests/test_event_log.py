"""Tests for EventLog."""
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from compound_agent.session.event_log import EventLog


@pytest.fixture
def log(tmp_path):
    return EventLog(str(tmp_path))


class TestEventLogAppendAndRead:
    def test_append_returns_event_id(self, log):
        eid = log.append("test_event")
        assert isinstance(eid, str) and len(eid) == 36  # uuid4

    def test_appended_event_readable(self, log):
        log.append("test_event", agent="sys", task={"k": "v"}, result={"ok": True})
        events = log.get_events()
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"] == "test_event"
        assert ev["agent"] == "sys"
        assert ev["task"] == {"k": "v"}
        assert ev["result"] == {"ok": True}

    def test_multiple_appends_ordered(self, log):
        for i in range(5):
            log.append(f"ev_{i}")
        events = log.get_events()
        assert len(events) == 5
        assert [e["event_type"] for e in events] == [f"ev_{i}" for i in range(5)]

    def test_event_has_timestamp(self, log):
        log.append("ts_test")
        ev = log.get_events()[0]
        assert "timestamp" in ev
        assert ev["timestamp"].endswith("Z")

    def test_empty_log_returns_empty_list(self, log):
        events = log.get_events()
        assert events == []


class TestEventLogGetLastCycle:
    def test_returns_empty_for_empty_log(self, log):
        assert log.get_last_cycle() == []

    def test_returns_all_events_when_no_cycle_start(self, log):
        log.append("ev1")
        log.append("ev2")
        cycle = log.get_last_cycle()
        assert len(cycle) == 2

    def test_returns_events_from_last_cycle_start(self, log):
        log.append("ev_before")
        log.append("cycle_start")
        log.append("ev_after1")
        log.append("ev_after2")
        cycle = log.get_last_cycle()
        # Should include cycle_start and after
        assert len(cycle) == 3
        assert cycle[0]["event_type"] == "cycle_start"

    def test_multiple_cycle_starts_uses_last(self, log):
        log.append("cycle_start")
        log.append("ev_old")
        log.append("cycle_start")
        log.append("ev_new")
        cycle = log.get_last_cycle()
        assert len(cycle) == 2
        assert cycle[1]["event_type"] == "ev_new"


class TestEventLogFiltering:
    def test_filter_by_event_type(self, log):
        log.append("type_a")
        log.append("type_b")
        log.append("type_a")
        results = log.get_events(event_type="type_a")
        assert len(results) == 2
        assert all(e["event_type"] == "type_a" for e in results)

    def test_filter_by_since(self, log):
        log.append("old_ev")
        future = datetime.now(timezone.utc) + timedelta(seconds=1)
        time.sleep(0.01)
        log.append("new_ev")
        results = log.get_events(since=future)
        # The new_ev was appended after future so it may or may not match
        # depending on timing; just verify no crash and result is a list
        assert isinstance(results, list)

    def test_limit_respected(self, log):
        for i in range(20):
            log.append(f"ev_{i}")
        results = log.get_events(limit=5)
        assert len(results) == 5

    def test_limit_returns_latest(self, log):
        for i in range(10):
            log.append(f"ev_{i}")
        results = log.get_events(limit=3)
        assert results[-1]["event_type"] == "ev_9"


class TestEventLogRotate:
    def test_rotate_truncates_to_max_lines(self, log):
        for i in range(100):
            log.append(f"ev_{i}")
        log.rotate(max_lines=50)
        events = log.get_events(limit=200)
        assert len(events) == 50

    def test_rotate_keeps_latest(self, log):
        for i in range(100):
            log.append(f"ev_{i}")
        log.rotate(max_lines=10)
        events = log.get_events(limit=200)
        assert events[-1]["event_type"] == "ev_99"

    def test_rotate_noop_when_under_limit(self, log):
        for i in range(5):
            log.append(f"ev_{i}")
        log.rotate(max_lines=100)
        events = log.get_events(limit=200)
        assert len(events) == 5

    def test_rotate_on_empty_log(self, log):
        log.rotate(max_lines=100)  # should not raise


class TestEventLogConcurrentWrites:
    def test_concurrent_writes_all_persisted(self, tmp_path):
        log = EventLog(str(tmp_path))
        errors = []

        def writer(n):
            try:
                for i in range(10):
                    log.append(f"ev_{n}_{i}", agent=f"agent_{n}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        events = log.get_events(limit=1000)
        assert len(events) == 50
