"""Morning research note renderer."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .calendar_nse import IST, format_close
from .filters import StockCatalyst, strength_label
from .global_cues import GlobalTape
from .market_context import MarketTape


def _fmt_mcap(cr: float | None) -> str:
    if cr is None:
        return "n/a"
    if cr >= 100_000:
        return f"₹{cr/100_000:.1f}L Cr"
    return f"₹{cr:,.0f} Cr"


def _market_line(c: StockCatalyst) -> str:
    parts: list[str] = []
    if c.cap_tier:
        parts.append(c.cap_tier)
    if c.market_cap_cr:
        parts.append(_fmt_mcap(c.market_cap_cr))
    if c.sector:
        parts.append(c.sector)
    if c.prev_day_chg_pct is not None:
        parts.append(f"prior {c.prev_day_chg_pct:+.1f}%")
    if c.liquidity_tier:
        parts.append(f"liq {c.liquidity_tier}")
    if c.tradeability:
        parts.append(c.tradeability)
    return " · ".join(parts) if parts else ""


def _global_section(gt: GlobalTape | None) -> list[str]:
    if not gt:
        return []
    lines = ["## Global Cues & GIFT Nifty", ""]
    g = gt.gift_nifty
    if g.last is not None:
        gap = g.implied_gap_vs_nifty_pct if g.implied_gap_vs_nifty_pct is not None else g.change_pct
        gap_s = f"{gap:+.2f}%" if gap is not None else "n/a"
        lines.append(
            f"- **GIFT Nifty:** **{g.last:,.2f}** ({gap_s}) — _{g.open_bias}_"
            + (f" · expiry {g.expiry}" if g.expiry else "")
            + " · NSE IX"
        )
    elif gt.implied_nifty_open_pct is not None:
        lines.append(f"- **Implied Nifty open (model):** {gt.implied_nifty_open_pct:+.2f}%")
    lines.append(f"- **Composite risk:** _{gt.composite_risk}_")
    cue_bits = []
    for c in gt.cues:
        if c.change_pct is None:
            continue
        short = c.name.replace(" Futures", "").replace(" Index", "")
        cue_bits.append(f"{short} {c.change_pct:+.2f}%")
    if cue_bits:
        lines.append(f"- **Strip:** {', '.join(cue_bits[:8])}")
    for note in gt.interpretation[:4]:
        lines.append(f"- {note}")
    if gt.errors:
        lines.append(f"- _Cue warnings: {'; '.join(gt.errors[:2])}_")
    lines.append("")
    return lines


def _tape_section(tape: MarketTape | None) -> list[str]:
    if not tape:
        return []
    lines = ["## Market Tape (NSE)", ""]
    f = tape.flows
    if f.fii_net_cr is not None:
        lines.append(
            f"- **Flows ({f.date or 'prior session'}):** FII net **{f.fii_net_cr:+,.0f} Cr**, "
            f"DII net **{(f.dii_net_cr or 0):+,.0f} Cr** — _{tape.flow_bias}_"
        )
    if tape.nifty.change_pct is not None:
        lines.append(
            f"- **Nifty 50:** {tape.nifty.change_pct:+.2f}%"
            + (f" ({tape.nifty.last:,.2f})" if tape.nifty.last else "")
        )
    if tape.bank_nifty.change_pct is not None:
        lines.append(f"- **Bank Nifty:** {tape.bank_nifty.change_pct:+.2f}%")
    if tape.india_vix.last is not None:
        lines.append(
            f"- **India VIX:** {tape.india_vix.last:.2f} ({tape.india_vix.change_pct:+.1f}% d/d) — _{tape.volatility_regime}_"
        )
    if tape.sector_leaders:
        sec = ", ".join(
            f"{s['index']} {s['change_pct']:+.1f}%"
            for s in tape.sector_leaders[:4]
            if s.get("change_pct") is not None
        )
        if sec:
            lines.append(f"- **Sector moves:** {sec}")
    for note in tape.interpretation[:4]:
        lines.append(f"- {note}")
    if tape.errors:
        lines.append(f"- _Data warnings: {'; '.join(tape.errors[:2])}_")
    lines.append("")
    return lines


def _cat_block(c: StockCatalyst) -> str:
    headlines = "\n".join(f"  - {a.title} ({a.published_at.strftime('%d %b %H:%M')} IST, {a.source})" for a in c.articles[:5])
    mkt = _market_line(c)
    mkt_block = f"- **Market context:** {mkt}\n" if mkt else ""
    filing = ""
    if getattr(c, "filing_status", ""):
        filing = f"- **Filing:** {c.filing_status}" + (f" — {c.filing_note}" if c.filing_note else "") + "\n"
    conv = ""
    if getattr(c, "conviction", 0):
        conv = f"- **Conviction:** {c.conviction}/100 · **Size:** {c.size_hint}\n"
    return f"""### {c.name} (`{c.symbol}`)
- **Catalyst:** {c.event_type.replace('_', ' ')}
- **Why it matters:** {c.why}
- **Opening impact:** {c.opening_impact}
- **Catalyst strength:** {c.stars} — {strength_label(c.strength)}
{conv}{filing}{mkt_block}- **Risks:** {c.risks}
- **Sources:** {', '.join(c.sources) or 'n/a'}
- **Headlines:**
{headlines}
"""


def _precision_section(precision: dict[str, Any] | None) -> list[str]:
    if not precision:
        return []
    lines = ["## Precision Layer", ""]
    lines.append(
        f"- **NSE filings:** scanned {precision.get('filings_scanned', 0)}; "
        f"verified {precision.get('filings_verified', 0)} catalysts"
    )
    sec = precision.get("secondary") or {}
    if sec:
        lines.append(
            f"- **Secondary wire ({sec.get('source')}):** {sec.get('confirmed', 0)}/{sec.get('top_checked', 0)} top names confirmed"
        )
    adr = precision.get("adr_tape") or {}
    if adr.get("composite_pct") is not None:
        lines.append(
            f"- **India ADRs:** {adr['composite_pct']:+.2f}% (IT {adr.get('it_bias')}, Banks {adr.get('banks_bias')})"
        )
    fo = precision.get("fo_overlay") or {}
    if fo.get("fo_bias"):
        lines.append(f"- **FO/fear overlay:** {fo.get('fo_bias')}")
        for note in (fo.get("interpretation") or [])[:2]:
            lines.append(f"  - {note}")
    fo_flow = precision.get("fo_flow") or {}
    if fo_flow.get("nifty_oi_chg_pct") is not None:
        lines.append(f"- **Nifty OI change:** {fo_flow['nifty_oi_chg_pct']:+.1f}%")
        for note in (fo_flow.get("interpretation") or [])[:2]:
            lines.append(f"  - {note}")
    deals = precision.get("deals") or {}
    if deals.get("bulk_count") is not None:
        lines.append(
            f"- **Large deals:** {deals.get('bulk_count', 0)} bulk / {deals.get('block_count', 0)} block ({deals.get('as_on') or 'n/a'})"
        )
    pre = precision.get("preopen") or {}
    if pre.get("auction_phase"):
        lines.append(f"- **Auction phase:** {pre.get('auction_phase')} ({pre.get('market_status') or ''})")
        if pre.get("gift_last") is not None:
            gchg = pre.get("gift_change_pct")
            gchg_s = f" ({gchg:+.2f}%)" if gchg is not None else ""
            lines.append(f"- **GIFT (live status):** {pre['gift_last']:,.0f}{gchg_s}")
    ev = precision.get("event_context") or {}
    if ev.get("regime"):
        lines.append(f"- **Event regime:** {ev.get('regime')}")
        for note in (ev.get("interpretation") or [])[:2]:
            lines.append(f"  - {note}")
    lines.append("")
    return lines


def build_market_view(
    bullish: list[StockCatalyst],
    bearish: list[StockCatalyst],
    llm_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if llm_view:
        return {
            "bias": llm_view.get("bias", "Mixed"),
            "confidence": llm_view.get("confidence_1_to_10", 5),
            "reasons": llm_view.get("reasons") or [],
            "opportunity": llm_view.get("biggest_opportunity", ""),
            "risk": llm_view.get("biggest_risk", ""),
        }

    b_score = sum(c.strength for c in bullish[:8])
    s_score = sum(c.strength for c in bearish[:8])
    if b_score > s_score + 3:
        bias = "Bullish"
    elif s_score > b_score + 3:
        bias = "Bearish"
    else:
        bias = "Mixed"
    conf = max(3, min(8, abs(b_score - s_score) + 3))
    reasons = []
    if bullish:
        reasons.append(f"Top bullish flow: {', '.join(c.symbol for c in bullish[:3])}")
    if bearish:
        reasons.append(f"Top bearish flow: {', '.join(c.symbol for c in bearish[:3])}")
    reasons.append(f"Strength sum bullish={b_score} vs bearish={s_score}")
    return {
        "bias": bias,
        "confidence": conf,
        "reasons": reasons,
        "opportunity": bullish[0].name if bullish else "None clear",
        "risk": bearish[0].name if bearish else "None clear",
    }


def render_report(
    *,
    cutoff: datetime,
    feed_stats: dict[str, Any],
    catalysts: list[StockCatalyst],
    ignored: list[dict],
    llm_view: dict[str, Any] | None = None,
    market_tape: MarketTape | None = None,
    global_tape: GlobalTape | None = None,
    precision: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now(IST)
    # Prefer conviction ranking when available
    ranked = sorted(catalysts, key=lambda c: (getattr(c, "conviction", 0), c.strength), reverse=True)
    bullish = [c for c in ranked if c.bias == "bullish" and c.strength >= 3][:8]
    bearish = [c for c in ranked if c.bias == "bearish" and c.strength >= 3][:8]
    if len(bullish) < 5:
        extra = [c for c in ranked if c.bias == "bullish" and c not in bullish]
        bullish = (bullish + extra)[:6]
    if len(bearish) < 5:
        extra = [c for c in ranked if c.bias == "bearish" and c not in bearish]
        bearish = (bearish + extra)[:6]

    carry = [c for c in catalysts if c.carryover and c.strength >= 2][:6]
    soft_ignored = [i for i in ignored[:15]]
    view = build_market_view(bullish, bearish, llm_view)

    unique_stocks = len({c.symbol for c in catalysts})
    lines = [
        "# Pre-Market Research Note — NSE",
        f"_Generated: {generated_at.strftime('%d %b %Y %H:%M IST')}_",
        "",
        "## News Window",
        "",
        "**Previous NSE Close:**",
        f"{format_close(cutoff)}",
        "",
        f"- Articles processed (in window): **{feed_stats.get('articles_in_window', 0)}**",
        f"- Pages fetched: **{feed_stats.get('pages_fetched', 0)}** (stop: {feed_stats.get('stopped_reason')})",
        f"- Unique stocks with catalysts: **{unique_stocks}**",
        f"- Intentionally excluded: **{len(ignored)}**",
        "",
    ]
    lines += _global_section(global_tape)
    lines += _tape_section(market_tape)
    lines += _precision_section(precision)
    lines += [
        "## Overall Market View",
        "",
        f"**Bias:** {view['bias']}  ",
        f"**Confidence:** {view['confidence']}/10",
        "",
        "**Reasons:**",
    ]
    for r in view["reasons"]:
        lines.append(f"- {r}")
    lines += [
        "",
        f"**Biggest opportunity:** {view['opportunity']}",
        f"**Biggest risk:** {view['risk']}",
        "",
        "## Top Bullish Stocks",
        "",
    ]
    if not bullish:
        lines.append("_No high-conviction bullish catalysts in window._")
    else:
        for c in bullish:
            lines.append(_cat_block(c))

    lines += ["## Top Bearish Stocks", ""]
    if not bearish:
        lines.append("_No high-conviction bearish catalysts in window._")
    else:
        for c in bearish:
            lines.append(_cat_block(c))

    lines += ["## Momentum Carryover", ""]
    if not carry:
        lines.append("_No clear late-session / early post-close carryover names flagged._")
    else:
        for c in carry:
            lines.append(
                f"- **{c.name} (`{c.symbol}`)** — {c.event_type}, {c.stars}; "
                f"catalyst may still be digesting into the open."
            )
        lines.append("")

    lines += ["## Sector / Theme Watch", ""]
    themes: dict[str, list[str]] = {}
    for c in catalysts[:30]:
        if c.strength < 3:
            continue
        themes.setdefault(c.event_type, []).append(c.symbol)
    if not themes:
        lines.append("_No clustered themes above moderate strength._")
    else:
        for et, syms in sorted(themes.items(), key=lambda x: -len(x[1]))[:8]:
            lines.append(f"- **{et.replace('_', ' ').title()}:** {', '.join(syms[:8])}")
    lines.append("")

    lines += ["## Neutral / Ignored (sample)", ""]
    if not soft_ignored:
        lines.append("_Nothing excluded._")
    else:
        for i in soft_ignored[:12]:
            lines.append(f"- {i.get('symbol') or '—'}: {i.get('title')} — _{i.get('reason')}_")
    lines += [
        "",
        "---",
        "_Desk note: filings + GIFT + conviction scored. Verify Tier-A filings before trading._",
        "",
    ]
    return "\n".join(lines)

