"""Live NSE market tape: flows, indices, volatility — for pre-market context."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

NSE_BASE = "https://www.nseindia.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


@dataclass
class IndexSnapshot:
    name: str
    last: float | None = None
    change_pct: float | None = None
    previous_close: float | None = None


@dataclass
class FlowSnapshot:
    date: str = ""
    fii_net_cr: float | None = None
    dii_net_cr: float | None = None
    fii_gross_buy_cr: float | None = None
    fii_gross_sell_cr: float | None = None


@dataclass
class MarketTape:
    fetched_at: str = ""
    flows: FlowSnapshot = field(default_factory=FlowSnapshot)
    nifty: IndexSnapshot = field(default_factory=lambda: IndexSnapshot("NIFTY 50"))
    bank_nifty: IndexSnapshot = field(default_factory=lambda: IndexSnapshot("NIFTY BANK"))
    india_vix: IndexSnapshot = field(default_factory=lambda: IndexSnapshot("INDIA VIX"))
    sector_leaders: list[dict[str, Any]] = field(default_factory=list)
    interpretation: list[str] = field(default_factory=list)
    flow_bias: str = "Neutral"
    volatility_regime: str = "Normal"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_HEADERS)
    s.get(f"{NSE_BASE}/", timeout=12)
    time.sleep(0.35)
    return s


def _pick_index(data: list[dict], *names: str) -> dict | None:
    wanted = {n.upper() for n in names}
    for row in data:
        label = (row.get("index") or row.get("indexSymbol") or "").upper()
        if label in wanted:
            return row
    return None


def _index_from_row(row: dict | None, name: str) -> IndexSnapshot:
    if not row:
        return IndexSnapshot(name)
    return IndexSnapshot(
        name=name,
        last=_num(row.get("last")),
        change_pct=_num(row.get("percentChange")),
        previous_close=_num(row.get("previousClose")),
    )


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_market_tape() -> MarketTape:
    """Pull previous-session NSE flows and index closes. Best-effort; never raises."""
    tape = MarketTape()
    try:
        s = _session()

        # FII / DII cash market flows (previous session)
        try:
            r = s.get(f"{NSE_BASE}/api/fiidiiTradeReact", timeout=12)
            r.raise_for_status()
            rows = r.json()
            fii_net = dii_net = None
            fii_buy = fii_sell = None
            flow_date = ""
            if isinstance(rows, list):
                for row in rows:
                    cat = str(row.get("category") or "").upper()
                    net = _num(row.get("netValue") or row.get("fiiNetValue") or row.get("diiNetValue"))
                    if not flow_date:
                        flow_date = str(row.get("date") or "")
                    if "FII" in cat or "FPI" in cat:
                        fii_net = net
                        fii_buy = _num(row.get("buyValue") or row.get("fiiBuyValue"))
                        fii_sell = _num(row.get("sellValue") or row.get("fiiSellValue"))
                    elif "DII" in cat:
                        dii_net = net
                # Legacy shape: list of daily aggregates
                if fii_net is None and rows and "fiiNetValue" in rows[0]:
                    latest = rows[0]
                    fii_net = _num(latest.get("fiiNetValue"))
                    dii_net = _num(latest.get("diiNetValue"))
                    fii_buy = _num(latest.get("fiiBuyValue"))
                    fii_sell = _num(latest.get("fiiSellValue"))
                    flow_date = str(latest.get("date") or flow_date)
            tape.flows = FlowSnapshot(
                date=flow_date,
                fii_net_cr=fii_net,
                dii_net_cr=dii_net,
                fii_gross_buy_cr=fii_buy,
                fii_gross_sell_cr=fii_sell,
            )
        except Exception as exc:  # noqa: BLE001
            tape.errors.append(f"FII/DII: {exc}")

        # Broad indices + VIX
        try:
            r = s.get(f"{NSE_BASE}/api/allIndices", timeout=12)
            r.raise_for_status()
            data = (r.json() or {}).get("data") or []
            tape.nifty = _index_from_row(_pick_index(data, "NIFTY 50", "NIFTY50"), "NIFTY 50")
            tape.bank_nifty = _index_from_row(_pick_index(data, "NIFTY BANK", "BANKNIFTY"), "NIFTY BANK")
            tape.india_vix = _index_from_row(_pick_index(data, "INDIA VIX", "INDIAVIX"), "INDIA VIX")

            # Top sector indices by absolute move (for theme context)
            sectors = [
                x
                for x in data
                if x.get("key") == "SECTORAL INDICES" or "SECTOR" in str(x.get("key", "")).upper()
            ]
            sectors.sort(key=lambda x: abs(_num(x.get("percentChange")) or 0), reverse=True)
            tape.sector_leaders = [
                {
                    "index": x.get("index"),
                    "change_pct": _num(x.get("percentChange")),
                }
                for x in sectors[:6]
            ]
        except Exception as exc:  # noqa: BLE001
            tape.errors.append(f"Indices: {exc}")

        tape.interpretation = _interpret(tape)
        tape.flow_bias = _flow_bias(tape.flows)
        tape.volatility_regime = _vol_regime(tape.india_vix)
    except Exception as exc:  # noqa: BLE001
        tape.errors.append(f"Session: {exc}")

    from datetime import datetime
    from .calendar_nse import IST

    tape.fetched_at = datetime.now(IST).isoformat()
    return tape


def _flow_bias(flows: FlowSnapshot) -> str:
    fii, dii = flows.fii_net_cr, flows.dii_net_cr
    if fii is None and dii is None:
        return "Unknown"
    fii = fii or 0
    dii = dii or 0
    if fii > 500 and dii > 0:
        return "Strong Risk-On"
    if fii > 0 and dii < 0:
        return "FII Buying / DII Booking"
    if fii < -500 and dii > 500:
        return "FII Selling / DII Support"
    if fii < 0 and dii < 0:
        return "Risk-Off"
    return "Mixed"


def _vol_regime(vix: IndexSnapshot) -> str:
    level = vix.last
    chg = vix.change_pct or 0
    if level is None:
        return "Unknown"
    if level >= 18 or (level >= 14 and chg > 5):
        return "Elevated"
    if level <= 12 and chg < 0:
        return "Complacent"
    return "Normal"


def _interpret(tape: MarketTape) -> list[str]:
    lines: list[str] = []
    f = tape.flows
    if f.date and f.fii_net_cr is not None:
        fii_s = f"+{f.fii_net_cr:,.0f}" if f.fii_net_cr >= 0 else f"{f.fii_net_cr:,.0f}"
        dii_s = f"+{f.dii_net_cr:,.0f}" if (f.dii_net_cr or 0) >= 0 else f"{f.dii_net_cr:,.0f}"
        lines.append(f"Cash flows ({f.date}): FII net {fii_s} Cr, DII net {dii_s} Cr — {tape.flow_bias}.")

    if tape.nifty.change_pct is not None:
        lines.append(
            f"Nifty prior close {tape.nifty.change_pct:+.2f}%"
            + (f" ({tape.nifty.last:,.2f})" if tape.nifty.last else "")
            + "; sets tone for gap direction."
        )
    if tape.bank_nifty.change_pct is not None:
        lines.append(f"Bank Nifty {tape.bank_nifty.change_pct:+.2f}% — financials often lead opening sentiment.")

    v = tape.india_vix
    if v.last is not None:
        lines.append(
            f"India VIX {v.last:.2f} ({v.change_pct:+.1f}% d/d) — {tape.volatility_regime} regime; "
            + ("fade oversized gap-ups on weak breadth." if tape.volatility_regime == "Elevated" else "normal gap-follow rules apply.")
        )

    if tape.sector_leaders:
        top = tape.sector_leaders[0]
        if top.get("index") and top.get("change_pct") is not None:
            lines.append(
                f"Largest sector move: {top['index']} {top['change_pct']:+.2f}% — check if your catalysts align with this tape."
            )
    return lines


def adjust_market_view(
    view: dict[str, Any],
    tape: MarketTape,
) -> dict[str, Any]:
    """Blend news-only bias with institutional tape context."""
    out = dict(view)
    reasons = list(out.get("reasons") or [])
    conf = int(out.get("confidence") or 5)

    if tape.nifty.change_pct is not None:
        if tape.nifty.change_pct <= -0.8 and out.get("bias") == "Bullish":
            conf = max(3, conf - 1)
            reasons.append(f"Index headwind: Nifty closed {tape.nifty.change_pct:+.2f}% — bullish stock gaps face tape drag.")
        elif tape.nifty.change_pct >= 0.5 and out.get("bias") == "Bearish":
            conf = max(3, conf - 1)
            reasons.append(f"Index support: Nifty closed {tape.nifty.change_pct:+.2f}% — bearish gaps may lack follow-through.")

    if tape.flow_bias == "Strong Risk-On" and out.get("bias") == "Bullish":
        conf = min(9, conf + 1)
        reasons.append("FII + DII both net buyers — risk appetite supports gap-up follow-through.")
    elif tape.flow_bias in {"Risk-Off", "FII Selling / DII Support"} and out.get("bias") == "Bullish":
        conf = max(3, conf - 1)
        reasons.append(f"Flow backdrop ({tape.flow_bias}) — treat bullish catalysts with smaller size.")

    if tape.volatility_regime == "Elevated":
        reasons.append("Elevated VIX — prefer liquid large-caps; avoid chasing thin mid-cap gaps.")

    out["reasons"] = reasons[:6]
    out["confidence"] = conf
    out["tape_flow_bias"] = tape.flow_bias
    out["tape_vol_regime"] = tape.volatility_regime
    return out
