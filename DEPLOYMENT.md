# FarmBiddy — Deployment Guide

This guide walks you through deploying the FarmBiddy Financial Forecast Skill so your boss can open **one public URL** and use the app from any computer.

---

## Recommended platform: **Render**

### Why Render (and not the others)?

| Platform | Verdict | Reason |
|----------|---------|--------|
| **Render** | **Recommended** | Built for Python web apps (FastAPI + uvicorn). Simple GitHub deploy. Free tier for demos. Optional persistent disk for saved forecasts/charts. |
| Railway | Good alternative | Similar to Render; usage-based pricing can be less predictable for beginners. |
| Fly.io | Powerful but complex | Requires Docker/containers and more DevOps setup. |
| Vercel | **Not suitable** | Serverless — no persistent disk, cold starts, poor fit for FastAPI apps that write chart files and forecast history. |
| Heroku | Possible | Works, but free tier removed; Render is simpler for this project. |

### Why this app needs a “real” server (not serverless)

FarmBiddy:

- Runs a **long-lived FastAPI** process
- **Writes files** (forecast JSON, Plotly HTML charts, comparisons)
- Serves those files back via `/chart-files/...`
- Will later add **PDF reports** and **Supabase** — both fit a traditional web service better

Render hosts one continuous web service — exactly what this prototype needs.

---

## Before you deploy — project checklist

### What gets committed to GitHub

| Commit | Do not commit |
|--------|----------------|
| `api/`, `frontend/`, `forecast_engine/`, `services/`, `models/`, `config/` | `.env` (secrets) |
| `datasets/` (mock farm JSON) | `outputs/history/*` (generated forecasts) |
| `requirements.txt`, `render.yaml`, `.gitignore` | `outputs/charts/*` (generated HTML) |
| Empty `outputs/*/.gitkeep` folders | `.venv/`, `__pycache__/` |

### Free tier limitation (important)

On Render’s **free** plan:

- The app **spins down after ~15 minutes** of no use — first visit after idle may take 30–60 seconds.
- **Disk is ephemeral** — forecast history and charts are **lost on redeploy or restart**.
- For a boss demo in one session this is fine (run forecasts, view charts, compare farms).
- For **persistent storage**, upgrade to Render **Starter** and enable a persistent disk (see below).

---

## Step 1 — Install Git (if needed)

Download: https://git-scm.com/download/win

Verify:

```bash
git --version
```

---

## Step 2 — Create a GitHub repository

1. Go to https://github.com and sign in.
2. Click **New repository**.
3. Name it e.g. `farmbiddy-forecast`.
4. Choose **Private** (recommended for a business prototype).
5. Do **not** add README, .gitignore, or license (we already have them).
6. Click **Create repository**.

---

## Step 3 — Push your code to GitHub

Open PowerShell in your project folder:

```powershell
cd "C:\Users\User\Desktop\CODE FARMBIDDY\TEST\DAIRY FINANCIALS"

git init
git add .
git status
```

Review `git status` — you should **not** see `.env` or files inside `outputs/history/` or `outputs/charts/`.

```powershell
git commit -m "Prepare FarmBiddy forecast app for Render deployment"

git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/farmbiddy-forecast.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

---

## Step 4 — Deploy on Render

### Option A — Using `render.yaml` (recommended)

1. Go to https://dashboard.render.com and sign up (GitHub login works best).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub account and select the `farmbiddy-forecast` repository.
3. Render detects `render.yaml` automatically.
4. Click **Apply** / **Deploy**.

### Option B — Manual web service

1. **New +** → **Web Service**.
2. Connect the GitHub repo.
3. Settings:
   - **Name:** `farmbiddy-forecast`
   - **Region:** Frankfurt (or closest to you)
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free
4. **Advanced** → **Health Check Path:** `/api/status`
5. **Environment** → add `PYTHON_VERSION` = `3.12.0`
6. Click **Create Web Service**.

---

## Step 5 — Get your public URL

After deploy succeeds (5–10 minutes first time), Render shows:

```
https://farmbiddy-forecast.onrender.com
```

Send that link to your boss. They can:

- Open the visual interface at `/`
- Select farms and run analysis
- Use Advisor Sandbox
- Generate and view charts
- Compare multiple farms

API docs remain at: `https://YOUR-APP.onrender.com/docs`

---

## Step 6 — Updating after code changes

```powershell
git add .
git commit -m "Describe your change"
git push
```

Render **automatically redeploys** on every push to `main`.

---

## Step 7 — Restart, logs, and troubleshooting

### Restart the service

Render dashboard → your service → **Manual Deploy** → **Clear build cache & deploy** (or **Restart** if available).

### View logs

Render dashboard → **Logs** tab. Watch for:

- `Application startup complete`
- Import errors (`ModuleNotFoundError`)
- Port binding errors (start command must use `$PORT`)

### Common issues

| Problem | Fix |
|---------|-----|
| **502 Bad Gateway** | Check logs; usually wrong start command. Must be `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| **Slow first load** | Free tier cold start — wait 30–60 seconds, refresh |
| **Charts not showing** | Run analysis with “Generate charts” enabled; check logs for Plotly errors |
| **Module not found** | Ensure package is in `requirements.txt` |
| **Farm file not found** | Ensure `datasets/*.json` was committed to Git |

### Test locally before pushing

```powershell
cd "C:\Users\User\Desktop\CODE FARMBIDDY\TEST\DAIRY FINANCIALS"
python -m pip install -r requirements.txt
uvicorn api.main:app --reload
```

Open http://127.0.0.1:8000

---

## Optional — Persistent storage (paid)

To keep forecast history and charts across restarts:

1. Upgrade web service to **Starter** plan.
2. Add a **Disk** (1 GB) mounted at `/opt/render/project/data`.
3. Add environment variable: `STORAGE_PATH=/opt/render/project/data`
4. Redeploy.

The app reads `STORAGE_PATH` from `config/paths.py` automatically.

---

## Local vs production configuration

| Setting | Local | Render |
|---------|-------|--------|
| Storage | `./outputs/` | `./outputs/` (free) or disk mount (paid) |
| Port | `8000` | `$PORT` (set by Render) |
| Host | `127.0.0.1` | `0.0.0.0` |

Copy `.env.example` to `.env` for local overrides (never commit `.env`).

---

## Production readiness recommendations

### Security (prototype stage)

- Keep the repo **private** on GitHub.
- Do **not** commit `.env` or API keys.
- The app has **no login** — anyone with the URL can use it. Acceptable for a closed demo; add auth before a public launch.
- Render provides HTTPS automatically.

### Maintainability

- Business logic stays in `forecast_engine/` and `services/` — not in `api/`.
- Paths centralized in `config/paths.py`.
- One `requirements.txt` for dependencies.

### Scalability

- Current design: single web instance, file-based storage.
- For more users: upgrade Render plan, add persistent disk or move storage to **Supabase Storage**.

### Future Supabase integration

Recommended path:

| Data | Supabase product |
|------|------------------|
| Farm records | PostgreSQL tables |
| Forecast history | PostgreSQL JSON columns or Storage buckets |
| Chart HTML | Storage buckets (public or signed URLs) |
| User accounts / advisors | Supabase Auth |

Replace file reads/writes in `output_service.py` and `chart_service.py` with Supabase client calls — paths in `config/paths.py` become a thin storage abstraction.

### Future PDF report generation

- Add `weasyprint` or `reportlab` to `requirements.txt`.
- Generate PDFs server-side into `STORAGE_ROOT/reports/`.
- Serve via a new `/report-files/` static mount (same pattern as charts).
- Render’s persistent disk or Supabase Storage for saved PDFs.

---

## Quick reference — files created for deployment

| File | Purpose |
|------|---------|
| `render.yaml` | Render Blueprint — build & start commands |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes generated outputs and secrets |
| `.env.example` | Documents optional `STORAGE_PATH` |
| `config/paths.py` | Central paths for local and cloud storage |

---

## Exact commands summary

```powershell
# One-time setup
git init
git add .
git commit -m "Prepare FarmBiddy forecast app for Render deployment"
git remote add origin https://github.com/YOUR_USERNAME/farmbiddy-forecast.git
git push -u origin main

# After each change
git add .
git commit -m "Your update message"
git push

# Local test
python -m pip install -r requirements.txt
uvicorn api.main:app --reload
```

Your boss opens: **https://YOUR-SERVICE-NAME.onrender.com**

No local installation required on their computer.
