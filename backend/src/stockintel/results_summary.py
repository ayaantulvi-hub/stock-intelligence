"""Print the latest stored test results as summary statistics, for the README and write-up.

Only aggregate figures from result tables are printed: no prices, headlines or holdings, so the
output is safe for a public job log and within the data providers' terms.
Run: python -m stockintel.results_summary
"""

from sqlalchemy import text

from stockintel.db import get_engine

QUERIES = {
    "candles": """SELECT pattern, horizon, signals, win_rate, avg_return, extra_return, t_stat
        FROM candle_tests WHERE run_at = (SELECT max(run_at) FROM candle_tests)
        ORDER BY t_stat DESC""",
    "candle_runs": """SELECT min(run_at)::date AS first, max(run_at)::date AS last,
        count(DISTINCT run_at) AS runs FROM candle_tests""",
    "signals": """SELECT r.signal, r.direction, r.horizon, r.sample_size, r.win_rate,
        r.baseline_win_rate, r.avg_return, r.baseline_avg_return, r.oos_sample_size, r.edge
        FROM backtest_results r WHERE r.run_id = (SELECT max(id) FROM backtest_runs)
        ORDER BY r.signal, r.horizon""",
    "models": """SELECT model, test_days, t_stat, spread, holdout_t_stat, holdout_spread,
        worst_year, worst_year_spread, calm_spread, stressed_spread, selected, edge, run_at::date
        FROM model_comparisons WHERE run_at = (SELECT max(run_at) FROM model_comparisons)
        ORDER BY t_stat DESC""",
    "stops": """SELECT stop_multiple, trails, trades, avg_return, win_rate, worst_return,
        stopped_share, run_at::date FROM stop_studies
        WHERE run_at = (SELECT max(run_at) FROM stop_studies) ORDER BY trails, stop_multiple""",
    "families": """SELECT family, change, t_stat, verdict FROM family_tests
        WHERE run_at = (SELECT max(run_at) FROM family_tests) ORDER BY t_stat""",
    "calibration": """SELECT model, low, high, rate, n FROM rank_calibration
        WHERE run_at = (SELECT max(run_at) FROM rank_calibration) ORDER BY low""",
    "market": """SELECT run_at::date, edge, t_stat, holdout_gain, test_dates FROM market_checks
        ORDER BY run_at DESC LIMIT 1""",
    "factors": """SELECT factor, spread, t_stat, dates FROM factor_tests
        WHERE tested_at > (SELECT max(tested_at) FROM factor_tests) - interval '1 day'
        ORDER BY abs(t_stat) DESC""",
    "day_trading": """SELECT DISTINCT ON (source) source, data_from, data_to, trades, mean_r,
        win_rate, t_stat, baseline_mean_r, verdict, run_at::date FROM day_trade_tests
        ORDER BY source, run_at DESC""",
    "ledger": """SELECT min(created_at)::date AS first_forecast, max(target_session) AS latest,
        count(*) AS forecasts, count(DISTINCT target_session) AS sessions FROM forecasts""",
    "scores": """SELECT count(*) AS scored, avg(in_range::int) AS in_range_share FROM forecast_scores""",
}


def main() -> None:
    with get_engine().connect() as conn:
        for name, query in QUERIES.items():
            try:
                rows = conn.execute(text(query)).mappings().all()
            except Exception as exc:  # noqa: BLE001 - report and continue to the next table
                conn.rollback()
                print(f"RESULT {name}: not available ({type(exc).__name__})")
                continue
            for row in rows:
                cells = {
                    k: round(v, 4) if isinstance(v, float) else v for k, v in dict(row).items()
                }
                print(f"RESULT {name}: {cells}")


if __name__ == "__main__":
    main()
