"""Stock-level market data overlay (cap, liquidity, prior session move)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .market_context import MarketTape

# Lazy import — yfinance is optional at import time
_yf_module = None


def _get_yf():
    global _yf_module
    if _yf_module is None:
        import yfinance as yf_mod

        _yf_module = yf_mod
    return _yf_module


def nse_yahoo_symbol(symbol: str) -> str:
    """Map NSE symbol to Yahoo Finance ticker."""
    sym = symbol.upper().strip()
    if sym.endswith(".NS"):
        return sym
    # Yahoo handles most NSE symbols with .NS; & is valid in tickers (e.g. M&MFIN.NS)
    return f"{sym}.NS"


@dataclass
class StockMarketData:
    symbol: str
    market_cap_cr: float | None = None
    sector: str = ""
    industry: str = ""
    avg_volume: int | None = None
    prev_close: float | None = None
    last_close: float | None = None
    prev_day_chg_pct: float | None = None
    cap_tier: str = ""
    liquidity_tier: str = ""
    tradeability: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cap_tier(mcap_inr: float | None) -> str:
    if mcap_inr is None:
        return "Unknown"
    cr = mcap_inr / 1e7  # INR to Cr (1 Cr = 10^7)
    if cr >= 100_000:
        return "Large"
    if cr >= 20_000:
        return "Mid"
    if cr >= 5_000:
        return "Small"
    return "Micro"


def _liquidity_tier(avg_vol: int | None, mcap_inr: float | None) -> str:
    if avg_vol is None:
        return "Unknown"
    if avg_vol >= 1_000_000:
        return "High"
    if avg_vol >= 250_000:
        return "Medium"
    if avg_vol >= 75_000:
        return "Low"
    return "Thin"


def _tradeability_note(cap: str, liq: str, chg: float | None) -> str:
    parts: list[str] = []
    if cap == "Micro":
        parts.append("Micro-cap — wide spreads, gap risk high")
    elif cap == "Small" and liq in {"Low", "Thin"}:
        parts.append("Small + illiquid — size down on opening prints")
    elif cap == "Large" and liq == "High":
        parts.append("Institutional liquidity — gaps more tradeable")
    if chg is not None:
        if chg >= 8:
            parts.append(f"Already +{chg:.1f}% prior session — sell-the-news risk")
        elif chg <= -8:
            parts.append(f"Already {chg:.1f}% prior session — may be oversold bounce setup")
    return "; ".join(parts) if parts else ""


def fetch_stock_data(symbols: list[str]) -> dict[str, StockMarketData]:
    """Batch-fetch Yahoo data for NSE symbols. Best-effort."""
    out: dict[str, StockMarketData] = {}
    if not symbols:
        return out

    yf = _get_yf()
    tickers = [nse_yahoo_symbol(s) for s in symbols]
    # Map yahoo ticker back to NSE symbol
    rev = {nse_yahoo_symbol(s): s.upper() for s in symbols}

    try:
        objs = yf.Tickers(" ".join(tickers))
    except Exception:
        return out

    for yt, nse_sym in rev.items():
        try:
            t = objs.tickers.get(yt) or yf.Ticker(yt)
            info = getattr(t, "fast_info", None)
            mcap = None
            if info is not None:
                mcap = getattr(info, "market_cap", None) or getattr(info, "marketCap", None)
            if mcap is None:
                try:
                    mcap = (t.info or {}).get("marketCap")
                except Exception:
                    mcap = None

            hist = t.history(period="8d", interval="1d", auto_adjust=False)
            prev_chg = None
            last_c = prev_c = None
            if hist is not None and len(hist) >= 2:
                last_c = float(hist["Close"].iloc[-1])
                prev_c = float(hist["Close"].iloc[-2])
                if prev_c:
                    prev_chg = round((last_c / prev_c - 1) * 100, 2)

            sector = industry = ""
            avg_vol = None
            try:
                inf = t.info or {}
                sector = str(inf.get("sector") or "")
                industry = str(inf.get("industry") or "")
                avg_vol = inf.get("averageVolume") or inf.get("averageVolume10days")
                if avg_vol is not None:
                    avg_vol = int(avg_vol)
            except Exception:
                pass

            cap = _cap_tier(mcap)
            liq = _liquidity_tier(avg_vol, mcap)
            mcap_cr = round(mcap / 1e7, 0) if mcap else None

            out[nse_sym] = StockMarketData(
                symbol=nse_sym,
                market_cap_cr=mcap_cr,
                sector=sector,
                industry=industry,
                avg_volume=avg_vol,
                prev_close=prev_c,
                last_close=last_c,
                prev_day_chg_pct=prev_chg,
                cap_tier=cap,
                liquidity_tier=liq,
                tradeability=_tradeability_note(cap, liq, prev_chg),
            )
        except Exception:
            out[nse_sym] = StockMarketData(symbol=nse_sym)
    return out


def _downgrade_opening(current: str) -> str:
    ladder = [
        "Gap Up Likely",
        "Watch for Breakout",
        "Mild Positive",
        "Neutral",
        "Mild Negative",
        "Watch for Fade",
        "Gap Down Risk",
    ]
    if current not in ladder:
        return current
    idx = ladder.index(current)
    return ladder[min(idx + 1, len(ladder) - 1)]


def apply_market_overlay(
    catalysts: list[StockCatalyst],
    stock_data: dict[str, StockMarketData],
    tape: MarketTape | None = None,
    *,
    top_n: int = 20,
    sector_flags: dict[str, str] | None = None,
    global_gap_pct: float | None = None,
) -> list[StockCatalyst]:
    """Attach market fields and refine opening impact using real price/liquidity/global cues."""
    ranked = sorted(catalysts, key=lambda c: c.strength, reverse=True)
    enrich_syms = {c.symbol.upper() for c in ranked[:top_n]}
    sector_flags = sector_flags or {}

    for c in catalysts:
        sd = stock_data.get(c.symbol.upper())
        if not sd:
            continue

        c.market_cap_cr = sd.market_cap_cr
        c.sector = sd.sector
        c.industry = sd.industry
        c.avg_volume = sd.avg_volume
        c.prev_day_chg_pct = sd.prev_day_chg_pct
        c.cap_tier = sd.cap_tier
        c.liquidity_tier = sd.liquidity_tier
        if sd.tradeability:
            c.tradeability = sd.tradeability

        # Sector-sensitive global flags
        sec_l = (sd.sector or "").lower()
        ind_l = (sd.industry or "").lower()
        for key, note in sector_flags.items():
            if key in sec_l or key in ind_l:
                c.tradeability = (c.tradeability + "; " if c.tradeability else "") + note
                if c.bias == "bullish" and ("headwind" in note.lower() or "caution" in note.lower() or "fade" in note.lower()):
                    if c.opening_impact == "Gap Up Likely":
                        c.opening_impact = "Mild Positive"
                break

        if c.symbol.upper() not in enrich_syms:
            continue

        chg = sd.prev_day_chg_pct
        # Prior-session move vs catalyst direction
        if c.bias == "bullish" and chg is not None:
            if chg >= 6 and c.opening_impact in {"Gap Up Likely", "Watch for Breakout"}:
                c.opening_impact = "Watch for Fade"
                c.risks = (c.risks + f" Price already +{chg:.1f}% — gap may be exhausted.").strip()
            elif chg >= 3 and c.opening_impact == "Gap Up Likely":
                c.opening_impact = _downgrade_opening(c.opening_impact)
                c.risks = (c.risks + f" Prior session +{chg:.1f}% limits upside at open.").strip()
        elif c.bias == "bearish" and chg is not None and chg <= -6:
            if c.opening_impact == "Gap Down Risk":
                c.opening_impact = "Mild Negative"
                c.risks = (c.risks + f" Already down {chg:.1f}% — further gap may be limited.").strip()

        # Liquidity / cap friction
        if sd.liquidity_tier == "Thin" and c.strength >= 3:
            c.strength = max(2, c.strength - 1)
            c.risks = (c.risks + " Thin liquidity — slippage on opening orders.").strip()
        if sd.cap_tier == "Micro":
            c.strength = max(2, c.strength - 1)

        # GIFT / global tape: mid/small bullish gaps fade on risk-off opens
        if global_gap_pct is not None and global_gap_pct <= -0.4:
            if c.bias == "bullish" and c.cap_tier in {"Mid", "Small", "Micro"}:
                if c.opening_impact == "Gap Up Likely":
                    c.opening_impact = "Mild Positive"
                c.risks = (c.risks + f" GIFT/global {global_gap_pct:+.2f}% — mid/small longs face tape drag.").strip()
        if global_gap_pct is not None and global_gap_pct >= 0.4:
            if c.bias == "bearish" and c.opening_impact == "Gap Down Risk" and c.cap_tier == "Large":
                c.opening_impact = "Mild Negative"
                c.risks = (c.risks + f" GIFT bid {global_gap_pct:+.2f}% may limit gap-downs.").strip()

    # Elevated VIX — downgrade aggressive gap calls on mid/small names
    if tape and tape.volatility_regime == "Elevated":
        for c in catalysts:
            if c.cap_tier in {"Small", "Micro"} and c.opening_impact == "Gap Up Likely":
                c.opening_impact = "Mild Positive"
                c.risks = (c.risks + " Elevated VIX — mid/small gap-ups often fade.").strip()

    return catalysts
