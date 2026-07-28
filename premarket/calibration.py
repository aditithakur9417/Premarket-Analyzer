"""Phase D — prediction logging and open calibration against actual prints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .calendar_nse import IST
from .filters import StockCatalyst

_YF = None


def _yf():
    global _YF
    if _YF is None:
        import yfinance as yf_mod

        _YF = yf_mod
    return _YF


LABEL_ORDER = [
    "Gap Up Likely",
    "Watch for Breakout",
    "Mild Positive",
    "Neutral",
    "Watch for Fade",
    "Mild Negative",
    "Gap Down Risk",
]


def label_from_open_pct(pct: float | None, predicted_bias: str = "") -> str:
    if pct is None:
        return "Unknown"
    # Actual open gap vs prior close
    if pct >= 2.0:
        return "Gap Up Likely"
    if pct >= 0.8:
        return "Mild Positive"
    if pct <= -2.0:
        return "Gap Down Risk"
    if pct <= -0.8:
        return "Mild Negative"
    if predicted_bias == "bullish" and 0.2 <= pct < 0.8:
        return "Mild Positive"
    if abs(pct) < 0.35:
        return "Neutral"
    return "Mild Positive" if pct > 0 else "Mild Negative"


def prediction_hit(predicted: str, actual_label: str, actual_pct: float | None) -> bool:
    if actual_pct is None:
        return False
    p = (predicted or "").lower()
    # Directional hit
    if "gap up" in p or "breakout" in p or "mild positive" in p:
        return actual_pct >= 0.3
    if "gap down" in p or "mild negative" in p:
        return actual_pct <= -0.3
    if "fade" in p:
        # Fade = not a strong continuation gap
        return abs(actual_pct) < 1.5
    if "neutral" in p:
        return abs(actual_pct) < 0.6
    return False


def fetch_open_vs_prev(symbol: str) -> dict[str, float | None]:
    """Return prior close, today's open, and open gap % using Yahoo."""
    yf = _yf()
    t = yf.Ticker(f"{symbol}.NS" if not symbol.endswith(".NS") else symbol)
    hist = t.history(period="8d", interval="1d", auto_adjust=False)
    if hist is None or len(hist) < 2:
        return {"prev_close": None, "open": None, "open_gap_pct": None}
    # Prefer latest row as "today" if market has opened; else last complete
    last = hist.iloc[-1]
    prev = hist.iloc[-2]
    prev_close = float(prev["Close"])
    day_open = float(last["Open"])
    # If last day is still prior session (same close≈open early), still compute
    gap = round((day_open / prev_close - 1) * 100, 2) if prev_close else None
    return {"prev_close": prev_close, "open": day_open, "open_gap_pct": gap}


def build_prediction_rows(
    catalysts: list[StockCatalyst],
    *,
    report_id: int | None,
    gift_gap_pct: float | None,
    limit: int = 15,
) -> list[dict[str, Any]]:
    rows = []
    for c in catalysts[:limit]:
        rows.append(
            {
                "report_id": report_id,
                "symbol": c.symbol,
                "name": c.name,
                "bias": c.bias,
                "event_type": c.event_type,
                "predicted_impact": c.opening_impact,
                "strength": c.strength,
                "conviction": getattr(c, "conviction", None),
                "size_hint": getattr(c, "size_hint", ""),
                "filing_status": getattr(c, "filing_status", ""),
                "gift_gap_pct": gift_gap_pct,
                "predicted_at": datetime.now(IST).isoformat(),
            }
        )
    return rows


@dataclass
class CalibrationSummary:
    settled: int = 0
    hits: int = 0
    hit_rate: float | None = None
    avg_abs_error_pct: float | None = None
    by_label: dict[str, dict[str, int]] = None  # type: ignore

    def to_dict(self) -> dict[str, Any]:
        return {
            "settled": self.settled,
            "hits": self.hits,
            "hit_rate": self.hit_rate,
            "avg_abs_error_pct": self.avg_abs_error_pct,
            "by_label": self.by_label or {},
        }
