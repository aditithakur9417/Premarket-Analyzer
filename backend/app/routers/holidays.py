from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import Holiday, User
from ..schemas import HolidayCreate, HolidayOut, HolidayUpdate, MessageOut
from ..services.seed import seed_holidays

router = APIRouter(prefix="/api/holidays", tags=["holidays"])


@router.get("", response_model=list[HolidayOut])
def list_holidays(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.query(Holiday).order_by(Holiday.holiday_date.asc()).all()
    return rows


@router.post("", response_model=HolidayOut)
def create_holiday(
    body: HolidayCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if db.query(Holiday).filter(Holiday.holiday_date == body.holiday_date).first():
        raise HTTPException(status_code=400, detail="Holiday already exists for that date")
    row = Holiday(
        holiday_date=body.holiday_date,
        name=body.name.strip(),
        notes=body.notes or "",
        source="manual",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{holiday_id}", response_model=HolidayOut)
def update_holiday(
    holiday_id: int,
    body: HolidayUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    row = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if body.holiday_date is not None and body.holiday_date != row.holiday_date:
        clash = db.query(Holiday).filter(Holiday.holiday_date == body.holiday_date).first()
        if clash:
            raise HTTPException(status_code=400, detail="Another holiday already uses that date")
        row.holiday_date = body.holiday_date
    if body.name is not None:
        row.name = body.name.strip()
    if body.notes is not None:
        row.notes = body.notes
    row.source = "manual"
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{holiday_id}", response_model=MessageOut)
def delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    row = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return MessageOut(message="Deleted")


@router.post("/seed-nse-2026", response_model=MessageOut)
def seed_nse(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    added = seed_holidays(db, only_missing=True)
    return MessageOut(message=f"Seeded {added} missing NSE 2026 holidays")
