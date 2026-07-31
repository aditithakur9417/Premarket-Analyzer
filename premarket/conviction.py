"""Conviction 0–100 and suggested position size for each catalyst."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .filters import HIGH_IMPACT_GAP_TYPES, StockCatalyst, sort_by_priority


OPENING_SCORE = {
    "Gap Up Likely": 18,
    "Watch for Breakout": 12,
    "Mild Positive": 8,
    "Neutral": 0,
    "Mild Negative": 8,
    "Watch for Fade": 4,
    "Gap Down Risk": 18,
}

# Expected open gap midpoint (%) by predicted label — for calibration MAE
EXPECTED_GAP_PCT = {
    "Gap Up Likely": 2.5,
    "Watch for Breakout": 1.0,
    "Mild Positive": 0.7,
    "Neutral": 0.0,
    "Watch for Fade": 0.3,
    "Mild Negative": -0.7,
    "Gap Down Risk": -2.5,
}


@dataclass
class ConvictionResult:
    conviction: int  # 0-100
    size_hint: str  # e.g. 1.0R, 0.5R, skip
    factors: list[str]


def score_catalyst(
    c: StockCatalyst,
    *,
    gift_gap_pct: float | None = None,
    event_regime: str = "Normal",
    global_risk: str = "Neutral",
) -> ConvictionResult:
    score = 20  # base
    factors: list[str] = []

    # Strength ★
    score += int(c.strength) * 8
    factors.append(f"strength {c.strength}/5")

    # High-move corporate event types
    if c.event_type in HIGH_IMPACT_GAP_TYPES and c.bias in {"bullish", "bearish"}:
        score += 8
        factors.append(f"high-move:{c.event_type}")

    # Opening impact alignment
    score += OPENING_SCORE.get(c.opening_impact, 0)
    if c.opening_impact:
        factors.append(c.opening_impact)

    # Filing verification
    status = getattr(c, "filing_status", "") or ""
    if status == "verified":
        score += 18
        factors.append("NSE filing verified")
    elif status == "unverified":
        score -= 14
        factors.append("unverified filing")
    elif status == "soft_match":
        score -= 4
        factors.append("soft filing match")

    if getattr(c, "secondary_confirmed", False):
        score += 6
        factors.append("secondary news confirm")

    # Liquidity / cap
    if c.liquidity_tier == "High":
        score += 8
        factors.append("high liquidity")
    elif c.liquidity_tier == "Thin":
        score -= 12
        factors.append("thin liquidity")
    elif c.liquidity_tier == "Low":
        score -= 6
        factors.append("low liquidity")

    if c.cap_tier == "Large":
        score += 6
    elif c.cap_tier == "Micro":
        score -= 10
        factors.append("micro-cap")
    elif c.cap_tier == "Small":
        score -= 4

    # Prior move (already priced)
    if c.prev_day_chg_pct is not None:
        if c.bias == "bullish" and c.prev_day_chg_pct >= 6:
            score -= 12
            factors.append(f"already +{c.prev_day_chg_pct:.1f}%")
        elif c.bias == "bearish" and c.prev_day_chg_pct <= -6:
            score -= 10
            factors.append(f"already {c.prev_day_chg_pct:.1f}%")

    # GIFT / global alignment
    if gift_gap_pct is not None:
        if c.bias == "bullish" and gift_gap_pct >= 0.3:
            score += 8
            factors.append("GIFT aligned")
        elif c.bias == "bullish" and gift_gap_pct <= -0.3:
            score -= 10
            factors.append("GIFT headwind")
        elif c.bias == "bearish" and gift_gap_pct <= -0.3:
            score += 8
            factors.append("GIFT aligned")
        elif c.bias == "bearish" and gift_gap_pct >= 0.3:
            score -= 8
            factors.append("GIFT squeeze risk")

    if global_risk in {"Risk-Off", "Mild Risk-Off"} and c.bias == "bullish":
        score -= 6
    if global_risk in {"Risk-On", "Mild Risk-On"} and c.bias == "bearish":
        score -= 4

    if event_regime in {"Event Risk", "Expiry"}:
        score -= 8
        factors.append(f"regime {event_regime}")

    if c.soft:
        score -= 6
        factors.append("soft signal")
    if c.carryover and c.opening_impact == "Watch for Fade":
        score -= 4

    oi = getattr(c, "oi_change_pct", None)
    if oi is not None and abs(oi) >= 15:
        score += 4 if (c.bias == "bullish" and oi > 0) or (c.bias == "bearish" and oi < 0) else 0
        factors.append(f"OI {oi:+.0f}%")

    if getattr(c, "deal_summary", ""):
        if "S" in c.deal_summary and c.bias == "bullish":
            score -= 5
            factors.append("block/bulk sellers")
        else:
            factors.append(c.deal_summary)

    score = max(0, min(100, score))

    # Size hint — 1.0R requires verified filing + decent liquidity
    if (
        score >= 75
        and c.liquidity_tier in {"High", "Medium", ""}
        and status == "verified"
        and event_regime not in {"Event Risk", "Expiry"}
    ):
        size = "1.0R"
    elif score >= 60 and status != "unverified":
        size = "0.75R"
    elif score >= 45:
        size = "0.5R"
    elif score >= 30:
        size = "0.25R / watch"
    else:
        size = "Skip / observe"

    if c.liquidity_tier == "Thin" and size.startswith("1"):
        size = "0.5R"
        factors.append("size capped for thin book")
    if status == "unverified" and size in {"1.0R", "0.75R"}:
        size = "0.5R"
        factors.append("size capped — unverified")

    return ConvictionResult(conviction=score, size_hint=size, factors=factors[:6])


def apply_conviction(
    catalysts: list[StockCatalyst],
    *,
    gift_gap_pct: float | None = None,
    event_regime: str = "Normal",
    global_risk: str = "Neutral",
) -> list[StockCatalyst]:
    for c in catalysts:
        res = score_catalyst(
            c,
            gift_gap_pct=gift_gap_pct,
            event_regime=event_regime,
            global_risk=global_risk,
        )
        c.conviction = res.conviction
        c.size_hint = res.size_hint
        c.conviction_factors = res.factors
    return sort_by_priority(catalysts)
