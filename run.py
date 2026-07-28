#!/usr/bin/env python3
"""Run one pre-market analysis pass and write the morning note."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from premarket.analyze import enrich_top_catalysts, market_view_llm, ollama_available
from premarket.calendar_nse import IST, previous_market_close
from premarket.filters import consolidate
from premarket.groww_feed import fetch_since
from premarket.global_cues import adjust_view_with_global, fetch_global_cues, sector_global_flags
from premarket.market_context import adjust_market_view, fetch_market_tape
from premarket.report import build_market_view, render_report
from premarket.stock_enrich import apply_market_overlay, fetch_stock_data


def main() -> int:
    parser = argparse.ArgumentParser(description="NSE pre-market news analyzer")
    parser.add_argument("--no-llm", action="store_true", help="Skip Ollama enrichment")
    parser.add_argument("--out", default="reports", help="Output directory")
    args = parser.parse_args()

    now = datetime.now(IST)
    cutoff = previous_market_close(now.date())
    print(f"[premarket] Now IST: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[premarket] Previous NSE close cutoff: {cutoff.isoformat()}")
    print("[premarket] Fetching Groww feed…")

    articles, feed_stats = fetch_since(cutoff)
    print(
        f"[premarket] Window articles={feed_stats['articles_in_window']} "
        f"pages={feed_stats['pages_fetched']} stop={feed_stats['stopped_reason']}"
    )

    catalysts, ignored = consolidate(articles, cutoff)
    print(f"[premarket] Catalysts={len(catalysts)} ignored={len(ignored)}")

    print("[premarket] Fetching NSE tape, GIFT Nifty & global cues…")
    market_tape = fetch_market_tape()
    global_tape = fetch_global_cues(nifty_cash_last=market_tape.nifty.last)
    top_symbols = [c.symbol for c in sorted(catalysts, key=lambda x: x.strength, reverse=True)[:20]]
    stock_data = fetch_stock_data(top_symbols)
    gift_gap = global_tape.gift_nifty.implied_gap_vs_nifty_pct
    if gift_gap is None:
        gift_gap = global_tape.gift_nifty.change_pct
    if gift_gap is None:
        gift_gap = global_tape.implied_nifty_open_pct
    catalysts = apply_market_overlay(
        catalysts,
        stock_data,
        market_tape,
        sector_flags=sector_global_flags(global_tape),
        global_gap_pct=gift_gap,
    )
    if market_tape.flows.fii_net_cr is not None:
        print(
            f"[premarket] Flows FII {market_tape.flows.fii_net_cr:+.0f} Cr "
            f"DII {(market_tape.flows.dii_net_cr or 0):+.0f} Cr — {market_tape.flow_bias}"
        )
    if global_tape.gift_nifty.last is not None:
        gap_txt = f"{gift_gap:+.2f}%" if gift_gap is not None else "n/a"
        print(
            f"[premarket] GIFT {global_tape.gift_nifty.last:.2f} ({gap_txt}) — "
            f"{global_tape.gift_nifty.open_bias} / {global_tape.composite_risk}"
        )

    use_llm = not args.no_llm and ollama_available()
    llm_view = None
    if use_llm:
        print("[premarket] Enriching top catalysts with Ollama qwen2.5:7b…")
        brief = (
            f"GIFT={global_tape.gift_nifty.open_bias} gap={gift_gap} risk={global_tape.composite_risk} "
            f"US={global_tape.us_futures_bias} VIX={market_tape.volatility_regime}"
        )
        catalysts = enrich_top_catalysts(catalysts, limit=8, global_context=brief)
        bullish = [c for c in catalysts if c.bias == "bullish"]
        bearish = [c for c in catalysts if c.bias == "bearish"]
        llm_view = market_view_llm(bullish, bearish, global_context=brief)
    else:
        print("[premarket] LLM unavailable or disabled — heuristic report only")

    bullish = [c for c in catalysts if c.bias == "bullish"]
    bearish = [c for c in catalysts if c.bias == "bearish"]
    view = adjust_market_view(build_market_view(bullish, bearish, llm_view), market_tape)
    view = adjust_view_with_global(view, global_tape)

    report = render_report(
        cutoff=cutoff,
        feed_stats=feed_stats,
        catalysts=catalysts,
        ignored=ignored,
        llm_view=llm_view,
        market_tape=market_tape,
        global_tape=global_tape,
        generated_at=now,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M")
    md_path = out_dir / f"premarket_{stamp}.md"
    json_path = out_dir / f"premarket_{stamp}.json"
    md_path.write_text(report, encoding="utf-8")

    payload = {
        "generated_at": now.isoformat(),
        "cutoff": cutoff.isoformat(),
        "feed_stats": feed_stats,
        "ignored_count": len(ignored),
        "market_tape": market_tape.to_dict(),
        "global_tape": global_tape.to_dict(),
        "market_view": view,
        "catalysts": [
            {
                "symbol": c.symbol,
                "name": c.name,
                "bias": c.bias,
                "event_type": c.event_type,
                "strength": c.strength,
                "opening_impact": c.opening_impact,
                "why": c.why,
                "risks": c.risks,
                "carryover": c.carryover,
                "sources": c.sources,
                "headlines": [a.title for a in c.articles],
                "market_cap_cr": c.market_cap_cr,
                "prev_day_chg_pct": c.prev_day_chg_pct,
                "cap_tier": c.cap_tier,
                "liquidity_tier": c.liquidity_tier,
                "sector": c.sector,
                "tradeability": c.tradeability,
            }
            for c in catalysts
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print()
    print(report)
    print(f"[premarket] Wrote {md_path}")
    print(f"[premarket] Wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
