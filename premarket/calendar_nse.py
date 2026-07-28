"""NSE trading calendar — previous session close (3:30 PM IST)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Fallback seed if DB provider not bound (CLI mode).
NSE_HOLIDAYS_2026: frozenset[date] = frozenset(
    {
        date(2026, 1, 15),
        date(2026, 1, 26),
        date(2026, 3, 3),
        date(2026, 3, 26),
        date(2026, 3, 31),
        date(2026, 4, 3),
        date(2026, 4, 14),
        date(2026, 5, 1),
        date(2026, 5, 28),
        date(2026, 6, 26),
        date(2026, 9, 14),
        date(2026, 10, 2),
        date(2026, 10, 20),
        date(2026, 11, 10),
        date(2026, 11, 24),
        date(2026, 12, 25),
    }
)

MARKET_CLOSE = time(15, 30)

_HolidayProvider = Callable[[], set[date]]
_holiday_provider: _HolidayProvider | None = None


def set_holiday_provider(provider: _HolidayProvider | None) -> None:
    """Bind a callable that returns the active holiday set (e.g. from DB)."""
    global _holiday_provider
    _holiday_provider = provider


def active_holidays() -> set[date]:
    if _holiday_provider is not None:
        return set(_holiday_provider())
    return set(NSE_HOLIDAYS_2026)


def is_trading_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return d not in active_holidays()


def previous_trading_day(as_of: date | None = None) -> date:
    """Most recent NSE trading day strictly before as_of (default: today IST)."""
    d = as_of or datetime.now(IST).date()
    cursor = d - timedelta(days=1)
    for _ in range(30):
        if is_trading_day(cursor):
            return cursor
        cursor -= timedelta(days=1)
    raise RuntimeError(f"Could not find previous trading day before {d}")


def previous_market_close(as_of: date | None = None) -> datetime:
    """Previous NSE session close timestamp in IST."""
    prev = previous_trading_day(as_of)
    return datetime.combine(prev, MARKET_CLOSE, tzinfo=IST)


def format_close(dt: datetime) -> str:
    return dt.strftime("%d %b %Y") + "\n3:30 PM IST"
