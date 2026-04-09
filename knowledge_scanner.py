import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def _parse_frontmatter(filepath):
    """Extract YAML frontmatter fields from a markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(4000)
    except Exception:
        return {}

    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    fields = {}
    for line in match.group(1).split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("\"'")
    return fields


def _category_from_path(filepath, vault_path):
    """Derive category from file path relative to vault."""
    rel = os.path.relpath(filepath, vault_path)
    parts = rel.split(os.sep)
    if len(parts) >= 3:
        return parts[-2]
    if len(parts) >= 2:
        return parts[-2]
    return "unknown"


def scan_recent_notes(config, days=7):
    """Scan Obsidian vault for notes saved in the last N days."""
    vault = config.vault_path
    cutoff = datetime.now(KST) - timedelta(days=days)
    notes = []

    for scan_path in config.knowledge_scan_paths:
        full_path = os.path.join(vault, scan_path)
        if not os.path.isdir(full_path):
            continue

        for filename in os.listdir(full_path):
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(full_path, filename)
            try:
                mtime = datetime.fromtimestamp(
                    os.path.getmtime(filepath), tz=KST
                )
            except Exception:
                continue

            if mtime < cutoff:
                continue

            fm = _parse_frontmatter(filepath)
            title = fm.get("title", filename.replace(".md", ""))
            description = fm.get("description", "")
            category = _category_from_path(filepath, vault)

            notes.append({
                "title": title,
                "description": description,
                "category": category,
                "saved": fm.get("saved", mtime.strftime("%Y-%m-%d")),
                "tags": fm.get("tags", ""),
                "source": fm.get("source", ""),
            })

    notes.sort(key=lambda n: n["saved"], reverse=True)
    logger.info(f"Knowledge scan: {len(notes)} notes in last {days} days")
    return notes


def save_project_ideas(vault_path, ideas_text, date_str, ideas_file="20_Projects/AI Ideas/project-ideas.md"):
    """Save structured project ideas extracted from weekly knowledge report."""
    ideas_dir = os.path.dirname(os.path.join(vault_path, ideas_file))
    os.makedirs(ideas_dir, exist_ok=True)
    filepath = os.path.join(vault_path, ideas_file)

    # Extract ideas section from the full report
    # Look for "프로젝트별 적용 가능한 인사이트" or "Actionable Insights by Project"
    ideas_section = ideas_text
    for marker in ["2. 프로젝트별", "2. Actionable"]:
        idx = ideas_text.find(marker)
        if idx != -1:
            # Find the next section (3.)
            next_idx = ideas_text.find("\n3.", idx)
            if next_idx != -1:
                ideas_section = ideas_text[idx:next_idx].strip()
            else:
                ideas_section = ideas_text[idx:].strip()
            break

    entry = f"\n\n## {date_str}\n\nstatus: proposed\n\n{ideas_section}\n"

    if os.path.exists(filepath):
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry)
    else:
        header = (
            "---\n"
            "title: Project Ideas\n"
            "description: AI-suggested project ideas from weekly knowledge reports\n"
            "type: reference\n"
            "tags: [project-ideas, compound-learning]\n"
            "---\n\n"
            "# Project Ideas\n\n"
            "Auto-extracted from weekly knowledge reports.\n"
            "Status: proposed → implemented | abandoned\n"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + entry)

    logger.info(f"Project ideas saved to {filepath}")


def save_weekly_report(vault_path, report_text, date_str):
    """Append weekly report to compound log (append-only, Managed Agents pattern)."""
    reports_dir = os.path.join(vault_path, "20_Projects", "Weekly Reports")
    os.makedirs(reports_dir, exist_ok=True)
    filepath = os.path.join(reports_dir, "compound-log.md")

    entry = f"\n\n---\n\n## Week of {date_str}\n\n{report_text}\n"

    if not os.path.exists(filepath):
        header = (
            "# Compound Learning Log\n\n"
            "Append-only log of weekly knowledge reports.\n"
            "Each week's analysis builds on previous weeks.\n"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + entry)
    else:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(entry)

    logger.info(f"Weekly report appended to {filepath}")
    return filepath


def load_previous_weekly_reports(vault_path, weeks=4):
    """Load the most recent N weeks from the compound log for compound learning."""
    filepath = os.path.join(vault_path, "20_Projects", "Weekly Reports", "compound-log.md")
    if not os.path.exists(filepath):
        return ""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return ""

    # Split by week separator and take the most recent N
    sections = content.split("\n---\n\n## Week of ")
    if len(sections) <= 1:
        return ""

    recent = sections[-weeks:]  # last N weeks
    result = "\n\n---\n\n".join(
        f"## Week of {s}" if not s.startswith("## Week of") else s
        for s in recent
    )
    # Limit total size to avoid blowing up the prompt
    return result[:6000]


def analyze_tag_connections(notes):
    """Find notes that share tags — real Zettelkasten-style connections."""
    from collections import defaultdict

    tag_to_notes = defaultdict(list)
    for note in notes:
        tags_str = note.get("tags", "").strip("[]")
        for tag in tags_str.split(","):
            tag = tag.strip().strip("'\"")
            if tag:
                tag_to_notes[tag].append(note["title"])

    # Find connections: notes sharing 2+ tags
    connections = []
    for i, n1 in enumerate(notes):
        tags1 = set(t.strip().strip("'\"") for t in n1.get("tags", "").strip("[]").split(",") if t.strip())
        for n2 in notes[i + 1:]:
            tags2 = set(t.strip().strip("'\"") for t in n2.get("tags", "").strip("[]").split(",") if t.strip())
            shared = tags1 & tags2
            if len(shared) >= 2:
                connections.append({
                    "note1": n1["title"],
                    "note2": n2["title"],
                    "shared_tags": list(shared),
                })

    # Top shared tags (tags appearing in 3+ notes)
    popular_tags = [(tag, titles) for tag, titles in tag_to_notes.items() if len(titles) >= 3]
    popular_tags.sort(key=lambda x: len(x[1]), reverse=True)

    return {
        "connections": connections[:10],
        "popular_tags": popular_tags[:5],
    }


def scan_all_notes(config):
    """Scan Obsidian vault for ALL notes (no date cutoff) for content drafting."""
    vault = config.vault_path
    notes = []

    for scan_path in config.knowledge_scan_paths:
        full_path = os.path.join(vault, scan_path)
        if not os.path.isdir(full_path):
            continue

        for filename in os.listdir(full_path):
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(full_path, filename)
            fm = _parse_frontmatter(filepath)
            title = fm.get("title", filename.replace(".md", ""))
            description = fm.get("description", "")
            category = _category_from_path(filepath, vault)

            notes.append({
                "title": title,
                "description": description,
                "category": category,
                "saved": fm.get("saved", ""),
                "tags": fm.get("tags", ""),
                "source": fm.get("source", ""),
                "applicable_when": fm.get("applicable_when", ""),
                "my_relevance": fm.get("my_relevance", ""),
            })

    notes.sort(key=lambda n: n.get("saved", ""), reverse=True)
    logger.info(f"Full vault scan: {len(notes)} total notes")
    return notes
