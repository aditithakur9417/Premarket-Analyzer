"""Groww public stock news feed client."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests

from .calendar_nse import IST

BASE_URL = "https://groww.in/v2/api/feed/public"
# size=100 returns stale/misordered pages — keep small.
PAGE_SIZE = 25
MAX_PAGES = 40


@dataclass
class Article:
    post_id: str
    title: str
    body: str
    published_at: datetime
    publisher: str
    source: str
    stocks: list[dict[str, str]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    soft_close: bool = False  # published in last 60m of prior session

    @property
    def primary_symbol(self) -> str | None:
        if not self.stocks:
            return None
        s = self.stocks[0]
        return s.get("nse") or s.get("bse") or s.get("name")

    @property
    def primary_name(self) -> str:
        if not self.stocks:
            return "Market / Sector"
        return self.stocks[0].get("name") or self.primary_symbol or "Unknown"


def _parse_published(value: str) -> datetime:
    """Groww returns naive timestamps that match IST wall clock."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def _extract_source(body: str) -> str:
    m = re.search(r"Source:\s*(.+)$", body.strip(), re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else "Unknown"


def _parse_article(item: dict[str, Any]) -> Article:
    data = item.get("data") or {}
    body = data.get("body") or ""
    stocks: list[dict[str, str]] = []
    for cta in data.get("cta") or []:
        if cta.get("type") != "STOCK":
            continue
        meta = cta.get("meta") or {}
        stocks.append(
            {
                "name": cta.get("ctaText") or "",
                "nse": str(meta.get("nseScriptCode") or ""),
                "bse": str(meta.get("bseScriptCode") or ""),
                "url": cta.get("ctaUrl") or "",
            }
        )
    return Article(
        post_id=item.get("postId") or item.get("name") or "",
        title=(data.get("title") or "").strip(),
        body=body.strip(),
        published_at=_parse_published(item["publishedAt"]),
        publisher=item.get("publisher") or "",
        source=_extract_source(body),
        stocks=stocks,
        raw=item,
    )


def fetch_feed_page(
    page: int, size: int = PAGE_SIZE, session: requests.Session | None = None
) -> list[Article]:
    sess = session or requests.Session()
    resp = sess.get(
        BASE_URL,
        params={"page": page, "publisherId": "stocknewssummary", "size": size},
        headers={"Accept": "application/json", "User-Agent": "premarket-analyzer/0.1"},
        timeout=30,
    )
    resp.raise_for_status()
    feed = resp.json().get("feed") or []
    return [_parse_article(x) for x in feed]


def fetch_since(cutoff: datetime) -> tuple[list[Article], dict[str, Any]]:
    """
    Paginate newest-first until articles fall before the soft-close window.

    Soft-close window: last 60 minutes of the previous session (14:30–15:30 IST).
    Those prints are included and marked soft_close=True so momentum carryover
    catalysts (e.g. order wins at 15:20) are not missed.
    Strict post-close articles (published_at > cutoff) are soft_close=False.
    """
    from datetime import time, timedelta

    soft_start = datetime.combine(cutoff.date(), time(14, 30), tzinfo=cutoff.tzinfo or IST)
    session = requests.Session()
    kept: list[Article] = []
    pages_fetched = 0
    total_seen = 0
    soft_close_count = 0
    stopped_reason = "max_pages"

    for page in range(1, MAX_PAGES + 1):
        batch = fetch_feed_page(page, PAGE_SIZE, session=session)
        pages_fetched += 1
        if not batch:
            stopped_reason = "empty_page"
            break

        batch = sorted(batch, key=lambda a: a.published_at, reverse=True)
        stop = False
        for art in batch:
            total_seen += 1
            if art.published_at > soft_start:
                art.soft_close = soft_start < art.published_at <= cutoff
                if art.soft_close:
                    soft_close_count += 1
                kept.append(art)
            else:
                stop = True
                stopped_reason = "hit_soft_close"
                break
        if stop:
            break
        if batch[-1].published_at <= soft_start:
            stopped_reason = "hit_soft_close"
            break
    else:
        stopped_reason = "max_pages"

    seen_ids: set[str] = set()
    unique: list[Article] = []
    for a in kept:
        if a.post_id in seen_ids:
            continue
        seen_ids.add(a.post_id)
        unique.append(a)

    stats = {
        "pages_fetched": pages_fetched,
        "articles_seen": total_seen,
        "articles_in_window": len(unique),
        "soft_close_articles": soft_close_count,
        "soft_close_start": soft_start.isoformat(),
        "stopped_reason": stopped_reason,
        "newest": unique[0].published_at.isoformat() if unique else None,
        "oldest_kept": unique[-1].published_at.isoformat() if unique else None,
    }
    return unique, stats
