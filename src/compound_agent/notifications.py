"""NotificationChannel — pluggable notification delivery abstraction."""
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Abstract notification channel for delivering briefings and plain messages."""

    @abstractmethod
    def send_briefing(self, message: str, briefing_type: str, mode: str) -> int | None:
        """Send a briefing with appropriate interaction elements for the channel.

        Args:
            message: The briefing text to send.
            briefing_type: Type of briefing (e.g. "trend", "morning", "knowledge").
            mode: Agent mode ("disabled", "reactive", "proactive", "self-improving", "multi-agent").

        Returns:
            A message identifier (int) if the channel supports it, else None.
        """
        ...

    @abstractmethod
    def send_plain(self, text: str) -> bool:
        """Send a plain text notification without interaction elements.

        Returns True on success, False on failure.
        """
        ...


class TelegramChannel(NotificationChannel):
    """Telegram implementation — wraps TelegramSender transparently."""

    def __init__(self, telegram_sender, evolution_checker=None):
        """
        Args:
            telegram_sender: A TelegramSender instance.
            evolution_checker: Optional callable(briefing_type) -> bool that returns
                True if there is an active prompt experiment for this briefing_type.
        """
        self._sender = telegram_sender
        self._evolution_checker = evolution_checker

    def send_briefing(self, message: str, briefing_type: str, mode: str) -> int | None:
        if mode in ("proactive", "self-improving"):
            has_experiment = False
            if mode == "self-improving" and self._evolution_checker:
                has_experiment = self._evolution_checker(briefing_type)

            if has_experiment:
                return self._sender.send_message_with_rating(message, briefing_type)
            return self._sender.send_message_with_engagement(message, briefing_type)
        else:
            self._sender.send_message(message)
            return None

    def send_plain(self, text: str) -> bool:
        return self._sender.send_message(text)


class LogChannel(NotificationChannel):
    """In-memory log channel for testing — records all sent messages."""

    def __init__(self):
        self.messages: list[dict] = []

    def send_briefing(self, message: str, briefing_type: str, mode: str) -> int | None:
        msg_id = len(self.messages) + 1
        self.messages.append({
            "type": "briefing",
            "message": message,
            "briefing_type": briefing_type,
            "mode": mode,
            "message_id": msg_id,
        })
        return msg_id

    def send_plain(self, text: str) -> bool:
        self.messages.append({
            "type": "plain",
            "message": text,
        })
        return True


def create_channel(config) -> NotificationChannel:
    """Factory: create the appropriate notification channel from config."""
    channel_type = getattr(config, "notification_channel", "telegram")

    if channel_type == "log":
        return LogChannel()

    # Default: Telegram
    from .telegram_sender import TelegramSender
    sender = TelegramSender(config.telegram_bot_token, config.telegram_chat_id)

    evolution_checker = None
    if config.agent_mode == "self-improving":
        def _check_evolution(briefing_type):
            try:
                from .evolution import Evolution
                from .memory import AgentMemory
                memory = AgentMemory(
                    memory_path=config.agent_memory_path,
                    ema_alpha=config.agent_ema_alpha,
                    min_reading_samples=config.agent_min_reading_samples,
                )
                evo = Evolution(config, memory)
                return evo.get_active_prompt(briefing_type) is not None
            except Exception as e:
                logger.warning("Evolution check failed: %s", e)
                return False
        evolution_checker = _check_evolution

    return TelegramChannel(sender, evolution_checker)
