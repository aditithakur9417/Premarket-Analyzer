"""Phase B — GIFT Nifty (NSE IX) + overnight global cues for open accuracy."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import requests

from .calendar_nse import IST

NSEIX = "https://www.nseix.com"
_YF = None


def _yf():
    global _YF
    if _YF is None:
        import yfinance as yf_mod

        _YF = yf_mod
    return _YF


@dataclass
class CuePoint:
    symbol: str
    name: str
    last: float | None = None
    change_pct: float | None = None
    previous_close: float | None = None
    source: str = ""


@dataclass
class GiftNiftySnapshot:
    last: float | None = None
    change_pct: float | None = None
    previous_close: float | None = None
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    expiry: str = ""
    timestamp: str = ""
    source: str = "nseix"
    implied_gap_vs_nifty_pct: float | None = None
    open_bias: str = "Unknown"  # Strong Gap Up / Gap Up / Flat / Gap Down / Strong Gap Down


@dataclass
class GlobalTape:
    fetched_at: str = ""
    gift_nifty: GiftNiftySnapshot = field(default_factory=GiftNiftySnapshot)
    cues: list[CuePoint] = field(default_factory=list)
    us_futures_bias: str = "Unknown"
    asia_bias: str = "Unknown"
    fx_bias: str = "Unknown"
    commodity_bias: str = "Unknown"
    composite_risk: str = "Neutral"  # Risk-On / Mild Risk-On / Neutral / Mild Risk-Off / Risk-Off
    implied_nifty_open_pct: float | None = None
    interpretation: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def cue_map(self) -> dict[str, CuePoint]:
        return {c.symbol: c for c in self.cues}


def _num(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _pct_bias(pct: float | None, *, strong: float = 0.6, mild: float = 0.2) -> str:
    if pct is None:
        return "Unknown"
    if pct >= strong:
        return "Strong Up"
    if pct >= mild:
        return "Up"
    if pct <= -strong:
        return "Strong Down"
    if pct <= -mild:
        return "Down"
    return "Flat"


def fetch_gift_nifty(nifty_cash_last: float | None = None) -> GiftNiftySnapshot:
    """Near-month GIFT Nifty (NSE IX Index Futures) — best free official proxy for cash open."""
    snap = GiftNiftySnapshot()
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Referer": f"{NSEIX}/",
        }
    )
    s.get(f"{NSEIX}/", timeout=12)
    # Prefer niccl-graph-headers — includes PREVCLOSE / OHLC for near month
    r = s.get(f"{NSEIX}/api/niccl-graph-headers", timeout=12)
    r.raise_for_status()
    rows = (r.json() or {}).get("data") or []
    row = None
    for item in rows:
        if str(item.get("UNDERLYING") or item.get("SYMBOL") or "").upper() == "NIFTY":
            row = item
            break
    if not row and rows:
        row = rows[0]
    if not row:
        # Fallback: market-rate derivative book — pick nearest expiry
        r2 = s.get(f"{NSEIX}/api/market-rate?type=derivative", timeout=12)
        r2.raise_for_status()
        futs = [
            x
            for x in (r2.json() or {}).get("data") or []
            if x.get("SYMBOL") == "NIFTY" and x.get("INSTRUMENTTYPE") == "FUTIDX"
        ]
        if not futs:
            raise RuntimeError("No GIFT Nifty contracts on NSEIX")
        # Sort by expiry date string like 28-Jul-2026
        def _exp_key(x: dict) -> datetime:
            try:
                return datetime.strptime(str(x.get("EXPIRYDATE") or ""), "%d-%b-%Y")
            except ValueError:
                return datetime.max

        futs.sort(key=_exp_key)
        row = futs[0]
        snap.expiry = str(row.get("EXPIRYDATE") or "")
        snap.last = _num(row.get("LASTPRICE"))
        snap.change_pct = _num(row.get("PERCHANGE"))
        snap.timestamp = str(row.get("TIMESTMP") or "")
    else:
        snap.expiry = str(row.get("EXPIRY") or row.get("EXPIRYDATE") or "")
        snap.last = _num(row.get("LASTPRICE"))
        snap.previous_close = _num(row.get("PREVCLOSE"))
        snap.day_open = _num(row.get("DAYOPEN"))
        snap.day_high = _num(row.get("DAYHIGH"))
        snap.day_low = _num(row.get("DAYLOW"))
        snap.change_pct = _num(row.get("PERCHANGE"))
        snap.timestamp = str(row.get("TIMESTMP") or "")
        if snap.change_pct is None and snap.last and snap.previous_close:
            snap.change_pct = round((snap.last / snap.previous_close - 1) * 100, 2)

    # Gap vs cash Nifty (when cash is closed, GIFT vs last cash ≈ expected open)
    if snap.last is not None and nifty_cash_last:
        snap.implied_gap_vs_nifty_pct = round((snap.last / nifty_cash_last - 1) * 100, 2)
        gap = snap.implied_gap_vs_nifty_pct
    else:
        gap = snap.change_pct

    if gap is None:
        snap.open_bias = "Unknown"
    elif gap >= 0.7:
        snap.open_bias = "Strong Gap Up"
    elif gap >= 0.25:
        snap.open_bias = "Gap Up"
    elif gap <= -0.7:
        snap.open_bias = "Strong Gap Down"
    elif gap <= -0.25:
        snap.open_bias = "Gap Down"
    else:
        snap.open_bias = "Flat Open"
    return snap


def _yahoo_cue(symbol: str, name: str) -> CuePoint:
    yf = _yf()
    t = yf.Ticker(symbol)
    last = prev = chg = None
    try:
        hist = t.history(period="5d", interval="1d", auto_adjust=False)
        if hist is not None and len(hist) >= 1:
            last = float(hist["Close"].iloc[-1])
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                if prev:
                    chg = round((last / prev - 1) * 100, 2)
        # Prefer intraday last when available (futures trade overnight)
        try:
            fi = t.fast_info
            lp = getattr(fi, "last_price", None)
            pc = getattr(fi, "previous_close", None)
            if lp is not None:
                last = float(lp)
            if pc is not None:
                prev = float(pc)
                if prev:
                    chg = round((last / prev - 1) * 100, 2)
        except Exception:
            pass
    except Exception:
        pass
    return CuePoint(symbol=symbol, name=name, last=last, change_pct=chg, previous_close=prev, source="yahoo")


GLOBAL_CUE_SPECS: list[tuple[str, str, str]] = [
    # symbol, name, bucket
    ("ES=F", "S&P 500 Futures", "us"),
    ("NQ=F", "Nasdaq Futures", "us"),
    ("YM=F", "Dow Futures", "us"),
    ("^N225", "Nikkei 225", "asia"),
    ("^HSI", "Hang Seng", "asia"),
    ("CL=F", "WTI Crude", "commodity"),
    ("GC=F", "Gold", "commodity"),
    ("INR=X", "USD/INR", "fx"),
    ("DX-Y.NYB", "US Dollar Index", "fx"),
]


def fetch_global_cues(*, nifty_cash_last: float | None = None) -> GlobalTape:
    """Assemble GIFT Nifty + overnight global strip. Best-effort; never raises."""
    tape = GlobalTape(fetched_at=datetime.now(IST).isoformat())

    try:
        tape.gift_nifty = fetch_gift_nifty(nifty_cash_last=nifty_cash_last)
    except Exception as exc:  # noqa: BLE001
        tape.errors.append(f"GIFT Nifty: {exc}")

    buckets: dict[str, list[float]] = {"us": [], "asia": [], "fx": [], "commodity": []}
    for symbol, name, bucket in GLOBAL_CUE_SPECS:
        try:
            cue = _yahoo_cue(symbol, name)
            tape.cues.append(cue)
            if cue.change_pct is not None:
                buckets[bucket].append(cue.change_pct)
        except Exception as exc:  # noqa: BLE001
            tape.errors.append(f"{symbol}: {exc}")

    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 2) if vals else None

    us_avg = _avg(buckets["us"])
    asia_avg = _avg(buckets["asia"])
    # For FX: rising USDINR = INR weak = usually mild risk-off for India importers / risk appetite
    inr = next((c.change_pct for c in tape.cues if c.symbol == "INR=X"), None)
    dxy = next((c.change_pct for c in tape.cues if c.symbol == "DX-Y.NYB"), None)
    crude = next((c.change_pct for c in tape.cues if c.symbol == "CL=F"), None)
    gold = next((c.change_pct for c in tape.cues if c.symbol == "GC=F"), None)

    tape.us_futures_bias = _pct_bias(us_avg)
    tape.asia_bias = _pct_bias(asia_avg)
    # Invert USDINR for "risk" language: INR strengthening (USDINR down) = mild risk-on
    fx_score = None
    if inr is not None:
        fx_score = -inr  # down USDINR → positive score
    elif dxy is not None:
        fx_score = -dxy
    tape.fx_bias = _pct_bias(fx_score, strong=0.4, mild=0.15)

    # Commodities: crude spike is mixed (energy +, consumption −); gold up = fear
    if gold is not None and gold >= 1.0 and (us_avg or 0) < 0:
        tape.commodity_bias = "Risk-Off (gold bid)"
    elif crude is not None and abs(crude) >= 2.0:
        tape.commodity_bias = f"Crude {'spike' if crude > 0 else 'drop'} ({crude:+.1f}%)"
    else:
        tape.commodity_bias = _pct_bias(crude, strong=2.0, mild=0.8)

    # Composite implied open model (used when GIFT unavailable; also cross-check)
    # Weights from typical India open sensitivity to overnight tape
    implied = 0.0
    wsum = 0.0
    if us_avg is not None:
        implied += 0.45 * us_avg
        wsum += 0.45
    if asia_avg is not None:
        implied += 0.25 * asia_avg
        wsum += 0.25
    if inr is not None:
        implied += 0.15 * (-inr)  # INR weakness weighs on risk assets
        wsum += 0.15
    if crude is not None:
        # Mild: India is net importer — big crude up is slight headwind unless oil stocks
        implied += 0.10 * (-0.25 * crude if crude > 0 else -0.1 * crude)
        wsum += 0.10
    if wsum:
        # Weighted sum (weights ~0.95); keep as model implied open %
        tape.implied_nifty_open_pct = round(implied, 2)

    # Prefer GIFT for composite risk; fall back to model
    gift_gap = tape.gift_nifty.implied_gap_vs_nifty_pct
    if gift_gap is None:
        gift_gap = tape.gift_nifty.change_pct
    lead = gift_gap if gift_gap is not None else tape.implied_nifty_open_pct

    if lead is None:
        tape.composite_risk = "Unknown"
    elif lead >= 0.5 and (us_avg or 0) >= 0:
        tape.composite_risk = "Risk-On"
    elif lead >= 0.2:
        tape.composite_risk = "Mild Risk-On"
    elif lead <= -0.5 and (us_avg or 0) <= 0:
        tape.composite_risk = "Risk-Off"
    elif lead <= -0.2:
        tape.composite_risk = "Mild Risk-Off"
    else:
        tape.composite_risk = "Neutral"

    tape.interpretation = _interpret_global(tape, us_avg, asia_avg, inr, crude)
    return tape


def _interpret_global(
    tape: GlobalTape,
    us_avg: float | None,
    asia_avg: float | None,
    inr: float | None,
    crude: float | None,
) -> list[str]:
    lines: list[str] = []
    g = tape.gift_nifty
    if g.last is not None:
        gap = g.implied_gap_vs_nifty_pct if g.implied_gap_vs_nifty_pct is not None else g.change_pct
        gap_s = f"{gap:+.2f}%" if gap is not None else "n/a"
        lines.append(
            f"GIFT Nifty {g.last:,.2f} ({gap_s} vs {'cash' if g.implied_gap_vs_nifty_pct is not None else 'prev'}) "
            f"— {g.open_bias} (exp {g.expiry or 'n/a'}, NSE IX)."
        )
    elif tape.implied_nifty_open_pct is not None:
        lines.append(
            f"GIFT unavailable — model implied Nifty open {tape.implied_nifty_open_pct:+.2f}% from global tape."
        )

    if us_avg is not None:
        lines.append(f"US futures overnight {us_avg:+.2f}% ({tape.us_futures_bias}) — primary driver of India open.")
    if asia_avg is not None:
        lines.append(f"Asia ({tape.asia_bias}) {asia_avg:+.2f}% — regional risk appetite.")
    if inr is not None:
        direction = "weaker INR" if inr > 0 else "stronger INR"
        lines.append(f"USD/INR {inr:+.2f}% ({direction}) — exporters vs importers diverge.")
    if crude is not None and abs(crude) >= 1.5:
        lines.append(
            f"Crude {crude:+.2f}% — energy names may gap with oil; OMCs/airlines/paint face opposite pressure."
        )
    lines.append(f"Composite pre-open risk: {tape.composite_risk}.")
    return lines


def adjust_view_with_global(view: dict[str, Any], global_tape: GlobalTape) -> dict[str, Any]:
    """Blend GIFT + global cues into desk bias / confidence."""
    out = dict(view)
    reasons = list(out.get("reasons") or [])
    conf = int(out.get("confidence") or 5)
    bias = str(out.get("bias") or "Mixed")

    gift_gap = global_tape.gift_nifty.implied_gap_vs_nifty_pct
    if gift_gap is None:
        gift_gap = global_tape.gift_nifty.change_pct
    if gift_gap is None:
        gift_gap = global_tape.implied_nifty_open_pct

    if gift_gap is not None:
        if gift_gap >= 0.35 and bias == "Bullish":
            conf = min(9, conf + 1)
            reasons.append(f"GIFT/global supports bulls ({gift_gap:+.2f}%) — gap-ups more likely to hold.")
        elif gift_gap <= -0.35 and bias == "Bullish":
            conf = max(2, conf - 2)
            reasons.append(f"GIFT/global headwind ({gift_gap:+.2f}%) — fade aggressive long gaps.")
        elif gift_gap <= -0.35 and bias == "Bearish":
            conf = min(9, conf + 1)
            reasons.append(f"GIFT confirms risk-off ({gift_gap:+.2f}%) — bearish catalysts have tape wind.")
        elif gift_gap >= 0.35 and bias == "Bearish":
            conf = max(2, conf - 1)
            reasons.append(f"GIFT bid ({gift_gap:+.2f}%) — bearish stock gaps may squeeze.")

        # If news was Mixed but GIFT is decisive, nudge bias
        if bias == "Mixed":
            if gift_gap >= 0.5:
                out["bias"] = "Mildly Bullish"
                reasons.append("News mixed but GIFT points to gap-up tape.")
            elif gift_gap <= -0.5:
                out["bias"] = "Mildly Bearish"
                reasons.append("News mixed but GIFT points to gap-down tape.")

    if global_tape.composite_risk == "Risk-Off" and bias == "Bullish":
        conf = max(2, conf - 1)
    if global_tape.composite_risk == "Risk-On" and bias == "Bearish":
        conf = max(2, conf - 1)

    out["reasons"] = reasons[:7]
    out["confidence"] = conf
    out["gift_open_bias"] = global_tape.gift_nifty.open_bias
    out["global_risk"] = global_tape.composite_risk
    out["gift_gap_pct"] = gift_gap
    return out


def sector_global_flags(global_tape: GlobalTape) -> dict[str, str]:
    """Return soft flags keyed by sector keyword for catalyst overlay."""
    flags: dict[str, str] = {}
    crude = next((c.change_pct for c in global_tape.cues if c.symbol == "CL=F"), None)
    inr = next((c.change_pct for c in global_tape.cues if c.symbol == "INR=X"), None)
    us = next((c.change_pct for c in global_tape.cues if c.symbol == "ES=F"), None)

    if crude is not None and crude >= 2.0:
        flags["energy"] = f"Crude +{crude:.1f}% — oil/gas may gap with commodity"
        flags["airlines"] = f"Crude +{crude:.1f}% — cost headwind for airlines/paint"
        flags["consumer"] = flags["airlines"]
    if crude is not None and crude <= -2.0:
        flags["energy"] = f"Crude {crude:.1f}% — energy gaps may fade"
        flags["airlines"] = f"Crude {crude:.1f}% — soft cost tailwind"

    if inr is not None and inr >= 0.3:
        flags["technology"] = f"INR weak ({inr:+.2f}%) — IT/exporters mild support"
        flags["industrials"] = f"INR weak — import-cost caution for industrials"
    if inr is not None and inr <= -0.3:
        flags["technology"] = f"INR strong ({inr:+.2f}%) — IT rupee translation headwind"

    if us is not None and us <= -0.8:
        flags["financial"] = f"US futures {us:+.2f}% — risk-off may hit banks/NBFCs at open"
        flags["technology"] = (flags.get("technology") or "") + f" US tech risk-off ({us:+.2f}%)"

    return {k: v.strip(" ;") for k, v in flags.items() if v}
