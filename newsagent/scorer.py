"""Pure Python weighted scoring formula. No API calls."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from newsagent.config import (
    WEIGHT_SOURCE_COUNT,
    WEIGHT_CLAUDE_SCORE,
    WEIGHT_RECENCY,
    TOP_N_STORIES,
)
from newsagent.fetcher import Article

logger = logging.getLogger(__name__)


@dataclass
class Cluster:
    """Raw cluster as returned by clustering.py."""
    cluster_id: int
    theme: str
    articles: list[Article]
    claude_score: float = 0.0
    claude_reasoning: str = ""


@dataclass
class ScoredCluster:
    cluster_id: int
    theme: str
    articles: list[Article]
    source_count: int
    claude_score: float
    claude_reasoning: str
    recency_score: float
    final_score: float
    sources: list[str] = field(default_factory=list)


def _recency_score(articles: list[Article]) -> float:
    """Return max recency score (0–1) based on the newest article in the cluster."""
    if not articles:
        return 0.0
    now = datetime.now(timezone.utc)
    newest = max(a.published for a in articles)
    age_days = (now - newest).total_seconds() / 86400
    return max(0.0, 1.0 - age_days / 7.0)


def score_clusters(clusters: list[Cluster]) -> list[ScoredCluster]:
    """
    Apply weighted scoring formula to each cluster and return sorted list.

    final = 0.50 * (source_count / 4)
          + 0.35 * (claude_score / 10)
          + 0.15 * max(0, 1 - age_days/7)
    """
    scored: list[ScoredCluster] = []

    for cluster in clusters:
        sources = list({a.source for a in cluster.articles})
        source_count = len(sources)
        recency = _recency_score(cluster.articles)

        final = (
            WEIGHT_SOURCE_COUNT * (source_count / 4.0)
            + WEIGHT_CLAUDE_SCORE * (cluster.claude_score / 10.0)
            + WEIGHT_RECENCY * recency
        )

        scored.append(
            ScoredCluster(
                cluster_id=cluster.cluster_id,
                theme=cluster.theme,
                articles=cluster.articles,
                source_count=source_count,
                claude_score=cluster.claude_score,
                claude_reasoning=cluster.claude_reasoning,
                recency_score=recency,
                final_score=final,
                sources=sources,
            )
        )
        logger.debug(
            "Cluster %d '%s': sources=%d claude=%.1f recency=%.2f final=%.3f",
            cluster.cluster_id,
            cluster.theme,
            source_count,
            cluster.claude_score,
            recency,
            final,
        )

    scored.sort(key=lambda c: c.final_score, reverse=True)
    return scored[:TOP_N_STORIES]
