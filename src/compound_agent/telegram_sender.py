import logging
import re

import requests

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
URL_RE = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')


class TelegramSender:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def get_updates(self, offset=None):
        """Poll for updates including both messages and callback queries."""
        params = {"timeout": 1}
        if offset:
            params["offset"] = offset
        try:
            resp = requests.get(f"{self.base_url}/getUpdates", params=params, timeout=5)
            if resp.ok:
                return resp.json().get("result", [])
        except Exception as e:
            logger.debug(f"Telegram poll error: {e}")
        return []

    def send_message(self, text, parse_mode="HTML"):
        chunks = self._split_message(text)
        for chunk in chunks:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": chunk,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
            )
            if not resp.ok:
                logger.error(f"Telegram send failed: {resp.text}")
                return False
        return True

    def send_message_with_keyboard(self, text, reply_markup, parse_mode="HTML"):
        """Send a Telegram message with an inline keyboard.

        Args:
            text: Message text
            reply_markup: Dict with inline_keyboard structure, e.g.:
                {"inline_keyboard": [[
                    {"text": "👍", "callback_data": "useful_trend_123"},
                    {"text": "👎", "callback_data": "skip_trend_123"},
                ]]}
            parse_mode: HTML or Markdown
        """
        chunks = self._split_message(text)
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            if i == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            resp = requests.post(f"{self.base_url}/sendMessage", json=payload)
            if not resp.ok:
                logger.error(f"Telegram send failed: {resp.text}")
                return False
        return True

    def send_message_with_engagement(self, text, briefing_type: str, parse_mode="HTML"):
        """Send a message with engagement feedback buttons. Returns message_id or None."""
        keyboard = {
            "inline_keyboard": [[
                {"text": "👍", "callback_data": f"eng_p_{briefing_type}"},
                {"text": "👎", "callback_data": f"eng_n_{briefing_type}"},
                {"text": "📌", "callback_data": f"eng_b_{briefing_type}"},
            ]]
        }
        return self._send_with_keyboard(text, keyboard, parse_mode)

    def send_message_with_rating(self, text, briefing_type: str, parse_mode="HTML"):
        """Send with engagement + prompt rating buttons. Returns message_id or None."""
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "👍", "callback_data": f"eng_p_{briefing_type}"},
                    {"text": "👎", "callback_data": f"eng_n_{briefing_type}"},
                    {"text": "📌", "callback_data": f"eng_b_{briefing_type}"},
                ],
                [
                    {"text": "⭐1", "callback_data": f"rate_1_{briefing_type}"},
                    {"text": "⭐2", "callback_data": f"rate_2_{briefing_type}"},
                    {"text": "⭐3", "callback_data": f"rate_3_{briefing_type}"},
                    {"text": "⭐4", "callback_data": f"rate_4_{briefing_type}"},
                    {"text": "⭐5", "callback_data": f"rate_5_{briefing_type}"},
                ],
            ]
        }
        return self._send_with_keyboard(text, keyboard, parse_mode)

    def _send_with_keyboard(self, text, keyboard, parse_mode="HTML"):
        """Send a message with inline keyboard. Returns message_id or None."""
        chunks = self._split_message(text)
        last_msg_id = None
        for i, chunk in enumerate(chunks):
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            if i == len(chunks) - 1:
                payload["reply_markup"] = keyboard
            resp = requests.post(f"{self.base_url}/sendMessage", json=payload)
            if not resp.ok:
                logger.error(f"Telegram send failed: {resp.text}")
                return None
            try:
                last_msg_id = resp.json().get("result", {}).get("message_id")
            except Exception:
                pass
        return last_msg_id

    def answer_callback_query(self, callback_query_id, text=None):
        """Acknowledge a callback query (removes the loading indicator on the button).

        Args:
            callback_query_id: The ID from the callback_query update
            text: Optional notification text to show the user
        """
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        requests.post(f"{self.base_url}/answerCallbackQuery", json=payload)

    def _split_message(self, text):
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]

        chunks = []
        while text:
            if len(text) <= MAX_MESSAGE_LENGTH:
                chunks.append(text)
                break
            split_idx = text[:MAX_MESSAGE_LENGTH].rfind("\n")
            if split_idx == -1:
                split_idx = MAX_MESSAGE_LENGTH
            chunks.append(text[:split_idx])
            text = text[split_idx:].lstrip("\n")
        return chunks
