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

EDITORIAL_FOCUS: str = _user_config.get("editorial", {}).get("focus", "").strip()
TOP_N_STORIES: int   = _user_config.get("digest", {}).get("top_n_stories", 10)
LOOKBACK_DAYS: int   = _user_config.get("digest", {}).get("lookback_days", 7)

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
        "source": "Spiegel",
        "url": "https://www.spiegel.de/international/index.rss",
        "fallback_url": "https://www.spiegel.de/schlagzeilen/index.rss",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        "source": "Ekathimerini",
        "url": "https://www.ekathimerini.com/rss/",
        "fallback_url": "https://www.ekathimerini.com/rss",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
    {
        "source": "TheLocalSweden",
        "url": "https://www.thelocal.se/feeds/rss.xml",
        "fallback_url": "https://www.thelocal.se/feeds/rss",
        "prominence_weight": 1.0,
        "timeout_secs": 15,
    },
]

# Derived — used in scorer.py to normalise source coverage (0–1)
NUM_SOURCES: int = len(RSS_FEEDS)

# ---------------------------------------------------------------------------
# Fetch / filter settings
# ---------------------------------------------------------------------------
MAX_ARTICLES_PER_SOURCE = 30   # 7 sources × 30 = ~210 articles max

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

SUMMARIZATION_PROMPT_TEMPLATE = """\
You are a skilled journalist writing for an informed general audience.

Write a summary of the following news story based on coverage from multiple major outlets.

Story theme: {theme}

Source articles:
{articles_text}

Write 3–4 paragraphs of flowing narrative prose. Be factual, balanced, and clear. \
Do NOT use bullet points or headers within the narrative.

After the narrative, on a new line write exactly:
KEY FACT: [one concise, striking sentence that captures the most important single fact]

Format your entire response in Markdown.
"""
