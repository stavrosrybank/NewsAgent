"""Fetch and normalise RSS feeds from all configured sources."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
from dateutil import parser as dateutil_parser

from newsagent.config import (
    RSS_FEEDS,
    LOOKBACK_DAYS,
    MAX_ARTICLES_PER_SOURCE,
    USER_AGENT,
)

logger = logging.getLogger(__name__)


@dataclass
class Article:
    source: str
    title: str
    url: str
    summary: str          # stripped HTML, max 500 chars
    published: datetime   # UTC-aware
    position: int         # 0-based index within feed


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(entry) -> Optional[datetime]:
    """Try multiple feedparser date fields; return UTC-aware datetime or None."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, field, None)
        if value:
            try:
                dt = datetime(*value[:6], tzinfo=timezone.utc)
                return dt
            except Exception:
                pass

    # Fallback: try raw string fields
    for field in ("published", "updated"):
        raw = getattr(entry, field, None)
        if raw:
            try:
                dt = dateutil_parser.parse(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except Exception:
                pass

    return None


def _fetch_feed(feed_cfg: dict) -> tuple[list[Article], list[str]]:
    """Fetch a single RSS feed; try fallback URL on failure."""
    articles: list[Article] = []
    warnings: list[str] = []
    source = feed_cfg["source"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    for url_key in ("url", "fallback_url"):
        url = feed_cfg.get(url_key)
        if not url:
            continue
        try:
            feed = feedparser.parse(
                url,
                request_headers={"User-Agent": USER_AGENT},
                timeout=feed_cfg.get("timeout_secs", 15),
            )
            if feed.bozo and not feed.entries:
                raise ValueError(f"bozo feed: {feed.bozo_exception}")

            for pos, entry in enumerate(feed.entries[:MAX_ARTICLES_PER_SOURCE]):
                published = _parse_date(entry)
                if published is None:
                    # Default to now so the article isn't dropped silently
                    published = datetime.now(timezone.utc)

                if published < cutoff:
                    continue

                title = (entry.get("title") or "").strip()
                link = entry.get("link") or entry.get("id") or ""
                raw_summary = entry.get("summary") or entry.get("description") or ""
                summary = _strip_html(raw_summary)[:500]

                if not title or not link:
                    continue

                articles.append(
                    Article(
                        source=source,
                        title=title,
                        url=link,
                        summary=summary,
                        published=published,
                        position=pos,
                    )
                )

            logger.info("Fetched %d articles from %s (%s)", len(articles), source, url)
            return articles, warnings  # success — don't try fallback

        except Exception as exc:
            msg = f"{source} ({url}): {exc}"
            logger.warning("Feed fetch failed: %s", msg)
            warnings.append(f"Warning: could not fetch {source} feed — {exc}")
            # Loop to try fallback_url

    if not articles:
        warnings.append(f"Warning: all URLs for {source} failed; source skipped.")

    return articles, warnings


def fetch_all() -> tuple[list[Article], list[str]]:
    """
    Fetch all configured RSS feeds in parallel.

    Returns:
        (articles, warnings) — articles sorted newest-first, plus human-readable warnings.
    """
    all_articles: list[Article] = []
    all_warnings: list[str] = []

    with ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as executor:
        futures = {executor.submit(_fetch_feed, cfg): cfg for cfg in RSS_FEEDS}
        for future in as_completed(futures, timeout=20):
            try:
                articles, warnings = future.result()
                all_articles.extend(articles)
                all_warnings.extend(warnings)
            except Exception as exc:
                cfg = futures[future]
                msg = f"Unexpected error fetching {cfg['source']}: {exc}"
                logger.error(msg)
                all_warnings.append(f"Warning: {msg}")

    all_articles.sort(key=lambda a: a.published, reverse=True)
    logger.info("Total articles fetched: %d", len(all_articles))
    return all_articles, all_warnings
