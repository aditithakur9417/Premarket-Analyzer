"""Run the premarket analyzer and persist results."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from premarket.analyze import enrich_top_catalysts, market_view_llm, ollama_available  # noqa: E402
from premarket.auction_flow import (  # noqa: E402
    attach_deals_to_catalysts,
    attach_oi_to_catalysts,
    fetch_fo_oi_spurts,
    fetch_large_deals,
    fetch_preopen_tape,
)
from premarket.calendar_nse import IST, previous_market_close, set_holiday_provider  # noqa: E402
from premarket.calibration import build_prediction_rows  # noqa: E402
from premarket.conviction import apply_conviction  # noqa: E402
from premarket.filings import fetch_announcements, index_filings, verify_catalysts  # noqa: E402
from premarket.filters import consolidate  # noqa: E402
from premarket.global_cues import adjust_view_with_global, fetch_global_cues, sector_global_flags  # noqa: E402
from premarket.groww_feed import fetch_since  # noqa: E402
from premarket.market_context import adjust_market_view, fetch_market_tape  # noqa: E402
from premarket.precision_extras import build_fo_overlay, fetch_event_context, fetch_india_adrs  # noqa: E402
from premarket.report import build_market_view, render_report  # noqa: E402
from premarket.secondary_news import cross_check_secondary, fetch_secondary_headlines  # noqa: E402
from premarket.stock_enrich import apply_market_overlay, fetch_stock_data  # noqa: E402

from ..models import Report
from .calibration_store import log_predictions
from .emailer import build_desk_email_html, send_email, settings_from_map
from .pdf_report import build_report_pdf_from_row
from .seed import get_setting_map, holiday_dates


def _global_brief(global_tape, market_tape) -> str:
    g = global_tape.gift_nifty
    gap = g.implied_gap_vs_nifty_pct if g.implied_gap_vs_nifty_pct is not None else g.change_pct
    parts = [
        f"GIFT Nifty: last={g.last}, gap={gap}, bias={g.open_bias}",
        f"Global risk: {global_tape.composite_risk}",
        f"US futures: {global_tape.us_futures_bias}; Asia: {global_tape.asia_bias}; FX: {global_tape.fx_bias}",
        f"India VIX regime: {market_tape.volatility_regime}; FII/DII: {market_tape.flow_bias}",
    ]
    return " | ".join(parts)


def _bind_holidays(db: Session) -> None:
    dates = holiday_dates(db)

    def provider():
        return dates

    set_holiday_provider(provider)


def _progress(db: Session, report: Report, pct: int, message: str) -> None:
    report.progress_pct = max(0, min(100, pct))
    report.progress_message = message[:240]
    db.commit()
    db.refresh(report)


def run_analysis(
    db: Session,
    *,
    use_llm: bool | None = None,
    send_mail: bool | None = None,
    report_id: int | None = None,
) -> Report:
    _bind_holidays(db)
    cfg = get_setting_map(db)
    email_cfg = settings_from_map(cfg)

    if use_llm is None:
        use_llm = cfg.get("use_llm", "true").lower() in {"1", "true", "yes"}
    if send_mail is None:
        send_mail = email_cfg["email_enabled"] and email_cfg["email_on_run"]

    now = datetime.now(IST)
    cutoff = previous_market_close(now.date())

    if report_id is not None:
        placeholder = db.query(Report).filter(Report.id == report_id).first()
        if not placeholder:
            raise ValueError(f"Report {report_id} not found")
    else:
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
            progress_pct=2,
            progress_message="Queued",
        )
        db.add(placeholder)
        db.commit()
        db.refresh(placeholder)

    try:
        _progress(db, placeholder, 8, "step:window|Resolving previous NSE close…")
        placeholder.cutoff_iso = cutoff.isoformat()
        db.commit()

        _progress(db, placeholder, 18, "step:fetch|Fetching Groww feed…")
        articles, feed_stats = fetch_since(cutoff)
        placeholder.articles_in_window = int(feed_stats.get("articles_in_window") or 0)
        _progress(
            db,
            placeholder,
            42,
            f"step:fetch|Fetched {placeholder.articles_in_window} articles in news window",
        )

        _progress(db, placeholder, 48, "step:classify|Classifying catalysts & filtering noise…")
        catalysts, ignored = consolidate(articles, cutoff)
        placeholder.unique_stocks = len({c.symbol for c in catalysts})
        _progress(
            db,
            placeholder,
            58,
            f"step:classify|Identified {placeholder.unique_stocks} stock catalysts",
        )

        _progress(db, placeholder, 62, "step:enrich|Fetching NSE tape, GIFT, ADRs & filings…")
        market_tape = fetch_market_tape()
        global_tape = fetch_global_cues(nifty_cash_last=market_tape.nifty.last)
        adr_tape = fetch_india_adrs()
        event_ctx = fetch_event_context(now.date())
        fo_overlay = build_fo_overlay(
            india_vix_last=market_tape.india_vix.last,
            india_vix_chg=market_tape.india_vix.change_pct,
            adr=adr_tape,
        )

        gift_gap = global_tape.gift_nifty.implied_gap_vs_nifty_pct
        if gift_gap is None:
            gift_gap = global_tape.gift_nifty.change_pct
        if gift_gap is None:
            gift_gap = global_tape.implied_nifty_open_pct

        top_symbols = [c.symbol for c in sorted(catalysts, key=lambda x: x.strength, reverse=True)[:20]]
        stock_data = fetch_stock_data(top_symbols)
        catalysts = apply_market_overlay(
            catalysts,
            stock_data,
            market_tape,
            sector_flags=sector_global_flags(global_tape),
            global_gap_pct=gift_gap,
        )

        filings_index: dict = {}
        filing_verifications: dict = {}
        try:
            ann = fetch_announcements(days=2)
            filings_index = index_filings(ann)
            filing_verifications = verify_catalysts(catalysts, filings_index, top_n=20)
            _progress(db, placeholder, 66, f"step:enrich|Cross-checked {len(ann)} NSE filings…")
        except Exception as exc:  # noqa: BLE001
            _progress(db, placeholder, 66, f"step:enrich|Filings unavailable ({exc})…")

        secondary = cross_check_secondary(catalysts, fetch_secondary_headlines())

        fo_flow = fetch_fo_oi_spurts()
        deals = fetch_large_deals()
        attach_oi_to_catalysts(catalysts, fo_flow)
        attach_deals_to_catalysts(catalysts, deals)
        # Merge FO bias into fo_overlay narrative
        if fo_flow.fo_bias and fo_flow.fo_bias != "Unknown":
            fo_overlay.fo_bias = fo_flow.fo_bias
            fo_overlay.interpretation = (fo_flow.interpretation or []) + list(fo_overlay.interpretation or [])
            fo_overlay.source = "oi_spurts+vix_adr"

        preopen = fetch_preopen_tape(watch_symbols=top_symbols[:15])

        # Event regime softens confidence later
        catalysts = apply_conviction(
            catalysts,
            gift_gap_pct=gift_gap,
            event_regime=event_ctx.regime,
            global_risk=global_tape.composite_risk,
        )
        _progress(db, placeholder, 69, "step:enrich|Conviction + size hints computed…")

        llm_view = None
        actually_used_llm = False
        if use_llm and ollama_available():
            _progress(db, placeholder, 72, "step:enrich|Enriching top names with AI…")
            brief = _global_brief(global_tape, market_tape) + f" | ADRs={adr_tape.composite_pct} | events={event_ctx.regime}"
            catalysts = enrich_top_catalysts(catalysts, limit=6, global_context=brief)
            bullish = [c for c in catalysts if c.bias == "bullish"]
            bearish = [c for c in catalysts if c.bias == "bearish"]
            _progress(db, placeholder, 78, "step:view|Building market view…")
            llm_view = market_view_llm(bullish, bearish, global_context=brief)
            actually_used_llm = True
            # Re-score conviction after LLM may change opening_impact
            catalysts = apply_conviction(
                catalysts,
                gift_gap_pct=gift_gap,
                event_regime=event_ctx.regime,
                global_risk=global_tape.composite_risk,
            )
        else:
            _progress(db, placeholder, 74, "step:view|Building heuristic market view…")

        _progress(db, placeholder, 82, "step:compose|Composing research note…")
        bullish = [c for c in catalysts if c.bias == "bullish"]
        bearish = [c for c in catalysts if c.bias == "bearish"]
        view = build_market_view(bullish, bearish, llm_view)
        view = adjust_market_view(view, market_tape)
        view = adjust_view_with_global(view, global_tape)
        if event_ctx.regime in {"Event Risk", "Expiry"}:
            view["confidence"] = max(2, int(view.get("confidence") or 5) - 1)
            reasons = list(view.get("reasons") or [])
            reasons.append(f"Macro regime: {event_ctx.regime} — size down single-name gaps.")
            view["reasons"] = reasons[:7]
        if adr_tape.composite_pct is not None and abs(adr_tape.composite_pct) >= 1.0:
            reasons = list(view.get("reasons") or [])
            reasons.append(f"India ADRs overnight {adr_tape.composite_pct:+.2f}%.")
            view["reasons"] = reasons[:7]

        precision = {
            "filings_scanned": sum(len(v) for v in filings_index.values()) if filings_index else 0,
            "filings_verified": sum(1 for v in filing_verifications.values() if v.verified),
            "secondary": secondary,
            "adr_tape": adr_tape.to_dict(),
            "event_context": event_ctx.to_dict(),
            "fo_overlay": fo_overlay.to_dict(),
            "fo_flow": fo_flow.to_dict(),
            "deals": deals.to_dict(),
            "preopen": preopen.to_dict(),
        }

        report_md = render_report(
            cutoff=cutoff,
            feed_stats=feed_stats,
            catalysts=catalysts,
            ignored=ignored,
            llm_view=llm_view,
            market_tape=market_tape,
            global_tape=global_tape,
            precision=precision,
            generated_at=now,
        )

        payload = {
            "generated_at": now.isoformat(),
            "cutoff": cutoff.isoformat(),
            "feed_stats": feed_stats,
            "ignored_count": len(ignored),
            "market_tape": market_tape.to_dict(),
            "global_tape": global_tape.to_dict(),
            "precision": precision,
            "market_view": view,
            "catalysts": [
                {
                    "symbol": c.symbol,
                    "name": c.name,
                    "bias": c.bias,
                    "event_type": c.event_type,
                    "strength": c.strength,
                    "opening_impact": c.opening_impact,
                    "why": c.why,
                    "risks": c.risks,
                    "carryover": c.carryover,
                    "sources": c.sources,
                    "headlines": [a.title for a in c.articles],
                    "market_cap_cr": c.market_cap_cr,
                    "sector": c.sector,
                    "industry": c.industry,
                    "prev_day_chg_pct": c.prev_day_chg_pct,
                    "cap_tier": c.cap_tier,
                    "liquidity_tier": c.liquidity_tier,
                    "tradeability": c.tradeability,
                    "filing_verified": c.filing_verified,
                    "filing_status": c.filing_status,
                    "filing_note": c.filing_note,
                    "secondary_confirmed": c.secondary_confirmed,
                    "conviction": c.conviction,
                    "size_hint": c.size_hint,
                    "conviction_factors": c.conviction_factors,
                    "oi_change_pct": c.oi_change_pct,
                    "deal_summary": c.deal_summary,
                }
                for c in catalysts
            ],
        }

        placeholder.markdown = report_md
        placeholder.payload_json = json.dumps(payload)
        placeholder.bias = str(view.get("bias", "Mixed"))
        placeholder.confidence = int(view.get("confidence", 5))
        placeholder.articles_in_window = int(feed_stats.get("articles_in_window") or 0)
        placeholder.unique_stocks = len({c.symbol for c in catalysts})
        placeholder.used_llm = actually_used_llm
        db.commit()

        # Log predictions for Phase D calibration
        try:
            preds = build_prediction_rows(
                catalysts,
                report_id=placeholder.id,
                gift_gap_pct=gift_gap,
                limit=15,
            )
            log_predictions(db, preds)
        except Exception:  # noqa: BLE001
            pass

        if send_mail:
            _progress(db, placeholder, 90, "step:email|Building PDF & sending email…")
            try:
                pdf_bytes = build_report_pdf_from_row(
                    report_id=placeholder.id,
                    bias=placeholder.bias,
                    confidence=placeholder.confidence,
                    cutoff_iso=placeholder.cutoff_iso,
                    articles_in_window=placeholder.articles_in_window,
                    unique_stocks=placeholder.unique_stocks,
                    payload_json=placeholder.payload_json,
                    created_at=placeholder.created_at,
                )
                html_body = build_desk_email_html(
                    report_id=placeholder.id,
                    bias=placeholder.bias,
                    confidence=placeholder.confidence,
                    articles=placeholder.articles_in_window,
                    stocks=placeholder.unique_stocks,
                    cutoff_iso=placeholder.cutoff_iso,
                    payload=payload,
                )
                subject = f"Premarket Desk — {now.strftime('%d %b %Y')} — {placeholder.bias}"
                send_email(
                    cfg=email_cfg,
                    subject=subject,
                    body_text=report_md,
                    body_html=html_body,
                    pdf_bytes=pdf_bytes,
                    pdf_filename=f"premarket-desk-{now.strftime('%Y%m%d')}-{placeholder.id}.pdf",
                )
                placeholder.emailed = True
                placeholder.email_error = ""
            except Exception as exc:  # noqa: BLE001
                placeholder.emailed = False
                placeholder.email_error = str(exc)[:500]

        placeholder.status = "ok"
        _progress(db, placeholder, 100, "step:done|Research note ready")
        db.commit()
        db.refresh(placeholder)
        return placeholder
    except Exception as exc:  # noqa: BLE001
        placeholder.status = "error"
        placeholder.progress_pct = 100
        placeholder.progress_message = f"step:error|Failed: {exc}"[:240]
        placeholder.markdown = f"Run failed: {exc}"
        placeholder.email_error = str(exc)[:500]
        db.commit()
        db.refresh(placeholder)
        raise
