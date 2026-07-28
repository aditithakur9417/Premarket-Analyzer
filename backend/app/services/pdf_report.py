"""Clean institutional PDF for premarket notes."""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INK = colors.HexColor("#1a1f1c")
MUTED = colors.HexColor("#5c6b62")
LINE = colors.HexColor("#d7ddd9")
ACCENT = colors.HexColor("#8a6b2f")
BULL = colors.HexColor("#1f6b4a")
BEAR = colors.HexColor("#9b3d32")
SOFT = colors.HexColor("#f4f6f4")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleDesk",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=INK,
            spaceAfter=4,
            leading=22,
        ),
        "sub": ParagraphStyle(
            "SubDesk",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=MUTED,
            spaceAfter=10,
            leading=12,
        ),
        "h2": ParagraphStyle(
            "H2Desk",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=INK,
            spaceBefore=12,
            spaceAfter=6,
            leading=15,
        ),
        "body": ParagraphStyle(
            "BodyDesk",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=INK,
            leading=12,
            spaceAfter=3,
        ),
        "small": ParagraphStyle(
            "SmallDesk",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            leading=10,
            spaceAfter=2,
        ),
        "card_title": ParagraphStyle(
            "CardTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=INK,
            leading=12,
        ),
    }


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _stars(n: int) -> str:
    n = max(0, min(5, int(n or 0)))
    return "*" * n + "-" * (5 - n)


def _bias_color(bias: str):
    b = (bias or "").lower()
    if "bull" in b:
        return BULL
    if "bear" in b:
        return BEAR
    return ACCENT


def build_report_pdf(
    *,
    report_id: int,
    bias: str,
    confidence: int,
    cutoff_iso: str,
    articles: int,
    stocks: int,
    payload: dict[str, Any],
    created_at: datetime | None = None,
) -> bytes:
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Premarket Desk #{report_id}",
    )
    story: list[Any] = []

    view = payload.get("market_view") or {}
    catalysts = payload.get("catalysts") or []
    when = (created_at or datetime.utcnow()).strftime("%d %b %Y %H:%M UTC")

    story.append(Paragraph("Premarket Desk", styles["title"]))
    story.append(
        Paragraph(
            f"NSE pre-market research note · Report #{report_id} · {when}",
            styles["sub"],
        )
    )

    summary = [
        [
            Paragraph(f"<b>Bias</b><br/>{_esc(str(view.get('bias') or bias))}", styles["body"]),
            Paragraph(f"<b>Confidence</b><br/>{int(view.get('confidence') or confidence)}/10", styles["body"]),
            Paragraph(f"<b>Articles</b><br/>{articles}", styles["body"]),
            Paragraph(f"<b>Stocks</b><br/>{stocks}", styles["body"]),
        ]
    ]
    t = Table(summary, colWidths=[40 * mm, 35 * mm, 35 * mm, 35 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TEXTCOLOR", (0, 0), (0, 0), _bias_color(str(view.get("bias") or bias))),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"News window cutoff: {_esc(cutoff_iso)}", styles["small"]))

    gt = payload.get("global_tape") or {}
    gift = gt.get("gift_nifty") or {}
    if gift.get("last") is not None or gt.get("composite_risk"):
        story.append(Paragraph("GIFT Nifty & global cues", styles["h2"]))
        if gift.get("last") is not None:
            gap = gift.get("implied_gap_vs_nifty_pct")
            if gap is None:
                gap = gift.get("change_pct")
            gap_s = f"{gap:+.2f}%" if gap is not None else "n/a"
            story.append(
                Paragraph(
                    f"GIFT Nifty {gift['last']:,.2f} ({gap_s}) — {_esc(gift.get('open_bias') or '')}",
                    styles["body"],
                )
            )
        story.append(Paragraph(f"Composite risk: {_esc(gt.get('composite_risk') or '')}", styles["body"]))
        cue_bits = []
        for c in (gt.get("cues") or [])[:6]:
            if c.get("change_pct") is None:
                continue
            cue_bits.append(f"{c.get('name')}: {c['change_pct']:+.2f}%")
        if cue_bits:
            story.append(Paragraph(_esc(" · ".join(cue_bits)), styles["small"]))
        for note in (gt.get("interpretation") or [])[:3]:
            story.append(Paragraph(f"• {_esc(str(note))}", styles["small"]))

    tape = payload.get("market_tape") or {}
    flows = tape.get("flows") or {}
    if flows.get("fii_net_cr") is not None:
        story.append(Paragraph("Market tape", styles["h2"]))
        fii = flows.get("fii_net_cr")
        dii = flows.get("dii_net_cr") or 0
        story.append(
            Paragraph(
                f"FII net {fii:+,.0f} Cr · DII net {dii:+,.0f} Cr · {_esc(tape.get('flow_bias') or '')}",
                styles["body"],
            )
        )
        nifty = tape.get("nifty") or {}
        vix = tape.get("india_vix") or {}
        if nifty.get("change_pct") is not None:
            story.append(Paragraph(f"Nifty {nifty['change_pct']:+.2f}%", styles["body"]))
        if vix.get("last") is not None:
            story.append(
                Paragraph(
                    f"India VIX {vix['last']:.2f} ({vix.get('change_pct', 0):+.1f}%) — {_esc(tape.get('volatility_regime') or '')}",
                    styles["body"],
                )
            )
        for note in (tape.get("interpretation") or [])[:3]:
            story.append(Paragraph(f"• {_esc(str(note))}", styles["small"]))

    reasons = view.get("reasons") or []
    if reasons or view.get("opportunity") or view.get("risk"):
        story.append(Paragraph("Market view", styles["h2"]))
        for r in reasons[:5]:
            story.append(Paragraph(f"• {_esc(str(r))}", styles["body"]))
        if view.get("opportunity"):
            story.append(Paragraph(f"<b>Opportunity:</b> {_esc(str(view['opportunity']))}", styles["body"]))
        if view.get("risk"):
            story.append(Paragraph(f"<b>Risk:</b> {_esc(str(view['risk']))}", styles["body"]))

    def section(title: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        story.append(Paragraph(title, styles["h2"]))
        for c in items:
            heads = c.get("headlines") or []
            head_txt = "<br/>".join(f"– {_esc(h)}" for h in heads[:3])
            block = [
                [
                    Paragraph(
                        f"<b>{_esc(c.get('symbol') or '')}</b>  {_esc(c.get('name') or '')}<br/>"
                        f"<font color='#5c6b62'>{_esc((c.get('event_type') or '').replace('_', ' '))}"
                        f" · {_stars(int(c.get('strength') or 0))} · {_esc(c.get('opening_impact') or '')}</font>",
                        styles["card_title"],
                    )
                ],
                [Paragraph(_esc(c.get("why") or ""), styles["body"])],
            ]
            if head_txt:
                block.append([Paragraph(head_txt, styles["small"])])
            if c.get("risks"):
                block.append([Paragraph(f"<b>Risk:</b> {_esc(c.get('risks') or '')}", styles["small"])])
            meta_bits = []
            if c.get("conviction"):
                meta_bits.append(f"Conviction {c['conviction']}/100 · Size {c.get('size_hint') or '—'}")
            if c.get("filing_status"):
                meta_bits.append(f"Filing: {c.get('filing_status')}")
            if meta_bits:
                block.append([Paragraph(_esc(" · ".join(meta_bits)), styles["small"])])
            mkt_parts = []
            if c.get("cap_tier"):
                mkt_parts.append(str(c.get("cap_tier")))
            if c.get("market_cap_cr"):
                mkt_parts.append(f"₹{c['market_cap_cr']:,.0f} Cr")
            if c.get("prev_day_chg_pct") is not None:
                mkt_parts.append(f"prior {c['prev_day_chg_pct']:+.1f}%")
            if c.get("liquidity_tier"):
                mkt_parts.append(f"liq {c['liquidity_tier']}")
            if mkt_parts:
                block.append([Paragraph(_esc(" · ".join(mkt_parts)), styles["small"])])
            ct = Table(block, colWidths=[170 * mm])
            ct.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        (
                            "LINEABOVE",
                            (0, 0),
                            (-1, 0),
                            2,
                            _bias_color(str(c.get("bias") or "")),
                        ),
                    ]
                )
            )
            story.append(ct)
            story.append(Spacer(1, 5))

    bull = [c for c in catalysts if c.get("bias") == "bullish" and int(c.get("strength") or 0) >= 3][:8]
    bear = [c for c in catalysts if c.get("bias") == "bearish" and int(c.get("strength") or 0) >= 3][:8]
    if not bull:
        bull = [c for c in catalysts if c.get("bias") == "bullish"][:6]
    if not bear:
        bear = [c for c in catalysts if c.get("bias") == "bearish"][:6]
    carry = [c for c in catalysts if c.get("carryover")][:6]

    section("Top bullish", bull)
    section("Top bearish", bear)
    if carry:
        story.append(Paragraph("Momentum carryover", styles["h2"]))
        for c in carry:
            story.append(
                Paragraph(
                    f"• <b>{_esc(c.get('symbol') or '')}</b> — {_esc((c.get('event_type') or '').replace('_', ' '))}"
                    f" ({_stars(int(c.get('strength') or 0))})",
                    styles["body"],
                )
            )

    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "Confidential desk note. Verify exchange filings before trading. Not investment advice.",
            styles["small"],
        )
    )

    doc.build(story)
    return buf.getvalue()


def build_report_pdf_from_row(
    *,
    report_id: int,
    bias: str,
    confidence: int,
    cutoff_iso: str,
    articles_in_window: int,
    unique_stocks: int,
    payload_json: str,
    created_at: datetime | None = None,
) -> bytes:
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return build_report_pdf(
        report_id=report_id,
        bias=bias,
        confidence=confidence,
        cutoff_iso=cutoff_iso,
        articles=articles_in_window,
        stocks=unique_stocks,
        payload=payload,
        created_at=created_at,
    )
