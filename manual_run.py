#!/usr/bin/env python3
"""Manual one-shot: fetch news, analyze, save report, optionally email."""

from __future__ import annotations

import argparse
import sys

from backend.app.database import SessionLocal, Base, engine
from backend.app.services.runner import run_analysis
from backend.app.services.seed import ensure_admin_user, seed_holidays, seed_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual Premarket Desk run")
    parser.add_argument("--email", action="store_true", help="Email the report after run")
    parser.add_argument("--no-email", action="store_true", help="Do not email (override settings)")
    parser.add_argument("--no-llm", action="store_true", help="Skip Ollama enrichment")
    parser.add_argument("--llm", action="store_true", help="Force LLM enrichment")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_admin_user(db)
        seed_settings(db)
        seed_holidays(db, only_missing=True)

        send_mail: bool | None
        if args.email:
            send_mail = True
        elif args.no_email:
            send_mail = False
        else:
            send_mail = None  # follow settings

        use_llm: bool | None
        if args.no_llm:
            use_llm = False
        elif args.llm:
            use_llm = True
        else:
            use_llm = None

        print("[manual] Fetching + analyzing…")
        report = run_analysis(db, use_llm=use_llm, send_mail=send_mail)
        print(f"[manual] Report #{report.id} status={report.status} bias={report.bias}")
        print(f"[manual] Articles={report.articles_in_window} stocks={report.unique_stocks}")
        if report.emailed:
            print("[manual] Email sent OK")
        elif send_mail is True or (send_mail is None):
            print(f"[manual] Email not sent: {report.email_error or 'disabled/skipped'}")
        print(report.markdown[:1500])
        if len(report.markdown) > 1500:
            print("\n… (truncated — full note saved in Desk history)")
        return 0 if report.status == "ok" else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
