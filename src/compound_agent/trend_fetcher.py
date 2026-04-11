import logging

import defusedxml.ElementTree as ElementTree
import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 15


def _safe_get(url, **kwargs):
    try:
        resp = requests.get(url, timeout=_TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp
    except Exception as e:
        logger.error(f"Fetch failed [{url}]: {e}")
        return None


def fetch_hackernews(limit=15):
    """Fetch top stories from Hacker News API (no auth required)."""
    resp = _safe_get("https://hacker-news.firebaseio.com/v0/topstories.json")
    if not resp:
        return []

    story_ids = resp.json()[:limit]
    stories = []
    for sid in story_ids:
        r = _safe_get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
        if not r:
            continue
        item = r.json()
        if not item or item.get("type") != "story":
            continue
        stories.append({
            "title": item.get("title", ""),
            "url": item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
            "score": item.get("score", 0),
            "comments": item.get("descendants", 0),
            "source": "Hacker News",
        })
    return stories


def fetch_reddit_rss(subreddits, limit=10):
    """Fetch top posts from Reddit subreddits via RSS (no auth required)."""
    stories = []
    for sub in subreddits:
        resp = _safe_get(
            f"https://www.reddit.com/r/{sub}/top/.rss?t=day&limit={limit}",
            headers={"User-Agent": "productivity-bot/1.0"},
        )
        if not resp:
            continue
        try:
            root = ElementTree.fromstring(resp.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns)[:limit]:
                title = entry.findtext("atom:title", "", ns)
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                stories.append({
                    "title": title,
                    "url": link,
                    "score": 0,
                    "comments": 0,
                    "source": f"r/{sub}",
                })
        except Exception as e:
            logger.error(f"Reddit RSS parse error [{sub}]: {e}")
    return stories


def fetch_geeknews_rss(limit=10):
    """Fetch recent items from GeekNews Atom feed."""
    resp = _safe_get("https://news.hada.io/rss/news")
    if not resp:
        return []

    stories = []
    try:
        root = ElementTree.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns)[:limit]:
            title = entry.findtext("atom:title", "", ns)
            link_el = entry.find("atom:link[@rel='alternate']", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            stories.append({
                "title": title,
                "url": link,
                "score": 0,
                "comments": 0,
                "source": "GeekNews",
            })
    except Exception as e:
        logger.error(f"GeekNews RSS parse error: {e}")
    return stories


def fetch_all_trends(config):
    """Collect trends from all configured sources and deduplicate by title."""
    all_items = []

    all_items.extend(fetch_hackernews(limit=config.trend_hn_limit))
    all_items.extend(fetch_reddit_rss(
        config.trend_subreddits, limit=config.trend_reddit_limit,
    ))
    all_items.extend(fetch_geeknews_rss(limit=config.trend_geeknews_limit))

    # Deduplicate by normalized title
    seen = set()
    unique = []
    for item in all_items:
        key = item["title"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)

    logger.info(
        f"Trends collected: {len(unique)} unique from {len(all_items)} total"
    )
    return unique
