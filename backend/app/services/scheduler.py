from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..database import SessionLocal
from .runner import run_analysis
from .seed import get_setting_map, set_setting

logger = logging.getLogger("premarket.scheduler")
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

DEFAULT_CRON = "15 8 * * mon-fri"
JOB_ID = "premarket_daily"


def _normalize_cron(cron: str) -> str:
    """Fix legacy numeric DOW: APScheduler 1-5 = Tue–Sat, not Mon–Fri."""
    parts = (cron or "").strip().split()
    if len(parts) != 5:
        return DEFAULT_CRON
    minute, hour, day, month, dow = parts
    if dow == "1-5":
        dow = "mon-fri"
    elif dow == "0-4":
        dow = "mon-fri"
    elif dow == "0-5":
        dow = "mon-sat"
    elif dow == "1-6":
        dow = "mon-sat"
    return f"{minute} {hour} {day} {month} {dow}"


def scheduled_job() -> None:
    db = SessionLocal()
    try:
        cfg = get_setting_map(db)
        if cfg.get("schedule_enabled", "true").lower() not in {"1", "true", "yes"}:
            logger.info("Scheduled run skipped (disabled)")
            return
        logger.info("Starting scheduled premarket run")
        run_analysis(db)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled run failed")
    finally:
        db.close()


def resync_schedule() -> str:
    db = SessionLocal()
    try:
        cfg = get_setting_map(db)
        raw = cfg.get("schedule_cron") or DEFAULT_CRON
        cron = _normalize_cron(raw)
        if cron != raw:
            set_setting(db, "schedule_cron", cron)
            logger.info("Normalized schedule_cron %r → %r", raw, cron)
        enabled = cfg.get("schedule_enabled", "true").lower() in {"1", "true", "yes"}
    finally:
        db.close()

    parts = cron.split()
    minute, hour, day, month, dow = parts
    if enabled:
        scheduler.add_job(
            scheduled_job,
            CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=dow,
                timezone="Asia/Kolkata",
            ),
            id=JOB_ID,
            replace_existing=True,
            # If Mac slept through 08:15, still fire when process wakes (up to 3h)
            misfire_grace_time=3 * 60 * 60,
            coalesce=True,
            max_instances=1,
        )
        logger.info("Schedule active: %s IST", cron)
    else:
        if scheduler.get_job(JOB_ID):
            scheduler.remove_job(JOB_ID)
        logger.info("Schedule disabled")
    return cron


def next_run_iso() -> str | None:
    job = scheduler.get_job(JOB_ID)
    if not job or not job.next_run_time:
        return None
    nxt: datetime = job.next_run_time
    return nxt.isoformat()


def settle_job() -> None:
    from .calibration_store import settle_open_predictions

    db = SessionLocal()
    try:
        result = settle_open_predictions(db)
        logger.info("Calibration settle: %s", result)
    except Exception:  # noqa: BLE001
        logger.exception("Calibration settle failed")
    finally:
        db.close()


def start_scheduler() -> None:
    resync_schedule()
    # Auto-settle morning predictions vs actual opens (~09:25 IST)
    scheduler.add_job(
        settle_job,
        CronTrigger(minute=25, hour=9, day_of_week="mon-fri", timezone="Asia/Kolkata"),
        id="premarket_settle",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
