"""India ADRs, event calendar, and F&O/fear overlay for open precision."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from .calendar_nse import IST

_YF = None


def _yf():
    global _YF
    if _YF is None:
        import yfinance as yf_mod

        _YF = yf_mod
    return _YF


# --- India ADRs (US-listed overnight India proxies) ---
INDIA_ADRS: list[tuple[str, str, str]] = [
    ("INFY", "Infosys ADR", "IT"),
    ("WIT", "Wipro ADR", "IT"),
    ("HDB", "HDFC Bank ADR", "Banks"),
    ("IBN", "ICICI Bank ADR", "Banks"),
    ("RDY", "Dr Reddy ADR", "Pharma"),
]


@dataclass
class AdrPoint:
    symbol: str
    name: str
    theme: str
    change_pct: float | None = None
    last: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdrTape:
    points: list[AdrPoint] = field(default_factory=list)
    it_bias: str = "Unknown"
    banks_bias: str = "Unknown"
    composite_pct: float | None = None
    interpretation: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fetch_india_adrs() -> AdrTape:
    tape = AdrTape()
    yf = _yf()
    it: list[float] = []
    banks: list[float] = []
    all_chg: list[float] = []
    for sym, name, theme in INDIA_ADRS:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="5d", interval="1d", auto_adjust=False)
            if hist is None or len(hist) < 2:
                continue
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            chg = round((last / prev - 1) * 100, 2) if prev else None
            tape.points.append(AdrPoint(symbol=sym, name=name, theme=theme, change_pct=chg, last=last))
            if chg is None:
                continue
            all_chg.append(chg)
            if theme == "IT":
                it.append(chg)
            if theme == "Banks":
                banks.append(chg)
        except Exception as exc:  # noqa: BLE001
            tape.errors.append(f"{sym}: {exc}")

    def _bias(vals: list[float]) -> str:
        if not vals:
            return "Unknown"
        avg = sum(vals) / len(vals)
        if avg >= 0.8:
            return "Bid"
        if avg <= -0.8:
            return "Offer"
        return "Flat"

    tape.it_bias = _bias(it)
    tape.banks_bias = _bias(banks)
    tape.composite_pct = round(sum(all_chg) / len(all_chg), 2) if all_chg else None
    if tape.composite_pct is not None:
        tape.interpretation.append(
            f"India ADRs overnight {tape.composite_pct:+.2f}% (IT {tape.it_bias}, Banks {tape.banks_bias})."
        )
    for p in tape.points:
        if p.change_pct is not None and abs(p.change_pct) >= 1.5:
            tape.interpretation.append(f"{p.name} {p.change_pct:+.2f}% — watch related NSE names at open.")
    return tape


# --- Macro / event calendar (static seed + expandable) ---
# Format: (date, name, impact: high|medium, note)
EVENT_SEED: list[tuple[date, str, str, str]] = [
    # Keep a rolling set; extend as needed / seed from admin later
    (date(2026, 7, 24), "Monthly F&O expiry week", "high", "Pin risk / volatility — stock gaps less reliable"),
    (date(2026, 7, 30), "US GDP / macro week watch", "medium", "Global futures may dominate India open"),
    (date(2026, 8, 1), "Likely US payrolls week", "high", "Risk-off/on swings — size down single-name gaps"),
    (date(2026, 8, 6), "RBI policy window (approx)", "high", "Banks/NBFCs sensitive; fade stock-specific noise"),
    (date(2026, 8, 15), "Independence Day (check holiday)", "high", "Session may be closed — verify holidays"),
]


@dataclass
class MacroEvent:
    event_date: str
    name: str
    impact: str
    note: str
    days_away: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EventContext:
    today: str = ""
    near_events: list[MacroEvent] = field(default_factory=list)
    regime: str = "Normal"  # Normal | Event Risk | Expiry
    interpretation: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fetch_event_context(as_of: date | None = None) -> EventContext:
    as_of = as_of or datetime.now(IST).date()
    ctx = EventContext(today=as_of.isoformat())
    near: list[MacroEvent] = []
    for d, name, impact, note in EVENT_SEED:
        delta = (d - as_of).days
        if -1 <= delta <= 5:
            near.append(MacroEvent(event_date=d.isoformat(), name=name, impact=impact, note=note, days_away=delta))
    # Heuristic: last Thursday-ish of month = expiry week for Indian monthly F&O (approx)
    if as_of.day >= 22:
        near.append(
            MacroEvent(
                event_date=as_of.isoformat(),
                name="Late-month F&O positioning",
                impact="medium",
                note="Elevated pin/gamma — prefer liquid large-caps",
                days_away=0,
            )
        )
    ctx.near_events = near
    if any(e.impact == "high" and e.days_away <= 1 for e in near):
        ctx.regime = "Event Risk"
    elif any("expir" in e.name.lower() or "f&o" in e.name.lower() for e in near):
        ctx.regime = "Expiry"
    for e in near[:4]:
        when = "today" if e.days_away == 0 else f"in {e.days_away}d" if e.days_away > 0 else "yesterday"
        ctx.interpretation.append(f"{e.name} ({when}, {e.impact}): {e.note}")
    return ctx


# --- F&O / fear proxy (VIX already in market_tape; add ADR-implied + simple FO bias) ---
@dataclass
class FoOverlay:
    nifty_pcr: float | None = None  # optional when API available
    fo_bias: str = "Unknown"
    interpretation: list[str] = field(default_factory=list)
    source: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_fo_overlay(*, india_vix_last: float | None, india_vix_chg: float | None, adr: AdrTape) -> FoOverlay:
    """Build F&O-ish overlay without brittle option-chain scrape."""
    fo = FoOverlay(source="vix+adr_proxy")
    vix = india_vix_last
    chg = india_vix_chg or 0
    if vix is not None:
        if vix >= 16 or chg >= 6:
            fo.fo_bias = "Hedge Bid / Caution"
            fo.interpretation.append(f"VIX {vix:.1f} ({chg:+.1f}%) — derivatives hedging elevated; fade thin gaps.")
        elif vix <= 12 and chg < 0:
            fo.fo_bias = "Complacent"
            fo.interpretation.append(f"VIX {vix:.1f} — complacent FO tape; gaps can extend then reverse hard.")
        else:
            fo.fo_bias = "Normal"
            fo.interpretation.append(f"VIX {vix:.1f} — normal FO fear regime.")
    if adr.composite_pct is not None:
        if adr.composite_pct <= -1.2:
            fo.interpretation.append("ADR selloff overnight — FO/cash open may gap risk-off even if domestic news is calm.")
        elif adr.composite_pct >= 1.2:
            fo.interpretation.append("ADR bid overnight — supportive for banks/IT related opens.")
    return fo
