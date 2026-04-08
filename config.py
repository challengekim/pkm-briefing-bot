import logging
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class Config:
    def __init__(self, config_path=None):
        # Load YAML config (optional, with fallback)
        cfg = self._load_yaml(config_path or _DEFAULT_CONFIG_PATH)

        # Secrets from .env only
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.personal_gmail_refresh_token = os.getenv("PERSONAL_GMAIL_REFRESH_TOKEN", "")
        self.work_gmail_refresh_token = os.getenv("WORK_GMAIL_REFRESH_TOKEN", "")
        self.google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.personal_calendar_id = os.getenv("PERSONAL_CALENDAR_ID", "primary")
        self.work_calendar_id = os.getenv("WORK_CALENDAR_ID", "primary")

        # LLM
        llm = cfg.get("llm", {})
        self.llm_provider = llm.get("provider", "gemini")
        self.llm_model = llm.get("model", self._default_model(self.llm_provider))
        self.llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        self.llm_base_url = llm.get("base_url", self._default_base_url(self.llm_provider))

        # Language
        self.language = cfg.get("language", "ko")
        patterns = cfg.get("language_patterns", {})
        lang_defaults = {
            "ko": {
                "action_required": r"\*\*액션 필요\*\*:\s*(.+?)(?:\n|$)",
                "none_value": "없음",
            },
            "en": {
                "action_required": r"\*\*Action Required\*\*:\s*(.+?)(?:\n|$)",
                "none_value": "None",
            },
        }
        defaults = lang_defaults.get(self.language, lang_defaults["ko"])
        self.action_pattern = patterns.get("action_required", defaults["action_required"])
        self.none_value = patterns.get("none_value", defaults["none_value"])

        # Accounts
        accounts = cfg.get("accounts", {})
        personal = accounts.get("personal", {})
        work = accounts.get("work", {})
        self.personal_display_name = personal.get("display_name", "개인")
        self.work_display_name = work.get("display_name", "회사")
        self.personal_senders = personal.get("newsletter_senders", [])
        self.work_label = work.get("label", "국내외BD")
        self.work_skip_keywords = work.get("skip_keywords", [])

        # Projects
        projects_list = cfg.get("projects", [])
        self.project_context = self._build_project_context(projects_list)
        self.project_repos = {
            p["name"]: os.path.expanduser(p["repo_path"])
            for p in projects_list if p.get("repo_path")
        }

        # Vault
        vault = cfg.get("vault", {})
        vault_path = os.getenv("VAULT_PATH") or vault.get("path", "")
        self.vault_path = os.path.expanduser(vault_path) if vault_path else ""
        self.obsidian_vault_path = self.vault_path  # backward compat alias
        self.knowledge_scan_paths = vault.get("scan_paths", [])
        self.ideas_file = vault.get("ideas_file", "20_Projects/AI Ideas/project-ideas.md")

        # Notifications
        notifications = cfg.get("notifications", {})
        self.knowledge_email_to = notifications.get("email_to", "")

        # Trends
        trends = cfg.get("trends", {})
        self.trend_subreddits = trends.get("subreddits", ["artificial", "MachineLearning", "LocalLLaMA"])
        self.trend_hn_limit = trends.get("hn_limit", 15)
        self.trend_reddit_limit = trends.get("reddit_limit", 8)
        self.trend_geeknews_limit = trends.get("geeknews_limit", 10)

        # Schedule
        schedule = cfg.get("schedule", {})
        self.schedule_timezone = schedule.get("timezone", "Asia/Seoul")
        self.schedule = self._parse_schedules(schedule)

    def _load_yaml(self, path):
        path = Path(path)
        if not path.exists():
            logger.warning(
                f"Config file not found: {path}. Using .env-only mode. "
                "Run setup_wizard.py to create config.yaml"
            )
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in {path}: {e}. Using defaults.")
            return {}

    def _build_project_context(self, projects):
        if not projects:
            return ""
        prefix = "I am running the following projects:" if self.language == "en" else "나는 다음 프로젝트들을 운영 중이다:"
        lines = [prefix]
        for i, p in enumerate(projects, 1):
            desc = p.get("description", "")
            lines.append(f"{i}. {p['name']} - {desc}")
        return "\n".join(lines)

    def _parse_schedules(self, schedule_cfg):
        """Parse schedule config into APScheduler cron kwargs."""
        result = {}
        known_keys = {"timezone"}  # skip non-schedule keys

        for key, value in schedule_cfg.items():
            if key in known_keys or not isinstance(value, str):
                continue
            result[key] = self._parse_schedule_entry(value)
        return result

    @staticmethod
    def _parse_schedule_entry(value):
        """Parse 'HH:MM' or 'qualifier HH:MM' into APScheduler cron kwargs.

        Formats:
          '08:00'       -> daily at 08:00 -> {hour: 8, minute: 0}
          'fri 18:00'   -> weekly on Friday -> {day_of_week: 'fri', hour: 18, minute: 0}
          '1st 11:00'   -> monthly on 1st -> {day: 1, hour: 11, minute: 0}
        """
        parts = value.strip().split()
        if len(parts) == 2:
            qualifier, time_str = parts
        elif len(parts) == 1:
            qualifier, time_str = None, parts[0]
        else:
            raise ValueError(f"Invalid schedule format: {value}")

        hour, minute = map(int, time_str.split(":"))
        kwargs = {"hour": hour, "minute": minute}

        if qualifier:
            # Weekly (mon, tue, wed, thu, fri, sat, sun)
            weekdays = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
            if qualifier.lower() in weekdays:
                kwargs["day_of_week"] = qualifier.lower()
            # Monthly (1st, 2nd, ..., 28th)
            elif qualifier.rstrip("stndrh").isdigit():
                day = int(re.match(r"(\d+)", qualifier).group(1))
                kwargs["day"] = day

        return kwargs

    @staticmethod
    def _default_model(provider):
        return {
            "gemini": "gemini-2.5-flash",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-haiku-4-5-20251001",
            "openrouter": "google/gemini-2.5-flash-preview-05-20:free",
            "ollama": "llama3.1:8b",
        }.get(provider, "gemini-2.5-flash")

    @staticmethod
    def _default_base_url(provider):
        return {
            "openrouter": "https://openrouter.ai/api/v1",
            "ollama": "http://localhost:11434/v1",
        }.get(provider)
