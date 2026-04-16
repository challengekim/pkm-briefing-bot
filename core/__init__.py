"""Core modules for Compound Brain."""
from core.summarizer import Summarizer
from core.scanner import (
    scan_recent_notes, scan_all_notes, save_project_ideas,
    save_weekly_report, load_previous_weekly_reports,
    analyze_tag_connections, save_url_to_vault, save_thought_to_vault,
    _validate_url,
)
from core.composer import (
    compose_trend_digest, compose_weekly_knowledge,
    compose_linkedin_draft, compose_meta_review_telegram, escape_html,
)
from core.reviewer import collect_monthly_stats
from core.trends import fetch_all_trends
from core.telegram import TelegramSender, URL_RE
