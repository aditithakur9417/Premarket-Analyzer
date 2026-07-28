# GitHub Actions — free morning desk (no VPS)

This runs **fetch → Gemini enrich → email** on GitHub’s servers.
Your Mac can be off. No Hostinger VPS required for the morning note.

Schedule: **Mon–Fri 08:15 IST** (`45 2 * * 1-5` UTC).

---

## 1) Push the workflow (if not already on GitHub)

The file lives at:

`.github/workflows/morning-desk.yml`

If you just added it locally:

```bash
git add .github docs/GITHUB_ACTIONS.md
git commit -m "Add GitHub Actions morning desk workflow"
git push origin main
```

---

## 2) Add repository secrets

GitHub → your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret name | Example / notes |
|-------------|-----------------|
| `GEMINI_API_KEY` | Your Gemini key (rotate if it was pasted in chat) |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_USER` | your Gmail |
| `SMTP_PASSWORD` | Gmail **app password** (not normal password) |
| `SMTP_FROM` | same as SMTP_USER (or display address) |
| `EMAIL_TO` | where the note should go |
| `SECRET_KEY` | any long random string |
| `ADMIN_PASSWORD` | any password (only used to seed DB in CI) |

Optional:

| Secret | Default if omitted |
|--------|--------------------|
| `GEMINI_MODEL` | `gemini-flash-latest` |
| `SMTP_PORT` | `587` |

Do **not** put these in code or commit `.env`.

---

## 3) Enable Actions

GitHub → **Actions** tab → allow workflows if prompted.

---

## 4) Test once (manual)

1. **Actions** → **Morning Desk** → **Run workflow** → **Run workflow**
2. Open the run → watch **Fetch, analyze, email**
3. Check your inbox

If email fails, read the job log for SMTP errors. If Gemini fails, check key/model/quota.

---

## 5) What you get / don’t get

| Included | Not included |
|----------|--------------|
| Morning email note | Always-on website UI |
| Gemini enrichment | Live Desk at a public URL |
| Free for normal private-repo minutes | Unlimited heavy runs |

For a live UI later, use a VPS. For “email me every morning,” Actions is enough.

---

## Troubleshooting

- **Schedule didn’t fire:** GitHub cron can be a few minutes late; inactive repos may skip schedules — use **Run workflow** to confirm setup.
- **Email not sent:** confirm all SMTP secrets + `EMAIL_TO`; Gmail needs an [app password](https://myaccount.google.com/apppasswords).
- **Gemini 429:** switch `GEMINI_MODEL` secret to `gemini-flash-latest` (or try Groq later).
- **Minutes:** private repos share a monthly free allotment; one ~3–8 min weekday run is usually fine.
