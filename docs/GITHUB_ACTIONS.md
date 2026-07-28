# GitHub Actions — free morning desk (no VPS)

This runs **fetch → Gemini enrich → email** on GitHub’s servers.
Your Mac can be off. No Hostinger VPS required for the morning note.

Schedule: triggered by **[cron-job.org](https://cron-job.org)** at Mon–Fri 08:15 IST (see §6). Manual **Run workflow** still works.

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

## 6) Extra reliability (free) — external cron

GitHub’s built-in schedule can pause after ~60 days of repo inactivity, and can run a bit late.

**Free workaround:** use [cron-job.org](https://cron-job.org) (free) to call GitHub every weekday and **start the same workflow**. Your Mac stays off; no VPS.

### A) Create a fine-grained GitHub token

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate**
2. Resource owner: your user
3. Repository access: **Only select** `Premarket-Analyzer`
4. Permissions → **Actions**: **Read and write**
5. Generate and **copy** the token (store only in cron-job.org — never commit it)

### B) Create the cron job

1. Sign up at https://cron-job.org (free)
2. **Create cronjob**:
   - **Title:** Premarket Morning Desk
   - **URL:**  
     `https://api.github.com/repos/aditithakur9417/Premarket-Analyzer/actions/workflows/morning-desk.yml/dispatches`
   - **Schedule:** every day Mon–Fri at **08:15**, timezone **Asia/Kolkata**
   - **Request method:** `POST`
   - **Request headers** (add all three):

| Header | Value |
|--------|--------|
| `Authorization` | `Bearer YOUR_GITHUB_TOKEN` |
| `Accept` | `application/vnd.github+json` |
| `Content-Type` | `application/json` |

   - **Request body:**

```json
{"ref":"main"}
```

3. Save → use **Run now** once → check GitHub **Actions** for a new **Morning Desk** run

### C) Avoid double emails

Pick **one** scheduler as primary:

- **Recommended:** keep cron-job.org + **remove** the `schedule:` block from `.github/workflows/morning-desk.yml` (leave `workflow_dispatch:`), **or**
- Keep GitHub’s `schedule:` and skip cron-job.org until you notice missed days

If both fire at the same time, you can get **two emails**.

### D) Token safety

- If the token leaks, revoke it in GitHub and create a new one
- Do not put the token in the repo, chat, or screenshots

---

## Troubleshooting

- **Schedule didn’t fire:** GitHub cron can be a few minutes late; inactive repos may skip schedules — use **Run workflow** or the cron-job.org ping above.
- **Email not sent:** confirm all SMTP secrets + `EMAIL_TO`; Gmail needs an [app password](https://myaccount.google.com/apppasswords).
- **Gemini 429:** use model `gemini-flash-latest` (already set in the workflow).
- **Minutes:** private repos share a monthly free allotment; one ~3–8 min weekday run is usually fine.
- **cron-job.org returns 401/403:** token missing Actions write permission, or wrong repo name in the URL.
- **cron-job.org returns 204:** success (GitHub accepted the dispatch).
