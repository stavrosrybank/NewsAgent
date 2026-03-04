"""Render HTML digest from DigestStory list using Jinja2."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from newsagent.summarizer import DigestStory

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATE_NAME = "digest.html.j2"


def render_digest(
    stories: list[DigestStory],
    total_articles: int,
    warnings: list[str],
    week_label: str | None = None,
) -> str:
    """
    Render the HTML digest and return it as a string.

    Args:
        stories: Ordered list of DigestStory objects.
        total_articles: Total number of articles fetched (for footer).
        warnings: Human-readable source warnings for footer.
        week_label: Override for the week label; defaults to current date.
    """
    now = datetime.now(timezone.utc)

    if week_label is None:
        # "Week of March 3, 2026"
        week_label = now.strftime("Week of %B %-d, %Y")

    generated_at = now.strftime("%Y-%m-%d %H:%M UTC")

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template(_TEMPLATE_NAME)

    html = template.render(
        week_label=week_label,
        generated_at=generated_at,
        total_articles=total_articles,
        stories=stories,
        warnings=warnings,
    )
    logger.info("HTML digest rendered (%d bytes)", len(html))
    return html
