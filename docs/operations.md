# Operations

This covers how the live Quant Lab is deployed, kept private, and recovered when something
fails. The project overview is in the [README](../README.md).

## Services

| Part | Where | Cost |
|---|---|---|
| Hourly data | GitHub Actions `update-data.yml`, started by cron-job.org | Free: the repository is public, so minutes are unlimited |
| Weekly studies | `backtest.yml` ("Quant studies"), Saturdays, or by hand | Free |
| Database | Neon free plan | Free up to 1 GB storage, 100 compute hours and 5 GB transfer a month |
| Dashboard | Render free web service, `render.yaml` and `Dockerfile` | Free; it sleeps when unused, so the first load takes about a minute |
| Data | Tiingo, Alpaca, SEC EDGAR, FRED | Free tiers only |

## Deploy

1. **Database.** Create a Neon project and copy its connection string. The first run creates
   the tables (`alembic upgrade head`).
2. **GitHub secrets** (Settings, Secrets and variables, Actions): `DATABASE_URL`,
   `TIINGO_API_TOKEN`, `FRED_API_KEY`, `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`,
   `SEC_CONTACT_EMAIL`. Secrets never appear in code or logs.
3. **Dashboard.** In Render, create a Blueprint from this repository, then set
   `DATABASE_URL` and `DASHBOARD_PASSWORD`. Sign in with any username and that password.
4. **Hourly trigger.** On cron-job.org, create a job with:
   - **Request:** `POST https://api.github.com/repos/<owner>/<repo>/actions/workflows/update-data.yml/dispatches`
   - **Body:** `{"ref":"main"}`
   - **Headers:** `Authorization: Bearer <fine-grained token with Actions: write>` and
     `Accept: application/vnd.github+json`
   - **Schedule:** minute 50, every hour, Monday to Saturday.

## Keep it private

- **The repository is public**, so job logs and issues are public too. Every step prints
  summary figures only, never prices.
- **The dashboard stays password protected,** because it charts series derived from Tiingo
  prices, which Tiingo's terms don't allow redistributing.
- **No GROQ_API_KEY is needed any more.** It was used only by the old app's news reader, so
  the secret can be deleted from GitHub.

## When something fails

| What you see | Likely cause | Fix |
|---|---|---|
| A feed shows an error on the Data section | A run failed or a key expired | Open Actions, Update data, read the failed step, and rerun it with **Run workflow**. |
| Prices only partly updated | Tiingo's 50-an-hour limit | Nothing: the next hourly run continues, and Alpaca fills every latest close in the meantime. |
| A study says "not run yet" | The weekly run hasn't happened or it failed | Run **Actions, Quant studies** by hand. |
| Site loads slowly | Render's free service was asleep | Wait about a minute. |
| Every connection fails | Neon's monthly compute or transfer is used up | Check Neon's Usage page. It resets next month; reduce the hourly runs on cron-job.org if it happens again. |
| Database full (1 GB) | Old rows built up | Run **Actions, Run one step, retention**. It removes only exact repeats and old logs. |

## Stored data

- **Records are never edited.** A correction adds a new row, so re-running any step loses
  nothing.
- **The old app's tables are kept as an archive** (forecasts, holdings, news and others). No
  code reads or writes them now. Dropping them would free space but can't be undone.
