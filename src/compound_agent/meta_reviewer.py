import logging
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .knowledge_scanner import _parse_frontmatter, _category_from_path

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def _git_commits_since(repo_path, days=30):
    """Get commit messages from a git repo in the last N days."""
    since = (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--oneline", "--no-merges"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    except Exception as e:
        logger.error(f"Git log failed for {repo_path}: {e}")
    return []


def collect_monthly_stats(config, days=30):
    """Collect comprehensive stats for the monthly meta review."""
    vault = config.vault_path
    cutoff = datetime.now(KST) - timedelta(days=days)

    # 1. Scan all notes from last 30 days
    all_notes = []
    for scan_path in config.knowledge_scan_paths:
        full_path = os.path.join(vault, scan_path)
        if not os.path.isdir(full_path):
            continue
        for filename in os.listdir(full_path):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(full_path, filename)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(filepath), tz=KST)
            except Exception:
                continue
            if mtime < cutoff:
                continue
            fm = _parse_frontmatter(filepath)
            all_notes.append({
                "title": fm.get("title", filename.replace(".md", "")),
                "category": _category_from_path(filepath, vault),
                "tags": fm.get("tags", ""),
                "source": fm.get("source", ""),
                "author": fm.get("author", ""),
                "saved": fm.get("saved", mtime.strftime("%Y-%m-%d")),
            })

    # 2. Category distribution
    category_counts = Counter(n["category"] for n in all_notes)

    # 3. Source/author frequency (who do we save from most?)
    author_counts = Counter(
        n["author"] for n in all_notes if n["author"]
    )

    # 4. Tag frequency
    tag_counts = Counter()
    for n in all_notes:
        tags_str = n["tags"].strip("[]")
        for tag in tags_str.split(","):
            tag = tag.strip().strip("'\"")
            if tag:
                tag_counts[tag] += 1

    # 5. Git commits per project (to check idea→implementation flow)
    project_commits = {}
    for name, repo in getattr(config, "project_repos", {}).items():
        if os.path.isdir(repo):
            commits = _git_commits_since(repo, days)
            project_commits[name] = {
                "count": len(commits),
                "recent": commits[:10],
            }

    # 6. Read project ideas file to check what was suggested
    ideas_file = os.path.join(vault, getattr(config, "ideas_file", "20_Projects/AI Ideas/project-ideas.md"))
    ideas_content = ""
    if os.path.exists(ideas_file):
        try:
            with open(ideas_file, "r", encoding="utf-8") as f:
                ideas_content = f.read()[-3000:]  # last 3000 chars
        except Exception:
            pass

    return {
        "total_notes": len(all_notes),
        "notes": all_notes,
        "category_counts": dict(category_counts.most_common()),
        "author_counts": dict(author_counts.most_common(10)),
        "tag_counts": dict(tag_counts.most_common(15)),
        "project_commits": project_commits,
        "ideas_content": ideas_content,
        "period_days": days,
    }
