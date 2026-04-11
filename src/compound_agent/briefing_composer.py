import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def escape_html(text):
    """Escape text for Telegram HTML parse mode. Handles &, <, > only (Telegram subset)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_to_html(text):
    """Convert markdown to HTML for email rendering."""
    import re
    if not text:
        return ""
    t = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Headers: ### → h4, ## → h3, # → h2
    t = re.sub(r"^### (.+)$", r'<h4 style="margin:16px 0 8px;font-size:15px;color:#374151;">\1</h4>', t, flags=re.MULTILINE)
    t = re.sub(r"^## (.+)$", r'<h3 style="margin:20px 0 8px;font-size:17px;color:#1e40af;">\1</h3>', t, flags=re.MULTILINE)
    t = re.sub(r"^# (.+)$", r'<h2 style="margin:24px 0 12px;font-size:20px;color:#1e3a5f;">\1</h2>', t, flags=re.MULTILINE)
    # Bold: **text**
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    # Italic: *text*
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    # Bullet lists: * item or - item
    t = re.sub(r"^[\*\-]\s+(.+)$", r'<li style="margin:2px 0;">\1</li>', t, flags=re.MULTILINE)
    # Wrap consecutive <li> in <ul>
    t = re.sub(r"((?:<li[^>]*>.*?</li>\n?)+)", r'<ul style="padding-left:20px;margin:8px 0;">\1</ul>', t)
    # Numbered lists: 1. item
    t = re.sub(r"^\d+\.\s+(.+)$", r'<li style="margin:2px 0;">\1</li>', t, flags=re.MULTILINE)
    # Horizontal rule: ---
    t = re.sub(r"^---+$", r'<hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">', t, flags=re.MULTILINE)
    # Line breaks for remaining plain lines
    t = re.sub(r"\n\n", r"<br><br>", t)
    return t


def _format_event_time(event):
    if event.get("all_day"):
        return "종일"
    start = event.get("start", "")
    if "T" in start:
        try:
            dt = datetime.fromisoformat(start)
            return dt.strftime("%H:%M")
        except (ValueError, TypeError):
            pass
    return start


def _format_event_line(event):
    time_str = _format_event_time(event)
    summary = escape_html(event.get("summary", ""))
    parts = [f"{time_str} {summary}"]
    location = event.get("location", "")
    if location:
        parts[0] += f" ({escape_html(location)})"
    meet_link = event.get("meet_link", "")
    if meet_link and not location:
        parts[0] += " (Google Meet)"
    return parts[0]


def _format_events_section(title, events_data):
    if not events_data:
        return ""
    events = events_data.get("events", [])
    total = events_data.get("total_count", len(events))
    if not events and total == 0:
        return ""

    lines = [f"\n<b>--- {escape_html(title)} ({total}건) ---</b>\n"]
    for event in events:
        lines.append(_format_event_line(event))
    if total > len(events):
        lines.append(f"  ... +{total - len(events)}건 더")
    return "\n".join(lines)


def _format_status_line(data_source_status):
    if all(data_source_status.values()):
        return ""
    parts = []
    for source, ok in data_source_status.items():
        parts.append(f"{source} {'OK' if ok else 'FAIL'}")
    return f"\n\n<i>[Data: {', '.join(parts)}]</i>"


def compose_morning(calendar_events, email_summaries, next_meeting,
                    meeting_prep, action_items, data_source_status):
    """Compose morning briefing HTML. email_summaries items must be pre-escaped HTML strings."""
    now = datetime.now(KST)
    weekday = WEEKDAY_KR[now.weekday()]
    parts = [f"<b>Morning Briefing — {now.strftime('%Y-%m-%d')} ({weekday})</b>"]

    # Calendar agenda
    if calendar_events:
        for label, events_data in calendar_events:
            section = _format_events_section(f"오늘 일정 - {label}", events_data)
            if section:
                parts.append(section)

    # Next meeting prep
    if next_meeting and meeting_prep:
        summary = escape_html(next_meeting.get("summary", ""))
        time_str = _format_event_time(next_meeting)
        attendees = next_meeting.get("attendees", [])
        attendees_str = ", ".join(attendees[:5])
        if len(attendees) > 5:
            attendees_str += f" 외 {len(attendees) - 5}명"

        prep_lines = [f"\n<b>--- 다음 미팅 준비 ---</b>\n"]
        prep_lines.append(f"<b>{summary}</b> ({time_str})")
        if attendees_str:
            prep_lines.append(f"참석: {escape_html(attendees_str)}")
        prep_lines.append(f"\n{escape_html(meeting_prep)}")
        parts.append("\n".join(prep_lines))

    # Email summaries
    for email_group in email_summaries:
        account = email_group.get("account", "")
        summaries = email_group.get("summaries", [])
        if not summaries:
            continue
        parts.append(f"\n<b>--- {escape_html(account)} ---</b>")
        for s in summaries:
            parts.append(s)

    # Action items
    if action_items:
        action_lines = ["\n<b>--- 액션 아이템 ---</b>\n"]
        for i, item in enumerate(action_items, 1):
            subj = escape_html(item.get("subject", ""))
            action = escape_html(item.get("action", ""))
            action_lines.append(f"{i}. <b>{subj}</b> — {action}")
        parts.append("\n".join(action_lines))

    # Status line
    parts.append(_format_status_line(data_source_status))

    return "\n".join(parts)


def compose_evening(email_summaries, tomorrow_events, data_source_status):
    """Compose evening review HTML. email_summaries items must be pre-escaped HTML strings."""
    now = datetime.now(KST)
    weekday = WEEKDAY_KR[now.weekday()]
    parts = [f"<b>Evening Review — {now.strftime('%Y-%m-%d')} ({weekday})</b>"]

    # Email summaries
    for email_group in email_summaries:
        account = email_group.get("account", "")
        summaries = email_group.get("summaries", [])
        if not summaries:
            continue
        parts.append(f"\n<b>--- {escape_html(account)} ---</b>")
        for s in summaries:
            parts.append(s)

    # Tomorrow's schedule
    if tomorrow_events:
        for label, events_data in tomorrow_events:
            section = _format_events_section(f"내일 일정 - {label}", events_data)
            if section:
                parts.append(section)

    # Status line
    parts.append(_format_status_line(data_source_status))

    return "\n".join(parts)


def compose_trend_digest(trend_summary, source_counts, data_source_status,
                         all_items=None):
    """Compose daily trend digest HTML."""
    now = datetime.now(KST)
    weekday = WEEKDAY_KR[now.weekday()]
    parts = [f"<b>Daily Tech Digest — {now.strftime('%Y-%m-%d')} ({weekday})</b>"]

    # Source stats
    source_line = " | ".join(
        f"{src} {cnt}건" for src, cnt in source_counts.items() if cnt > 0
    )
    if source_line:
        parts.append(f"\n<i>수집: {source_line}</i>")

    # Gemini summary (already formatted, no escape needed)
    if trend_summary:
        parts.append(f"\n{trend_summary}")

    # Remaining items grouped by source
    if all_items:
        parts.append(f"\n<b>--- 전체 수집 목록 ({len(all_items)}건) ---</b>")
        by_source = {}
        for item in all_items:
            src = item["source"]
            if src not in by_source:
                by_source[src] = []
            by_source[src].append(item)
        for src, items in by_source.items():
            parts.append(f"\n<i>{escape_html(src)}</i>")
            for item in items:
                title = escape_html(item.get("title_ko", item["title"])[:80])
                url = item.get("url", "")
                if url:
                    parts.append(f"• <a href=\"{url}\">{title}</a>")
                else:
                    parts.append(f"• {title}")

    parts.append(_format_status_line(data_source_status))
    return "\n".join(parts)


def compose_weekly_knowledge(knowledge_summary, notes, data_source_status):
    """Compose weekly knowledge compound learning report HTML."""
    now = datetime.now(KST)
    parts = [f"<b>Weekly Knowledge Report — {now.strftime('%Y-%m-%d')}</b>"]

    parts.append(f"\n<i>이번 주 저장된 노트: {len(notes)}건</i>")

    if knowledge_summary:
        parts.append(f"\n{knowledge_summary}")

    if notes:
        parts.append(f"\n<b>--- 이번 주 저장 목록 ---</b>")
        for n in notes:
            title = escape_html(n["title"][:60])
            cat = escape_html(n["category"])
            parts.append(f"• [{cat}] {title}")

    parts.append(_format_status_line(data_source_status))
    return "\n".join(parts)


def compose_weekly_knowledge_email(knowledge_summary, notes):
    """Compose weekly knowledge report as styled HTML email."""
    now = datetime.now(KST)
    weekday = WEEKDAY_KR[now.weekday()]

    note_rows = ""
    for n in notes:
        title = escape_html(n["title"][:70])
        cat = escape_html(n["category"])
        note_rows += f'<tr><td style="padding:4px 8px;color:#6b7280;">{cat}</td><td style="padding:4px 8px;">{title}</td></tr>\n'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;padding:20px;color:#1f2937;">
<div style="border-bottom:3px solid #2563eb;padding-bottom:12px;margin-bottom:24px;">
  <h1 style="margin:0;font-size:22px;color:#1e40af;">Weekly Knowledge Report</h1>
  <p style="margin:4px 0 0;color:#6b7280;font-size:14px;">{now.strftime('%Y-%m-%d')} ({weekday}) | {len(notes)}건 저장</p>
</div>

<div style="background:#f0f9ff;border-left:4px solid #2563eb;padding:16px;margin-bottom:24px;border-radius:0 8px 8px 0;line-height:1.7;">{_md_to_html(knowledge_summary or '(요약 없음)')}</div>

<h2 style="font-size:16px;color:#1e40af;border-bottom:1px solid #e5e7eb;padding-bottom:8px;">이번 주 저장 목록</h2>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
{note_rows}
</table>

<div style="margin-top:32px;padding-top:12px;border-top:1px solid #e5e7eb;color:#9ca3af;font-size:12px;">
  Productivity Bot — Compound Knowledge System
</div>
</body></html>"""


def compose_linkedin_draft(draft_text, note_count, has_trends, data_source_status):
    """Compose LinkedIn draft post for Telegram delivery."""
    now = datetime.now(KST)
    parts = [f"<b>LinkedIn Draft — {now.strftime('%Y-%m-%d')}</b>"]
    trend_label = "트렌드 포함" if has_trends else "트렌드 없음"
    parts.append(f"<i>참고 노트: {note_count}건 | {trend_label}</i>\n")

    if draft_text:
        parts.append(escape_html(draft_text))

    parts.append("\n<i>— 위 초안을 검토 후 링크드인에 게시하세요 —</i>")
    parts.append(_format_status_line(data_source_status))
    return "\n".join(parts)


def compose_meta_review_email(meta_summary, stats):
    """Compose monthly meta review as styled HTML email."""
    now = datetime.now(KST)

    cat_rows = ""
    for cat, cnt in stats["category_counts"].items():
        cat_rows += f'<tr><td style="padding:4px 8px;">{escape_html(cat)}</td><td style="padding:4px 8px;text-align:right;">{cnt}건</td></tr>\n'

    author_rows = ""
    for author, cnt in list(stats["author_counts"].items())[:8]:
        author_rows += f'<tr><td style="padding:4px 8px;">{escape_html(author[:30])}</td><td style="padding:4px 8px;text-align:right;">{cnt}건</td></tr>\n'

    commits_rows = ""
    for name, d in stats["project_commits"].items():
        commits_rows += f'<tr><td style="padding:4px 8px;">{escape_html(name)}</td><td style="padding:4px 8px;text-align:right;">{d["count"]}건</td></tr>\n'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:680px;margin:0 auto;padding:20px;color:#1f2937;">
<div style="border-bottom:3px solid #7c3aed;padding-bottom:12px;margin-bottom:24px;">
  <h1 style="margin:0;font-size:22px;color:#5b21b6;">Monthly Meta Review</h1>
  <p style="margin:4px 0 0;color:#6b7280;font-size:14px;">{now.strftime('%Y-%m-%d')} | 최근 {stats['period_days']}일 | {stats['total_notes']}건 저장</p>
</div>

<div style="background:#f5f3ff;border-left:4px solid #7c3aed;padding:16px;margin-bottom:24px;border-radius:0 8px 8px 0;line-height:1.7;">{_md_to_html(meta_summary or '(분석 없음)')}</div>

<div style="display:flex;gap:16px;margin-bottom:24px;">
<div style="flex:1;">
<h3 style="font-size:14px;color:#5b21b6;margin-bottom:8px;">카테고리 분포</h3>
<table style="width:100%;border-collapse:collapse;font-size:13px;">{cat_rows}</table>
</div>
<div style="flex:1;">
<h3 style="font-size:14px;color:#5b21b6;margin-bottom:8px;">자주 저장하는 소스</h3>
<table style="width:100%;border-collapse:collapse;font-size:13px;">{author_rows}</table>
</div>
</div>

<h3 style="font-size:14px;color:#5b21b6;margin-bottom:8px;">프로젝트 활동 (git commits)</h3>
<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px;">{commits_rows}</table>

<div style="margin-top:32px;padding-top:12px;border-top:1px solid #e5e7eb;color:#9ca3af;font-size:12px;">
  Productivity Bot — Compound Knowledge System (Meta Review)
</div>
</body></html>"""


def compose_meta_review_telegram(meta_summary, stats):
    """Compose monthly meta review for Telegram."""
    now = datetime.now(KST)
    parts = [f"<b>Monthly Meta Review — {now.strftime('%Y-%m-%d')}</b>"]
    parts.append(f"\n<i>최근 {stats['period_days']}일 | {stats['total_notes']}건 저장</i>")

    if meta_summary:
        parts.append(f"\n{meta_summary}")

    cat_line = " | ".join(f"{c} {n}건" for c, n in list(stats["category_counts"].items())[:6])
    if cat_line:
        parts.append(f"\n<b>카테고리:</b> {cat_line}")

    commits_line = " | ".join(f"{n} {d['count']}건" for n, d in stats["project_commits"].items())
    if commits_line:
        parts.append(f"<b>커밋:</b> {commits_line}")

    return "\n".join(parts)


def compose_focused_analysis(topic: str, summary: str, notes: list) -> str:
    """Compose a focused topic analysis message for Telegram.

    Args:
        topic: Category/topic name (e.g., "AI Engineering")
        summary: LLM-generated analysis text
        notes: List of note dicts with 'title' and optionally 'source'

    Returns: HTML string for Telegram
    """
    parts = [f"🔍 <b>{escape_html(topic)} — 집중 분석</b>"]

    if summary:
        parts.append(f"\n{_md_to_html(summary)}")

    if notes:
        parts.append(f"\n📎 관련 노트 ({len(notes)}개):")
        for note in notes:
            title = escape_html(note.get("title", ""))
            parts.append(f"• {title}")

    return "\n".join(parts)


def compose_article_suggestions(suggestions: str, weak_categories: list) -> str:
    """Compose article suggestion message when knowledge report is skipped.

    Args:
        suggestions: LLM-generated suggestion text
        weak_categories: List of category names that are under-represented

    Returns: HTML string for Telegram
    """
    parts = ["💡 <b>이번 주 추천 읽을거리</b>"]

    if weak_categories:
        cats = ", ".join(escape_html(c) for c in weak_categories)
        parts.append(f"\n보강이 필요한 분야: {cats}")

    if suggestions:
        parts.append(f"\n{_md_to_html(suggestions)}")

    return "\n".join(parts)


def compose_skip_notification(reason: str, alternative: str = None) -> str:
    """Compose a skip notification message.

    Args:
        reason: Why the action was skipped
        alternative: Optional suggestion for what to do instead

    Returns: HTML string for Telegram
    """
    parts = ["⏭️ <b>작업 건너뜀</b>", f"\n{escape_html(reason)}"]

    if alternative:
        parts.append(f"\n💡 대신: {escape_html(alternative)}")

    return "\n".join(parts)


def compose_contextual_save(title: str, category: str, related_notes: list,
                            topic_count: int, is_trigger: bool = False) -> str:
    """Compose context-aware URL save response for Telegram.

    Args:
        title: Saved article title
        category: Detected category
        related_notes: List of related note dicts with 'title'
        topic_count: How many articles in this category this week
        is_trigger: Whether this triggers a focused analysis (3+ saves)

    Returns: HTML string for Telegram
    """
    parts = [
        f'✓ "{escape_html(title)}"',
        f"→ {escape_html(category)} (이번 주 {topic_count}개 저장)",
    ]

    if related_notes:
        parts.append("\n🔗 볼트의 관련 글:")
        for note in related_notes:
            note_title = escape_html(note.get("title", ""))
            parts.append(f'• "{note_title}"')

    if is_trigger:
        parts.append(f"\n💡 같은 주제 기사가 {topic_count}개 모였습니다 — 집중 분석을 진행할까요?")

    return "\n".join(parts)


def compose_proactive_suggestion(suggestion_type: str, content: str, category: str = None) -> str:
    """Format a proactive suggestion message."""
    header_map = {
        "suggest_articles": "💡 맞춤 추천",
        "suggest_trending": "🔥 관심 트렌드",
        "suggest_linkedin": "✍️ LinkedIn 주제 추천",
    }
    header = header_map.get(suggestion_type, "💡 추천")

    parts = [f"<b>{header}</b>"]
    if category:
        parts.append(f"<i>카테고리: {escape_html(category)}</i>")
    parts.append("")
    parts.append(escape_html(content))

    return "\n".join(parts)


def compose_weekly(week_meetings, email_stats, next_week_events,
                   weekly_summary, data_source_status):
    now = datetime.now(KST)
    parts = [f"<b>Weekly Digest — {now.strftime('%Y-%m-%d')}</b>"]

    # This week's meetings
    if week_meetings:
        total = 0
        for label, events_data in week_meetings:
            count = events_data.get("total_count", 0)
            total += count
        parts.append(f"\n<b>--- 이번 주 미팅 ({total}건) ---</b>")
        for label, events_data in week_meetings:
            events = events_data.get("events", [])
            if events:
                parts.append(f"\n<i>{escape_html(label)}</i>")
                for event in events[:5]:
                    parts.append(_format_event_line(event))
                remaining = events_data.get("total_count", 0) - 5
                if remaining > 0:
                    parts.append(f"  ... +{remaining}건 더")

    # Email stats
    personal = email_stats.get("personal", 0)
    work = email_stats.get("work", 0)
    if personal or work:
        parts.append(f"\n<b>--- 이메일 처리 통계 ---</b>")
        parts.append(f"개인: {personal}건 | 회사: {work}건 | 합계: {personal + work}건")

    # Next week preview
    if next_week_events:
        for label, events_data in next_week_events:
            section = _format_events_section(f"다음 주 일정 - {label}", events_data)
            if section:
                parts.append(section)

    # Gemini weekly summary
    if weekly_summary:
        parts.append(f"\n<b>--- 주간 리뷰 ---</b>\n")
        parts.append(escape_html(weekly_summary))

    # Status line
    parts.append(_format_status_line(data_source_status))

    return "\n".join(parts)
