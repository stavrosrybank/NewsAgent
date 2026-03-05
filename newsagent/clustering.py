"""
Cluster articles into story groups and get Claude editorial scores.

Claude Call 1 — Cluster all articles into thematic groups.
Claude Call 2 — Score each cluster for newsworthiness.
"""

import json
import logging
import re
import time
from typing import Optional

import anthropic

from newsagent.config import (
    CLAUDE_MODEL,
    CLAUDE_MAX_RETRIES,
    CLAUDE_RETRY_DELAYS,
    CLUSTERING_PROMPT_TEMPLATE,
    SCORING_PROMPT_TEMPLATE,
    EDITORIAL_FOCUS,
    FEEDBACK_TEXT,
    NUM_SOURCES,
)
from newsagent.fetcher import Article
from newsagent.scorer import Cluster

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry helper
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
                logger.warning("Server error %d (attempt %d/%d)", exc.status_code, attempt + 1, CLAUDE_MAX_RETRIES)
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
# Jaccard fallback clusterer
# ---------------------------------------------------------------------------

def _tokenise(title: str) -> set[str]:
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "of", "and", "or",
                 "for", "is", "are", "was", "were", "be", "been", "as", "with",
                 "it", "its", "by", "from", "that", "this", "has", "have",
                 "had", "not", "but", "he", "she", "they", "we", "you"}
    tokens = re.findall(r"\b[a-z]+\b", title.lower())
    return {t for t in tokens if t not in stopwords and len(t) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _jaccard_cluster(articles: list[Article], threshold: float = 0.2) -> list[Cluster]:
    """Greedy Jaccard title-overlap clustering as JSON-parse fallback."""
    token_sets = [_tokenise(a.title) for a in articles]
    assigned = [-1] * len(articles)
    clusters: list[list[int]] = []

    for i in range(len(articles)):
        best_cluster = -1
        best_score = threshold
        for ci, c_indices in enumerate(clusters):
            score = max(_jaccard(token_sets[i], token_sets[j]) for j in c_indices)
            if score > best_score:
                best_score = score
                best_cluster = ci
        if best_cluster == -1:
            clusters.append([i])
            assigned[i] = len(clusters) - 1
        else:
            clusters[best_cluster].append(i)
            assigned[i] = best_cluster

    result: list[Cluster] = []
    for ci, indices in enumerate(clusters):
        cluster_articles = [articles[i] for i in indices]
        theme = cluster_articles[0].title[:80]
        result.append(Cluster(cluster_id=ci + 1, theme=theme, articles=cluster_articles))

    logger.info("Jaccard fallback produced %d clusters", len(result))
    return result


# ---------------------------------------------------------------------------
# Claude Call 1 — Cluster
# ---------------------------------------------------------------------------

def _format_articles_for_prompt(articles: list[Article]) -> str:
    # Titles only — keeps the clustering prompt short even with 300+ articles
    return "\n".join(f"[{idx}] ({a.source}) {a.title}" for idx, a in enumerate(articles))


def cluster_articles(
    articles: list[Article],
    client: anthropic.Anthropic,
) -> list[Cluster]:
    """
    Call Claude to cluster articles into thematic groups.
    Falls back to Jaccard heuristic if JSON parsing fails.
    """
    articles_text = _format_articles_for_prompt(articles)
    prompt = CLUSTERING_PROMPT_TEMPLATE.format(articles_text=articles_text)

    logger.info("Sending %d articles to Claude for clustering…", len(articles))
    raw = call_claude_with_retry(
        client,
        prompt=prompt,
        temperature=0.2,
        max_tokens=8192,
    )

    try:
        data = json.loads(raw)
        raw_clusters = data["clusters"]
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Claude clustering JSON parse failed: %s\nRaw response:\n%s", exc, raw[:500])
        return _jaccard_cluster(articles)

    clusters: list[Cluster] = []
    for rc in raw_clusters:
        indices = rc.get("article_indices", [])
        cluster_articles_list = []
        for i in indices:
            if 0 <= i < len(articles):
                cluster_articles_list.append(articles[i])
        if cluster_articles_list:
            clusters.append(
                Cluster(
                    cluster_id=rc["cluster_id"],
                    theme=rc.get("theme", "Unknown"),
                    articles=cluster_articles_list,
                )
            )

    logger.info("Claude produced %d clusters", len(clusters))
    return clusters


# ---------------------------------------------------------------------------
# Claude Call 2 — Score
# ---------------------------------------------------------------------------

def _format_clusters_for_scoring(clusters: list[Cluster]) -> str:
    lines = []
    for c in clusters:
        sources = list({a.source for a in c.articles})
        lines.append(
            f"Cluster {c.cluster_id}: {c.theme} | Sources: {', '.join(sources)} ({len(sources)}/{NUM_SOURCES})"
        )
    return "\n".join(lines)


def score_clusters_with_claude(
    clusters: list[Cluster],
    client: anthropic.Anthropic,
    previous_themes: Optional[list[str]] = None,
) -> list[Cluster]:
    """
    Call Claude to assign editorial newsworthiness scores and categories to each cluster.
    Mutates cluster.claude_score, cluster.claude_reasoning, and cluster.category in place.
    Returns the same list.
    """
    clusters_text = _format_clusters_for_scoring(clusters)

    if previous_themes:
        memory_text = "\n".join(f"- {t}" for t in previous_themes)
    else:
        memory_text = "No previous digest history available."

    prompt = SCORING_PROMPT_TEMPLATE.format(
        clusters_text=clusters_text,
        editorial_focus=EDITORIAL_FOCUS or "No specific editorial preferences set.",
        feedback_text=FEEDBACK_TEXT,
        memory_text=memory_text,
    )

    logger.info("Sending %d clusters to Claude for scoring…", len(clusters))
    raw = call_claude_with_retry(
        client,
        prompt=prompt,
        temperature=0.2,
        max_tokens=4096,
    )

    try:
        data = json.loads(raw)
        scores_map = {s["cluster_id"]: s for s in data["scores"]}
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("Claude scoring JSON parse failed: %s\nRaw:\n%s", exc, raw[:500])
        for c in clusters:
            c.claude_score = 5.0
            c.claude_reasoning = "Score unavailable (parse error)"
        return clusters

    for c in clusters:
        entry = scores_map.get(c.cluster_id)
        if entry:
            c.claude_score = float(entry.get("score", 5.0))
            c.claude_reasoning = entry.get("reasoning", "")
            c.category = entry.get("category", "Wild Card")
        else:
            c.claude_score = 5.0
            c.claude_reasoning = "No score returned by Claude"

    return clusters
