"""The market check: do economy-wide readings say anything about the whole market's next month?

The yield curve, borrowing costs, oil, the dollar, fear (VIX), inflation expectations, jobless
claims, the Fed's direction and government policy all move every stock at once. They can't
rank one stock against another, so they are judged here, on one question: will the average
stock rise over the next 20 trading days?

Tested like everything else: each year is predicted only from earlier years, the last two
years are held back for one final check, and with only one reading per month the bar is high.
Unless it passes, the check is shown for information and never changes a decision.

Run weekly: python -m stockintel.regime
"""

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import Engine, text

from stockintel.backtest import MIN_Z
from stockintel.factors import MARKET_WIDE, NAMES
from stockintel.forecast import FIRST_TEST_YEAR, RANK_HORIZON

HOLDOUT_YEARS = 2
FAVOURABLE, CAUTIOUS = 0.6, 0.4


def monthly(panel: pd.DataFrame) -> pd.DataFrame:
    """One row per date: the readings, and whether the average stock rose over 20 days."""
    columns = [c for c in MARKET_WIDE if c in panel]
    data = panel[panel["eligible"]]
    table = data.groupby("date")[columns].first()
    table["market_future"] = data.groupby("date")["future_20d"].mean()
    return table.sort_index()


def _model():
    return make_pipeline(
        SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.1, max_iter=500)
    )


def _t(values: np.ndarray) -> float:
    if len(values) < 2 or values.std(ddof=1) == 0:
        return 0.0
    return float(values.mean() / (values.std(ddof=1) / np.sqrt(len(values))))


def test(table: pd.DataFrame, first_year: int = FIRST_TEST_YEAR) -> dict:
    columns = [c for c in table if c != "market_future" and table[c].notna().any()]
    known = table.dropna(subset=["market_future"])
    last_year = int(known.index.year.max()) if len(known) else first_year
    holdout_from = pd.Timestamp(last_year - HOLDOUT_YEARS + 1, 1, 1)
    gains, dates = [], []
    for year in range(first_year, last_year + 1):
        cutoff = pd.Timestamp(year, 1, 1) - pd.Timedelta(days=RANK_HORIZON * 2)
        train = known[known.index < cutoff].iloc[::RANK_HORIZON]
        test_rows = known[known.index.year == year].iloc[::RANK_HORIZON]
        if len(train) < 40 or test_rows.empty:
            continue
        y = train["market_future"] > 0
        base = float(y.mean())
        chance = _model().fit(train[columns], y).predict_proba(test_rows[columns])[:, 1]
        up = (test_rows["market_future"] > 0).to_numpy()
        loss = -np.log(np.clip(np.where(up, chance, 1 - chance), 1e-9, 1))
        base_loss = -np.log(np.clip(np.where(up, base, 1 - base), 1e-9, 1))
        gains.append(base_loss - loss)
        dates.append(test_rows.index.to_numpy())
    if not gains:
        return {"edge": False, "t_stat": None, "holdout_gain": None, "test_dates": 0}
    gain = pd.Series(np.concatenate(gains), index=pd.DatetimeIndex(np.concatenate(dates)))
    early, late = gain[gain.index < holdout_from], gain[gain.index >= holdout_from]
    t = _t(early.to_numpy())
    holdout = float(late.mean()) if len(late) else None
    return {
        "edge": bool(t >= MIN_Z and holdout is not None and holdout > 0),
        "t_stat": t,
        "holdout_gain": holdout,
        "test_dates": len(gain),
    }


def latest(table: pd.DataFrame) -> dict:
    """Today's readings, and the model's chance the average stock rises, from all past data."""
    columns = [c for c in table if c != "market_future" and table[c].notna().any()]
    known = table.dropna(subset=["market_future"]).iloc[::RANK_HORIZON]
    today = table.iloc[[-1]]
    chance = None
    if len(known) >= 40:
        chance = float(
            _model()
            .fit(known[columns], known["market_future"] > 0)
            .predict_proba(today[columns])[0, 1]
        )
    readings = []
    for column in columns:
        value = today[column].iloc[0]
        history = table[column].dropna()
        if pd.isna(value) or history.empty:
            continue
        readings.append(
            {
                "factor": column,
                "name": NAMES.get(column, column),
                "value": float(value),
                "percentile": round(float((history <= value).mean()) * 100),
            }
        )
    return {"date": today.index[0].date().isoformat(), "chance": chance, "readings": readings}


def state(chance: float | None) -> str:
    if chance is None:
        return "Not verified"
    return "Favourable" if chance >= FAVOURABLE else "Cautious" if chance <= CAUTIOUS else "Neutral"


def run(engine: Engine, panel: pd.DataFrame | None = None) -> dict:
    from stockintel.forecast import load_panel

    panel = load_panel(engine) if panel is None else panel
    table = monthly(panel)
    result = {**test(table), **latest(table)}
    result["state"] = state(result["chance"])
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO market_checks (run_at, edge, t_stat, holdout_gain, test_dates,
                     chance, state, readings)
                   VALUES (:run_at, :edge, :t, :holdout, :dates, :chance, :state,
                     CAST(:readings AS jsonb))"""
            ),
            {
                "run_at": datetime.now(UTC),
                "edge": result["edge"],
                "t": result["t_stat"],
                "holdout": result["holdout_gain"],
                "dates": result["test_dates"],
                "chance": result["chance"],
                "state": result["state"],
                "readings": json.dumps(result["readings"]),
            },
        )
    return result


def current(engine: Engine) -> dict | None:
    query = """SELECT run_at, edge, t_stat, holdout_gain, test_dates, chance, state, readings
               FROM market_checks ORDER BY id DESC LIMIT 1"""
    with engine.connect() as conn:
        row = conn.execute(text(query)).first()
    return None if row is None else dict(row._mapping)


if __name__ == "__main__":
    from stockintel.db import get_engine

    output = run(get_engine())
    print({k: v for k, v in output.items() if k != "readings"})
