"""
NewsAgent — Weekly News Digest Orchestrator
==========================================
Fetch → Cluster → Score → Summarise → Render → Send
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from newsagent.clustering import cluster_articles, score_clusters_with_claude
from newsagent.fetcher import fetch_all
from newsagent.mailer import send_digest
from newsagent.renderer import render_digest
from newsagent.scorer import score_clusters
from newsagent.summarizer import summarise_top_stories

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("newsagent.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("newsagent.main")

_MEMORY_PATH = Path(__file__).parent / "memory" / "history.json"
_MEMORY_LOOKBACK = 3  # How many past digests to draw previous themes from


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def _load_memory() -> dict:
    if _MEMORY_PATH.exists():
        try:
            with open(_MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not load memory file: %s", exc)
    return {"digests": []}


def _save_memory(memory: dict, themes: list[str]) -> None:
    entry = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "themes": themes,
    }
    memory["digests"].append(entry)
    # Keep only last 10 digests to avoid unbounded growth
    memory["digests"] = memory["digests"][-10:]
    try:
        _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
        logger.info("Memory saved (%d digest entries)", len(memory["digests"]))
    except Exception as exc:
        logger.warning("Could not save memory file: %s", exc)


def _previous_themes(memory: dict) -> list[str]:
    """Return themes from the last MEMORY_LOOKBACK digests, oldest first."""
    recent = memory.get("digests", [])[-_MEMORY_LOOKBACK:]
    themes = []
    for entry in recent:
        themes.extend(entry.get("themes", []))
    return themes


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set.")
    return value


def _week_label() -> str:
    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    monday -= timedelta(days=days_since_monday)
    return monday.strftime("Week of %B %-d, %Y")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=" * 60)
    logger.info("NewsAgent starting")
    logger.info("=" * 60)

    # Read secrets from environment
    anthropic_api_key = _require_env("ANTHROPIC_API_KEY")
    smtp_host         = _require_env("SMTP_HOST")
    smtp_port         = int(_require_env("SMTP_PORT"))
    smtp_user         = _require_env("SMTP_USER")
    smtp_password     = _require_env("SMTP_PASSWORD")
    email_from        = _require_env("EMAIL_FROM")
    email_to          = _require_env("EMAIL_TO")

    client = anthropic.Anthropic(api_key=anthropic_api_key)

    # Load memory (previous digest themes)
    memory = _load_memory()
    prev_themes = _previous_themes(memory)
    if prev_themes:
        logger.info("Loaded %d previous themes from memory", len(prev_themes))

    # 1. Fetch
    logger.info("Step 1/6 — Fetching RSS feeds")
    articles, warnings = fetch_all()
    logger.info("Fetched %d articles; %d warning(s)", len(articles), len(warnings))
    if not articles:
        raise RuntimeError("No articles fetched — cannot produce digest.")

    # 2. Cluster
    logger.info("Step 2/6 — Clustering articles")
    raw_clusters = cluster_articles(articles, client)
    logger.info("Produced %d clusters", len(raw_clusters))

    # 3. Score (Claude editorial + weighted formula)
    logger.info("Step 3/6 — Scoring clusters")
    raw_clusters = score_clusters_with_claude(raw_clusters, client, previous_themes=prev_themes)
    top_scored = score_clusters(raw_clusters)
    logger.info("Selected top %d stories", len(top_scored))

    # 4. Summarise
    logger.info("Step 4/6 — Summarising top stories")
    stories = summarise_top_stories(top_scored, client)
    logger.info("Summarised %d stories", len(stories))

    # 5. Render
    logger.info("Step 5/6 — Rendering HTML digest")
    week_label = _week_label()
    html = render_digest(
        stories=stories,
        total_articles=len(articles),
        warnings=warnings,
        week_label=week_label,
    )

    # 6. Send
    subject = f"Weekly News Digest — {week_label}"
    logger.info("Step 6/6 — Sending email: '%s'", subject)

    try:
        send_digest(
            html,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            email_from=email_from,
            email_to=email_to,
            subject=subject,
        )
    except Exception as exc:
        fallback_filename = f"digest_{datetime.now(timezone.utc).strftime('%Y%m%d')}.html"
        try:
            with open(fallback_filename, "w", encoding="utf-8") as f:
                f.write(html)
            logger.error("SMTP failed — HTML saved to %s", fallback_filename)
        except Exception as write_exc:
            logger.error("Could not save fallback HTML: %s", write_exc)
        raise RuntimeError(f"Email delivery failed: {exc}") from exc

    # Save memory after successful send
    current_themes = [s.theme for s in stories]
    _save_memory(memory, current_themes)

    logger.info("NewsAgent completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.critical("NewsAgent failed with unhandled exception:\n%s", traceback.format_exc())
        sys.exit(1)
