"""
Generate narrative summaries for each top story via parallel Claude calls.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import markdown as md_lib
import anthropic

from newsagent.clustering import call_claude_with_retry
from newsagent.config import SUMMARIZATION_PROMPT_TEMPLATE
from newsagent.fetcher import Article
from newsagent.scorer import ScoredCluster

logger = logging.getLogger(__name__)

_MAX_SUMMARY_WORKERS = 5


@dataclass
class DigestStory:
    rank: int
    theme: str
    sources: list[str]
    source_count: int
    final_score: float
    body_html: str              # narrative paragraphs as HTML
    key_fact: str               # extracted KEY FACT line (plain text)
    articles: list[Article]     # for "read more" links
    claude_reasoning: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_articles_for_summary(articles: list[Article]) -> str:
    lines = []
    for a in articles:
        lines.append(f"Source: {a.source}")
        lines.append(f"Title: {a.title}")
        if a.summary:
            lines.append(f"Summary: {a.summary}")
        lines.append("")
    return "\n".join(lines)


def _parse_key_fact(text: str) -> tuple[str, str]:
    """
    Split Claude's response into (narrative, key_fact).
    Returns (full text, '') if KEY FACT line is not found.
    """
    marker = "KEY FACT:"
    idx = text.upper().find(marker)
    if idx == -1:
        return text.strip(), ""
    narrative = text[:idx].strip()
    key_fact = text[idx + len(marker):].strip().lstrip("*_").rstrip("*_")
    return narrative, key_fact


def _markdown_to_html(text: str) -> str:
    return md_lib.markdown(text, extensions=["nl2br"])


def _fallback_body(cluster: ScoredCluster) -> tuple[str, str]:
    """Generate minimal fallback body when Claude summarisation fails."""
    parts = [f"<p><strong>{cluster.theme}</strong></p>"]
    for a in cluster.articles[:3]:
        snippet = a.summary[:300] if a.summary else a.title
        parts.append(f"<p><em>{a.source}:</em> {snippet}</p>")
    return "\n".join(parts), ""


# ---------------------------------------------------------------------------
# Single-story summariser
# ---------------------------------------------------------------------------

def _summarise_one(
    rank: int,
    cluster: ScoredCluster,
    client: anthropic.Anthropic,
) -> DigestStory:
    articles_text = _format_articles_for_summary(cluster.articles)
    prompt = SUMMARIZATION_PROMPT_TEMPLATE.format(
        theme=cluster.theme,
        articles_text=articles_text,
    )

    try:
        raw = call_claude_with_retry(
            client,
            prompt=prompt,
            temperature=0.5,
            max_tokens=800,
        )
        narrative_md, key_fact = _parse_key_fact(raw)
        body_html = _markdown_to_html(narrative_md)
    except Exception as exc:
        logger.warning("Summarisation failed for cluster %d '%s': %s", cluster.cluster_id, cluster.theme, exc)
        body_html, key_fact = _fallback_body(cluster)

    return DigestStory(
        rank=rank,
        theme=cluster.theme,
        sources=cluster.sources,
        source_count=cluster.source_count,
        final_score=cluster.final_score,
        body_html=body_html,
        key_fact=key_fact,
        articles=cluster.articles,
        claude_reasoning=cluster.claude_reasoning,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarise_top_stories(
    top_clusters: list[ScoredCluster],
    client: anthropic.Anthropic,
) -> list[DigestStory]:
    """
    Summarise each top cluster in parallel (max 5 concurrent Claude calls).
    Returns DigestStory list in rank order.
    """
    stories: list[DigestStory] = [None] * len(top_clusters)  # type: ignore[list-item]

    with ThreadPoolExecutor(max_workers=_MAX_SUMMARY_WORKERS) as executor:
        futures = {
            executor.submit(_summarise_one, rank + 1, cluster, client): rank
            for rank, cluster in enumerate(top_clusters)
        }
        for future in as_completed(futures):
            rank = futures[future]
            try:
                stories[rank] = future.result()
                logger.info("Summarised story #%d: %s", rank + 1, top_clusters[rank].theme)
            except Exception as exc:
                logger.error("Fatal error summarising story #%d: %s", rank + 1, exc)
                cluster = top_clusters[rank]
                body_html, key_fact = _fallback_body(cluster)
                stories[rank] = DigestStory(
                    rank=rank + 1,
                    theme=cluster.theme,
                    sources=cluster.sources,
                    source_count=cluster.source_count,
                    final_score=cluster.final_score,
                    body_html=body_html,
                    key_fact=key_fact,
                    articles=cluster.articles,
                )

    return [s for s in stories if s is not None]
