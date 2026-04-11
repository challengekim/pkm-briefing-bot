"""Tests for NotificationChannel abstraction."""
import pytest
from unittest.mock import MagicMock

from compound_agent.notifications import (
    LogChannel,
    NotificationChannel,
    TelegramChannel,
)


# ------------------------------------------------------------------
# TelegramChannel
# ------------------------------------------------------------------

class TestTelegramChannel:
    def test_send_briefing_disabled_mode_sends_plain(self):
        sender = MagicMock()
        channel = TelegramChannel(sender)
        result = channel.send_briefing("hello", "trend", "disabled")
        sender.send_message.assert_called_once_with("hello")
        assert result is None

    def test_send_briefing_multi_agent_sends_plain(self):
        sender = MagicMock()
        channel = TelegramChannel(sender)
        result = channel.send_briefing("hello", "trend", "multi-agent")
        sender.send_message.assert_called_once_with("hello")
        assert result is None

    def test_send_briefing_proactive_sends_engagement(self):
        sender = MagicMock()
        sender.send_message_with_engagement.return_value = 42
        channel = TelegramChannel(sender)
        result = channel.send_briefing("hello", "trend", "proactive")
        sender.send_message_with_engagement.assert_called_once_with("hello", "trend")
        assert result == 42

    def test_send_briefing_self_improving_no_experiment_sends_engagement(self):
        sender = MagicMock()
        sender.send_message_with_engagement.return_value = 43
        channel = TelegramChannel(sender, evolution_checker=lambda bt: False)
        result = channel.send_briefing("hello", "trend", "self-improving")
        sender.send_message_with_engagement.assert_called_once()
        assert result == 43

    def test_send_briefing_self_improving_with_experiment_sends_rating(self):
        sender = MagicMock()
        sender.send_message_with_rating.return_value = 44
        channel = TelegramChannel(sender, evolution_checker=lambda bt: True)
        result = channel.send_briefing("hello", "trend", "self-improving")
        sender.send_message_with_rating.assert_called_once_with("hello", "trend")
        assert result == 44

    def test_send_plain_delegates_to_sender(self):
        sender = MagicMock()
        sender.send_message.return_value = True
        channel = TelegramChannel(sender)
        result = channel.send_plain("skip notification")
        sender.send_message.assert_called_once_with("skip notification")
        assert result is True


# ------------------------------------------------------------------
# LogChannel
# ------------------------------------------------------------------

class TestLogChannel:
    def test_send_briefing_records_message(self):
        channel = LogChannel()
        msg_id = channel.send_briefing("hello", "trend", "multi-agent")
        assert msg_id == 1
        assert len(channel.messages) == 1
        assert channel.messages[0]["type"] == "briefing"
        assert channel.messages[0]["briefing_type"] == "trend"
        assert channel.messages[0]["mode"] == "multi-agent"

    def test_send_plain_records_message(self):
        channel = LogChannel()
        result = channel.send_plain("skip reason")
        assert result is True
        assert len(channel.messages) == 1
        assert channel.messages[0]["type"] == "plain"
        assert channel.messages[0]["message"] == "skip reason"

    def test_message_ids_increment(self):
        channel = LogChannel()
        id1 = channel.send_briefing("a", "trend", "disabled")
        id2 = channel.send_briefing("b", "morning", "disabled")
        assert id1 == 1
        assert id2 == 2


# ------------------------------------------------------------------
# ABC enforcement
# ------------------------------------------------------------------

class TestNotificationChannelABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            NotificationChannel()
