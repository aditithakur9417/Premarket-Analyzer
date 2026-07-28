"""Persist and settle opening-impact predictions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from premarket.calibration import (
    CalibrationSummary,
    fetch_open_vs_prev,
    label_from_open_pct,
    prediction_hit,
)

from ..models import OpenPrediction


def log_predictions(db: Session, rows: list[dict[str, Any]]) -> int:
    n = 0
    for row in rows:
        gift = row.get("gift_gap_pct")
        pred = OpenPrediction(
            report_id=int(row.get("report_id") or 0),
            symbol=str(row.get("symbol") or "").upper(),
            name=str(row.get("name") or ""),
            bias=str(row.get("bias") or ""),
            event_type=str(row.get("event_type") or ""),
            predicted_impact=str(row.get("predicted_impact") or ""),
            strength=int(row.get("strength") or 0),
            conviction=int(row.get("conviction") or 0),
            size_hint=str(row.get("size_hint") or ""),
            filing_status=str(row.get("filing_status") or ""),
            gift_gap_pct="" if gift is None else str(gift),
        )
        db.add(pred)
        n += 1
    db.commit()
    return n


def settle_open_predictions(db: Session, *, limit: int = 40) -> dict[str, Any]:
    """Fill actual open gaps for unsettled predictions (run after ~09:20 IST)."""
    pending = (
        db.query(OpenPrediction)
        .filter(OpenPrediction.settled.is_(False))
        .order_by(OpenPrediction.created_at.desc())
        .limit(limit)
        .all()
    )
    settled = 0
    hits = 0
    errors: list[str] = []
    for row in pending:
        try:
            data = fetch_open_vs_prev(row.symbol)
            gap = data.get("open_gap_pct")
            if gap is None:
                errors.append(f"{row.symbol}: no open data")
                continue
            actual_label = label_from_open_pct(gap, row.bias)
            row.actual_open_gap_pct = str(gap)
            row.actual_label = actual_label
            row.hit = prediction_hit(row.predicted_impact, actual_label, gap)
            row.settled = True
            row.settled_at = datetime.utcnow()
            settled += 1
            if row.hit:
                hits += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{row.symbol}: {exc}")
    db.commit()
    return {"settled": settled, "hits": hits, "errors": errors[:8]}


def calibration_stats(db: Session, *, limit: int = 200) -> dict[str, Any]:
    rows = (
        db.query(OpenPrediction)
        .filter(OpenPrediction.settled.is_(True))
        .order_by(OpenPrediction.settled_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return CalibrationSummary().to_dict()
    hits = sum(1 for r in rows if r.hit)
    errs: list[float] = []
    by_label: dict[str, dict[str, int]] = {}
    for r in rows:
        bucket = by_label.setdefault(r.predicted_impact or "?", {"n": 0, "hits": 0})
        bucket["n"] += 1
        if r.hit:
            bucket["hits"] += 1
        try:
            # crude directional error vs expected
            gap = float(r.actual_open_gap_pct)
            errs.append(abs(gap))
        except (TypeError, ValueError):
            pass
    summary = CalibrationSummary(
        settled=len(rows),
        hits=hits,
        hit_rate=round(hits / len(rows), 3) if rows else None,
        avg_abs_error_pct=round(sum(errs) / len(errs), 2) if errs else None,
        by_label=by_label,
    )
    recent = [
        {
            "id": r.id,
            "symbol": r.symbol,
            "predicted": r.predicted_impact,
            "actual_gap_pct": r.actual_open_gap_pct,
            "actual_label": r.actual_label,
            "hit": r.hit,
            "conviction": r.conviction,
            "filing_status": r.filing_status,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows[:30]
    ]
    out = summary.to_dict()
    out["recent"] = recent
    return out
