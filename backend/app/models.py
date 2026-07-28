from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Holiday(Base):
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("holiday_date", name="uq_holiday_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(64), default="manual")  # nse_seed | manual
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    cutoff_iso: Mapped[str] = mapped_column(String(64))
    bias: Mapped[str] = mapped_column(String(32), default="Mixed")
    confidence: Mapped[int] = mapped_column(Integer, default=5)
    articles_in_window: Mapped[int] = mapped_column(Integer, default=0)
    unique_stocks: Mapped[int] = mapped_column(Integer, default=0)
    markdown: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    email_error: Mapped[str] = mapped_column(Text, default="")
    used_llm: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="ok")  # ok | error | running
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str] = mapped_column(String(255), default="")


class OpenPrediction(Base):
    """Logged morning predictions settled against actual open prints."""

    __tablename__ = "open_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(Integer, index=True, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    bias: Mapped[str] = mapped_column(String(16), default="")
    event_type: Mapped[str] = mapped_column(String(64), default="")
    predicted_impact: Mapped[str] = mapped_column(String(64), default="")
    strength: Mapped[int] = mapped_column(Integer, default=0)
    conviction: Mapped[int] = mapped_column(Integer, default=0)
    size_hint: Mapped[str] = mapped_column(String(32), default="")
    filing_status: Mapped[str] = mapped_column(String(32), default="")
    gift_gap_pct: Mapped[str] = mapped_column(String(16), default="")
    # Settlement
    settled: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_open_gap_pct: Mapped[str] = mapped_column(String(16), default="")
    actual_label: Mapped[str] = mapped_column(String(64), default="")
    hit: Mapped[bool] = mapped_column(Boolean, default=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
