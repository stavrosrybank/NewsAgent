"""
Generate summaries for each selected story via parallel Claude calls.
Returns DigestStory objects with English titles, HTML body, and key fact.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import anthropic

from newsagent.selector import call_claude_with_retry, SelectedStory
from newsagent.config import SUMMARIZATION_PROMPT_TEMPLATE, SUMMARY_WORDS

logger = logging.getLogger(__name__)

_MAX_SUMMARY_WORKERS = 5


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class DigestStory:
    rank: int
    title_en: str       # English title (translated if needed)
    category: str
    source: str         # source name (e.g. "BerlinerZeitung")
    url: str            # direct article URL
    body_html: str      # summary as an HTML paragraph
    key_fact: str       # one striking sentence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```[a-z]*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)
    return clean.strip()


def _fallback(story: SelectedStory) -> DigestStory:
    """Minimal fallback when Claude summarisation fails."""
    a = story.article
    snippet = a.summary[:300] if a.summary else a.title
    return DigestStory(
        rank=story.rank,
        title_en=a.title,
        category=story.category,
        source=a.source,
        url=a.url,
        body_html=f"<p>{snippet}</p>",
        key_fact="",
    )


# ---------------------------------------------------------------------------
# Single-story summariser
# ---------------------------------------------------------------------------

def _summarise_one(story: SelectedStory, client: anthropic.Anthropic) -> DigestStory:
    a = story.article
    article_text = f"Title: {a.title}"
    if a.summary:
        article_text += f"\nSummary: {a.summary}"

    prompt = SUMMARIZATION_PROMPT_TEMPLATE.format(
        category=story.category,
        source=a.source,
        original_title=a.title,
        articles_text=article_text,
    )

    try:
        raw = call_claude_with_retry(
            client,
            prompt=prompt,
            temperature=0.5,
            max_tokens=max(400, SUMMARY_WORDS * 3),
        )
        data = json.loads(_strip_fences(raw))
        title_en  = data.get("title_en", a.title).strip()
        summary   = data.get("summary", "").strip()
        key_fact  = data.get("key_fact", "").strip()
        body_html = f"<p>{summary}</p>" if summary else f"<p>{a.summary or a.title}</p>"
    except Exception as exc:
        logger.warning("Summarisation failed for '%s': %s", a.title[:60], exc)
        return _fallback(story)

    return DigestStory(
        rank=story.rank,
        title_en=title_en,
        category=story.category,
        source=a.source,
        url=a.url,
        body_html=body_html,
        key_fact=key_fact,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarise_top_stories(
    selected: list[SelectedStory],
    client: anthropic.Anthropic,
) -> list[DigestStory]:
    """Summarise all selected stories in parallel. Returns list in rank order."""
    stories: list[DigestStory | None] = [None] * len(selected)

    with ThreadPoolExecutor(max_workers=_MAX_SUMMARY_WORKERS) as executor:
        futures = {
            executor.submit(_summarise_one, story, client): i
            for i, story in enumerate(selected)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                stories[i] = future.result()
                logger.info(
                    "Summarised story #%d (%s): %s",
                    selected[i].rank,
                    selected[i].category,
                    selected[i].article.title[:60],
                )
            except Exception as exc:
                logger.error("Fatal error summarising story %d: %s", i, exc)
                stories[i] = _fallback(selected[i])

    return [s for s in stories if s is not None]
