"""Pure Python weighted scoring formula. No API calls."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from newsagent.config import (
    WEIGHT_SOURCE_COUNT,
    WEIGHT_CLAUDE_SCORE,
    WEIGHT_RECENCY,
    TOP_N_STORIES,
    NUM_SOURCES,
    DIGEST_SLOTS,
)
from newsagent.fetcher import Article

logger = logging.getLogger(__name__)

# Broad categories that should be filled LAST so regional/specialized slots
# get first pick of all available clusters.
_BROAD_CATEGORIES = {"Global Geopolitical", "Wild Card"}

# Sources that are exclusively regional — used as fallback when Claude
# assigns a regional article to a generic category.
_SOURCE_CATEGORY_FALLBACK: dict[str, str] = {
    "BerlinerZeitung": "Germany/Berlin",
    "DeutscheWelle":   "Germany/Berlin",
    "SvD":             "Sweden",
    "GreeceReuters":   "Greece",
}


def _has_regional_source(cluster: "ScoredCluster", category: str) -> bool:
    target = {src for src, cat in _SOURCE_CATEGORY_FALLBACK.items() if cat == category}
    return any(a.source in target for a in cluster.articles)


@dataclass
class Cluster:
    """Raw cluster as returned by clustering.py."""
    cluster_id: int
    theme: str
    articles: list[Article]
    claude_score: float = 0.0
    claude_reasoning: str = ""
    category: str = "Wild Card"


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
    category: str = "Wild Card"
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

    final = 0.50 * (source_count / NUM_SOURCES)
          + 0.35 * (claude_score / 10)
          + 0.15 * max(0, 1 - age_days/7)

    If DIGEST_SLOTS are configured, fills category slots first, then Wild Card.
    """
    scored: list[ScoredCluster] = []

    for cluster in clusters:
        sources = list({a.source for a in cluster.articles})
        source_count = len(sources)
        recency = _recency_score(cluster.articles)

        final = (
            WEIGHT_SOURCE_COUNT * (source_count / NUM_SOURCES)
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
                category=cluster.category,
                sources=sources,
            )
        )
        logger.debug(
            "Cluster %d '%s': sources=%d claude=%.1f recency=%.2f final=%.3f cat=%s",
            cluster.cluster_id,
            cluster.theme,
            source_count,
            cluster.claude_score,
            recency,
            final,
            cluster.category,
        )

    scored.sort(key=lambda c: c.final_score, reverse=True)

    if not DIGEST_SLOTS:
        return scored[:TOP_N_STORIES]

    # --- Category-based slot filling ---
    selected: list[ScoredCluster] = []
    selected_ids: set[int] = set()

    # Pass 1: fill all non-Wild Card category slots — narrow/regional first
    for slot in sorted(DIGEST_SLOTS, key=lambda s: (1 if s["category"] in _BROAD_CATEGORIES else 0)):
        cat = slot["category"]
        count = slot.get("count", 1)
        if cat == "Wild Card":
            continue

        filled = 0
        for cluster in scored:
            if filled >= count:
                break
            if cluster.cluster_id not in selected_ids and cluster.category == cat:
                selected.append(cluster)
                selected_ids.add(cluster.cluster_id)
                filled += 1
                logger.info("Category slot '%s': '%s'", cat, cluster.theme)

        # Fallback: if Claude didn't assign this regional category, look for
        # clusters that contain articles from the corresponding regional sources.
        if filled < count:
            for cluster in scored:
                if filled >= count:
                    break
                if cluster.cluster_id not in selected_ids and _has_regional_source(cluster, cat):
                    selected.append(cluster)
                    selected_ids.add(cluster.cluster_id)
                    filled += 1
                    logger.info(
                        "Regional-source fallback slot '%s': '%s' (Claude assigned: %s)",
                        cat, cluster.theme, cluster.category,
                    )

        if filled < count:
            logger.warning(
                "Category '%s': only found %d/%d stories (not enough articles in that category)",
                cat, filled, count,
            )

    # Pass 2: Wild Card — fill from global top list (any category not already selected)
    wild_card_count = sum(s.get("count", 1) for s in DIGEST_SLOTS if s["category"] == "Wild Card")
    wild_filled = 0
    for cluster in scored:
        if wild_filled >= wild_card_count:
            break
        if cluster.cluster_id not in selected_ids:
            selected.append(cluster)
            selected_ids.add(cluster.cluster_id)
            wild_filled += 1
            logger.info("Wild Card slot: '%s' (category: %s)", cluster.theme, cluster.category)

    # Pass 3: if total < TOP_N_STORIES, pad from global top list
    for cluster in scored:
        if len(selected) >= TOP_N_STORIES:
            break
        if cluster.cluster_id not in selected_ids:
            selected.append(cluster)
            selected_ids.add(cluster.cluster_id)

    selected.sort(key=lambda c: c.final_score, reverse=True)
    return selected
