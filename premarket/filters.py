"""Low-value filters, event classification, and stock-level deduplication."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Literal

from .calendar_nse import IST
from .groww_feed import Article

Bias = Literal["bullish", "bearish", "neutral"]
EventType = str

IGNORE_PATTERNS = [
    r"\bstock(?:s)? to watch\b",
    r"\btop picks?\b",
    r"\btechnical (?:analysis|breakout|breakdown|view)\b",
    r"\bchart (?:pattern|setup|view)\b",
    r"\bfutures target\b",
    r"\bintraday (?:pick|idea|view|trade)\b",
    r"\bshort[- ]term gains?\b",
    r"\ba hold\b.*\bcaution\b",
    r"\bbuy .+\bfor short[- ]term\b",
    r"\brsi\b",
    r"\bmoving average\b",
    r"\bweekly (?:wrap|roundup|recap|summary)\b",
    r"\bmonthly (?:wrap|roundup|recap|summary)\b",
    r"\bwhat (?:is|are) .+\?\b",
    r"\bexplained\b",
    r"\bex[- ]?dividend\b",
    r"\brecord date\b",
    r"\bdividend reminder\b",
    r"\bprice (?:recovers?|falls?|rises?|jumps?|slides?) (?:as|after|on)\b",
    r"\bshares? (?:trade|trading) (?:higher|lower|flat)\b",
    r"\bcloses? (?:higher|lower|flat)\b",
    r"\bintraday\b",
    r"\beducational\b",
]

# Soft / noise events — keep but heavily down-rank unless exceptional
SOFT_PATTERNS = [
    (r"\bbulk (?:deal|buy|sell|trade)\b", "bulk_deal"),
    (r"\bblock (?:deal|buy|sell|trade)\b", "block_deal"),
    (r"\bconcall\b", "concall_commentary"),
    (r"\bearnings call\b", "earnings_call_schedule"),
    (r"\bto hold .+ call\b", "earnings_call_schedule"),
    (r"\bresults? call on\b", "earnings_call_schedule"),
    (r"\bbroker(?:age)? (?:upgrade|downgrade|initiates?|maintains?|raises?|cuts?)\b", "broker_note"),
    (r"\btarget (?:price|raised|cut)\b", "broker_note"),
]

# Title subject → synthetic symbol when Groww only tags peers
TITLE_ENTITY_MAP: list[tuple[str, str, str]] = [
    (r"\bbluestone\b", "BLUESTONE", "Bluestone Jewellery"),
    (r"\bhuhtamaki\b", "HUHTAMAKI", "Huhtamaki India"),
    (r"\bdata patterns\b", "DATAPATTNS", "Data Patterns"),
    (r"\bkalyan jewell", "KALYANKJIL", "Kalyan Jewellers"),
    (r"\bcanara robeco\b", "CANARAROE", "Canara Robeco AMC"),
]

BULLISH_EVENTS: list[tuple[str, EventType, int]] = [
    (r"\b(?:revenue|sales|top[- ]line).{0,40}\b(?:beat|surge|jump|rise|grow|up|soars?)\b", "earnings_beat", 4),
    (r"\b(?:profit|pat|net profit|ebitda|ebit).{0,40}\b(?:beat|surge|jump|rise|grow|up|soars?)\b", "earnings_beat", 5),
    (r"\bebit soars?\b", "earnings_beat", 5),
    (r"\bmargin (?:expansion|improve|up)\b", "margin_expansion", 4),
    (r"\bguidance (?:raised|hike|upgrade|increase)\b", "guidance_raised", 5),
    (r"\border (?:win|bag|secure|wins|bags|secures)\b", "order_win", 5),
    (r"\b(?:contract|deal) (?:win|award|bag|secure)\b", "order_win", 5),
    (r"\b(?:bags?|wins?|secures?|awarded)\b.{0,40}\b(?:order|contract|deal|bid)\b", "order_win", 5),
    (r"\blowest bidder\b", "order_win", 5),
    (r"\bl1\b.{0,20}\bbid\b", "order_win", 5),
    (r"\bupgrades?\b.{0,30}\b(?:to )?['\"]?buy['\"]?\b", "broker_upgrade", 4),
    (r"\b(?:approval|clears?|cleared|nod)\b", "regulatory_approval", 4),
    (r"\b(?:acquisition|acquire|merger|amalgamation)\b", "m_and_a", 4),
    (r"\b(?:partnership|jv|joint venture|mou|tie[- ]?up)\b", "partnership", 3),
    (r"\b(?:capacity|plant|facility).{0,30}\b(?:expand|new|commission)\b", "capacity_expansion", 4),
    (r"\bbuyback\b", "buyback", 4),
    (r"\bbonus\b", "bonus", 3),
    (r"\bpromoter.{0,20}\b(?:buy|bought|purchase|increas)\b", "promoter_buying", 4),
    (r"\brating.{0,20}\b(?:upgrade|reaffirm|aaa|aa)\b", "credit_positive", 3),
    (r"\bfund raise|qip|preferential|fpo\b", "fundraising", 3),
    (r"\bstake sale\b", "stake_sale", 3),
]

BEARISH_EVENTS: list[tuple[str, EventType, int]] = [
    (r"\b(?:revenue|sales).{0,40}\b(?:miss|fall|drop|decline|down|slump)\b", "earnings_miss", 4),
    (r"\b(?:profit|pat|net profit|ebitda).{0,40}\b(?:miss|fall|drop|decline|down|slump|loss)\b", "earnings_miss", 5),
    (r"\bmargin (?:contraction|compress|decline|down)\b", "margin_contraction", 4),
    (r"\bguidance (?:cut|lower|slash|downgrade)\b", "guidance_cut", 5),
    (r"\b(?:sebi|nclt|ed|cbi).{0,40}\b(?:probe|notice|action|raid|penalty|ban)\b", "regulatory_action", 5),
    (r"\b(?:fraud|diversion|default|insolvency|bankruptcy)\b", "distress", 5),
    (r"\b(?:ceo|cfo|md|chairman).{0,30}\b(?:resign|quit|step(?:s|ped)? down)\b", "mgmt_exit", 4),
    (r"\brating.{0,20}\b(?:downgrade|cut|negative|watch)\b", "credit_negative", 4),
    (r"\bpromoter.{0,20}\b(?:sell|sold|pledge|dilut)\b", "promoter_selling", 4),
    (r"\b(?:loss|losses) (?:widen|mount|surge)\b", "earnings_miss", 4),
]


def _text(article: Article) -> str:
    return f"{article.title}\n{article.body}".lower()


def is_low_value(article: Article) -> tuple[bool, str]:
    text = _text(article)
    for pat in IGNORE_PATTERNS:
        if re.search(pat, text, re.I):
            return True, f"Matched ignore pattern: {pat}"
    # Pure price-recap with no catalyst language
    if re.search(r"\b(?:up|down|rise|fall|surge|plunge)\s+\d+(?:\.\d+)?%\b", text) and not any(
        re.search(p, text, re.I) for p, _, _ in BULLISH_EVENTS + BEARISH_EVENTS
    ):
        return True, "Price movement recap without new catalyst"
    return False, ""


def classify_article(article: Article) -> dict:
    text = _text(article)
    ignored, reason = is_low_value(article)
    if ignored:
        return {
            "keep": False,
            "reason": reason,
            "bias": "neutral",
            "event_type": "ignored",
            "base_strength": 0,
            "soft": False,
        }

    has_hard_numbers = bool(
        re.search(
            r"\b(?:revenue|sales|profit|pat|ebitda|ebit).{0,40}\b(?:\d|jump|soar|surge|beat|rise|fall|drop)\b",
            text,
            re.I,
        )
        or re.search(r"\b(?:lowest bidder|l1\b|₹\s*\d|rs\.?\s*\d)", text, re.I)
    )

    soft = False
    soft_type = None
    for pat, et in SOFT_PATTERNS:
        if re.search(pat, text, re.I):
            # Hard results / upgrades should not be buried as soft noise
            if has_hard_numbers and et in {"earnings_call_schedule", "concall_commentary", "broker_note"}:
                continue
            if et == "broker_note" and re.search(r"\bupgrades?\b.{0,30}\bbuy\b", text, re.I):
                continue
            soft = True
            soft_type = et
            break

    best_bias: Bias = "neutral"
    best_type: EventType = soft_type or "general_news"
    best_score = 1 if not soft else 0

    for pat, et, score in BULLISH_EVENTS:
        if re.search(pat, text, re.I) and score > best_score:
            best_bias, best_type, best_score = "bullish", et, score
    for pat, et, score in BEARISH_EVENTS:
        if re.search(pat, text, re.I) and score > best_score:
            best_bias, best_type, best_score = "bearish", et, score

    # P&L overrides topline when both directions appear (e.g. revenue up, profit down)
    profit_down = bool(
        re.search(
            r"\b(?:profit|pat|net profit|ebitda).{0,40}\b(?:miss|fall|falls|drop|decline|down|slump|loss)\b",
            text,
            re.I,
        )
    )
    profit_up = bool(
        re.search(
            r"\b(?:profit|pat|net profit|ebitda|ebit).{0,40}\b(?:beat|surge|jump|rise|rises|grow|up|soars?)\b",
            text,
            re.I,
        )
    )
    if profit_down and not profit_up:
        # Turnaround phrasing: "profit ₹6 cr vs ₹34 cr loss" is bullish, not a miss
        turnaround = bool(
            re.search(r"\b(?:profit|pat|net profit).{0,50}\bvs\b.{0,30}\bloss\b", text, re.I)
            or re.search(r"\bloss\b.{0,20}\bto\b.{0,20}\b(?:profit|pat)\b", text, re.I)
        )
        if turnaround:
            best_bias, best_type, best_score = "bullish", "earnings_beat", max(best_score, 5)
        else:
            best_bias, best_type, best_score = "bearish", "earnings_miss", max(best_score, 5)
    elif profit_up and not profit_down:
        best_bias, best_type, best_score = "bullish", "earnings_beat", max(best_score, 5)

    # Explicit surge language in title wins for direction
    if re.search(r"\b(?:revenue|sales).{0,30}\b(?:jumps?|soars?|surges?)\b", article.title, re.I) and best_bias != "bearish":
        best_bias = "bullish"
        best_score = max(best_score, 4)
        if best_type in {"ignored", "general_news", "sector_spillover"}:
            best_type = "earnings_beat"

    # Soft events alone stay weak
    if soft and best_type in {t for _, t in SOFT_PATTERNS}:
        best_score = min(best_score, 2)
        if best_bias == "neutral":
            if re.search(r"\bbuy|bought|purchase\b", text):
                best_bias = "bullish"
            elif re.search(r"\bsell|sold\b", text):
                best_bias = "bearish"

    # Source tier bump
    src = article.source.lower()
    if any(x in src for x in ("bse", "nse")) and "bulk" not in src and "block" not in src:
        best_score = min(5, best_score + 1)
    elif any(x in src for x in ("livesquawk", "scoutquest")):
        best_score = max(1, best_score)

    return {
        "keep": True,
        "reason": "",
        "bias": best_bias,
        "event_type": best_type,
        "base_strength": best_score,
        "soft": soft,
    }


@dataclass
class StockCatalyst:
    symbol: str
    name: str
    bias: Bias
    event_type: str
    strength: int  # 1-5
    articles: list[Article] = field(default_factory=list)
    soft: bool = False
    carryover: bool = False
    why: str = ""
    opening_impact: str = "Neutral"
    risks: str = ""
    sources: list[str] = field(default_factory=list)
    # Market overlay (filled by stock_enrich after news scoring)
    market_cap_cr: float | None = None
    sector: str = ""
    industry: str = ""
    avg_volume: int | None = None
    prev_day_chg_pct: float | None = None
    cap_tier: str = ""
    liquidity_tier: str = ""
    tradeability: str = ""
    # Precision layer
    filing_verified: bool = False
    filing_status: str = ""  # verified | soft_match | unverified | not_required
    filing_note: str = ""
    secondary_confirmed: bool = False
    conviction: int = 0
    size_hint: str = ""
    conviction_factors: list[str] = field(default_factory=list)
    oi_change_pct: float | None = None
    deal_summary: str = ""

    @property
    def stars(self) -> str:
        filled = "★" * self.strength
        empty = "☆" * (5 - self.strength)
        return filled + empty


def _is_carryover_candidate(article: Article, prev_close: datetime) -> bool:
    soft_start = datetime.combine(prev_close.date(), time(14, 30), tzinfo=IST)
    return soft_start <= article.published_at <= prev_close


def strength_label(n: int) -> str:
    return {
        5: "Extremely strong catalyst",
        4: "Strong catalyst",
        3: "Moderate catalyst",
        2: "Weak catalyst",
        1: "Very weak catalyst",
    }.get(n, "Unrated")


def _title_entity(article: Article) -> tuple[str, str] | None:
    title = article.title.lower()
    for pat, sym, name in TITLE_ENTITY_MAP:
        if re.search(pat, title, re.I):
            return sym, name
    return None


def resolve_article_targets(article: Article) -> list[dict[str, str]]:
    """
    Map an article to one or more stocks.
    Groww often tags peer CTAs (e.g. Titan/Kalyan) on a Bluestone headline —
    use the title company as primary and CTAs as peer spillover.
    """
    title_hit = _title_entity(article)
    cta_keys: list[tuple[str, str]] = []
    for s in article.stocks:
        key = (s.get("nse") or s.get("bse") or s.get("name") or "").upper()
        if not key:
            continue
        cta_keys.append((key, s.get("name") or key))

    if title_hit:
        t_sym, t_name = title_hit
        targets = [{"symbol": t_sym, "name": t_name, "role": "primary"}]
        for key, name in cta_keys:
            if key == t_sym:
                continue
            # Peer mentioned in body as reacting / sector
            targets.append({"symbol": key, "name": name, "role": "peer_spillover"})
        return targets

    if cta_keys:
        return [{"symbol": cta_keys[0][0], "name": cta_keys[0][1], "role": "primary"}]
    return [{"symbol": "UNKNOWN", "name": "Unknown", "role": "primary"}]


def _has_mixed_quality_hedges(text: str) -> bool:
    """Bullish print with explicit demand/geo/margin hedges → lower opening conviction."""
    return bool(
        re.search(
            r"\b(?:weak international|war[- ]related|despite .{0,40}challenge|offsets? weak|"
            r"margin pressure|cost pressure|one[- ]off|below estimate|missed .{0,20}estimate)\b",
            text,
            re.I,
        )
    )


def _already_moved_in_headlines(text: str) -> bool:
    """Prior-session surge language ⇒ next open is often fade/digest, not fresh gap."""
    return bool(
        re.search(
            r"\b(?:surges?|jumps?|soars?|rall(?:y|ies)|gains?)\s+\d+(?:\.\d+)?%\b|"
            r"\bstock soars\b|\bshares (?:surge|jump|soar)\b",
            text,
            re.I,
        )
    )


def opening_from_strength(
    bias: Bias,
    strength: int,
    soft: bool,
    event_type: str = "",
    *,
    carryover: bool = False,
    priced_in: bool = False,
    mixed_quality: bool = False,
) -> str:
    if bias == "neutral" or strength <= 1:
        return "Neutral"
    if soft and strength <= 2:
        return "Mild Positive" if bias == "bullish" else "Mild Negative"

    # Sell-the-news / digest setups: strong catalyst already in motion
    if bias == "bullish" and (carryover or priced_in) and event_type in {
        "earnings_beat",
        "guidance_raised",
        "broker_upgrade",
        "margin_expansion",
    }:
        if mixed_quality or priced_in:
            return "Watch for Fade"
        return "Mild Positive"

    if bias == "bullish" and mixed_quality and strength >= 3:
        return "Mild Positive"

    if bias == "bullish" and strength >= 4 and event_type in {
        "earnings_beat",
        "order_win",
        "broker_upgrade",
        "guidance_raised",
    }:
        return "Gap Up Likely"
    table = {
        ("bullish", 5): "Gap Up Likely",
        ("bullish", 4): "Gap Up Likely",
        ("bullish", 3): "Mild Positive",
        ("bullish", 2): "Watch for Breakout",
        ("bearish", 5): "Gap Down Risk",
        ("bearish", 4): "Gap Down Risk",
        ("bearish", 3): "Mild Negative",
        ("bearish", 2): "Mild Negative",
    }
    return table.get((bias, strength), "Neutral")


def consolidate(articles: list[Article], prev_close: datetime) -> tuple[list[StockCatalyst], list[dict]]:
    ignored: list[dict] = []
    buckets: dict[str, list[tuple[Article, dict, str, str]]] = {}
    # value: article, meta, display_name, role

    for art in articles:
        meta = classify_article(art)
        if not meta["keep"]:
            ignored.append(
                {
                    "title": art.title,
                    "symbol": art.primary_symbol,
                    "reason": meta["reason"],
                    "published_at": art.published_at.isoformat(),
                }
            )
            continue

        for target in resolve_article_targets(art):
            m = dict(meta)
            role = target["role"]
            if role == "peer_spillover":
                # Inherit story direction; peer reaction to positive peer news is bullish
                if m["bias"] == "bearish" and re.search(
                    r"\b(?:jumps?|soars?|surges?|beat|win|wins)\b", art.title, re.I
                ):
                    m["bias"] = "bullish"
                if m["bias"] == "neutral":
                    m["bias"] = "bullish"
                m["event_type"] = "sector_spillover"
                m["base_strength"] = min(3, max(2, int(m["base_strength"]) - 1))
                m["soft"] = True
            key = target["symbol"].upper()
            buckets.setdefault(key, []).append((art, m, target["name"], role))

    catalysts: list[StockCatalyst] = []
    for key, items in buckets.items():
        items_sorted = sorted(items, key=lambda x: x[1]["base_strength"], reverse=True)
        arts = [a for a, _, _, _ in items_sorted]
        metas = [m for _, m, _, _ in items_sorted]
        name = items_sorted[0][2]

        bias: Bias = "neutral"
        best = -1
        event_type = "general_news"
        soft = all(m["soft"] for m in metas)
        hard_biases = [m for m in metas if not m["soft"] and m["bias"] in {"bullish", "bearish"}]
        pool = hard_biases or metas
        for m in pool:
            score = m["base_strength"]
            prefer = False
            if score > best:
                prefer = True
            elif score == best:
                if m["bias"] == "bearish" and bias != "bearish":
                    prefer = True
                if m["event_type"] == "earnings_miss" and event_type == "earnings_beat":
                    prefer = True
            if prefer:
                best = score
                bias = m["bias"]  # type: ignore
                event_type = m["event_type"]
            if not m["soft"]:
                soft = False

        joined = " ".join(f"{a.title} {a.body}" for a in arts).lower()
        if re.search(r"\b(?:profit|pat|ebitda).{0,40}\b(?:fall|falls|drop|decline|down|miss)\b", joined) and not re.search(
            r"\b(?:profit|pat|ebitda|ebit).{0,40}\b(?:beat|surge|jump|rise|up|soar)\b", joined
        ):
            # Only force miss if this stock is the subject, not a peer spillover-only bucket
            roles = {r for _, _, _, r in items}
            if "primary" in roles:
                bias, event_type = "bearish", "earnings_miss"
                best = max(best, 4)

        bump = 1 if len(items) >= 3 and best >= 3 else 0
        # Earnings + broker upgrade confirmation
        if any(m["event_type"] == "earnings_beat" for m in metas) and any(
            m["event_type"] == "broker_upgrade" for m in metas
        ):
            bump = max(bump, 1)
        strength = min(5, max(1, best + bump))

        if soft and event_type in {
            "bulk_deal",
            "block_deal",
            "broker_note",
            "earnings_call_schedule",
            "concall_commentary",
            "sector_spillover",
        }:
            strength = min(strength, 3 if event_type == "sector_spillover" else 2)

        carryover = any(getattr(a, "soft_close", False) or _is_carryover_candidate(a, prev_close) for a in arts)
        evening = datetime.combine(prev_close.date(), time(18, 0), tzinfo=IST)
        if any(prev_close < a.published_at <= evening for a in arts) and strength >= 3:
            carryover = True

        titles = "; ".join(a.title for a in arts[:4])
        roles = sorted({r for _, _, _, r in items})
        why = f"{len(arts)} related item(s)"
        if "peer_spillover" in roles and "primary" not in roles:
            why = f"Peer/sector spillover from related headlines. {titles}"
        else:
            why = f"{len(arts)} related item(s). Primary: {titles}"
        sources = sorted({a.source for a in arts})

        joined_full = " ".join(f"{a.title} {a.body}" for a in arts)
        mixed_quality = _has_mixed_quality_hedges(joined_full)
        already_moved = _already_moved_in_headlines(joined_full)
        # Fresh catalyst after evening prior day / morning of session
        fresh_overnight = any(a.published_at > evening for a in arts)
        # Sell-the-news only when hedges exist or stock already surged on the print
        priced_in = (already_moved and not fresh_overnight) or (carryover and mixed_quality)

        if mixed_quality and bias == "bullish" and strength >= 4:
            strength = max(3, strength - 1)

        risks = "Single-source paraphrase; verify exchange filing before sizing."
        if soft:
            risks = "Soft/commentary signal — may already be priced or lack follow-through."
        if event_type in {"bulk_deal", "block_deal"}:
            risks = "Bulk/block prints are often non-directional noise."
        if event_type == "partnership":
            risks = "MoU/partnership headlines frequently lack near-term P&L impact."
        if event_type == "sector_spillover":
            risks = "Peer reaction only — confirm stock-specific catalyst before sizing."
        if carryover and not fresh_overnight:
            risks = (risks + " Late prior-session print — part of move may already be in.").strip()
        if priced_in and bias == "bullish":
            risks = "Sell-the-news risk: catalyst already circulating; open can fade despite good numbers."
        if mixed_quality and bias == "bullish":
            risks = "Mixed-quality beat — hedges in the print (geo/demand/margins) can cap follow-through."

        opening = opening_from_strength(
            bias,
            strength,
            soft,
            event_type,
            carryover=carryover and not fresh_overnight,
            priced_in=priced_in,
            mixed_quality=mixed_quality,
        )

        catalysts.append(
            StockCatalyst(
                symbol=key,
                name=name,
                bias=bias,
                event_type=event_type,
                strength=strength,
                articles=arts,
                soft=soft,
                carryover=carryover,
                why=why,
                opening_impact=opening,
                risks=risks,
                sources=sources,
            )
        )

    catalysts.sort(key=lambda c: (c.strength, len(c.articles)), reverse=True)
    return catalysts, ignored