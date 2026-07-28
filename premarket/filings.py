"""NSE corporate filings cross-check — Tier-A verification for catalysts."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

import requests

from .calendar_nse import IST
from .filters import StockCatalyst

NSE = "https://www.nseindia.com"

# Filing subjects that confirm a real corporate event
MATERIAL_PATTERNS = [
    r"outcome of board",
    r"financial result",
    r"audited|unaudited",
    r"award(?:ing)? of order",
    r"bagging.?receiving of order",
    r"order.?contract",
    r"acquisition|amalgamation|merger|scheme",
    r"buy.?back",
    r"preferential|qip|fpo|rights issue",
    r"credit rating",
    r"sebi|penalty|show.?cause",
    r"resignation|appointment of",
    r"disclosure under",
    r"updates?.{0,20}project",
    r"press release",
    r"clarification",
]

NOISE_PATTERNS = [
    r"newspaper publication",
    r"loss of share certificate",
    r"trading window",
    r"record date",
    r"book closure",
    r"investor (?:meet|presentation)(?! outcome)",
    r"newspaper",
]


@dataclass
class FilingHit:
    symbol: str
    subject: str
    published_at: str
    company: str = ""
    url: str = ""
    material: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FilingVerification:
    symbol: str
    verified: bool = False
    filing_count: int = 0
    material_count: int = 0
    hits: list[FilingHit] = field(default_factory=list)
    status: str = "unverified"  # verified | soft_match | unverified | no_data
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Referer": f"{NSE}/companies-listing/corporate-filings-announcements",
        }
    )
    s.get(f"{NSE}/", timeout=12)
    time.sleep(0.35)
    return s


def _is_material(subject: str, text: str) -> bool:
    subj = subject.lower().strip()
    blob = f"{subject} {text}".lower()
    # Title-level noise always wins (newspaper reprints often paste material keywords in body)
    if any(re.search(p, subj, re.I) for p in NOISE_PATTERNS):
        return False
    if any(re.search(p, blob, re.I) for p in NOISE_PATTERNS) and not any(
        re.search(p, subj, re.I) for p in MATERIAL_PATTERNS[:8]
    ):
        return False
    return any(re.search(p, blob, re.I) for p in MATERIAL_PATTERNS)


def fetch_announcements(days: int = 2) -> list[dict[str, Any]]:
    """Pull recent NSE equity corporate announcements. Best-effort."""
    to_d = datetime.now(IST).date()
    from_d = to_d - timedelta(days=max(1, days))
    s = _session()
    url = (
        f"{NSE}/api/corporate-announcements?index=equities"
        f"&from_date={from_d.strftime('%d-%m-%Y')}&to_date={to_d.strftime('%d-%m-%Y')}"
    )
    r = s.get(url, timeout=25)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def index_filings(rows: list[dict[str, Any]]) -> dict[str, list[FilingHit]]:
    out: dict[str, list[FilingHit]] = {}
    for row in rows:
        sym = str(row.get("symbol") or "").upper().strip()
        if not sym:
            continue
        subject = str(row.get("desc") or row.get("subject") or "")
        text = str(row.get("attchmntText") or "")
        hit = FilingHit(
            symbol=sym,
            subject=subject,
            published_at=str(row.get("an_dt") or row.get("sort_date") or ""),
            company=str(row.get("sm_name") or ""),
            url=str(row.get("attchmntFile") or ""),
            material=_is_material(subject, text),
        )
        out.setdefault(sym, []).append(hit)
    return out


def verify_catalysts(
    catalysts: list[StockCatalyst],
    filings_by_symbol: dict[str, list[FilingHit]],
    *,
    top_n: int = 20,
) -> dict[str, FilingVerification]:
    """Mark top catalysts as filing-verified / soft / unverified and adjust scores."""
    results: dict[str, FilingVerification] = {}
    ranked = sorted(catalysts, key=lambda c: c.strength, reverse=True)[:top_n]

    for c in catalysts:
        hits = filings_by_symbol.get(c.symbol.upper(), [])
        material = [h for h in hits if h.material]
        # Prefer stronger subjects first for the note
        material.sort(
            key=lambda h: (
                0 if re.search(r"outcome of board|financial result|order", h.subject, re.I) else 1,
                h.published_at,
            )
        )
        soft = [h for h in hits if not h.material]
        v = FilingVerification(symbol=c.symbol, filing_count=len(hits), material_count=len(material), hits=material[:5] or soft[:3])

        # Event types that *should* have filings
        needs_filing = c.event_type in {
            "earnings_beat",
            "earnings_miss",
            "order_win",
            "guidance_raised",
            "guidance_cut",
            "m_and_a",
            "buyback",
            "regulatory_action",
            "regulatory_approval",
            "fundraising",
        }

        if material:
            v.verified = True
            v.status = "verified"
            v.note = f"NSE filing: {material[0].subject}"
            c.filing_verified = True
            c.filing_status = "verified"
            c.filing_note = v.note
            if c.strength < 5 and needs_filing:
                c.strength = min(5, c.strength + 1)
        elif soft and needs_filing:
            v.status = "soft_match"
            v.note = f"NSE noise/related filing only: {soft[0].subject}"
            c.filing_verified = False
            c.filing_status = "soft_match"
            c.filing_note = v.note
        elif needs_filing:
            v.status = "unverified"
            v.note = "No matching NSE filing in window — treat as paraphrase risk"
            c.filing_verified = False
            c.filing_status = "unverified"
            c.filing_note = v.note
            # Downgrade high-conviction gaps without filing
            if c in ranked and c.opening_impact == "Gap Up Likely":
                c.opening_impact = "Mild Positive"
            if c in ranked and c.strength >= 4:
                c.strength = max(2, c.strength - 1)
            c.risks = (c.risks + " Unverified vs NSE filings.").strip()
        else:
            v.status = "not_required"
            v.note = "Soft/commentary event — filing optional"
            c.filing_status = "not_required"
            c.filing_note = v.note

        results[c.symbol.upper()] = v
    return results
