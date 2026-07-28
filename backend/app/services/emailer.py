"""SMTP email delivery for morning notes."""

from __future__ import annotations

import html
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any


def _bool(v: str | bool | None, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).lower() in {"1", "true", "yes", "on"}


def settings_from_map(cfg: dict[str, str]) -> dict[str, Any]:
    return {
        "smtp_host": cfg.get("smtp_host", ""),
        "smtp_port": int(cfg.get("smtp_port") or 587),
        "smtp_user": cfg.get("smtp_user", ""),
        "smtp_password": cfg.get("smtp_password", ""),
        "smtp_from": cfg.get("smtp_from") or cfg.get("smtp_user", ""),
        "smtp_use_tls": _bool(cfg.get("smtp_use_tls"), True),
        "email_to": cfg.get("email_to", ""),
        "email_enabled": _bool(cfg.get("email_enabled")),
        "email_on_run": _bool(cfg.get("email_on_run"), True),
    }


def send_email(
    *,
    cfg: dict[str, Any],
    subject: str,
    body_text: str,
    body_html: str | None = None,
    to_override: str | None = None,
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "premarket-desk.pdf",
) -> None:
    to_addr = (to_override or cfg.get("email_to") or "").strip()
    host = (cfg.get("smtp_host") or "").strip()
    if not to_addr:
        raise ValueError("No recipient configured (email_to)")
    if not host:
        raise ValueError("SMTP host not configured")

    from_addr = cfg.get("smtp_from") or cfg.get("smtp_user") or to_addr

    if pdf_bytes:
        msg = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            alt.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(alt)
        part = MIMEApplication(pdf_bytes, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        msg.attach(part)
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    port = int(cfg.get("smtp_port") or 587)
    use_tls = bool(cfg.get("smtp_use_tls", True))
    # Gmail/Outlook on 587 require STARTTLS before AUTH
    if port == 587:
        use_tls = True
    user = cfg.get("smtp_user") or ""
    password = cfg.get("smtp_password") or ""

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=45) as server:
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [a.strip() for a in to_addr.split(",") if a.strip()], msg.as_string())
        return

    with smtplib.SMTP(host, port, timeout=45) as server:
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if user:
            server.login(user, password)
        server.sendmail(from_addr, [a.strip() for a in to_addr.split(",") if a.strip()], msg.as_string())


def build_desk_email_html(
    *,
    report_id: int,
    bias: str,
    confidence: int,
    articles: int,
    stocks: int,
    cutoff_iso: str,
    payload: dict[str, Any],
) -> str:
    view = payload.get("market_view") or {}
    catalysts = payload.get("catalysts") or []
    bias_final = str(view.get("bias") or bias)
    conf = int(view.get("confidence") or confidence)
    bias_color = "#1f6b4a" if "bull" in bias_final.lower() else "#9b3d32" if "bear" in bias_final.lower() else "#8a6b2f"

    def cards(items: list[dict[str, Any]], border: str) -> str:
        chunks = []
        for c in items:
            heads = "".join(
                f"<li style='margin:0 0 4px;color:#5c6b62'>{html.escape(h)}</li>"
                for h in (c.get("headlines") or [])[:2]
            )
            stars = "★" * int(c.get("strength") or 0) + "☆" * (5 - int(c.get("strength") or 0))
            chunks.append(
                f"""
                <div style="border:1px solid #d7ddd9;border-top:3px solid {border};border-radius:10px;padding:12px 14px;margin:0 0 10px;background:#fff">
                  <div style="font-family:Arial,sans-serif;font-size:14px;font-weight:700;color:#1a1f1c">
                    {html.escape(str(c.get('symbol') or ''))}
                    <span style="font-weight:400;color:#5c6b62"> · {html.escape(str(c.get('name') or ''))}</span>
                  </div>
                  <div style="font-family:Arial,sans-serif;font-size:12px;color:#8a6b2f;margin:4px 0 6px">{stars} · {html.escape(str(c.get('opening_impact') or ''))}</div>
                  <div style="font-family:Arial,sans-serif;font-size:13px;color:#1a1f1c;line-height:1.4">{html.escape(str(c.get('why') or ''))}</div>
                  {"<ul style='padding-left:18px;margin:8px 0 0'>" + heads + "</ul>" if heads else ""}
                </div>
                """
            )
        return "".join(chunks) or "<p style='color:#5c6b62;font-family:Arial,sans-serif;font-size:13px'>None highlighted.</p>"

    bull = [c for c in catalysts if c.get("bias") == "bullish" and int(c.get("strength") or 0) >= 3][:5]
    bear = [c for c in catalysts if c.get("bias") == "bearish" and int(c.get("strength") or 0) >= 3][:5]
    if not bull:
        bull = [c for c in catalysts if c.get("bias") == "bullish"][:5]
    if not bear:
        bear = [c for c in catalysts if c.get("bias") == "bearish"][:5]

    reasons_items = "".join(f"<li>{html.escape(str(r))}</li>" for r in (view.get("reasons") or [])[:4])
    reasons_block = ""
    if reasons_items:
        reasons_block = (
            "<div style='padding:4px 22px 12px'>"
            "<div style='font-family:Arial,sans-serif;font-size:13px;font-weight:700;margin-bottom:6px'>Why this tape</div>"
            f"<ul style='font-family:Arial,sans-serif;font-size:13px;color:#1a1f1c;margin:0;padding-left:18px'>{reasons_items}</ul>"
            "</div>"
        )

    return f"""
    <div style="background:#f4f6f4;padding:24px 12px">
      <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #d7ddd9;border-radius:14px;overflow:hidden">
        <div style="padding:20px 22px;border-bottom:1px solid #d7ddd9">
          <div style="font-family:Georgia,serif;font-size:22px;color:#1a1f1c">Premarket Desk</div>
          <div style="font-family:Arial,sans-serif;font-size:12px;color:#5c6b62;margin-top:4px">
            Report #{report_id} · NSE morning note · PDF attached
          </div>
        </div>
        <div style="padding:16px 22px;display:flex;gap:8px;flex-wrap:wrap">
          <div style="flex:1;min-width:110px;background:#f4f6f4;border-radius:10px;padding:10px 12px">
            <div style="font-family:Arial,sans-serif;font-size:11px;color:#5c6b62;text-transform:uppercase">Bias</div>
            <div style="font-family:Georgia,serif;font-size:20px;color:{bias_color}">{html.escape(bias_final)}</div>
          </div>
          <div style="flex:1;min-width:110px;background:#f4f6f4;border-radius:10px;padding:10px 12px">
            <div style="font-family:Arial,sans-serif;font-size:11px;color:#5c6b62;text-transform:uppercase">Confidence</div>
            <div style="font-family:Georgia,serif;font-size:20px;color:#1a1f1c">{conf}/10</div>
          </div>
          <div style="flex:1;min-width:110px;background:#f4f6f4;border-radius:10px;padding:10px 12px">
            <div style="font-family:Arial,sans-serif;font-size:11px;color:#5c6b62;text-transform:uppercase">Coverage</div>
            <div style="font-family:Georgia,serif;font-size:20px;color:#1a1f1c">{articles} / {stocks}</div>
          </div>
        </div>
        <div style="padding:0 22px 8px;font-family:Arial,sans-serif;font-size:12px;color:#5c6b62">
          Cutoff: {html.escape(cutoff_iso)}
        </div>
        {reasons_block}
        <div style="padding:8px 22px 4px;font-family:Arial,sans-serif;font-size:14px;font-weight:700;color:#1f6b4a">Top bullish</div>
        <div style="padding:0 22px 8px">{cards(bull, "#1f6b4a")}</div>
        <div style="padding:8px 22px 4px;font-family:Arial,sans-serif;font-size:14px;font-weight:700;color:#9b3d32">Top bearish</div>
        <div style="padding:0 22px 16px">{cards(bear, "#9b3d32")}</div>
        <div style="padding:14px 22px;background:#f4f6f4;font-family:Arial,sans-serif;font-size:11px;color:#5c6b62">
          Full clean PDF is attached. Verify filings before trading. Not investment advice.
        </div>
      </div>
    </div>
    """


def markdown_to_simple_html(md: str) -> str:
    escaped = html.escape(md)
    return f"<pre style='font-family:ui-monospace,Menlo,monospace;font-size:13px;line-height:1.45;white-space:pre-wrap'>{escaped}</pre>"
