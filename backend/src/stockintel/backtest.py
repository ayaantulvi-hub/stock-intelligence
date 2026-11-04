"""Backtesting: did each signal beat simply holding, after costs, on data it had not seen?

Rules that keep the test honest:
- A signal on one candle is traded at the next candle's open, never the same close.
- Walk-forward: each year counts only if earlier years alone had already shown an edge.
- Results are compared with a baseline that holds through the same years.
- Run python -m stockintel.backtest after prices are loaded.
"""

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from stockintel.charts import adjust, pattern_history
from stockintel.db import get_engine

HORIZONS = (5, 20)
PRIMARY_HORIZON = 20
COST_BPS = 10.0
MIN_SAMPLE = 30
# 8 rules over 2 holding periods is 16 tests, so some would pass by luck at the usual 2.0.
# 3.0 allows for that, and for trades that overlap in time.
MIN_Z = 3.0
SIZE_LIMIT = 1000
SURVIVORSHIP_NOTE = (
    "Survivorship bias, reduced but not removed: each stock is tested only from when it was "
    "already among about the 1,000 largest, but companies that later failed or were bought "
    "are still missing, so results may look better than they really were."
)


class LookAheadError(Exception):
    """A signal changed when future bars were added, so it used data it could not know."""


def assert_no_look_ahead(signal_fn, frame: pd.DataFrame, checkpoints: int = 8) -> None:
    """Fail if signal_fn's past output changes when later bars are removed."""
    full = signal_fn(frame)
    start = len(frame) // 2
    for end in np.linspace(start, len(frame) - 1, checkpoints, dtype=int):
        partial = signal_fn(frame.iloc[: end + 1].reset_index(drop=True))
        if not partial.equals(full.iloc[: end + 1].reset_index(drop=True)):
            raise LookAheadError(f"signal changed when bars after row {end} were removed")


@dataclass
class Tally:
    wins: int = 0
    count: int = 0
    total: float = 0.0

    def add(self, returns: np.ndarray) -> None:
        self.wins += int((returns > 0).sum())
        self.count += len(returns)
        self.total += float(returns.sum())

    def merge(self, other: "Tally") -> None:
        self.wins += other.wins
        self.count += other.count
        self.total += other.total

    @property
    def win_rate(self) -> float | None:
        return self.wins / self.count if self.count else None

    @property
    def average(self) -> float | None:
        return self.total / self.count if self.count else None


def has_edge(signal: Tally, baseline: Tally) -> bool:
    """Needs enough cases, a better average, and a win rate clearly above chance."""
    if signal.count < MIN_SAMPLE or not baseline.count:
        return False
    rate, expected = signal.win_rate, baseline.win_rate
    error = sqrt(max(expected * (1 - expected), 1e-9) / signal.count)
    return (rate - expected) / error >= MIN_Z and signal.average > baseline.average


class Backtest:
    def __init__(self, cost_bps: float = COST_BPS):
        self.cost = cost_bps / 10000
        self.signals: dict[tuple, dict[int, Tally]] = defaultdict(lambda: defaultdict(Tally))
        self.baselines: dict[tuple, dict[int, Tally]] = defaultdict(lambda: defaultdict(Tally))

    def add_stock(self, frame: pd.DataFrame, eligible: np.ndarray | None = None) -> None:
        """frame: oldest-first adjusted bars with market_date, open and close.

        eligible marks the days this stock had really earned a place on the list.
        """
        if len(frame) < 2:
            return
        flags = pattern_history(frame)
        opens = frame["open"].to_numpy(dtype=float)
        closes = frame["close"].to_numpy(dtype=float)
        years = pd.to_datetime(frame["market_date"]).dt.year.to_numpy()
        for horizon in HORIZONS:
            # Enter at the next open, leave at the close `horizon` bars later.
            count = len(frame) - horizon - 1
            if count <= 0:
                continue
            allowed = np.ones(count, bool) if eligible is None else eligible[:count]
            gross = closes[horizon + 1 :][:count] / opens[1 : count + 1] - 1
            long_net, short_net = gross - self.cost, -gross - self.cost
            for (name, direction), column in flags.items():
                returns = long_net if direction == "bullish" else short_net
                fired = column.to_numpy()[:count]
                for year in np.unique(years[:count]):
                    in_year = (years[:count] == year) & allowed
                    self.signals[(name, direction, horizon)][int(year)].add(
                        returns[in_year & fired]
                    )
                    self.baselines[(direction, horizon)][int(year)].add(returns[in_year])

    def results(self) -> list[dict]:
        output = []
        for (name, direction, horizon), by_year in sorted(self.signals.items()):
            baseline_by_year = self.baselines[(direction, horizon)]
            total, total_base = Tally(), Tally()
            seen, seen_base = Tally(), Tally()
            oos, oos_base = Tally(), Tally()
            for year in sorted(by_year):
                # This year's decision uses only the years before it.
                if has_edge(seen, seen_base):
                    oos.merge(by_year[year])
                    oos_base.merge(baseline_by_year[year])
                seen.merge(by_year[year])
                seen_base.merge(baseline_by_year[year])
            total.merge(seen)
            total_base.merge(seen_base)
            output.append(
                {
                    "signal": name,
                    "direction": direction,
                    "horizon": horizon,
                    "sample_size": total.count,
                    "win_rate": total.win_rate,
                    "baseline_win_rate": total_base.win_rate,
                    "avg_return": total.average,
                    "baseline_avg_return": total_base.average,
                    "oos_sample_size": oos.count,
                    "oos_win_rate": oos.win_rate,
                    "oos_baseline_win_rate": oos_base.win_rate,
                    "oos_avg_return": oos.average,
                    "oos_baseline_avg_return": oos_base.average,
                    "edge": has_edge(oos, oos_base),
                }
            )
        return output


def calibration(records: list[tuple[float, bool]], buckets: int = 5) -> list[dict]:
    """Compare stated chances with what happened. Used to score forecasts in Milestone 5."""
    grouped = defaultdict(list)
    for chance, happened in records:
        grouped[min(int(chance * buckets), buckets - 1)].append((chance, happened))
    return [
        {
            "stated": sum(item[0] for item in rows) / len(rows),
            "actual": sum(item[1] for item in rows) / len(rows),
            "count": len(rows),
        }
        for _, rows in sorted(grouped.items())
    ]


def eligibility(engine: Engine) -> dict[int, set[int]]:
    """For each company, the years it ranked among the largest, as known at the time."""
    query = "SELECT year, cik FROM historic_float WHERE size_rank <= :limit"
    table: dict[int, set[int]] = defaultdict(set)
    with engine.connect() as conn:
        for year, cik in conn.execute(text(query), {"limit": SIZE_LIMIT}):
            table[cik].add(year)
    return table


def eligible_days(dates: pd.Series, years: set[int]) -> np.ndarray:
    """A mid-year size is reported in filings by about the next March, so use it from April."""
    days = pd.to_datetime(dates)
    known = np.where(days.dt.month >= 4, days.dt.year - 1, days.dt.year - 2)
    return np.isin(known, sorted(years))


def run(engine: Engine, cost_bps: float = COST_BPS) -> int:
    test = Backtest(cost_bps)
    sizes = eligibility(engine)
    if not sizes:
        raise RuntimeError("no past company sizes stored: backtest blocked")
    first, last, stocks = None, None, 0
    with engine.connect() as conn:
        companies = conn.execute(text("SELECT id, cik FROM securities ORDER BY id")).all()
        for security_id, cik in companies:
            rows = conn.execute(
                text(
                    """SELECT DISTINCT ON (market_date) market_date, open, high, low, close,
                         volume, div_cash, split_factor
                       FROM price_bars WHERE security_id = :id
                       ORDER BY market_date, id DESC"""
                ),
                {"id": security_id},
            ).all()
            if len(rows) < 260:
                continue
            frame = adjust(pd.DataFrame([row._mapping for row in rows]))
            test.add_stock(frame, eligible_days(frame["market_date"], sizes.get(cik, set())))
            stocks += 1
            first = min(first or rows[0].market_date, rows[0].market_date)
            last = max(last or rows[-1].market_date, rows[-1].market_date)
    if not stocks:
        raise RuntimeError("no stock has enough price history to test")
    results = test.results()
    with engine.begin() as conn:
        run_id = conn.execute(
            text(
                """INSERT INTO backtest_runs (stocks, first_date, last_date, cost_bps, note)
                   VALUES (:stocks, :first, :last, :cost, :note) RETURNING id"""
            ),
            {
                "stocks": stocks,
                "first": first,
                "last": last,
                "cost": cost_bps,
                "note": SURVIVORSHIP_NOTE,
            },
        ).scalar_one()
        conn.execute(
            text(
                """INSERT INTO backtest_results (run_id, signal, direction, horizon, sample_size,
                     win_rate, baseline_win_rate, avg_return, baseline_avg_return,
                     oos_sample_size, oos_win_rate, oos_baseline_win_rate, oos_avg_return,
                     oos_baseline_avg_return, edge)
                   VALUES (:run_id, :signal, :direction, :horizon, :sample_size, :win_rate,
                     :baseline_win_rate, :avg_return, :baseline_avg_return, :oos_sample_size,
                     :oos_win_rate, :oos_baseline_win_rate, :oos_avg_return,
                     :oos_baseline_avg_return, :edge)"""
            ),
            [{**row, "run_id": run_id} for row in results],
        )
    for row in results:
        print(
            row["signal"],
            row["direction"],
            row["horizon"],
            "cases",
            row["sample_size"],
            "win",
            row["win_rate"],
            "base",
            row["baseline_win_rate"],
            "tested",
            row["oos_sample_size"],
            "edge",
            row["edge"],
        )
    print("stocks", stocks, first, last)
    return run_id


if __name__ == "__main__":
    run(get_engine())
