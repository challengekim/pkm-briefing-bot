"""Tests for Hands utility methods — lightweight, no I/O."""
import pytest
from unittest.mock import MagicMock, patch


class TestHandsSendSkipNotification:
    def setup_method(self):
        self.config = MagicMock()
        # Prevent lazy property imports from running
        with patch("compound_agent.hands.Hands.telegram", new_callable=lambda: property(lambda self: self._mock_tg)):
            pass

    def _make_hands(self):
        """Build a Hands instance with channel mocked at the instance level."""
        from compound_agent.hands import Hands
        mock_channel = MagicMock()
        mock_channel.send_plain.return_value = True
        h = Hands(self.config, channel=mock_channel)
        h._telegram = MagicMock()
        return h

    def test_send_skip_notification_no_new_notes_sends_korean_message(self):
        """send_skip_notification with no_new_notes sends a Korean message."""
        h = self._make_hands()
        h.send_skip_notification("no_new_notes")
        h.channel.send_plain.assert_called_once()
        msg = h.channel.send_plain.call_args[0][0]
        assert "노트" in msg or "지식" in msg

    def test_send_skip_notification_consecutive_failures_includes_details(self):
        """consecutive_failures reason embeds the details string in the message."""
        h = self._make_hands()
        h.send_skip_notification("consecutive_failures", details="트렌드 다이제스트")
        msg = h.channel.send_plain.call_args[0][0]
        assert "트렌드 다이제스트" in msg

    def test_send_skip_notification_unknown_reason_sends_fallback_message(self):
        """Unknown reason sends a generic fallback message containing the reason."""
        h = self._make_hands()
        h.send_skip_notification("some_unknown_reason")
        msg = h.channel.send_plain.call_args[0][0]
        assert "some_unknown_reason" in msg

    def test_send_skip_notification_returns_success_dict(self):
        """send_skip_notification returns dict with success=True."""
        h = self._make_hands()
        result = h.send_skip_notification("no_new_notes")
        assert result["success"] is True
        assert result["reason"] == "no_new_notes"

    def test_send_skip_notification_no_trends_sends_message(self):
        """no_trends reason sends a relevant Korean message."""
        h = self._make_hands()
        h.send_skip_notification("no_trends")
        h.channel.send_plain.assert_called_once()
        msg = h.channel.send_plain.call_args[0][0]
        assert len(msg) > 0


class TestHandsGetRelatedNotes:
    def setup_method(self):
        self.config = MagicMock()

    def _make_hands(self):
        from compound_agent.hands import Hands
        return Hands(self.config)

    def test_get_related_notes_filters_by_category(self):
        """get_related_notes returns only notes matching the given category."""
        h = self._make_hands()
        mock_notes = [
            {"title": "AI Note", "category": "ai-eng", "source": "https://a.com", "saved": "2026-04-09"},
            {"title": "Biz Note", "category": "business", "source": "https://b.com", "saved": "2026-04-09"},
            {"title": "AI Note 2", "category": "ai-eng", "source": "https://c.com", "saved": "2026-04-09"},
        ]
        # hands.get_related_notes does a local `from compound_agent.knowledge_scanner import scan_recent_notes`
        # so we must patch at the knowledge_scanner module level.
        with patch("compound_agent.knowledge_scanner.scan_recent_notes", return_value=mock_notes):
            results = h.get_related_notes("ai-eng")
        titles = [r["title"] for r in results]
        assert "AI Note" in titles
        assert "Biz Note" not in titles

    def test_get_related_notes_respects_limit(self):
        """get_related_notes returns at most limit entries."""
        h = self._make_hands()
        mock_notes = [
            {"title": f"Note{i}", "category": "ai-eng", "source": f"https://{i}.com", "saved": "2026-04-09"}
            for i in range(10)
        ]
        with patch("compound_agent.knowledge_scanner.scan_recent_notes", return_value=mock_notes):
            results = h.get_related_notes("ai-eng", limit=3)
        assert len(results) <= 3

    def test_get_related_notes_excludes_url(self):
        """get_related_notes excludes the note whose source matches exclude_url."""
        h = self._make_hands()
        mock_notes = [
            {"title": "Excluded", "category": "ai-eng", "source": "https://exclude.com", "saved": "2026-04-09"},
            {"title": "Included", "category": "ai-eng", "source": "https://include.com", "saved": "2026-04-09"},
        ]
        with patch("compound_agent.knowledge_scanner.scan_recent_notes", return_value=mock_notes):
            results = h.get_related_notes("ai-eng", exclude_url="https://exclude.com", limit=10)
        titles = [r["title"] for r in results]
        assert "Excluded" not in titles
        assert "Included" in titles

    def test_get_related_notes_returns_empty_on_exception(self):
        """get_related_notes returns [] when knowledge_scanner raises."""
        h = self._make_hands()
        with patch("compound_agent.knowledge_scanner.scan_recent_notes", side_effect=RuntimeError("vault error")):
            results = h.get_related_notes("ai-eng")
        assert results == []
