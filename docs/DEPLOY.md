# Deploy Premarket Desk

One container serves **backend + built frontend**. LLM should be a **cloud free key** (Gemini/Groq) so it does not depend on your laptop.

## 1) Build locally (required before Docker)

```bash
cd frontend
npm install
npm run build
cd ..
```

This writes `frontend/dist/`, which the Dockerfile copies into the image.

## 2) Prepare `.env` on the server

```bash
cp .env.example .env
```

Set at least:

```env
SECRET_KEY=long-random-string
ADMIN_PASSWORD=strong-password
COOKIE_SECURE=true
CORS_ORIGINS=https://your-domain.com

# Free LLM (independent of your Mac)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-flash-latest

# Optional email bootstrap (also editable in Settings UI)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app-password
SMTP_FROM=you@gmail.com
EMAIL_TO=you@gmail.com
USE_LLM_DEFAULT=true
SCHEDULE_CRON=15 8 * * mon-fri
```

Do **not** commit `.env`. Rotate any key that was pasted in chat.

## 3) Deploy with Docker (recommended)

On the VPS (or any host with Docker):

```bash
# after frontend build + .env
docker compose up -d --build
```

App: **http://SERVER_IP:8000** (or your reverse-proxy HTTPS URL).

Login: `admin` / `ADMIN_PASSWORD`.

Check LLM:

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
# look for "llm": { "active": "gemini", ... }
```

### Optional: Ollama on the same server (~8GB+ RAM)

```bash
# in .env:
# OLLAMA_BASE_URL=http://ollama:11434
# LLM_PROVIDER=auto

docker compose --profile ollama --profile pull run --rm ollama-pull
docker compose --profile ollama up -d --build
```

For a small VPS, skip Ollama and keep Gemini/Groq only.

## 4) Deploy without Docker (VPS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cd frontend && npm install && npm run build && cd ..

# keep process alive (example)
.env loaded via pydantic; export critical vars or use systemd EnvironmentFile
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Put nginx/Caddy in front for HTTPS. Set `COOKIE_SECURE=true` and `CORS_ORIGINS` to your public URL.

**Scheduler note:** morning cron only fires while uvicorn is running. Use systemd/`docker restart unless-stopped` so the process stays up.

## 5) Post-deploy checklist

1. Login works
2. Settings → enable email → **Send test email**
3. Desk → **Fetch & email now** (or `python manual_run.py --email`)
4. `/api/health` shows `llm.active` = `gemini` (or groq)
5. Leave the container/process running overnight for the 08:15 IST schedule

## Common hosts

| Host | Tip |
|------|-----|
| Any VPS (Hetzner, DigitalOcean, AWS Lightsail) | Best fit — Docker + always-on for cron |
| Railway / Render / Fly | Single web service from Dockerfile; set env vars in dashboard; no Ollama unless paid RAM |
| Your Mac only | Fine for testing; **not** independent — Mac must stay on for schedule |

## Rebuild after code changes

```bash
cd frontend && npm run build && cd ..
docker compose up -d --build
```
