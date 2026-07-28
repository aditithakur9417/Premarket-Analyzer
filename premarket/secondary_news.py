"""Optional secondary headline cross-check (Moneycontrol RSS)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import requests

from .filters import StockCatalyst

MC_RSS = "https://www.moneycontrol.com/rss/latestnews.xml"


@dataclass
class SecondaryHit:
    symbol: str
    title: str
    link: str = ""


def fetch_secondary_headlines(limit: int = 80) -> list[dict[str, str]]:
    try:
        r = requests.get(
            MC_RSS,
            headers={"User-Agent": "Mozilla/5.0 PremarketDesk/1.0"},
            timeout=12,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title:
                items.append({"title": title, "link": link})
        return items
    except Exception:
        return []


def cross_check_secondary(
    catalysts: list[StockCatalyst],
    headlines: list[dict[str, str]],
    *,
    top_n: int = 15,
) -> dict[str, Any]:
    """Flag whether top symbols also appear on secondary wire."""
    ranked = catalysts[:top_n]
    hits: list[dict[str, str]] = []
    confirmed = 0
    for c in ranked:
        name_pat = re.escape(c.name.split()[0]) if c.name else c.symbol
        sym = re.escape(c.symbol)
        matched = []
        for h in headlines:
            t = h["title"]
            if re.search(rf"\b{sym}\b", t, re.I) or re.search(name_pat, t, re.I):
                matched.append(h)
        if matched:
            confirmed += 1
            c.secondary_confirmed = True
            hits.append({"symbol": c.symbol, "title": matched[0]["title"], "link": matched[0].get("link", "")})
        else:
            c.secondary_confirmed = False
    return {
        "source": "moneycontrol_rss",
        "headlines_scanned": len(headlines),
        "top_checked": len(ranked),
        "confirmed": confirmed,
        "hits": hits[:12],
    }
