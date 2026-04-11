"""Tests for vault_search and TelegramHandler Q&A routing."""
import pytest
from unittest.mock import MagicMock, patch

from compound_agent.vault_search import search_vault, synthesize_answer
from compound_agent.telegram_handler import TelegramHandler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_NOTES = [
    {
        "title": "LLM Agent Architecture",
        "description": "How to build autonomous agents with LLMs",
        "category": "ai-eng",
        "saved": "2024-01-10",
        "tags": "[ai, agents]",
        "source": "https://example.com/1",
    },
    {
        "title": "Marketing Growth Tactics",
        "description": "SEO and conversion strategies for SaaS",
        "category": "marketing",
        "saved": "2024-01-09",
        "tags": "[marketing, seo]",
        "source": "https://example.com/2",
    },
    {
        "title": "RAG Pipeline Design",
        "description": "Retrieval augmented generation patterns",
        "category": "ai-eng",
        "saved": "2024-01-08",
        "tags": "[ai, rag]",
        "source": "https://example.com/3",
    },
]


def _make_handler():
    config = MagicMock()
    config.telegram_chat_id = "123"
    config.agent_mode = "proactive"
    brain = MagicMock()
    telegram = MagicMock()
    state = MagicMock()
    state.current_state = "idle"
    handler = TelegramHandler(config, brain, telegram, state)
    return handler, config, brain, telegram, state


# ---------------------------------------------------------------------------
# search_vault tests
# ---------------------------------------------------------------------------

class TestSearchVault:
    def test_returns_matching_notes_by_keyword(self):
        config = MagicMock()
        with patch("compound_agent.vault_search.scan_recent_notes", return_value=SAMPLE_NOTES):
            results = search_vault(config, "agent LLM")
        titles = [r["title"] for r in results]
        assert "LLM Agent Architecture" in titles

    def test_excludes_non_matching_notes(self):
        config = MagicMock()
        with patch("compound_agent.vault_search.scan_recent_notes", return_value=SAMPLE_NOTES):
            results = search_vault(config, "agent LLM")
        titles = [r["title"] for r in results]
        assert "Marketing Growth Tactics" not in titles

    def test_returns_empty_when_no_matches(self):
        config = MagicMock()
        with patch("compound_agent.vault_search.scan_recent_notes", return_value=SAMPLE_NOTES):
            results = search_vault(config, "blockchain cryptocurrency")
        assert results == []

    def test_sorts_by_relevance_descending(self):
        config = MagicMock()
        # "ai-eng" appears in both ai notes; "agent" appears only in first
        with patch("compound_agent.vault_search.scan_recent_notes", return_value=SAMPLE_NOTES):
            results = search_vault(config, "agent architecture ai-eng")
        # LLM Agent Architecture matches title ("agent", "architecture") + category ("ai-eng")
        assert results[0]["title"] == "LLM Agent Architecture"

    def test_respects_max_results(self):
        config = MagicMock()
        with patch("compound_agent.vault_search.scan_recent_notes", return_value=SAMPLE_NOTES):
            results = search_vault(config, "ai", max_results=1)
        assert len(results) <= 1

    def test_empty_query_returns_all_up_to_max(self):
        """Single-char words are filtered; effectively empty query returns first max_results."""
        config = MagicMock()
        with patch("compound_agent.vault_search.scan_recent_notes", return_value=SAMPLE_NOTES):
            results = search_vault(config, "a", max_results=10)
        # "a" is len 1 so filtered — no keywords → return first max_results
        assert results == SAMPLE_NOTES[:10]

    def test_passes_days_to_scanner(self):
        config = MagicMock()
        with patch("compound_agent.vault_search.scan_recent_notes", return_value=[]) as mock_scan:
            search_vault(config, "test", days=60)
        mock_scan.assert_called_once_with(config, days=60)


# ---------------------------------------------------------------------------
# synthesize_answer tests
# ---------------------------------------------------------------------------

class TestSynthesizeAnswer:
    def test_returns_no_notes_message_when_empty(self):
        summarizer = MagicMock()
        result = synthesize_answer(summarizer, "어떤 AI 트렌드가 있나요?", [])
        assert result == "관련 노트를 찾지 못했습니다."
        summarizer._generate.assert_not_called()

    def test_calls_generate_with_query_and_note_context(self):
        summarizer = MagicMock()
        summarizer._generate.return_value = "LLM 기반 에이전트가 주요 트렌드입니다."
        result = synthesize_answer(summarizer, "AI 트렌드", SAMPLE_NOTES[:2])
        assert result == "LLM 기반 에이전트가 주요 트렌드입니다."
        prompt_used = summarizer._generate.call_args[0][0]
        assert "AI 트렌드" in prompt_used
        assert "LLM Agent Architecture" in prompt_used

    def test_includes_note_descriptions_in_prompt(self):
        summarizer = MagicMock()
        summarizer._generate.return_value = "답변"
        synthesize_answer(summarizer, "질문", SAMPLE_NOTES[:1])
        prompt_used = summarizer._generate.call_args[0][0]
        assert "How to build autonomous agents" in prompt_used

    def test_caps_notes_at_ten(self):
        """Only first 10 notes are included in the prompt."""
        summarizer = MagicMock()
        summarizer._generate.return_value = "답변"
        many_notes = [
            {"title": f"Note {i}", "description": f"Desc {i}"} for i in range(15)
        ]
        synthesize_answer(summarizer, "질문", many_notes)
        prompt_used = summarizer._generate.call_args[0][0]
        assert "Note 9" in prompt_used
        assert "Note 10" not in prompt_used


# ---------------------------------------------------------------------------
# TelegramHandler routing tests
# ---------------------------------------------------------------------------

class TestTelegramHandlerRouting:
    def _make_update(self, text, chat_id="123"):
        return {
            "update_id": 1,
            "message": {
                "chat": {"id": chat_id},
                "text": text,
            },
        }

    def test_url_routes_to_handle_urls(self):
        handler, config, brain, telegram, state = _make_handler()
        with patch.object(handler, "_handle_urls") as mock_urls, \
             patch.object(telegram, "get_updates", return_value=[self._make_update("https://example.com")]):
            handler.poll_and_process()
        mock_urls.assert_called_once_with(["https://example.com"])

    def test_plain_text_routes_to_handle_question(self):
        handler, config, brain, telegram, state = _make_handler()
        with patch.object(handler, "_handle_question") as mock_q, \
             patch.object(telegram, "get_updates", return_value=[self._make_update("AI 에이전트란?")]):
            handler.poll_and_process()
        mock_q.assert_called_once_with("AI 에이전트란?")

    def test_slash_command_routes_to_handle_command(self):
        handler, config, brain, telegram, state = _make_handler()
        with patch.object(handler, "_handle_command") as mock_cmd, \
             patch.object(telegram, "get_updates", return_value=[self._make_update("/status")]):
            handler.poll_and_process()
        mock_cmd.assert_called_once_with("/status")

    def test_wrong_chat_id_ignored(self):
        handler, config, brain, telegram, state = _make_handler()
        with patch.object(handler, "_handle_question") as mock_q, \
             patch.object(telegram, "get_updates", return_value=[self._make_update("질문", chat_id="999")]):
            handler.poll_and_process()
        mock_q.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_command tests
# ---------------------------------------------------------------------------

class TestHandleCommand:
    def test_status_command_sends_status(self):
        handler, config, brain, telegram, state = _make_handler()
        brain.memory = None
        with patch.object(handler, "_get_status_text", return_value="상태OK"):
            handler._handle_command("/status")
        telegram.send_message.assert_called_once_with("상태OK")

    def test_help_command_sends_help_text(self):
        handler, config, brain, telegram, state = _make_handler()
        handler._handle_command("/help")
        call_args = telegram.send_message.call_args[0][0]
        assert "/status" in call_args
        assert "/report" in call_args
        assert "/help" in call_args

    def test_report_command_calls_run_weekly_knowledge(self):
        handler, config, brain, telegram, state = _make_handler()
        brain.hands.run_weekly_knowledge.return_value = {"success": True}
        handler._handle_command("/report")
        brain.hands.run_weekly_knowledge.assert_called_once()

    def test_report_command_sends_failure_message_on_error(self):
        handler, config, brain, telegram, state = _make_handler()
        brain.hands.run_weekly_knowledge.side_effect = RuntimeError("boom")
        handler._handle_command("/report")
        calls = [c[0][0] for c in telegram.send_message.call_args_list]
        assert any("오류" in c or "❌" in c for c in calls)


# ---------------------------------------------------------------------------
# _handle_question tests
# ---------------------------------------------------------------------------

class TestHandleQuestion:
    def test_no_results_sends_not_found_message(self):
        handler, config, brain, telegram, state = _make_handler()
        with patch("compound_agent.vault_search.search_vault", return_value=[]):
            handler._handle_question("알 수 없는 질문")
        telegram.send_message.assert_called_once()
        assert "찾지 못했습니다" in telegram.send_message.call_args[0][0]

    def test_sends_answer_with_sources(self):
        handler, config, brain, telegram, state = _make_handler()
        with patch("compound_agent.vault_search.search_vault", return_value=SAMPLE_NOTES[:2]), \
             patch("compound_agent.vault_search.synthesize_answer", return_value="AI 에이전트는 LLM 기반입니다."):
            handler._handle_question("AI 에이전트란?")
        msg = telegram.send_message.call_args[0][0]
        assert "AI 에이전트는 LLM 기반입니다." in msg
        assert "참고 노트" in msg

    def test_exception_sends_error_message(self):
        handler, config, brain, telegram, state = _make_handler()
        with patch("compound_agent.vault_search.search_vault", side_effect=Exception("db error")):
            handler._handle_question("질문")
        msg = telegram.send_message.call_args[0][0]
        assert "❌" in msg
