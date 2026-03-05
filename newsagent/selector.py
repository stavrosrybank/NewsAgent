"""
Article selection via a single Claude call.
Replaces the cluster + score pipeline (clustering.py + scorer.py).
"""

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import anthropic

from newsagent.config import (
    CLAUDE_MODEL,
    CLAUDE_MAX_RETRIES,
    CLAUDE_RETRY_DELAYS,
    SELECTION_PROMPT_TEMPLATE,
    DIGEST_SLOTS,
    EDITORIAL_FOCUS,
)
from newsagent.fetcher import Article

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SelectedStory:
    """An article chosen for a specific category slot."""
    category: str
    article: Article
    rank: int


@dataclass
class CategoryError:
    """A category slot that could not be filled."""
    category: str
    reason: str


# ---------------------------------------------------------------------------
# Claude retry helper (shared — imported by summarizer.py)
# ---------------------------------------------------------------------------

def call_claude_with_retry(
    client: anthropic.Anthropic,
    *,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call Claude with exponential backoff on rate-limit / 5xx errors."""
    last_exc: Optional[Exception] = None

    for attempt in range(CLAUDE_MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except anthropic.RateLimitError as exc:
            last_exc = exc
            logger.warning("Rate limit hit (attempt %d/%d)", attempt + 1, CLAUDE_MAX_RETRIES)
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                last_exc = exc
                logger.warning(
                    "Server error %d (attempt %d/%d)", exc.status_code, attempt + 1, CLAUDE_MAX_RETRIES
                )
            else:
                raise
        except anthropic.APIConnectionError as exc:
            last_exc = exc
            logger.warning("Connection error (attempt %d/%d): %s", attempt + 1, CLAUDE_MAX_RETRIES, exc)

        if attempt < CLAUDE_MAX_RETRIES:
            delay = CLAUDE_RETRY_DELAYS[min(attempt, len(CLAUDE_RETRY_DELAYS) - 1)]
            logger.info("Retrying in %ds…", delay)
            time.sleep(delay)

    raise RuntimeError(f"Claude call failed after {CLAUDE_MAX_RETRIES} retries") from last_exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_articles(articles: list[Article]) -> str:
    return "\n".join(f"[{idx}] ({a.source}) {a.title}" for idx, a in enumerate(articles))


def _normalize_source(name: str) -> str:
    """Match a preferred_source name to the actual source name in RSS_FEEDS (case-insensitive)."""
    from newsagent.config import RSS_FEEDS
    name_lower = name.lower()
    for feed in RSS_FEEDS:
        if feed["source"].lower() == name_lower:
            return feed["source"]
    return name  # return as-is if no match (will be logged as unknown)


def _build_categories_text() -> str:
    lines = []
    for slot in DIGEST_SLOTS:
        cat = slot["category"]
        count = slot.get("count", 1)
        desc = slot.get("description", "")
        preferred = [_normalize_source(s) for s in slot.get("preferred_sources", [])]
        entry = f'- "{cat}" (count: {count})'
        if preferred:
            entry += f', preferred_sources: {", ".join(preferred)}'
        if desc:
            entry += f': {desc}'
        lines.append(entry)
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences Claude sometimes adds despite instructions."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```[a-z]*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)
    return clean.strip()


def _to_index_list(raw_val) -> Optional[list[int]]:
    """Normalise a selection value to a list of ints, or None if empty/null."""
    if raw_val is None:
        return None
    if isinstance(raw_val, int):
        return [raw_val]
    if isinstance(raw_val, list):
        return [v for v in raw_val if isinstance(v, int)]
    if isinstance(raw_val, dict):
        # {"indices": null, "reason": "..."} or {"index": 5}
        inner = raw_val.get("indices") or raw_val.get("index")
        if inner is None:
            return None
        return _to_index_list(inner)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_articles(
    articles: list[Article],
    client: anthropic.Anthropic,
) -> tuple[list[SelectedStory], list[CategoryError]]:
    """
    Single Claude call to select the best article(s) for each category slot.
    Returns (selected_stories_in_rank_order, category_errors).
    """
    if not articles:
        return [], [CategoryError(s["category"], "No articles fetched") for s in DIGEST_SLOTS]

    prompt = SELECTION_PROMPT_TEMPLATE.format(
        articles_text=_format_articles(articles),
        categories_text=_build_categories_text(),
        editorial_focus=EDITORIAL_FOCUS or "No specific editorial guidance.",
    )

    logger.info("Sending %d articles to Claude for category selection…", len(articles))
    raw = call_claude_with_retry(client, prompt=prompt, temperature=0.1, max_tokens=4096)

    try:
        data = json.loads(_strip_fences(raw))
        selections_map: dict = data["selections"]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Selection JSON parse failed: %s\nRaw:\n%s", exc, raw[:500])
        return [], [CategoryError(s["category"], "Claude parse error") for s in DIGEST_SLOTS]

    selected: list[SelectedStory] = []
    errors: list[CategoryError] = []
    used_indices: set[int] = set()
    rank = 1

    for slot in DIGEST_SLOTS:
        cat = slot["category"]
        count = slot.get("count", 1)
        raw_val = selections_map.get(cat)

        # Extract reason if Claude returned a null-with-reason dict
        reason = "No suitable article found"
        if isinstance(raw_val, dict):
            reason = raw_val.get("reason", reason)

        indices = _to_index_list(raw_val)

        if not indices:
            errors.append(CategoryError(cat, reason))
            continue

        filled = 0
        for idx in indices[:count]:
            if idx < 0 or idx >= len(articles):
                logger.warning("Category '%s': index %d out of range", cat, idx)
                continue
            if idx in used_indices:
                logger.warning("Category '%s': index %d already used", cat, idx)
                continue
            used_indices.add(idx)
            a = articles[idx]
            selected.append(SelectedStory(category=cat, article=a, rank=rank))
            logger.info("Category '%s' → [%d] (%s) %s", cat, idx, a.source, a.title[:70])
            rank += 1
            filled += 1

        if filled == 0:
            errors.append(CategoryError(cat, "Selected index was invalid or already used"))

    logger.info(
        "Selection complete: %d stories selected, %d category error(s)",
        len(selected), len(errors),
    )
    return selected, errors
