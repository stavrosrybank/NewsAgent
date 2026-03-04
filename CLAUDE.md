# NewsAgent

## Project Overview

This project is a weekly news digest that automatically identifies and summarizes the biggest news stories of the week.

## Goals

- Scrape news from Reuters, Associated Press, BBC News, and The Guardian
- Determine "newsworthiness" by cross-referencing coverage across sources and applying internal ranking logic
- Deliver a weekly update highlighting the most significant stories
- Run automatically via GitHub Actions

## Stack

- **Language**: Python
- **Automation**: GitHub Actions (scheduled weekly run)

## Newsworthiness Logic

Stories are ranked based on:
- Cross-source coverage: how many of the four sources covered the same story
- Coverage prominence (e.g., front page vs. secondary coverage)
- Additional internal scoring logic (e.g., recency, topic weight, keyword signals)

## Sources

1. [Reuters](https://www.reuters.com)
2. [Associated Press](https://apnews.com)
3. [BBC News](https://www.bbc.com/news)
4. [The Guardian](https://www.theguardian.com)
