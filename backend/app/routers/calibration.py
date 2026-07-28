"""Calibration API — settle predictions vs actual opens and show hit rate."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import User
from ..schemas import MessageOut
from ..services.calibration_store import calibration_stats, settle_open_predictions

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


@router.get("")
def get_calibration(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return calibration_stats(db)


@router.post("/settle", response_model=MessageOut)
def settle_calibration(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    result = settle_open_predictions(db)
    return MessageOut(
        message=(
            f"Settled {result['settled']} predictions "
            f"({result['hits']} directional hits). "
            + (f"Issues: {', '.join(result['errors'][:3])}" if result.get("errors") else "")
        ).strip()
    )
