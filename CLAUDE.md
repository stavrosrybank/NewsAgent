# NewsAgent

## Project Overview

A weekly news digest that automatically fetches, clusters, scores, and summarises the most important news stories of the week, then emails an HTML digest every Friday at 08:00 UTC.

## Stack

- **Language**: Python 3.11
- **AI**: Claude API (`claude-sonnet-4-6`) — clustering, scoring, summarisation
- **Email**: SendGrid SMTP relay
- **Automation**: GitHub Actions (scheduled weekly + manual `workflow_dispatch`)

## Sources (8 RSS feeds)

| Name | Coverage | Language |
|------|----------|----------|
| Reuters | Global (via Google News) | English |
| AP | Global (via Google News) | English |
| BBC | Global | English |
| Guardian | Global/UK | English |
| DeutscheWelle | Germany/Europe | English |
| BerlinerZeitung | Berlin local | German |
| SvD | Sweden | Swedish |
| GreeceReuters | Greece (via Google News → Reuters) | English |

## Pipeline

```
Fetch RSS (parallel) → Cluster articles (Claude) → Score clusters (Claude)
→ Weighted formula → Select top 10 (with guaranteed slots) → Summarise (Claude, parallel)
→ Render HTML → Send via SendGrid
```

## Scoring Formula

```
final = 0.50 × (source_count / 8)   # coverage breadth
      + 0.35 × (claude_score / 10)  # editorial importance
      + 0.15 × recency_score        # freshness within 7-day window
```

**Guaranteed slots**: `DeutscheWelle`, `BerlinerZeitung`, `SvD`, and `GreeceReuters` each always get one reserved slot in the top 10, regardless of their raw score. Remaining slots are filled by global top scorers.

## User Configuration (`newsagent.toml`)

All editorial and digest settings live in `newsagent.toml` — no Python changes needed:

- `[editorial] focus` — plain-English instructions sent to Claude when scoring (geographic priorities, topics to deprioritise, etc.)
- `[digest] top_n_stories` — number of stories in the digest (default 10)
- `[digest] lookback_days` — how far back to fetch articles (default 7)
- `[digest] summary_paragraphs` — length of each story summary (default 1)
- `[digest] guaranteed_sources` — sources that always get a slot in the digest

## Project Structure

```
NewsAgent/
├── CLAUDE.md
├── newsagent.toml          # User-editable config (prompts, digest settings)
├── requirements.txt
├── .env.example
├── main.py                 # Orchestrator entry point
├── .github/workflows/
│   └── weekly_digest.yml   # Friday 08:00 UTC schedule
└── newsagent/
    ├── config.py           # Loads newsagent.toml; all constants and prompt templates
    ├── fetcher.py          # RSS fetch + Article dataclass + date filtering
    ├── clustering.py       # Claude Call 1 (cluster) + Call 2 (score) + Jaccard fallback
    ├── scorer.py           # Weighted formula + guaranteed slots logic
    ├── summarizer.py       # Parallel Claude summarisation + DigestStory dataclass
    ├── renderer.py         # Jinja2 HTML rendering
    ├── mailer.py           # SendGrid SMTP send
    └── templates/
        └── digest.html.j2  # Inline-CSS HTML email template (600px, Gmail-compatible)
```

## GitHub Secrets Required

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `SMTP_HOST` | `smtp.sendgrid.net` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `apikey` (literal string) |
| `SMTP_PASSWORD` | SendGrid API key |
| `EMAIL_FROM` | Verified SendGrid sender address |
| `EMAIL_TO` | Recipient address(es), comma-separated |

## Claude API Calls per Run

| Call | Purpose | Count | Temp | Max tokens |
|------|---------|-------|------|-----------|
| 1 | Cluster all articles | 1 | 0.2 | 8192 |
| 2 | Score all clusters | 1 | 0.2 | 2048 |
| 3–12 | Summarise each top story | 10 | 0.5 | 350 |

**Total: ~12 API calls per run.**
