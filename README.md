# Premarket Desk

Password-gated NSE pre-market catalyst analyzer with admin holiday calendar, email delivery, and scheduled runs.

## Features

- **Login** — single admin user (cookie session)
- **Desk** — run analysis, view/history, email note
- **Holidays** — NSE 2026 seed + add/remove yourself (drives previous close cutoff)
- **Settings** — SMTP email, schedule (IST cron), LLM toggle, change password
- **Scheduler** — default `08:15 IST` Mon–Fri

## Local development

```bash
cp .env.example .env
# edit SECRET_KEY and ADMIN_PASSWORD

# backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 — login `admin` / password from `.env`.

## Production (Docker)

Full guides:
- **[docs/DEPLOY.md](docs/DEPLOY.md)** — general Docker / VPS
- **[docs/HOSTINGER_HPANEL.md](docs/HOSTINGER_HPANEL.md)** — Hostinger hPanel (VPS + Docker Manager)
- **[docs/GITHUB_ACTIONS.md](docs/GITHUB_ACTIONS.md)** — free morning run via GitHub Actions (no VPS)
- **[docs/LLM_DEPLOY.md](docs/LLM_DEPLOY.md)** — free Gemini/Groq (no local Ollama)
- **[docs/ACCURACY_UPGRADES.md](docs/ACCURACY_UPGRADES.md)** — premarket classifier / filings accuracy

```bash
# Frontend is built inside Docker now; local build optional
cp .env.example .env   # set SECRET_KEY, ADMIN_PASSWORD, GEMINI_API_KEY
docker compose up -d --build
```

Open http://localhost:8000

Set `COOKIE_SECURE=true` behind HTTPS. Use Gemini/Groq in `.env` so the desk does not depend on your laptop.

## Email

In **Settings**, configure SMTP (Gmail app password, Resend SMTP, etc.), recipients, enable email, then **Send test email**.

**Run + email** on the Desk tab sends the morning note after each analysis.

## Manual fetch & email (anytime)

**In the UI (Desk tab):** use **Fetch & email now** or **Fetch only**.

**From terminal:**

```bash
source .venv/bin/activate
python manual_run.py --email          # fetch + analyze + email
python manual_run.py --no-email       # fetch + analyze only
python manual_run.py --email --no-llm # faster, no Ollama
```

Scheduled runs still fire on the IST cron if enabled in Settings.
