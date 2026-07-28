from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import User
from ..schemas import DeskSettings, EmailSettings, MessageOut
from ..services.emailer import send_email, settings_from_map
from ..services.scheduler import _normalize_cron, next_run_iso, resync_schedule
from ..services.seed import get_setting_map, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _load_desk(db: Session) -> DeskSettings:
    cfg = get_setting_map(db)
    email = EmailSettings(
        smtp_host=cfg.get("smtp_host", ""),
        smtp_port=int(cfg.get("smtp_port") or 587),
        smtp_user=cfg.get("smtp_user", ""),
        smtp_password=cfg.get("smtp_password", ""),
        smtp_from=cfg.get("smtp_from", ""),
        smtp_use_tls=cfg.get("smtp_use_tls", "true").lower() in {"1", "true", "yes"},
        email_to=cfg.get("email_to", ""),
        email_enabled=cfg.get("email_enabled", "false").lower() in {"1", "true", "yes"},
        email_on_run=cfg.get("email_on_run", "true").lower() in {"1", "true", "yes"},
    )
    cron = _normalize_cron(cfg.get("schedule_cron", "15 8 * * mon-fri"))
    return DeskSettings(
        use_llm=cfg.get("use_llm", "true").lower() in {"1", "true", "yes"},
        schedule_enabled=cfg.get("schedule_enabled", "true").lower() in {"1", "true", "yes"},
        schedule_cron=cron,
        next_run_at=next_run_iso(),
        email=email,
    )


@router.get("", response_model=DeskSettings)
def get_settings_api(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return _load_desk(db)


@router.put("", response_model=DeskSettings)
def put_settings(body: DeskSettings, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    set_setting(db, "use_llm", "true" if body.use_llm else "false")
    set_setting(db, "schedule_enabled", "true" if body.schedule_enabled else "false")
    set_setting(db, "schedule_cron", _normalize_cron(body.schedule_cron.strip() or "15 8 * * mon-fri"))
    e = body.email
    set_setting(db, "smtp_host", e.smtp_host.strip())
    set_setting(db, "smtp_port", str(e.smtp_port))
    set_setting(db, "smtp_user", e.smtp_user.strip())
    # Keep existing password if blank submitted (UI can send empty to mean unchanged)
    if e.smtp_password:
        set_setting(db, "smtp_password", e.smtp_password)
    set_setting(db, "smtp_from", e.smtp_from.strip())
    set_setting(db, "smtp_use_tls", "true" if e.smtp_use_tls else "false")
    set_setting(db, "email_to", e.email_to.strip())
    set_setting(db, "email_enabled", "true" if e.email_enabled else "false")
    set_setting(db, "email_on_run", "true" if e.email_on_run else "false")
    resync_schedule()
    return _load_desk(db)


@router.post("/test-email", response_model=MessageOut)
def test_email(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    cfg = settings_from_map(get_setting_map(db))
    try:
        send_email(
            cfg=cfg,
            subject="Premarket Desk — test email",
            body_text="Your SMTP settings work. You will receive morning notes here.",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageOut(message="Test email sent")
