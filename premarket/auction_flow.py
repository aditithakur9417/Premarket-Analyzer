"""F&O OI spurts, bulk/block deals, and pre-open auction snapshots."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

from .filters import StockCatalyst

NSE = "https://www.nseindia.com"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Referer": f"{NSE}/",
        }
    )
    s.get(f"{NSE}/", timeout=12)
    time.sleep(0.3)
    return s


def _num(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ---- F&O OI spurts ----
@dataclass
class OiSpurt:
    symbol: str
    latest_oi: float | None = None
    prev_oi: float | None = None
    change_in_oi: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    underlying: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FoFlowTape:
    nifty_oi_chg_pct: float | None = None
    banknifty_oi_chg_pct: float | None = None
    fo_bias: str = "Unknown"
    top_spurts: list[OiSpurt] = field(default_factory=list)
    by_symbol: dict[str, dict[str, Any]] = field(default_factory=dict)
    interpretation: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nifty_oi_chg_pct": self.nifty_oi_chg_pct,
            "banknifty_oi_chg_pct": self.banknifty_oi_chg_pct,
            "fo_bias": self.fo_bias,
            "top_spurts": [s.to_dict() for s in self.top_spurts],
            "interpretation": self.interpretation,
            "errors": self.errors,
        }


def fetch_fo_oi_spurts() -> FoFlowTape:
    tape = FoFlowTape()
    try:
        s = _session()
        s.headers["Referer"] = f"{NSE}/market-data/oi-spurts"
        r = s.get(f"{NSE}/api/live-analysis-oi-spurts-underlyings", timeout=15)
        r.raise_for_status()
        rows = (r.json() or {}).get("data") or []
        by_sym = {str(x.get("symbol") or "").upper(): x for x in rows}
        nifty = by_sym.get("NIFTY")
        bank = by_sym.get("BANKNIFTY")
        if nifty:
            tape.nifty_oi_chg_pct = _num(nifty.get("avgInOI"))
        if bank:
            tape.banknifty_oi_chg_pct = _num(bank.get("avgInOI"))

        # Index OI rising hard often = fresh positioning / hedge build
        n = tape.nifty_oi_chg_pct or 0
        if n >= 25:
            tape.fo_bias = "Heavy OI Build"
        elif n >= 10:
            tape.fo_bias = "OI Building"
        elif n <= -10:
            tape.fo_bias = "OI Unwinding"
        else:
            tape.fo_bias = "Normal OI"

        spurts: list[OiSpurt] = []
        for x in rows:
            sym = str(x.get("symbol") or "").upper()
            if not sym:
                continue
            sp = OiSpurt(
                symbol=sym,
                latest_oi=_num(x.get("latestOI")),
                prev_oi=_num(x.get("prevOI")),
                change_in_oi=_num(x.get("changeInOI")),
                change_pct=_num(x.get("avgInOI")),
                volume=_num(x.get("volume")),
                underlying=_num(x.get("underlyingValue")),
            )
            if sym not in {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}:
                tape.by_symbol[sym] = sp.to_dict()
                spurts.append(sp)
        spurts.sort(key=lambda z: abs(z.change_pct or 0), reverse=True)
        tape.top_spurts = spurts[:8]

        if tape.nifty_oi_chg_pct is not None:
            tape.interpretation.append(
                f"Nifty fut OI {tape.nifty_oi_chg_pct:+.1f}% d/d — {tape.fo_bias}."
            )
        if tape.banknifty_oi_chg_pct is not None:
            tape.interpretation.append(f"Bank Nifty OI {tape.banknifty_oi_chg_pct:+.1f}%.")
        if tape.top_spurts:
            top = ", ".join(
                f"{s.symbol} ({s.change_pct:+.0f}%)" for s in tape.top_spurts[:4] if s.change_pct is not None
            )
            tape.interpretation.append(f"Stock OI spurts: {top}.")
    except Exception as exc:  # noqa: BLE001
        tape.errors.append(str(exc))
    return tape


def attach_oi_to_catalysts(catalysts: list[StockCatalyst], fo: FoFlowTape) -> None:
    for c in catalysts:
        raw = fo.by_symbol.get(c.symbol.upper())
        if not raw or raw.get("change_pct") is None:
            continue
        pct = float(raw["change_pct"])
        c.oi_change_pct = pct
        note = f"F&O OI {pct:+.1f}%"
        c.tradeability = (c.tradeability + "; " if c.tradeability else "") + note
        if abs(pct) >= 20 and c.bias == "bullish" and c.opening_impact == "Mild Positive":
            if (c.prev_day_chg_pct or 0) < 4:
                c.opening_impact = "Watch for Breakout"


# ---- Bulk / block deals ----
@dataclass
class DealPrint:
    symbol: str
    side: str
    client: str
    qty: float | None
    price: float | None
    deal_type: str  # bulk | block
    date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DealsTape:
    as_on: str = ""
    bulk: list[DealPrint] = field(default_factory=list)
    block: list[DealPrint] = field(default_factory=list)
    by_symbol: dict[str, list[DealPrint]] = field(default_factory=dict)
    interpretation: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_on": self.as_on,
            "bulk_count": len(self.bulk),
            "block_count": len(self.block),
            "matched": {k: [d.to_dict() for d in v] for k, v in list(self.by_symbol.items())[:30]},
            "interpretation": self.interpretation,
            "errors": self.errors,
        }


def fetch_large_deals() -> DealsTape:
    tape = DealsTape()
    try:
        s = _session()
        s.headers["Referer"] = f"{NSE}/market-data/large-deals"
        r = s.get(f"{NSE}/api/snapshot-capital-market-largedeal", timeout=15)
        r.raise_for_status()
        data = r.json() or {}
        tape.as_on = str(data.get("as_on_date") or "")

        def _parse(rows: list, kind: str) -> list[DealPrint]:
            out = []
            for row in rows or []:
                sym = str(row.get("symbol") or "").upper()
                if not sym:
                    continue
                d = DealPrint(
                    symbol=sym,
                    side=str(row.get("buySell") or "").upper(),
                    client=str(row.get("clientName") or "")[:80],
                    qty=_num(row.get("qty")),
                    price=_num(row.get("watp")),
                    deal_type=kind,
                    date=str(row.get("date") or tape.as_on),
                )
                out.append(d)
                tape.by_symbol.setdefault(sym, []).append(d)
            return out

        tape.bulk = _parse(data.get("BULK_DEALS_DATA") or [], "bulk")
        tape.block = _parse(data.get("BLOCK_DEALS_DATA") or [], "block")
        tape.interpretation.append(
            f"Large deals ({tape.as_on or 'prior'}): {len(tape.bulk)} bulk, {len(tape.block)} block."
        )
    except Exception as exc:  # noqa: BLE001
        tape.errors.append(str(exc))
    return tape


def attach_deals_to_catalysts(catalysts: list[StockCatalyst], deals: DealsTape) -> None:
    for c in catalysts:
        prints = deals.by_symbol.get(c.symbol.upper()) or []
        if not prints:
            continue
        buys = sum(1 for d in prints if d.side == "BUY")
        sells = sum(1 for d in prints if d.side == "SELL")
        clients = sorted({d.client for d in prints if d.client})[:2]
        c.deal_summary = f"{buys}B/{sells}S bulk-block" + (f" ({', '.join(clients)})" if clients else "")
        c.tradeability = (c.tradeability + "; " if c.tradeability else "") + c.deal_summary
        # Named selling into bullish catalyst = caution
        if sells > buys and c.bias == "bullish" and c.opening_impact == "Gap Up Likely":
            c.opening_impact = "Mild Positive"
            c.risks = (c.risks + " Bulk/block sellers present.").strip()


# ---- Pre-open auction ----
@dataclass
class PreopenRow:
    symbol: str
    iep: float | None = None  # indicative equilibrium / last in preopen feed
    change_pct: float | None = None
    previous_close: float | None = None
    final_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreopenTape:
    fetched_at: str = ""
    market_status: str = ""
    trade_date: str = ""
    nifty_last: float | None = None
    nifty_change: float | None = None
    gift_last: float | None = None
    gift_change_pct: float | None = None
    indicative: dict[str, Any] = field(default_factory=dict)
    advances: int | None = None
    declines: int | None = None
    unchanged: int | None = None
    rows: list[PreopenRow] = field(default_factory=list)
    matched: list[dict[str, Any]] = field(default_factory=list)
    interpretation: list[str] = field(default_factory=list)
    auction_phase: str = "Unknown"  # Pre-Open | Open | Closed | Unknown
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fetch_preopen_tape(watch_symbols: list[str] | None = None) -> PreopenTape:
    """Live NSE market status + pre-open indicative book."""
    from datetime import datetime
    from .calendar_nse import IST

    tape = PreopenTape(fetched_at=datetime.now(IST).isoformat())
    watch = {s.upper() for s in (watch_symbols or [])}
    try:
        s = _session()
        st = s.get(f"{NSE}/api/marketStatus", timeout=12)
        st.raise_for_status()
        status = st.json() or {}
        for m in status.get("marketState") or []:
            if m.get("market") == "Capital Market":
                tape.market_status = str(m.get("marketStatus") or "")
                tape.trade_date = str(m.get("tradeDate") or "")
                tape.nifty_last = _num(m.get("last"))
                tape.nifty_change = _num(m.get("variation"))
                break
        gift = status.get("giftnifty") or {}
        tape.gift_last = _num(gift.get("LASTPRICE"))
        tape.gift_change_pct = _num(gift.get("PERCHANGE"))
        tape.indicative = status.get("indicativenifty50") or {}

        ms = tape.market_status.lower()
        if "pre" in ms and "open" in ms:
            tape.auction_phase = "Pre-Open"
        elif ms == "open":
            tape.auction_phase = "Open"
        elif ms == "closed":
            tape.auction_phase = "Closed"
        else:
            tape.auction_phase = tape.market_status or "Unknown"

        # Pre-open / indicative stock board
        s.headers["Referer"] = f"{NSE}/market-data/pre-open-market-cm-and-emerge-market"
        po = s.get(f"{NSE}/api/market-data-pre-open?key=ALL", timeout=20)
        po.raise_for_status()
        payload = po.json() or {}
        tape.advances = _num(payload.get("advances"))
        if tape.advances is not None:
            tape.advances = int(tape.advances)
        tape.declines = int(_num(payload.get("declines")) or 0) if payload.get("declines") is not None else None
        tape.unchanged = int(_num(payload.get("unchanged")) or 0) if payload.get("unchanged") is not None else None

        for item in payload.get("data") or []:
            meta = item.get("metadata") or item
            sym = str(meta.get("symbol") or "").upper()
            if not sym:
                continue
            row = PreopenRow(
                symbol=sym,
                iep=_num(meta.get("lastPrice") or meta.get("iep") or meta.get("finalPrice")),
                change_pct=_num(meta.get("pChange")),
                previous_close=_num(meta.get("previousClose")),
                final_price=_num(meta.get("finalPrice") or meta.get("lastPrice")),
            )
            if watch and sym in watch:
                tape.matched.append({**row.to_dict(), "watched": True})
            elif not watch and abs(row.change_pct or 0) >= 2.0:
                tape.rows.append(row)

        tape.rows = sorted(tape.rows, key=lambda r: abs(r.change_pct or 0), reverse=True)[:15]
        # Always include watch matches even if also in movers
        if watch:
            # Fill unmatched watches from full scan
            have = {m["symbol"] for m in tape.matched}
            for item in payload.get("data") or []:
                meta = item.get("metadata") or item
                sym = str(meta.get("symbol") or "").upper()
                if sym in watch and sym not in have:
                    tape.matched.append(
                        PreopenRow(
                            symbol=sym,
                            iep=_num(meta.get("lastPrice")),
                            change_pct=_num(meta.get("pChange")),
                            previous_close=_num(meta.get("previousClose")),
                        ).to_dict()
                    )

        if tape.gift_last is not None:
            if tape.gift_change_pct is not None:
                tape.interpretation.append(
                    f"GIFT (marketStatus) {tape.gift_last:,.0f} ({tape.gift_change_pct:+.2f}%) — phase {tape.auction_phase}."
                )
            else:
                tape.interpretation.append(
                    f"GIFT (marketStatus) {tape.gift_last:,.0f} — phase {tape.auction_phase}."
                )
        if tape.advances is not None and tape.declines is not None:
            tape.interpretation.append(
                f"Pre-open board: {tape.advances} adv / {tape.declines} dec / {tape.unchanged or 0} flat."
            )
        if tape.matched:
            tape.interpretation.append(f"Watchlist indicative prints: {len(tape.matched)} names.")
    except Exception as exc:  # noqa: BLE001
        tape.errors.append(str(exc))

    return tape


def compare_predictions_to_preopen(
    catalysts: list[StockCatalyst],
    preopen: PreopenTape,
) -> list[dict[str, Any]]:
    """During auction: flag hold / size-down / cancel vs our predicted impact."""
    by = {m["symbol"]: m for m in preopen.matched}
    # also index movers
    for r in preopen.rows:
        by.setdefault(r.symbol, r.to_dict())

    out = []
    for c in catalysts[:20]:
        m = by.get(c.symbol.upper())
        if not m or m.get("change_pct") is None:
            continue
        pct = float(m["change_pct"])
        pred = (c.opening_impact or "").lower()
        action = "Hold plan"
        if "gap up" in pred or "breakout" in pred or "mild positive" in pred:
            if pct < -0.5:
                action = "Cancel / reverse risk — indicative opposite"
            elif pct < 0.3:
                action = "Size down — weak indicative vs bullish call"
            elif pct >= 2.0:
                action = "Chase risk — already extended in auction"
        elif "gap down" in pred or "mild negative" in pred:
            if pct > 0.5:
                action = "Cancel — indicative squeeze vs bearish call"
            elif pct > -0.3:
                action = "Size down — weak downside in auction"
        elif "fade" in pred:
            if abs(pct) < 0.8:
                action = "Fade setup intact"
            else:
                action = "Fade less likely — strong continuation print"
        out.append(
            {
                "symbol": c.symbol,
                "predicted": c.opening_impact,
                "indicative_pct": pct,
                "iep": m.get("iep"),
                "action": action,
                "conviction": getattr(c, "conviction", 0),
                "size_hint": getattr(c, "size_hint", ""),
            }
        )
    return out
