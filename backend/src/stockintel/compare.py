"""Test different model types on identical data, and keep the honest winner.

Every model predicts the same dates using only earlier data. The last HOLDOUT_YEARS are kept
out of choosing the winner, then used once to check it, because testing many models makes a
lucky winner likely. This runs weekly, so a better model can replace the current one, but
only by passing the same rules.

Run: python -m stockintel.compare
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import Engine, text

from stockintel.backtest import MIN_Z
from stockintel.db import get_engine
from stockintel.forecast import (
    FIRST_TEST_YEAR,
    MIN_TEST_DAYS,
    RANK_HORIZON,
    load_panel,
    usable,
)
from stockintel.market import sessions_between
from stockintel.profiles import TEAM

HOLDOUT_YEARS = 2
ROUND_TRIP = 0.002
TRAIN_EVERY = 5


def _linear():
    return make_pipeline(
        SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.01, max_iter=300)
    )


def _forest():
    return make_pipeline(
        SimpleImputer(strategy="median"),
        RandomForestClassifier(
            n_estimators=80, max_depth=6, min_samples_leaf=500, n_jobs=-1, random_state=0
        ),
    )


def _boosted():
    return HistGradientBoostingClassifier(
        max_depth=3, max_iter=80, learning_rate=0.05, min_samples_leaf=500, random_state=0
    )


def _network():
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        MLPClassifier(
            hidden_layer_sizes=(32, 16),
            alpha=0.01,
            max_iter=25,
            early_stopping=True,
            random_state=0,
        ),
    )


MODELS = {
    "Linear model": _linear,
    "Random forest": _forest,
    "Gradient boosting": _boosted,
    "Neural network": _network,
}


def fit_ranker(name: str, x: pd.DataFrame, y: pd.Series):
    """Train a named model and return a function giving each stock's chance of beating others."""
    names = list(MODELS) if name == TEAM else [name]
    fitted = [MODELS[item]().fit(x, y) for item in names]
    return lambda rows: np.mean([m.predict_proba(rows)[:, 1] for m in fitted], axis=0)


def _t_stat(values: np.ndarray) -> float:
    if len(values) < 2 or values.std(ddof=1) == 0:
        return 0.0
    return float(values.mean() / (values.std(ddof=1) / np.sqrt(len(values))))


def _date_results(test: pd.DataFrame, chance: np.ndarray) -> pd.DataFrame:
    labels = test["excess_20d"].to_numpy() > 0
    table = test[["date", "excess_20d", "vix"]].assign(
        chance=chance,
        loss=-np.log(np.clip(np.where(labels, chance, 1 - chance), 1e-9, 1)),
    )
    rows = []
    for day, group in table.groupby("date"):
        top = group[group["chance"] >= group["chance"].quantile(0.9)]["excess_20d"].mean()
        low = group[group["chance"] <= group["chance"].quantile(0.1)]["excess_20d"].mean()
        rows.append(
            {
                "date": day,
                "gain": np.log(2) - group["loss"].mean(),
                "loss": group["loss"].mean(),
                "spread": top - low - ROUND_TRIP,
                "vix": group["vix"].mean(),
            }
        )
    return pd.DataFrame(rows)


def score(table: pd.DataFrame, holdout_from: pd.Timestamp) -> dict:
    """Summarise one model. Choosing uses early dates, and the hold-out is reported apart."""
    early = table[table["date"] < holdout_from]
    late = table[table["date"] >= holdout_from]
    years = table.assign(year=table["date"].dt.year).groupby("year")["spread"].mean()
    calm_line = table["vix"].median()
    return {
        "test_days": len(table),
        "loss": float(table["loss"].mean()),
        "baseline_loss": float(np.log(2)),
        "t_stat": _t_stat(early["gain"].to_numpy()),
        "spread": float(early["spread"].mean()) if len(early) else 0.0,
        "holdout_t_stat": _t_stat(late["gain"].to_numpy()) if len(late) > 1 else None,
        "holdout_spread": float(late["spread"].mean()) if len(late) else None,
        "worst_year": int(years.idxmin()) if len(years) else None,
        "worst_year_spread": float(years.min()) if len(years) else None,
        "calm_spread": _mean(table[table["vix"] <= calm_line]["spread"]),
        "stressed_spread": _mean(table[table["vix"] > calm_line]["spread"]),
    }


def _mean(values: pd.Series) -> float | None:
    return None if values.empty or values.isna().all() else float(values.mean())


def choose(scores: dict[str, dict]) -> str:
    """The winner is picked on early years only, so the hold-out stays a fair check."""
    return max(scores, key=lambda name: scores[name]["t_stat"])


def has_edge(result: dict) -> bool:
    """Passed the early test, and stayed positive on the years it never saw."""
    return bool(
        result["test_days"] >= MIN_TEST_DAYS // 2
        and result["t_stat"] >= MIN_Z
        and result["spread"] > 0
        and result["holdout_spread"] is not None
        and result["holdout_spread"] > 0
    )


def compare(panel: pd.DataFrame, first_year: int = FIRST_TEST_YEAR) -> list[dict]:
    data = panel[panel["eligible"]].dropna(subset=["excess_20d"])
    last_year = int(data["date"].dt.year.max())
    holdout_from = pd.Timestamp(last_year - HOLDOUT_YEARS + 1, 1, 1)
    collected: dict[str, list[pd.DataFrame]] = {name: [] for name in [*MODELS, TEAM]}
    for year in range(first_year, last_year + 1):
        cutoff = pd.Timestamp(year, 1, 1) - pd.Timedelta(days=RANK_HORIZON * 2)
        history = data[data["date"] < cutoff]
        this_year = data[data["date"].dt.year == year]
        if len(history) < 5000 or this_year.empty:
            continue
        spaced = sessions_between(this_year["date"].min().date(), this_year["date"].max().date())
        test = this_year[this_year["date"].isin(pd.to_datetime(spaced[::RANK_HORIZON]))]
        days = sorted(history["date"].unique())[::TRAIN_EVERY]
        train = history[history["date"].isin(days)]
        columns = usable(train)
        chances = []
        for name, factory in MODELS.items():
            chance = (
                factory()
                .fit(train[columns], train["excess_20d"] > 0)
                .predict_proba(test[columns])[:, 1]
            )
            chances.append(chance)
            collected[name].append(_date_results(test, chance))
        collected[TEAM].append(_date_results(test, np.mean(chances, axis=0)))
    if not collected[TEAM]:
        return []
    scores = {
        name: score(pd.concat(parts, ignore_index=True), holdout_from)
        for name, parts in collected.items()
    }
    winner = choose(scores)
    return [
        {
            "model": name,
            **result,
            "selected": name == winner,
            "edge": name == winner and has_edge(result),
        }
        for name, result in scores.items()
    ]


def factor_weights(panel: pd.DataFrame) -> list[dict]:
    """How much each factor counted in a random forest. Weights add up to 1."""
    data = panel[panel["eligible"]].dropna(subset=["excess_20d"])
    days = sorted(data["date"].unique())[::TRAIN_EVERY]
    train = data[data["date"].isin(days)]
    if train.empty:
        return []
    columns = usable(train)
    fitted = _forest().fit(train[columns], train["excess_20d"] > 0)
    weights = fitted[-1].feature_importances_
    used = [name for i, name in enumerate(columns) if i < len(weights)]
    return [
        {"factor": name, "weight": float(weight)}
        for name, weight in zip(used, weights, strict=True)
    ]


def run(engine: Engine) -> list[dict]:
    panel = load_panel(engine)
    results = compare(panel)
    weights = factor_weights(panel)
    now = datetime.now(UTC)
    if weights:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO factor_weights (run_at, factor, weight)
                       VALUES (:run_at, :factor, :weight)"""
                ),
                [{**row, "run_at": now} for row in weights],
            )
    if results:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO model_comparisons (run_at, model, test_days, loss,
                         baseline_loss, t_stat, spread, holdout_t_stat, holdout_spread,
                         worst_year, worst_year_spread, calm_spread, stressed_spread,
                         selected, edge)
                       VALUES (:run_at, :model, :test_days, :loss, :baseline_loss, :t_stat,
                         :spread, :holdout_t_stat, :holdout_spread, :worst_year,
                         :worst_year_spread, :calm_spread, :stressed_spread, :selected, :edge)"""
                ),
                [{**row, "run_at": now} for row in results],
            )
    for row in results:
        print(row)
    return results


if __name__ == "__main__":
    run(get_engine())
