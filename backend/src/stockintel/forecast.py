"""Forecast engine and ledger.

    python -m stockintel.forecast evaluate   Walk-forward test. Run weekly.
    python -m stockintel.forecast daily      Score past forecasts, write the next ones.

A forecast's probabilities are only called an edge if walk-forward testing beat the
baseline. Otherwise it is recorded and displayed as "No reliable edge".
"""

import json
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sqlalchemy import Engine, text

from stockintel.backtest import MIN_Z
from stockintel.charts import adjust
from stockintel.db import get_engine
from stockintel.factors import LIVE_IDS, MARKET_WIDE, NAMES, stock_factors
from stockintel.market import latest_expected_session, session_close, sessions_between

FLAT_BAND = 0.001
RANK_HORIZON = 20
FIRST_TEST_YEAR = 2015
MIN_TEST_DAYS = 60
CLASSES = np.array(["down", "flat", "up"])


def outcome(change: float) -> str:
    if change > FLAT_BAND:
        return "up"
    return "down" if change < -FLAT_BAND else "flat"


def model(seed: int = 0) -> HistGradientBoostingClassifier:
    # Small, heavily averaged trees. Gu, Kelly & Xiu (2020) found trees among the best
    # methods, and stock data is too noisy for anything larger.
    return HistGradientBoostingClassifier(
        max_depth=3, max_iter=80, learning_rate=0.05, min_samples_leaf=500, random_state=seed
    )


def build_panel(frames: dict[str, pd.DataFrame], slope: pd.Series | None) -> pd.DataFrame:
    """Combine stocks into one table, with factors ranked 0 to 1 across each day."""
    closes = pd.DataFrame(
        {
            ticker: frame.set_index(pd.to_datetime(frame["market_date"]))["close"]
            for ticker, frame in frames.items()
        }
    ).sort_index()
    market = closes.pct_change(fill_method=None).mean(axis=1)
    parts = []
    for ticker, frame in frames.items():
        dates = pd.to_datetime(frame["market_date"])
        factors = stock_factors(frame, market.reindex(dates))
        factors["ticker"] = ticker
        factors["date"] = dates.to_numpy()
        following = frame["close"].shift(-1) / frame["close"] - 1
        factors["next_change"] = following
        factors["future_20d"] = frame["close"].shift(-RANK_HORIZON) / frame["close"] - 1
        factors["last_close"] = frame["close"]
        factors["recent_low"] = (
            frame["close"].pct_change(fill_method=None).rolling(250).quantile(0.05)
        )
        factors["recent_high"] = (
            frame["close"].pct_change(fill_method=None).rolling(250).quantile(0.95)
        )
        parts.append(factors)
    panel = pd.concat(parts, ignore_index=True)
    stock_columns = [item for item in LIVE_IDS if item not in MARKET_WIDE]
    panel[stock_columns] = panel.groupby("date")[stock_columns].rank(pct=True)
    panel["market_20d"] = panel["date"].map((1 + market).rolling(20).apply(np.prod, raw=True) - 1)
    if slope is None or slope.empty:
        raise RuntimeError("no Treasury yield data: forecasts blocked")
    # Treasury yields are published the next day, so each date uses the day before's.
    dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    known = slope.sort_index().shift(1).reindex(dates, method="ffill")
    panel["yield_slope"] = panel["date"].map(known)
    panel["target_day"] = panel["next_change"].map(lambda v: None if pd.isna(v) else outcome(v))
    median = panel.groupby("date")["future_20d"].transform("median")
    panel["excess_20d"] = panel["future_20d"] - median
    return panel


@dataclass(frozen=True)
class Evaluation:
    model: str
    test_days: int
    first_test: date
    last_test: date
    model_loss: float
    baseline_loss: float
    t_stat: float
    top_minus_bottom: float | None
    edge: bool


def _losses(y: np.ndarray, probabilities: np.ndarray, classes: np.ndarray) -> np.ndarray:
    index = {name: i for i, name in enumerate(classes)}
    picked = probabilities[np.arange(len(y)), [index[item] for item in y]]
    return -np.log(np.clip(picked, 1e-9, 1))


def _verdict(name, dates, model_losses, base_losses, spread) -> Evaluation:
    table = pd.DataFrame({"date": dates, "gain": base_losses - model_losses})
    daily = table.groupby("date")["gain"].mean()
    t_stat = (
        float(daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily)))) if len(daily) > 1 else 0.0
    )
    edge = len(daily) >= MIN_TEST_DAYS and t_stat >= MIN_Z and (spread is None or spread > 0)
    return Evaluation(
        name,
        len(daily),
        pd.Timestamp(daily.index.min()).date(),
        pd.Timestamp(daily.index.max()).date(),
        float(model_losses.mean()),
        float(base_losses.mean()),
        t_stat,
        spread,
        bool(edge),
    )


def walk_forward(panel: pd.DataFrame, first_year: int = FIRST_TEST_YEAR) -> list[Evaluation]:
    """Each test year is predicted by a model trained only on earlier data."""
    data = panel.dropna(subset=["next_change"])
    years = sorted(y for y in data["date"].dt.year.unique() if y >= first_year)
    day_dates, day_model, day_base = [], [], []
    rank_dates, rank_model, rank_base, spreads = [], [], [], []
    for year in years:
        cutoff = pd.Timestamp(year, 1, 1)
        train = data[data["date"] < cutoff - pd.Timedelta(days=2)]
        test = data[data["date"].dt.year == year]
        if len(train) < 5000 or test.empty:
            continue
        fitted = model().fit(train[LIVE_IDS], train["target_day"])
        probabilities = fitted.predict_proba(test[LIVE_IDS])
        base = (
            train["target_day"]
            .value_counts(normalize=True)
            .reindex(fitted.classes_)
            .fillna(0)
            .to_numpy()
        )
        y = test["target_day"].to_numpy()
        day_dates.append(test["date"].to_numpy())
        day_model.append(_losses(y, probabilities, fitted.classes_))
        day_base.append(_losses(y, np.tile(base, (len(y), 1)), fitted.classes_))

        # Leave a gap so no training outcome runs into the test year.
        rank_train = data[data["date"] < cutoff - pd.Timedelta(days=RANK_HORIZON * 2)].dropna(
            subset=["excess_20d"]
        )
        spaced = sessions_between(test["date"].min().date(), test["date"].max().date())[
            ::RANK_HORIZON
        ]
        rank_test = test[test["date"].isin(pd.to_datetime(spaced))].dropna(subset=["excess_20d"])
        if len(rank_train) < 5000 or rank_test.empty:
            continue
        ranker = model().fit(rank_train[LIVE_IDS], rank_train["excess_20d"] > 0)
        chance = ranker.predict_proba(rank_test[LIVE_IDS])[:, 1]
        labels = rank_test["excess_20d"].to_numpy() > 0
        rank_dates.append(rank_test["date"].to_numpy())
        rank_model.append(-np.log(np.clip(np.where(labels, chance, 1 - chance), 1e-9, 1)))
        rank_base.append(np.full(len(labels), np.log(2)))
        scored = rank_test.assign(chance=chance)
        for _, group in scored.groupby("date"):
            top = group[group["chance"] >= group["chance"].quantile(0.9)]["excess_20d"].mean()
            bottom = group[group["chance"] <= group["chance"].quantile(0.1)]["excess_20d"].mean()
            spreads.append(top - bottom)
    output = []
    if day_dates:
        output.append(
            _verdict(
                "next_day",
                np.concatenate(day_dates),
                np.concatenate(day_model),
                np.concatenate(day_base),
                None,
            )
        )
    if rank_dates:
        # Both sides pay 0.10% round trip, so the spread must clear 0.20%.
        spread = float(np.nanmean(spreads)) - 0.002
        output.append(
            _verdict(
                "rank_20d",
                np.concatenate(rank_dates),
                np.concatenate(rank_model),
                np.concatenate(rank_base),
                spread,
            )
        )
    return output


def load_frames(engine: Engine) -> dict[str, pd.DataFrame]:
    frames = {}
    with engine.connect() as conn:
        securities = conn.execute(
            text("SELECT id, ticker FROM securities ORDER BY universe_rank")
        ).all()
        for security in securities:
            rows = conn.execute(
                text(
                    """SELECT DISTINCT ON (market_date) market_date, open, high, low, close,
                         volume, div_cash, split_factor
                       FROM price_bars WHERE security_id = :id
                       ORDER BY market_date, id DESC"""
                ),
                {"id": security.id},
            ).all()
            if len(rows) >= 300:
                frames[security.ticker] = adjust(pd.DataFrame([row._mapping for row in rows]))
    return frames


def load_slope(engine: Engine) -> pd.Series | None:
    query = """SELECT DISTINCT ON (series_id, observation_date) series_id, observation_date, value
               FROM economic_observations WHERE series_id IN ('DGS2', 'DGS10')
               ORDER BY series_id, observation_date, realtime_start DESC"""
    with engine.connect() as conn:
        rows = pd.DataFrame([row._mapping for row in conn.execute(text(query))])
    if rows.empty:
        return None
    wide = rows.pivot(index="observation_date", columns="series_id", values="value").dropna()
    wide.index = pd.to_datetime(wide.index)
    return wide["DGS10"] - wide["DGS2"]


def evaluate(engine: Engine) -> list[Evaluation]:
    frames = load_frames(engine)
    if not frames:
        raise RuntimeError("no stock has enough price history to evaluate")
    results = walk_forward(build_panel(frames, load_slope(engine)))
    with engine.begin() as conn:
        for item in results:
            conn.execute(
                text(
                    """INSERT INTO model_evaluations (model, stocks, test_days, first_test,
                         last_test, model_loss, baseline_loss, t_stat, top_minus_bottom, edge)
                       VALUES (:model, :stocks, :test_days, :first_test, :last_test,
                         :model_loss, :baseline_loss, :t_stat, :top_minus_bottom, :edge)"""
                ),
                {**item.__dict__, "stocks": len(frames)},
            )
            print(item)
    return results


def latest_evaluations(engine: Engine) -> dict[str, dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT ON (model) * FROM model_evaluations ORDER BY model, id DESC")
        ).all()
    return {row.model: dict(row._mapping) for row in rows}


def confidence(edge: bool, probabilities: dict, base: dict) -> str:
    if not edge:
        return "None"
    lead = max(abs(probabilities[key] - base[key]) for key in probabilities)
    return "High" if lead >= 0.05 else "Medium" if lead >= 0.02 else "Low"


def drivers(row: pd.Series) -> list[dict]:
    """Every factor reading, most unusual first. Shows what stands out, not what caused it."""
    readings = [
        (item, float(row[item]))
        for item in LIVE_IDS
        if item not in MARKET_WIDE and pd.notna(row[item])
    ]
    readings.sort(key=lambda pair: abs(pair[1] - 0.5), reverse=True)
    return [
        {"factor": item, "name": NAMES[item], "percentile": round(value * 100)}
        for item, value in readings
    ]


def next_session(day: date) -> date:
    return sessions_between(day + timedelta(days=1), day + timedelta(days=10))[0]


def write_forecasts(engine: Engine, panel: pd.DataFrame, now: datetime) -> int:
    evaluations = latest_evaluations(engine)
    expected = latest_expected_session(now)
    target = next_session(expected)
    latest = panel[panel["date"] == pd.Timestamp(expected)].dropna(subset=["recent_low"])
    if latest.empty:
        raise RuntimeError(f"no prices for {expected}: forecasts blocked as stale")
    train = panel.dropna(subset=["next_change"])
    fitted = model().fit(train[LIVE_IDS], train["target_day"])
    base = train["target_day"].value_counts(normalize=True).to_dict()
    probabilities = pd.DataFrame(
        fitted.predict_proba(latest[LIVE_IDS]), columns=fitted.classes_, index=latest.index
    )
    rank_train = panel.dropna(subset=["excess_20d"])
    ranker = model().fit(rank_train[LIVE_IDS], rank_train["excess_20d"] > 0)
    ranks = pd.Series(ranker.predict_proba(latest[LIVE_IDS])[:, 1], index=latest.index).rank(
        pct=True
    )
    day_edge = bool(evaluations.get("next_day", {}).get("edge", False))
    rank_edge = bool(evaluations.get("rank_20d", {}).get("edge", False))
    written = 0
    with engine.begin() as conn:
        for index, row in latest.iterrows():
            chances = {key: float(probabilities.loc[index, key]) for key in ("up", "flat", "down")}
            written += conn.execute(
                text(
                    """INSERT INTO forecasts (security_id, as_of_session, target_session,
                         target_close, last_close, p_up, p_flat, p_down, range_low, range_high,
                         rank_20d, next_day_edge, rank_edge, confidence, drivers)
                       SELECT id, :as_of, :target, :target_close, :close, :up, :flat, :down,
                         :low, :high, :rank, :day_edge, :rank_edge, :confidence, :drivers
                       FROM securities WHERE ticker = :ticker
                       ON CONFLICT (security_id, target_session) DO NOTHING"""
                ),
                {
                    "ticker": row["ticker"],
                    "as_of": expected,
                    "target": target,
                    "target_close": session_close(target),
                    "close": float(row["last_close"]),
                    **chances,
                    "low": float(row["last_close"] * (1 + row["recent_low"])),
                    "high": float(row["last_close"] * (1 + row["recent_high"])),
                    "rank": float(ranks[index]),
                    "day_edge": day_edge,
                    "rank_edge": rank_edge,
                    "confidence": confidence(day_edge, chances, base),
                    "drivers": json.dumps(drivers(row)),
                },
            ).rowcount
    return written


def score_forecasts(engine: Engine) -> int:
    """Score every forecast whose target day now has a stored close."""
    query = """
        SELECT f.*, (SELECT p.close FROM price_bars p
                     WHERE p.security_id = f.security_id AND p.market_date = f.target_session
                     ORDER BY p.id DESC LIMIT 1) AS actual,
               (SELECT p.split_factor FROM price_bars p
                     WHERE p.security_id = f.security_id AND p.market_date = f.target_session
                     ORDER BY p.id DESC LIMIT 1) AS split,
               (SELECT p.div_cash FROM price_bars p
                     WHERE p.security_id = f.security_id AND p.market_date = f.target_session
                     ORDER BY p.id DESC LIMIT 1) AS dividend,
               (SELECT p.close FROM price_bars p
                     WHERE p.security_id = f.security_id AND p.market_date = f.as_of_session
                     ORDER BY p.id DESC LIMIT 1) AS raw_previous
        FROM forecasts f LEFT JOIN forecast_scores s ON s.forecast_id = f.id
        WHERE s.forecast_id IS NULL"""
    scored = 0
    with engine.begin() as conn:
        for row in conn.execute(text(query)).all():
            if row.actual is None or row.raw_previous is None:
                continue
            change = (row.actual * row.split + row.dividend) / row.raw_previous - 1
            result = outcome(change)
            chances = {"up": row.p_up, "flat": row.p_flat, "down": row.p_down}
            brier = sum((value - (key == result)) ** 2 for key, value in chances.items())
            uniform = sum((1 / 3 - (key == result)) ** 2 for key in chances)
            level = row.last_close * (1 + change)
            conn.execute(
                text(
                    """INSERT INTO forecast_scores (forecast_id, actual_close, outcome, brier,
                         baseline_brier, in_range)
                       VALUES (:id, :actual, :outcome, :brier, :baseline, :in_range)"""
                ),
                {
                    "id": row.id,
                    "actual": row.actual,
                    "outcome": result,
                    "brier": brier,
                    "baseline": uniform,
                    "in_range": bool(row.range_low <= level <= row.range_high),
                },
            )
            scored += 1
    return scored


def daily(engine: Engine, now: datetime) -> None:
    print("scored", score_forecasts(engine))
    frames = load_frames(engine)
    print("written", write_forecasts(engine, build_panel(frames, load_slope(engine)), now))


if __name__ == "__main__":
    if sys.argv[1:] == ["evaluate"]:
        evaluate(get_engine())
    elif sys.argv[1:] == ["daily"]:
        daily(get_engine(), datetime.now(UTC))
    else:
        sys.exit(__doc__)
