"""Live pre-open auction watch — compare indicative prints vs last desk note."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from premarket.auction_flow import compare_predictions_to_preopen, fetch_preopen_tape
from premarket.filters import StockCatalyst

from ..auth import require_admin
from ..database import get_db
from ..models import Report, User

router = APIRouter(prefix="/api/preopen", tags=["preopen"])


@router.get("")
def preopen_watch(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Snapshot NSE pre-open / market status and score vs latest report catalysts."""
    row = (
        db.query(Report)
        .filter(Report.status == "ok")
        .order_by(Report.created_at.desc())
        .first()
    )
    watch: list[str] = []
    catalysts: list[StockCatalyst] = []
    if row:
        try:
            payload = json.loads(row.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        for c in (payload.get("catalysts") or [])[:20]:
            sym = str(c.get("symbol") or "").upper()
            if not sym:
                continue
            watch.append(sym)
            catalysts.append(
                StockCatalyst(
                    symbol=sym,
                    name=str(c.get("name") or sym),
                    bias=c.get("bias") or "neutral",  # type: ignore[arg-type]
                    event_type=str(c.get("event_type") or ""),
                    strength=int(c.get("strength") or 0),
                    opening_impact=str(c.get("opening_impact") or "Neutral"),
                )
            )
            catalysts[-1].conviction = int(c.get("conviction") or 0)
            catalysts[-1].size_hint = str(c.get("size_hint") or "")

    try:
        tape = fetch_preopen_tape(watch_symbols=watch or None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Pre-open fetch failed: {exc}") from exc

    actions = compare_predictions_to_preopen(catalysts, tape) if catalysts else []
    return {
        "report_id": row.id if row else None,
        "preopen": tape.to_dict(),
        "actions": actions,
    }
