"""Central configuration: RSS feeds, constants, and prompt templates."""

import tomllib
from pathlib import Path

# ---------------------------------------------------------------------------
# Load newsagent.toml
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).parent.parent / "newsagent.toml"


def _load_user_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}


_user_config = _load_user_config()

EDITORIAL_FOCUS: str = _user_config.get("editorial", {}).get("focus", "").strip()
LOOKBACK_DAYS: int   = _user_config.get("digest", {}).get("lookback_days", 7)
SUMMARY_WORDS: int   = _user_config.get("digest", {}).get("summary_words", 80)
DIGEST_SLOTS: list   = _user_config.get("digest", {}).get("slots", [])

# ---------------------------------------------------------------------------
# RSS feeds
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    {
        "source": "Reuters",
        "url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": "https://news.google.com/rss/search?q=reuters+world+news&hl=en-US&gl=US&ceid=US:en",
        "timeout_secs": 15,
    },
    {
        "source": "AP",
        "url": "https://news.google.com/rss/search?q=site:apnews.com&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": "https://apnews.com/hub/ap-top-news.rss",
        "timeout_secs": 15,
    },
    {
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/rss.xml",
        "fallback_url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "timeout_secs": 15,
    },
    {
        "source": "Guardian",
        "url": "https://www.theguardian.com/world/rss",
        "fallback_url": "https://www.theguardian.com/international/rss",
        "timeout_secs": 15,
    },
    {
        "source": "DeutscheWelle",
        "url": "https://rss.dw.com/rdf/rss-en-top",
        "fallback_url": "https://rss.dw.com/xml/rss-en-world",
        "timeout_secs": 15,
    },
    {
        "source": "BerlinerZeitung",
        "url": "https://www.berliner-zeitung.de/feed.rss",
        "fallback_url": "https://news.google.com/rss/search?q=Berlin+site:berliner-zeitung.de&hl=de&gl=DE&ceid=DE:de",
        "timeout_secs": 15,
    },
    {
        "source": "SvD",
        "url": "https://www.svd.se/feed/articles.rss",
        "fallback_url": "https://www.svd.se/rss.xml",
        "timeout_secs": 15,
    },
    {
        "source": "GreeceReuters",
        "url": "https://news.google.com/rss/search?q=Greece+site:reuters.com&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": "https://news.google.com/rss/search?q=Greece+news&hl=en-US&gl=US&ceid=US:en",
        "timeout_secs": 15,
    },
]

# ---------------------------------------------------------------------------
# Claude model & retry settings
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_RETRIES = 3
CLAUDE_RETRY_DELAYS = [5, 10, 20]

# ---------------------------------------------------------------------------
# Fetch settings
# ---------------------------------------------------------------------------
MAX_ARTICLES_PER_SOURCE = 50
USER_AGENT = "NewsAgent/1.0 (weekly digest bot)"

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SELECTION_PROMPT_TEMPLATE = """\
You are a news editor selecting stories for a weekly digest.

Here are all articles fetched from RSS feeds this week:
{articles_text}

Select the best article(s) for each category below.

Rules:
- If "preferred_sources" are listed for a category, you MUST select from those sources first.
  Only fall back to other sources if no preferred-source article fits the category.
- Each article index can only be used ONCE across all categories.
- If no suitable article exists for a category, return null with a brief reason
  (e.g. "no BerlinerZeitung articles available", "feed blocked").
- Prefer recent, important, and distinct stories. Avoid picking the same event
  for multiple categories.

Editorial guidance:
{editorial_focus}

Categories:
{categories_text}

Return ONLY valid JSON, no markdown code fences, no explanation:
{{
  "selections": {{
    "Category Name": [4, 12],
    "Other Category": [1],
    "Missing Category": {{"indices": null, "reason": "brief reason"}}
  }}
}}
"""

SUMMARIZATION_PROMPT_TEMPLATE = f"""\
You are a journalist writing a concise weekly digest story.

Category: {{category}}
Source: {{source}}
Original title: {{original_title}}

Article content:
{{articles_text}}

Write a summary of approximately {SUMMARY_WORDS} words.

Return ONLY valid JSON (no markdown code fences, no explanation):
{{{{
  "title_en": "English title — translate if the original is not in English, otherwise copy it verbatim",
  "summary": "One short paragraph of approximately {SUMMARY_WORDS} words. Factual, clear prose. No bullet points or headers.",
  "key_fact": "One concise, striking sentence capturing the single most important fact."
}}}}
"""
