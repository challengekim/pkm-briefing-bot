import logging
import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

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


def parse_project_ideas(vault_path, ideas_file="20_Projects/AI Ideas/project-ideas.md"):
    """Parse project ideas file into structured list.

    Returns list of dicts: {id, date, status, text, keywords}
    Keywords are auto-extracted from idea text (nouns/phrases after bullets).
    """
    filepath = os.path.join(vault_path, ideas_file)
    if not os.path.exists(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    ideas = []
    # Split by date sections (## YYYY-MM-DD or ## Week of ...)
    sections = re.split(r"(?=^## )", content, flags=re.MULTILINE)

    for section in sections:
        if not section.strip().startswith("## "):
            continue

        # Extract date from header
        header_match = re.match(r"## (.+)", section.strip())
        if not header_match:
            continue
        date_str = header_match.group(1).strip()

        # Extract status
        status_match = re.search(r"status:\s*(\w+)", section)
        status = status_match.group(1) if status_match else "proposed"

        # Extract bullet points as individual ideas
        bullets = re.findall(r"[-*]\s+(.+)", section)
        for i, bullet in enumerate(bullets):
            idea_id = f"{date_str}_{i}"
            keywords = _extract_keywords(bullet)
            ideas.append({
                "id": idea_id,
                "date": date_str,
                "status": status,
                "text": bullet.strip(),
                "keywords": keywords,
            })

    return ideas


def update_idea_status(vault_path, idea_id, new_status, project_name=None,
                       ideas_file="20_Projects/AI Ideas/project-ideas.md"):
    """Update status of an idea in the ideas file.

    Appends a metadata comment after the idea's date section header.
    """
    filepath = os.path.join(vault_path, ideas_file)
    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Find and update status line for the idea's date section
    date_part = idea_id.rsplit("_", 1)[0]
    pattern = rf"(## {re.escape(date_part)}.*?)(status:\s*)\w+"
    replacement = rf"\g<1>\g<2>{new_status}"
    updated = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)

    if updated != content:
        import tempfile
        parent = os.path.dirname(filepath)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(updated)
            os.replace(tmp_path, filepath)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.info("Updated idea %s status to %s", idea_id, new_status)


def _extract_keywords(text):
    """Extract likely keywords from idea text for git commit matching.

    Extracts capitalized terms, quoted terms, and technical terms (3+ chars).
    """
    keywords = set()

    # Quoted terms
    for match in re.findall(r'["\'](.+?)["\']', text):
        keywords.add(match.lower())

    # Capitalized multi-word terms (e.g., "RAG Pipeline", "Auth System")
    for match in re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", text):
        keywords.add(match.lower())

    # Technical terms: words with special chars or ALL CAPS
    for word in re.findall(r"\b[A-Z]{2,}\b", text):
        if len(word) >= 3:
            keywords.add(word.lower())

    # Hyphenated terms
    for match in re.findall(r"\b\w+-\w+(?:-\w+)*\b", text):
        if len(match) >= 5:
            keywords.add(match.lower())

    # Fallback: significant words (4+ chars, not common)
    stop_words = {"with", "from", "that", "this", "have", "will", "been", "more",
                  "into", "about", "than", "them", "some", "would", "could", "should",
                  "which", "their", "other", "using", "based", "what", "when", "your"}
    for word in re.findall(r"\b\w{4,}\b", text):
        lower = word.lower()
        if lower not in stop_words:
            keywords.add(lower)

    return list(keywords)[:10]  # Cap at 10 keywords


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


def _validate_url(url):
    """Block requests to internal/private networks (SSRF protection)."""
    import ipaddress
    import socket
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("No hostname in URL")
    blocked = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
    ]
    for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
        ip = ipaddress.ip_address(info[4][0])
        for net in blocked:
            if ip in net:
                raise ValueError(f"URL resolves to blocked network: {ip}")


def save_url_to_vault(url, vault_path, scan_paths, summarizer=None):
    """Save a URL to the vault as a markdown file with frontmatter.

    Uses requests + beautifulsoup4 to extract content.
    Optionally uses summarizer for AI-generated description.
    """
    _validate_url(url)

    # Fetch the page
    headers = {"User-Agent": "Mozilla/5.0 (compound-brain bot)"}
    resp = requests.get(url, headers=headers, timeout=15, allow_redirects=False)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract title
    title = ""
    if soup.title:
        title = soup.title.string.strip()
    if not title:
        title = urlparse(url).netloc

    # Extract main text content — remove non-content tags
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    body_text = soup.get_text(separator="\n", strip=True)
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)
    body_text = body_text[:10000]

    # Auto-detect category from URL domain and content
    domain = urlparse(url).netloc.lower()
    category = _detect_category(domain, title, body_text)

    # Generate description
    description = title
    if summarizer:
        try:
            desc_prompt = (
                f"Summarize this article in one sentence (under 100 chars):\n\n"
                f"Title: {title}\n\nContent: {body_text[:2000]}"
            )
            description = summarizer._generate(desc_prompt).strip()[:150]
        except Exception:
            pass

    # Generate tags
    tags = _detect_tags(domain, title, category)

    # Build filename
    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:60].strip()
    filename = f"{safe_title}.md"

    # Determine save path
    category_paths = {
        "ai-eng": "10_Knowledge/References/AI Engineering",
        "ai-tool": "10_Knowledge/References/AI Tools",
        "business": "10_Knowledge/References/Business",
        "engineering": "10_Knowledge/References/Engineering",
        "marketing": "10_Knowledge/References/Marketing",
    }
    rel_path = category_paths.get(category, "00_Inbox/Read Later")

    save_dir = os.path.join(vault_path, rel_path)
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, filename)

    # Write file
    now = datetime.now(KST)
    tags_str = ", ".join(tags)
    content = (
        f"---\n"
        f"source: {url}\n"
        f"title: \"{title}\"\n"
        f"description: \"{description}\"\n"
        f"saved: {now.strftime('%Y-%m-%d')}\n"
        f"type: article\n"
        f"tags: [{tags_str}]\n"
        f"status: pending\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"> Source: {url}\n\n"
        f"{body_text}\n"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Saved: {filepath}")
    return {"title": title, "path": filepath, "category": category}


def _detect_category(domain, title, body):
    """Simple keyword-based category detection."""
    text = f"{domain} {title} {body[:500]}".lower()
    if any(k in text for k in ["llm", "ai agent", "machine learning", "gpt", "claude", "gemini", "neural", "transformer"]):
        return "ai-eng"
    if any(k in text for k in ["ai tool", "saas", "app", "product", "tool"]):
        return "ai-tool"
    if any(k in text for k in ["marketing", "seo", "ads", "growth", "conversion"]):
        return "marketing"
    if any(k in text for k in ["startup", "business", "funding", "revenue", "company"]):
        return "business"
    if any(k in text for k in ["engineering", "devops", "infrastructure", "deploy", "ci/cd"]):
        return "engineering"
    return "ai-eng"  # default for tech content


def _detect_tags(domain, title, category):
    """Generate basic tags."""
    tags = [category.replace("-", "_") if category != "ai-eng" else "ai"]
    if "github.com" in domain:
        tags.append("open-source")
    if any(k in title.lower() for k in ["agent", "에이전트"]):
        tags.append("ai-agents")
    if any(k in title.lower() for k in ["claude", "anthropic"]):
        tags.append("claude-code")
    return tags
