# Operations

How the live system is deployed, kept private and recovered when something fails. The project overview is in the [README](../README.md).

## Services

| Part | Where | Cost |
|---|---|---|
| Hourly data updates | GitHub Actions `update-data.yml`, started by cron-job.org | Free: the repository is public, so minutes are unlimited |
| Daily decisions | The first update after 10:50 UTC (2:50pm Dubai) on each US trading day, Monday included | Free |
| Weekly backtest and day-trading test | `backtest.yml` and `day-trading-test.yml`, Saturdays | Free |
| Database | Neon free plan | Free up to 1 GB storage, 100 compute hours and 5 GB transfer a month |
| Dashboard | Render free web service, `render.yaml` and `Dockerfile` | Free; sleeps when unused, so the first load takes about a minute |
| Data | Tiingo, Alpaca (IEX and SIP), SEC EDGAR, FRED, FINRA, House Clerk, Groq | Free tiers only |

## Deploy

1. **Database.** Create a Neon project and copy its connection string. Tables are created by the
   first update run (`alembic upgrade head`).
2. **GitHub secrets** (Settings, Secrets and variables, Actions): `DATABASE_URL`,
   `TIINGO_API_TOKEN`, `FRED_API_KEY`, `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`,
   `GROQ_API_KEY`, `SEC_CONTACT_EMAIL`. Secrets never appear in code or logs.
3. **Dashboard.** In Render, create a Blueprint from this repository. Set `DATABASE_URL`,
   `DASHBOARD_PASSWORD`, `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY`. Sign in with any
   username and that password.
4. **Hourly trigger.** On cron-job.org, create a job that sends
   `POST https://api.github.com/repos/<owner>/<repo>/actions/workflows/update-data.yml/dispatches`
   with body `{"ref":"main"}` and headers `Authorization: Bearer <fine-grained token with
   Actions: write>` and `Accept: application/vnd.github+json`. Schedule: minute 50, every hour,
   Monday to Saturday (Dubai time).

## Keep it private

The repository is public. Holdings are entered only through **Actions, Set holdings**, which reads
them from the trigger and never prints them. Alert issues give only a count; details are on the
password-protected Alerts page. Never add a step that prints holdings, shares or stops.

## When something fails

| What you see | Likely cause | Fix |
|---|---|---|
| "Not verified" or stale prices on the site | An update didn't run or a feed failed | Open Actions, Update data, and read the last run's Report step. Run it by hand with **Run workflow**. |
| No decisions today | The daily run didn't happen before the US open | Run **Update data** by hand with "Write forecasts" ticked, before 9:30am New York. After the open, forecasts are refused on purpose. |
| Prices only partly updated | Tiingo's 50-an-hour limit | Nothing: the next hourly run continues. Alpaca fills every latest close in the meantime. |
| "Groq: no valid reply" | The free AI service failed three times | It retries next hour. News warnings are skipped until then. |
| Site loads slowly | Render's free service was asleep | Wait about a minute. |
| Every connection fails | Neon's monthly compute or transfer is used up | Check Neon's Usage page. It resets next month; reduce the hourly runs on cron-job.org if it recurs. |
| Database full (1 GB) | Old rows built up | Run **Actions, Run one step, retention**. It deletes only data the decisions no longer use. |
| A stock says it is too new to judge | It has under 250 days of prices | Nothing: it gets decisions once it has a year of history. |

Stored records are never edited. A correction adds a new row, so nothing is lost by re-running
any step, and forecasts already written are never replaced.

