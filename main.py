"""
NewsAgent — Weekly News Digest Orchestrator
===========================================
Fetch → Select → Summarise → Render → Send
"""

import json
import logging
import os
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from newsagent.fetcher import fetch_all
from newsagent.mailer import send_digest
from newsagent.renderer import render_digest
from newsagent.selector import select_articles
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
_MEMORY_LOOKBACK = 3


# ---------------------------------------------------------------------------
# Memory helpers (tracks previously covered titles to avoid repetition)
# ---------------------------------------------------------------------------

def _load_memory() -> dict:
    if _MEMORY_PATH.exists():
        try:
            with open(_MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not load memory file: %s", exc)
    return {"digests": []}


def _save_memory(memory: dict, titles: list[str]) -> None:
    entry = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "titles": titles,
    }
    memory["digests"].append(entry)
    memory["digests"] = memory["digests"][-10:]
    try:
        _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
        logger.info("Memory saved (%d digest entries)", len(memory["digests"]))
    except Exception as exc:
        logger.warning("Could not save memory file: %s", exc)


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set.")
    return value


def _week_label() -> str:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0)
    monday -= timedelta(days=now.weekday())
    return monday.strftime("Week of %B %-d, %Y")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("=" * 60)
    logger.info("NewsAgent starting")
    logger.info("=" * 60)

    anthropic_api_key = _require_env("ANTHROPIC_API_KEY")
    smtp_host         = _require_env("SMTP_HOST")
    smtp_port         = int(_require_env("SMTP_PORT"))
    smtp_user         = _require_env("SMTP_USER")
    smtp_password     = _require_env("SMTP_PASSWORD")
    email_from        = _require_env("EMAIL_FROM")
    email_to          = _require_env("EMAIL_TO")

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    memory = _load_memory()

    # 1. Fetch
    logger.info("Step 1/5 — Fetching RSS feeds")
    articles, warnings = fetch_all()
    logger.info("Fetched %d articles; %d warning(s)", len(articles), len(warnings))
    source_counts = Counter(a.source for a in articles)
    for source, count in sorted(source_counts.items()):
        logger.info("  %-20s %d articles", source, count)
    if not articles:
        raise RuntimeError("No articles fetched — cannot produce digest.")

    # 2. Select one article per category
    logger.info("Step 2/5 — Selecting articles by category")
    selected, category_errors = select_articles(articles, client)
    logger.info(
        "Selected %d stories; %d category error(s)",
        len(selected), len(category_errors),
    )
    for err in category_errors:
        logger.warning("Category '%s': %s", err.category, err.reason)
    if not selected:
        raise RuntimeError("No articles selected — cannot produce digest.")

    # 3. Summarise
    logger.info("Step 3/5 — Summarising selected stories")
    stories = summarise_top_stories(selected, client)
    logger.info("Summarised %d stories", len(stories))

    # 4. Render
    logger.info("Step 4/5 — Rendering HTML digest")
    week_label = _week_label()
    html = render_digest(
        stories=stories,
        category_errors=category_errors,
        total_articles=len(articles),
        warnings=warnings,
        week_label=week_label,
    )

    # 5. Send
    subject = f"Weekly News Digest — {week_label}"
    logger.info("Step 5/5 — Sending email: '%s'", subject)

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

    # Save memory
    _save_memory(memory, [s.title_en for s in stories])
    logger.info("NewsAgent completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.critical("NewsAgent failed:\n%s", traceback.format_exc())
        sys.exit(1)
