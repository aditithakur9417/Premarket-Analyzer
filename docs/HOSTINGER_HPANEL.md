# Deploy on Hostinger (hPanel) — independent of your Mac

Premarket Desk is a **long-running Python app** (FastAPI + morning scheduler).  
It does **not** fit normal shared “Website” hosting. Use a **VPS**.

## What you need

1. Hostinger **VPS** (Docker template recommended)
2. Project on **GitHub** (public or private)
3. Env vars: `SECRET_KEY`, `ADMIN_PASSWORD`, `GEMINI_API_KEY`, etc.

Your laptop can be off after deploy. Gemini runs in the cloud.

---

## Path A — Docker Manager in hPanel (easiest)

### 1. VPS

- hPanel → **VPS** → create/manage server  
- OS/template: **Docker** (so Docker Manager is available)

### 2. Push this repo to GitHub

Include `Dockerfile` + `docker-compose.yml` (already set to build the frontend inside Docker).

### 3. Deploy

1. hPanel → your VPS → **Docker Manager**
2. **Compose** → **Compose from URL** (or manual paste)
3. Point at your repo’s `docker-compose.yml`
4. Project name e.g. `premarket-desk`
5. Add **environment variables** (do not put secrets in GitHub):

```env
SECRET_KEY=long-random-string
ADMIN_PASSWORD=strong-password
COOKIE_SECURE=true
CORS_ORIGINS=https://your-domain.com
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-flash-latest
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=gmail-app-password
SMTP_FROM=you@gmail.com
EMAIL_TO=you@gmail.com
USE_LLM_DEFAULT=true
SCHEDULE_CRON=15 8 * * mon-fri
```

6. **Deploy** and wait for the build (first time can take a few minutes)

### 4. Open the app

- `http://YOUR_VPS_IP:8000`  
- Or attach a domain + SSL in hPanel, then set `CORS_ORIGINS` / `COOKIE_SECURE=true` to that HTTPS URL

Login: `admin` / your `ADMIN_PASSWORD`.

### 5. Verify

- Desk loads  
- Settings → test email  
- Fetch once  
- Keep the container **running** so 08:15 IST cron still fires  

Docs: [Hostinger Docker Manager](https://www.hostinger.com/support/12040815-how-to-deploy-your-first-container-with-hostinger-docker-manager/)

---

## Path B — SSH on VPS (no Docker Manager)

```bash
git clone https://github.com/YOUR_USER/premarket-analyzer.git
cd premarket-analyzer
cp .env.example .env   # edit secrets + GEMINI_API_KEY
docker compose up -d --build
```

Same result: always-on desk on the VPS.

---

## Shared hosting / “Websites” in hPanel?

**Skip for this project.** No reliable always-on uvicorn + APScheduler. Use VPS.

---

## After deploy checklist

| Check | Why |
|-------|-----|
| Container status = running | Scheduler needs process up |
| Gemini key in env | LLM without your Mac |
| Email in Settings | Morning note delivery |
| Firewall allows port 8000 (or 80/443 via proxy) | Public access |

Rebuild after code changes: push to GitHub → redeploy in Docker Manager (or `docker compose up -d --build` over SSH).
