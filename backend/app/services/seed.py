"""Seed NSE holidays and app defaults."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..auth import hash_password
from ..config import get_settings
from ..models import AppSetting, Holiday, User

NSE_2026: list[tuple[date, str]] = [
    (date(2026, 1, 15), "Municipal Corporation Election - Maharashtra"),
    (date(2026, 1, 26), "Republic Day"),
    (date(2026, 3, 3), "Holi"),
    (date(2026, 3, 26), "Shri Ram Navami"),
    (date(2026, 3, 31), "Shri Mahavir Jayanti"),
    (date(2026, 4, 3), "Good Friday"),
    (date(2026, 4, 14), "Dr. Baba Saheb Ambedkar Jayanti"),
    (date(2026, 5, 1), "Maharashtra Day"),
    (date(2026, 5, 28), "Bakri Id"),
    (date(2026, 6, 26), "Muharram"),
    (date(2026, 9, 14), "Ganesh Chaturthi"),
    (date(2026, 10, 2), "Mahatma Gandhi Jayanti"),
    (date(2026, 10, 20), "Dussehra"),
    (date(2026, 11, 10), "Diwali-Balipratipada"),
    (date(2026, 11, 24), "Prakash Gurpurb Sri Guru Nanak Dev"),
    (date(2026, 12, 25), "Christmas"),
]

DEFAULT_SETTINGS = {
    "use_llm": "true",
    "schedule_enabled": "true",
    "schedule_cron": "15 8 * * mon-fri",
    "email_enabled": "false",
    "email_on_run": "true",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_use_tls": "true",
    "email_to": "",
}


def ensure_admin_user(db: Session) -> None:
    settings = get_settings()
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        db.add(
            User(
                username="admin",
                password_hash=hash_password(settings.admin_password),
                is_admin=True,
            )
        )
        db.commit()


def seed_settings(db: Session) -> None:
    settings = get_settings()
    defaults = dict(DEFAULT_SETTINGS)
    if settings.smtp_host:
        defaults.update(
            {
                "smtp_host": settings.smtp_host,
                "smtp_port": str(settings.smtp_port),
                "smtp_user": settings.smtp_user,
                "smtp_password": settings.smtp_password,
                "smtp_from": settings.smtp_from or settings.smtp_user,
                "smtp_use_tls": "true" if settings.smtp_use_tls else "false",
                "email_to": settings.email_to,
                "email_enabled": "true" if settings.email_to else "false",
            }
        )
    defaults["use_llm"] = "true" if settings.use_llm_default else "false"
    defaults["schedule_cron"] = settings.schedule_cron

    for key, value in defaults.items():
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not row:
            db.add(AppSetting(key=key, value=value))
    db.commit()


def seed_holidays(db: Session, *, only_missing: bool = True) -> int:
    added = 0
    for d, name in NSE_2026:
        existing = db.query(Holiday).filter(Holiday.holiday_date == d).first()
        if existing:
            if only_missing:
                continue
            existing.name = name
            existing.source = "nse_seed"
        else:
            db.add(Holiday(holiday_date=d, name=name, source="nse_seed", notes="Seeded from NSE 2026 calendar"))
            added += 1
    db.commit()
    return added


def get_setting_map(db: Session) -> dict[str, str]:
    return {r.key: r.value for r in db.query(AppSetting).all()}


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def holiday_dates(db: Session) -> set[date]:
    return {h.holiday_date for h in db.query(Holiday).all()}
