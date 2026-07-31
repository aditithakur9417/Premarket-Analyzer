"""Optional secondary headline cross-check (Moneycontrol RSS)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import requests

from .filters import StockCatalyst

MC_RSS = "https://www.moneycontrol.com/rss/latestnews.xml"

# First tokens that are too generic for name matching
_STOP = {
    "the",
    "a",
    "an",
    "india",
    "indian",
    "state",
    "bank",
    "new",
    "ltd",
    "limited",
    "company",
    "industries",
    "corp",
    "corporation",
}


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


def _name_tokens(name: str) -> list[str]:
    toks = re.findall(r"[A-Za-z]{3,}", name or "")
    return [t for t in toks if t.lower() not in _STOP][:3]


def cross_check_secondary(
    catalysts: list[StockCatalyst],
    headlines: list[dict[str, str]],
    *,
    top_n: int = 20,
) -> dict[str, Any]:
    """Flag whether top symbols also appear on secondary wire (tight matching)."""
    ranked = sorted(catalysts, key=lambda c: (c.conviction, c.strength), reverse=True)[:top_n]
    hits: list[dict[str, str]] = []
    confirmed = 0
    for c in ranked:
        sym = re.escape(c.symbol)
        tokens = _name_tokens(c.name)
        matched = []
        for h in headlines:
            t = h["title"]
            if re.search(rf"\b{sym}\b", t, re.I):
                matched.append(h)
                continue
            # Require ≥2 distinctive name tokens, or one long unique token (≥6)
            if len(tokens) >= 2 and all(re.search(rf"\b{re.escape(tok)}\b", t, re.I) for tok in tokens[:2]):
                matched.append(h)
            elif len(tokens) == 1 and len(tokens[0]) >= 6 and re.search(rf"\b{re.escape(tokens[0])}\b", t, re.I):
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
