from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import SessionLocal, get_db
from ..models import Report, User
from ..schemas import MessageOut, ReportDetail, ReportSummary, RunRequest
from ..services.emailer import build_desk_email_html, send_email, settings_from_map
from ..services.pdf_report import build_report_pdf_from_row
from ..services.runner import run_analysis
from ..services.seed import get_setting_map

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _clear_stale_runs(db: Session, minutes: int = 25) -> None:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    stale = (
        db.query(Report)
        .filter(Report.status == "running", Report.created_at < cutoff)
        .all()
    )
    for row in stale:
        row.status = "error"
        row.progress_pct = 100
        row.progress_message = "Timed out / interrupted"
        row.markdown = "Run timed out or was interrupted."
    if stale:
        db.commit()


def _background_run(report_id: int, use_llm: bool | None, send_email_flag: bool | None) -> None:
    db = SessionLocal()
    try:
        run_analysis(db, use_llm=use_llm, send_mail=send_email_flag, report_id=report_id)
    except Exception:  # noqa: BLE001
        pass
    finally:
        db.close()


@router.get("", response_model=list[ReportSummary])
def list_reports(db: Session = Depends(get_db), user: User = Depends(require_admin), limit: int = 30):
    _clear_stale_runs(db)
    return db.query(Report).order_by(Report.created_at.desc()).limit(min(limit, 100)).all()


@router.get("/latest", response_model=ReportDetail)
def latest_report(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _clear_stale_runs(db)
    row = (
        db.query(Report)
        .filter(Report.status.in_(["ok", "running", "error"]))
        .order_by(Report.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No reports yet")
    # Prefer latest ok if latest is an old error noise? Keep latest of any.
    return _detail(row)


@router.get("/active", response_model=Optional[ReportDetail])
def active_run(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _clear_stale_runs(db)
    row = db.query(Report).filter(Report.status == "running").order_by(Report.created_at.desc()).first()
    if not row:
        return None
    return _detail(row)


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    row = db.query(Report).filter(Report.id == report_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return _detail(row)


@router.post("/run", response_model=ReportDetail)
def trigger_run(
    body: RunRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    body = body or RunRequest()
    _clear_stale_runs(db)
    running = db.query(Report).filter(Report.status == "running").first()
    if running:
        return _detail(running)

    from premarket.calendar_nse import IST, previous_market_close
    from ..services.runner import _bind_holidays

    _bind_holidays(db)
    cutoff = previous_market_close()
    placeholder = Report(
        created_at=datetime.utcnow(),
        cutoff_iso=cutoff.isoformat(),
        bias="Pending",
        confidence=0,
        articles_in_window=0,
        unique_stocks=0,
        markdown="Running…",
        payload_json="{}",
        used_llm=False,
        status="running",
        progress_pct=3,
        progress_message="step:window|Starting desk run…",
    )
    db.add(placeholder)
    db.commit()
    db.refresh(placeholder)

    thread = threading.Thread(
        target=_background_run,
        args=(placeholder.id, body.use_llm, body.send_email),
        daemon=True,
    )
    thread.start()
    return _detail(placeholder)


@router.get("/{report_id}/pdf")
def download_pdf(report_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    row = db.query(Report).filter(Report.id == report_id).first()
    if not row or row.status != "ok":
        raise HTTPException(status_code=404, detail="Report not found")
    pdf = build_report_pdf_from_row(
        report_id=row.id,
        bias=row.bias,
        confidence=row.confidence,
        cutoff_iso=row.cutoff_iso,
        articles_in_window=row.articles_in_window,
        unique_stocks=row.unique_stocks,
        payload_json=row.payload_json,
        created_at=row.created_at,
    )
    filename = f"premarket-desk-{row.id}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{report_id}/email", response_model=MessageOut)
def email_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    row = db.query(Report).filter(Report.id == report_id).first()
    if not row or row.status != "ok":
        raise HTTPException(status_code=404, detail="Report not found")
    cfg = settings_from_map(get_setting_map(db))
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    try:
        pdf_bytes = build_report_pdf_from_row(
            report_id=row.id,
            bias=row.bias,
            confidence=row.confidence,
            cutoff_iso=row.cutoff_iso,
            articles_in_window=row.articles_in_window,
            unique_stocks=row.unique_stocks,
            payload_json=row.payload_json,
            created_at=row.created_at,
        )
        html_body = build_desk_email_html(
            report_id=row.id,
            bias=row.bias,
            confidence=row.confidence,
            articles=row.articles_in_window,
            stocks=row.unique_stocks,
            cutoff_iso=row.cutoff_iso,
            payload=payload,
        )
        send_email(
            cfg=cfg,
            subject=f"Premarket Desk — {row.bias} (#{row.id})",
            body_text=row.markdown,
            body_html=html_body,
            pdf_bytes=pdf_bytes,
            pdf_filename=f"premarket-desk-{row.id}.pdf",
        )
        row.emailed = True
        row.email_error = ""
        db.commit()
    except Exception as exc:  # noqa: BLE001
        row.email_error = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MessageOut(message="Email sent with PDF attachment")

def _detail(row: Report) -> ReportDetail:
    try:
        payload = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return ReportDetail(
        id=row.id,
        created_at=row.created_at,
        cutoff_iso=row.cutoff_iso,
        bias=row.bias,
        confidence=row.confidence,
        articles_in_window=row.articles_in_window,
        unique_stocks=row.unique_stocks,
        emailed=row.emailed,
        used_llm=row.used_llm,
        status=row.status,
        progress_pct=getattr(row, "progress_pct", 0) or 0,
        progress_message=getattr(row, "progress_message", "") or "",
        markdown=row.markdown,
        payload=payload,
    )
