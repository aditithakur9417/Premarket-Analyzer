"""NSE corporate filings — discovery + Tier-A semantic verification."""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

import requests

from .calendar_nse import IST
from .filters import Bias, StockCatalyst
from .groww_feed import Article

NSE = "https://www.nseindia.com"

# Filing subjects that confirm a real corporate event
MATERIAL_PATTERNS = [
    r"outcome of board",
    r"financial result",
    r"audited|unaudited",
    r"award(?:ing)? of order",
    r"bagging.?receiving of order",
    r"order.?contract",
    r"acquisition|amalgamation|merger|scheme|slump.?sale|demerger|hive.?off|takeover",
    r"buy.?back|open.?offer|delisting",
    r"preferential|qip|fpo|rights issue|fund.?rais",
    r"us.?fda|anda|licence|license|clearance",
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

# Subject must relate to the catalyst event_type for true "verified"
EVENT_SUBJECT_PATTERNS: dict[str, list[str]] = {
    "m_and_a": [
        r"acqui",
        r"merger",
        r"amalgam",
        r"slump",
        r"demerger",
        r"hive",
        r"scheme of",
        r"takeover",
        r"business transfer",
        r"undertaking",
    ],
    "order_win": [r"order", r"contract", r"loa", r"award", r"bagging", r"purchase order"],
    "fundraising": [
        r"qip",
        r"preferential",
        r"rights",
        r"fpo",
        r"ofs",
        r"fund.?rais",
        r"allotment",
        r"issue of",
    ],
    "buyback": [r"buy.?back", r"buyback"],
    "open_offer": [r"open.?offer", r"delisting", r"creeping"],
    "promoter_buying": [r"promoter", r"shareholding", r"sast", r"disclosure under"],
    "promoter_selling": [r"promoter", r"pledge", r"shareholding", r"sast"],
    "regulatory_approval": [r"approv", r"clearance", r"licence", r"license", r"us.?fda", r"anda", r"nod"],
    "regulatory_action": [r"sebi", r"penalty", r"show.?cause", r"nclt", r"raid"],
    "earnings_beat": [r"financial result", r"audited", r"unaudited", r"outcome of board"],
    "earnings_miss": [r"financial result", r"audited", r"unaudited", r"outcome of board"],
    "guidance_raised": [r"guidance", r"outlook", r"press release", r"outcome of board"],
    "guidance_cut": [r"guidance", r"outlook", r"press release", r"outcome of board"],
    "business_entry": [r"press release", r"new business", r"outcome of board", r"updates?"],
    "capacity_expansion": [r"capacity", r"plant", r"facility", r"commission", r"project"],
    "partnership": [r"mou", r"joint venture", r"partnership", r"collaboration", r"agreement"],
    "policy_tailwind": [r"pli", r"policy", r"cabinet"],
}

NEEDS_FILING = {
    "earnings_beat",
    "earnings_miss",
    "order_win",
    "guidance_raised",
    "guidance_cut",
    "m_and_a",
    "buyback",
    "open_offer",
    "promoter_buying",
    "regulatory_action",
    "regulatory_approval",
    "fundraising",
    "business_entry",
}


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
        return asdict(self)


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
    if any(re.search(p, subj, re.I) for p in NOISE_PATTERNS):
        return False
    if any(re.search(p, blob, re.I) for p in NOISE_PATTERNS) and not any(
        re.search(p, subj, re.I) for p in MATERIAL_PATTERNS[:8]
    ):
        return False
    return any(re.search(p, blob, re.I) for p in MATERIAL_PATTERNS)


def subject_matches_event(event_type: str, subject: str) -> bool:
    """True if filing subject is semantically related to the catalyst type."""
    pats = EVENT_SUBJECT_PATTERNS.get(event_type) or []
    if not pats:
        return True  # unknown types: don't over-block
    return any(re.search(p, subject, re.I) for p in pats)


def infer_event_from_subject(subject: str) -> tuple[str, Bias, int]:
    """Map a filing subject → (event_type, bias, strength)."""
    s = subject.lower()
    checks: list[tuple[str, str, Bias, int]] = [
        (r"slump.?sale|demerger|hive.?off|amalgam|merger|acqui|takeover|scheme of arrangement|business transfer", "m_and_a", "bullish", 5),
        (r"award(?:ing)? of order|bagging|order.?contract|purchase order|\bloa\b", "order_win", "bullish", 5),
        (r"buy.?back", "buyback", "bullish", 5),
        (r"open.?offer|delisting", "open_offer", "bullish", 5),
        (r"rights issue|qip|preferential|fpo|\bofs\b|fund.?rais", "fundraising", "bullish", 4),
        (r"us.?fda|anda|licence|license|clearance", "regulatory_approval", "bullish", 5),
        (r"sebi|penalty|show.?cause|raid", "regulatory_action", "bearish", 5),
        (r"financial result|audited|unaudited", "earnings_beat", "bullish", 3),
        (r"outcome of board", "m_and_a", "bullish", 3),  # generic board — weak until text clarifies
        (r"promoter|sast|shareholding", "promoter_buying", "bullish", 3),
        (r"mou|joint venture|partnership|collaboration", "partnership", "bullish", 3),
    ]
    for pat, et, bias, strength in checks:
        if re.search(pat, s, re.I):
            # Dilutive fundraising hints
            if et == "fundraising" and re.search(r"discount|dilution|rights", s, re.I):
                return et, "bearish", strength
            if et == "earnings_beat" and re.search(r"loss|decline|fall", s, re.I):
                return "earnings_miss", "bearish", 4
            if et == "m_and_a" and re.search(r"outcome of board", s, re.I) and not re.search(
                r"acqui|merger|slump|demerger|scheme|takeover", s, re.I
            ):
                continue  # bare board outcome — skip discovery
            return et, bias, strength
    return "general_news", "neutral", 2


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


def discover_catalysts_from_filings(
    filings_by_symbol: dict[str, list[FilingHit]],
    existing: list[StockCatalyst],
    *,
    max_new: int = 25,
) -> list[StockCatalyst]:
    """Create catalysts from material NSE filings Groww never carried."""
    have = {c.symbol.upper() for c in existing}
    discovered: list[StockCatalyst] = []
    # Rank material hits by specificity
    candidates: list[tuple[int, FilingHit, str, Bias, int]] = []
    for sym, hits in filings_by_symbol.items():
        if sym in have:
            continue
        for h in hits:
            if not h.material:
                continue
            et, bias, strength = infer_event_from_subject(h.subject)
            if et == "general_news" or bias == "neutral":
                continue
            rank = strength + (2 if et in {"m_and_a", "order_win", "buyback", "open_offer"} else 0)
            candidates.append((rank, h, et, bias, strength))

    candidates.sort(key=lambda x: x[0], reverse=True)
    seen_sym: set[str] = set()
    for _, hit, et, bias, strength in candidates:
        if hit.symbol in seen_sym:
            continue
        seen_sym.add(hit.symbol)
        art = Article(
            post_id=f"nse-{hit.symbol}-{hit.published_at}",
            title=hit.subject[:240] or f"NSE filing {hit.symbol}",
            body=f"Discovered from NSE corporate announcement. {hit.company}",
            published_at=datetime.now(IST),
            publisher="NSE",
            source="NSE Filings",
            stocks=[{"nse": hit.symbol, "name": hit.company or hit.symbol}],
        )
        c = StockCatalyst(
            symbol=hit.symbol,
            name=hit.company or hit.symbol,
            bias=bias,
            event_type=et,
            strength=strength,
            articles=[art],
            soft=False,
            why=f"NSE filing discovery: {hit.subject}",
            opening_impact="Gap Up Likely" if bias == "bullish" and strength >= 4 else (
                "Gap Down Risk" if bias == "bearish" and strength >= 4 else "Mild Positive" if bias == "bullish" else "Mild Negative"
            ),
            risks="Filing-sourced — confirm deal economics before sizing.",
            sources=["NSE Filings"],
            filing_verified=True,
            filing_status="verified",
            filing_note=f"NSE filing: {hit.subject}",
            filing_url=hit.url,
            priority_tier="verified_gap",
        )
        discovered.append(c)
        if len(discovered) >= max_new:
            break
    return discovered


def verify_catalysts(
    catalysts: list[StockCatalyst],
    filings_by_symbol: dict[str, list[FilingHit]],
    *,
    top_n: int = 40,
) -> dict[str, FilingVerification]:
    """Mark catalysts with semantic filing match; downgrade unverified needs_filing."""
    results: dict[str, FilingVerification] = {}
    ranked = sorted(catalysts, key=lambda c: c.strength, reverse=True)[:top_n]

    for c in catalysts:
        hits = filings_by_symbol.get(c.symbol.upper(), [])
        material = [h for h in hits if h.material]
        material.sort(
            key=lambda h: (
                0 if subject_matches_event(c.event_type, h.subject) else 1,
                0 if re.search(r"outcome of board|financial result|order|acqui", h.subject, re.I) else 1,
                h.published_at,
            )
        )
        soft = [h for h in hits if not h.material]
        semantic = [h for h in material if subject_matches_event(c.event_type, h.subject)]
        v = FilingVerification(
            symbol=c.symbol,
            filing_count=len(hits),
            material_count=len(material),
            hits=(semantic or material)[:5] or soft[:3],
        )

        needs_filing = c.event_type in NEEDS_FILING

        if semantic:
            best = semantic[0]
            v.verified = True
            v.status = "verified"
            v.note = f"NSE filing: {best.subject}"
            c.filing_verified = True
            c.filing_status = "verified"
            c.filing_note = v.note
            c.filing_url = best.url or c.filing_url
            if c.strength < 5 and needs_filing:
                c.strength = min(5, c.strength + 1)
        elif material and needs_filing:
            # Material but wrong event family — soft only
            v.status = "soft_match"
            v.note = f"NSE filing on symbol but weak event match: {material[0].subject}"
            c.filing_verified = False
            c.filing_status = "soft_match"
            c.filing_note = v.note
            c.filing_url = material[0].url or c.filing_url
        elif soft and needs_filing:
            v.status = "soft_match"
            v.note = f"NSE noise/related filing only: {soft[0].subject}"
            c.filing_verified = False
            c.filing_status = "soft_match"
            c.filing_note = v.note
            c.filing_url = soft[0].url or c.filing_url
        elif needs_filing:
            v.status = "unverified"
            v.note = "No matching NSE filing in window — treat as paraphrase risk"
            c.filing_verified = False
            c.filing_status = "unverified"
            c.filing_note = v.note
            # Downgrade ALL needs_filing unverified (not only top_n)
            if c.opening_impact == "Gap Up Likely":
                c.opening_impact = "Mild Positive"
            if c.opening_impact == "Gap Down Risk":
                c.opening_impact = "Mild Negative"
            if c.strength >= 4:
                c.strength = max(2, c.strength - 1)
            c.risks = (c.risks + " Unverified vs NSE filings.").strip()
        else:
            v.status = "not_required"
            v.note = "Soft/commentary event — filing optional"
            c.filing_status = "not_required"
            c.filing_note = v.note
            if material:
                c.filing_url = material[0].url or c.filing_url

        # Prefer attaching a URL even for soft
        if not c.filing_url and v.hits:
            c.filing_url = v.hits[0].url

        results[c.symbol.upper()] = v
        _ = ranked  # kept for API compat / future focus lists
    return results
