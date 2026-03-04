"""Central configuration: RSS feeds, constants, weights, and prompt templates.

User-editable settings (editorial focus, digest size, lookback window) live in
`newsagent.toml` at the repo root — no Python changes needed for those.
"""

import tomllib
from pathlib import Path

# ---------------------------------------------------------------------------
# Load user config from newsagent.toml (optional — falls back to defaults)
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).parent.parent / "newsagent.toml"

def _load_user_config() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}

_user_config = _load_user_config()

EDITORIAL_FOCUS: str      = _user_config.get("editorial", {}).get("focus", "").strip()
TOP_N_STORIES: int        = _user_config.get("digest", {}).get("top_n_stories", 10)
LOOKBACK_DAYS: int        = _user_config.get("digest", {}).get("lookback_days", 7)
SUMMARY_PARAGRAPHS: int   = _user_config.get("digest", {}).get("summary_paragraphs", 1)
GUARANTEED_SOURCES: list  = _user_config.get("digest", {}).get("guaranteed_sources", [])

def _paragraph_instruction(n: int) -> str:
    if n == 1:
        return "Write exactly 1 paragraph (4–6 sentences) of clear, factual prose."
    return f"Write exactly {n} paragraphs of clear, factual prose."

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

# Derived — used in scorer.py to normalise source coverage (0–1)
NUM_SOURCES: int = len(RSS_FEEDS)

# ---------------------------------------------------------------------------
# Fetch / filter settings
# ---------------------------------------------------------------------------
MAX_ARTICLES_PER_SOURCE = 50   # 7 sources × 50 = ~350 articles; ensures full 7-day coverage

USER_AGENT = "NewsAgent/1.0 (weekly digest bot)"

# ---------------------------------------------------------------------------
# Claude model
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Score weights  (must sum to 1.0)
# ---------------------------------------------------------------------------
WEIGHT_SOURCE_COUNT = 0.50   # coverage breadth across sources
WEIGHT_CLAUDE_SCORE = 0.35   # editorial importance from Claude
WEIGHT_RECENCY      = 0.15   # recency within the look-back window

# ---------------------------------------------------------------------------
# Retry settings for Claude calls
# ---------------------------------------------------------------------------
CLAUDE_MAX_RETRIES = 3
CLAUDE_RETRY_DELAYS = [5, 10, 20]  # seconds between retries

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------
_SOURCE_LIST = ", ".join(f["source"] for f in RSS_FEEDS)

CLUSTERING_PROMPT_TEMPLATE = f"""\
You are a news editor assistant. Below is a numbered list of news article titles \
and summaries collected from {_SOURCE_LIST} in the past 7 days.

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

SCORING_PROMPT_TEMPLATE = """\
You are a senior news editor. Below are clusters of related news stories from \
the past week, each with a theme and the sources that covered it.

Your task: score each cluster from 1–10 on newsworthiness.

Editorial guidance:
{editorial_focus}

General scoring criteria:
- Geopolitical significance
- Economic impact
- Human interest / scale
- Novelty and unexpectedness
- Likelihood of long-term consequence

Clusters:
{clusters_text}

Respond ONLY with valid JSON in exactly this format (no markdown, no explanation):
{{
  "scores": [
    {{
      "cluster_id": 1,
      "score": 8.5,
      "reasoning": "One sentence explanation."
    }}
  ]
}}
"""

SUMMARIZATION_PROMPT_TEMPLATE = f"""\
You are a skilled journalist writing a concise weekly digest for a busy reader.

Write a summary of the following news story based on coverage from multiple major outlets.

Story theme: {{theme}}

Source articles:
{{articles_text}}

{_paragraph_instruction(SUMMARY_PARAGRAPHS)} \
Cover the key who/what/why/impact. Do NOT use bullet points or headers.

After the paragraph(s), on a new line write exactly:
KEY FACT: [one concise, striking sentence that captures the single most important fact]

Format your entire response in Markdown.
"""
