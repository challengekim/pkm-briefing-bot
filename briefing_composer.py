import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def escape_html(text):
    """Escape text for Telegram HTML parse mode. Handles &, <, > only (Telegram subset)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_status_line(data_source_status):
    if all(data_source_status.values()):
        return ""
    parts = []
    for source, ok in data_source_status.items():
        parts.append(f"{source} {'OK' if ok else 'FAIL'}")
    return f"\n\n<i>[Data: {', '.join(parts)}]</i>"


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
