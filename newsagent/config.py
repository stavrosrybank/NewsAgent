"""Central configuration: RSS feeds, constants, weights, and prompt templates.

User-editable settings live in `newsagent.toml` (editorial focus, digest slots,
word count, etc.) and `feedback.toml` (story ratings). No Python changes needed.
"""

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

EDITORIAL_FOCUS: str  = _user_config.get("editorial", {}).get("focus", "").strip()
TOP_N_STORIES: int    = _user_config.get("digest", {}).get("top_n_stories", 10)
LOOKBACK_DAYS: int    = _user_config.get("digest", {}).get("lookback_days", 7)
SUMMARY_WORDS: int    = _user_config.get("digest", {}).get("summary_words", 80)
DIGEST_SLOTS: list    = _user_config.get("digest", {}).get("slots", [])

# Flat category list for the scoring prompt (excludes Wild Card — handled separately)
_CATEGORY_LIST = "\n".join(
    f"- {s['category']}" for s in DIGEST_SLOTS if s["category"] != "Wild Card"
) or "- Global Geopolitical\n- Wild Card"

# ---------------------------------------------------------------------------
# Load feedback.toml
# ---------------------------------------------------------------------------
_FEEDBACK_PATH = Path(__file__).parent.parent / "feedback.toml"

def _load_feedback() -> dict:
    if _FEEDBACK_PATH.exists():
        with open(_FEEDBACK_PATH, "rb") as f:
            return tomllib.load(f)
    return {}

_feedback = _load_feedback()

def _build_feedback_text() -> str:
    likes    = _feedback.get("likes", {})
    dislikes = _feedback.get("dislikes", {})
    liked_topics    = likes.get("topics", [])
    liked_themes    = likes.get("themes", [])
    disliked_topics = dislikes.get("topics", [])
    disliked_themes = dislikes.get("themes", [])
    if not any([liked_topics, liked_themes, disliked_topics, disliked_themes]):
        return "No reader feedback provided yet."
    parts = []
    if liked_topics or liked_themes:
        parts.append("Reader enjoyed (seek similar):")
        if liked_topics:  parts.append(f"  Topics: {', '.join(liked_topics)}")
        if liked_themes:  parts.append(f"  Stories: {', '.join(liked_themes)}")
    if disliked_topics or disliked_themes:
        parts.append("Reader did NOT enjoy (deprioritise similar):")
        if disliked_topics: parts.append(f"  Topics: {', '.join(disliked_topics)}")
        if disliked_themes: parts.append(f"  Stories: {', '.join(disliked_themes)}")
    return "\n".join(parts)

FEEDBACK_TEXT: str = _build_feedback_text()

# ---------------------------------------------------------------------------
# RSS feeds
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    {
        # Reuters dropped official RSS in 2020; use Google News RSS filtered to reuters.com
        "source": "Reuters",
        "url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": "https://news.google.com/rss/search?q=reuters+world+news&hl=en-US&gl=US&ceid=US:en",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        # AP dropped official RSS; use Google News RSS filtered to apnews.com
        "source": "AP",
        "url": "https://news.google.com/rss/search?q=site:apnews.com&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": "https://apnews.com/hub/ap-top-news.rss",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        "source": "BBC",
        "url": "https://feeds.bbci.co.uk/news/rss.xml",
        "fallback_url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        "source": "Guardian",
        "url": "https://www.theguardian.com/world/rss",
        "fallback_url": "https://www.theguardian.com/international/rss",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        # Deutsche Welle — English-language German/European news
        "source": "DeutscheWelle",
        "url": "https://rss.dw.com/rdf/rss-en-top",
        "fallback_url": "https://rss.dw.com/xml/rss-en-world",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        # Berliner Zeitung — Berlin local news (German language; Claude reads it fine)
        "source": "BerlinerZeitung",
        "url": "https://www.berliner-zeitung.de/feed.rss",
        "fallback_url": "https://news.google.com/rss/search?q=Berlin+site:berliner-zeitung.de&hl=de&gl=DE&ceid=DE:de",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        # SvD (Svenska Dagbladet) — Swedish news (Swedish language; Claude reads it fine)
        "source": "SvD",
        "url": "https://www.svd.se/feed/articles.rss",
        "fallback_url": "https://www.svd.se/rss.xml",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        # Greece news via Reuters on Google News
        "source": "GreeceReuters",
        "url": "https://news.google.com/rss/search?q=Greece+site:reuters.com&hl=en-US&gl=US&ceid=US:en",
        "fallback_url": "https://news.google.com/rss/search?q=Greece+news&hl=en-US&gl=US&ceid=US:en",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
]

NUM_SOURCES: int = len(RSS_FEEDS)

# ---------------------------------------------------------------------------
# Fetch / filter settings
# ---------------------------------------------------------------------------
MAX_ARTICLES_PER_SOURCE = 50
USER_AGENT = "NewsAgent/1.0 (weekly digest bot)"

# ---------------------------------------------------------------------------
# Claude model
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Score weights  (must sum to 1.0)
# ---------------------------------------------------------------------------
WEIGHT_SOURCE_COUNT = 0.50
WEIGHT_CLAUDE_SCORE = 0.35
WEIGHT_RECENCY      = 0.15

# ---------------------------------------------------------------------------
# Retry settings for Claude calls
# ---------------------------------------------------------------------------
CLAUDE_MAX_RETRIES = 3
CLAUDE_RETRY_DELAYS = [5, 10, 20]

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------
_SOURCE_LIST = ", ".join(f["source"] for f in RSS_FEEDS)

CLUSTERING_PROMPT_TEMPLATE = f"""\
You are a news editor assistant. Below is a numbered list of news article titles \
collected from {_SOURCE_LIST} in the past 7 days.

Your task: group these articles into thematic clusters where each cluster \
represents a single distinct news story or ongoing event.

Articles:
{{articles_text}}

Rules:
- Each article belongs to exactly one cluster.
- Clusters should be tight — only group articles that clearly cover the same story.
- Unrelated or unique articles should each form their own single-article cluster.
- Give each cluster a concise theme label (max 10 words).

Respond ONLY with valid JSON in exactly this format (no markdown, no explanation):
{{{{
  "clusters": [
    {{{{
      "cluster_id": 1,
      "theme": "Brief theme description",
      "article_indices": [0, 3, 7]
    }}}}
  ]
}}}}
"""

SCORING_PROMPT_TEMPLATE = f"""\
You are a senior news editor. Below are clusters of news stories from the past week.

Your tasks:
1. Score each cluster from 1–10 on newsworthiness.
2. Assign each cluster to exactly one category from the list below.

Valid categories:
{_CATEGORY_LIST}
- Wild Card

Category assignment rules:
- "Germany/Berlin": stories primarily about Germany or Berlin.
- "Sweden": stories primarily about Sweden or Swedish affairs.
- "Greece": stories primarily about Greece or Greek affairs.
- "Global Geopolitical": major international political/military/diplomatic events.
- "Science/Tech/AI": science, technology, or artificial intelligence.
- "Finance/Business/Economy": markets, economy, business, trade.
- "Culture": arts, society, sports, lifestyle.
- "Wild Card": use only if no other category fits well.

Editorial guidance:
{{editorial_focus}}

Reader feedback from previous digests:
{{feedback_text}}

Topics already covered in recent digests (deprioritise unless major new developments):
{{memory_text}}

General scoring criteria:
- Geopolitical significance
- Economic impact
- Human interest / scale
- Novelty and unexpectedness
- Likelihood of long-term consequence

Clusters:
{{clusters_text}}

Respond ONLY with valid JSON in exactly this format (no markdown, no explanation):
{{{{
  "scores": [
    {{{{
      "cluster_id": 1,
      "score": 8.5,
      "reasoning": "One sentence explanation.",
      "category": "Global Geopolitical"
    }}}}
  ]
}}}}
"""

SUMMARIZATION_PROMPT_TEMPLATE = f"""\
You are a skilled journalist writing a concise weekly digest for a busy reader.

Write a summary of the following news story based on coverage from multiple major outlets.

Story theme: {{theme}}

Source articles:
{{articles_text}}

Write approximately {SUMMARY_WORDS} words of clear, factual prose. \
Cover the key who/what/why/impact in a single tight paragraph. \
Do NOT use bullet points or headers.

After the paragraph, on a new line write exactly:
KEY FACT: [one concise, striking sentence that captures the single most important fact]

Format your entire response in Markdown.
"""
