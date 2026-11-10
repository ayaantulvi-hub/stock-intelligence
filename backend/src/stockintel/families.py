"""Factor families: related factors combined into one score, so the model weighs a few clear
ideas instead of many overlapping, noisy numbers.

Each family is the average of its factors' rankings (0 to 1 across stocks each day), each turned
the right way round. Which way is right, and whether a factor counts at all, is learned from the
training years only: a factor counts only if stocks ranked high on it clearly did differently
from stocks ranked low. A factor with no clear effect gets no say, so it can't add noise.

Factors that are the same for every stock on a day (the yield curve, oil, the dollar and so on)
can't rank stocks against each other, so they aren't in any family. They feed the market check
in regime.py, and they reach the ranking through each stock's measured sensitivity to them
(the "Economy exposure" family): a bank and a heavy borrower react to the same curve differently.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

FAMILIES = {
    "Value": ["value", "sector_value"],
    "Quality": ["profitability", "sector_profit", "investment", "accruals", "fscore", "issuance"],
    "Growth": ["revenue_growth", "earnings_drift"],
    "Trend": [
        "mom_12_1",
        "mom_6_1",
        "sector_momentum",
        "high_52w",
        "above_200",
        "macd_hist",
        "chart_pattern",
        "fib_pullback",
    ],
    "Recent pullback": ["reversal_1m", "reversal_5d", "rsi"],
    "Risk": ["vol_60", "vol_20", "beta", "max_ret"],
    "Size and trading": ["size", "illiquidity", "dollar_volume"],
    "Big money": ["insider", "insider_cluster", "fund_buying"],
    "Economy exposure": [
        "rate_beta",
        "policy_beta",
        "curve_tilt",
        "rate_tilt",
        "oil_tilt",
        "dollar_tilt",
        "cpi_tilt",
    ],
}
MEMBERS = [factor for members in FAMILIES.values() for factor in members]
# Training rows overlap (each looks 20 days ahead), which inflates certainty, so the bar is high.
MIN_T = 3.0
EDGE = 0.3  # Top and bottom 30% are compared.


def directions(x: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    """+1 if a high ranking went with beating other stocks, -1 if the reverse, 0 if unclear."""
    out = {}
    beat = np.asarray(y, dtype=float)
    for factor in MEMBERS:
        if factor not in x:
            out[factor] = 0.0
            continue
        values = x[factor].to_numpy(dtype=float)
        high, low = beat[values >= 1 - EDGE], beat[values <= EDGE]
        if len(high) < 100 or len(low) < 100:
            out[factor] = 0.0
            continue
        gap = high.mean() - low.mean()
        se = np.sqrt(high.var() / len(high) + low.var() / len(low))
        t = gap / se if se > 0 else 0.0
        out[factor] = float(np.sign(gap)) if abs(t) >= MIN_T else 0.0
    return out


def scores(x: pd.DataFrame, signs: dict[str, float], dropped: tuple[str, ...] = ()) -> pd.DataFrame:
    """One 0-to-1 score per family: 1 means every counted factor points to beating others."""
    out = {}
    for family, members in FAMILIES.items():
        if family in dropped:
            continue
        parts = []
        for factor in members:
            sign = signs.get(factor, 0.0)
            if sign == 0.0 or factor not in x:
                continue
            values = x[factor].astype(float)
            parts.append(values if sign > 0 else 1 - values)
        out[family] = pd.concat(parts, axis=1).mean(axis=1) if parts else np.nan
    return pd.DataFrame(out, index=x.index)


class FamilyModel:
    """Ranks stocks on family scores. `kind` is equal (plain average), linear or boosted."""

    def __init__(self, kind: str, dropped: tuple[str, ...] = ()):
        self.kind, self.dropped = kind, dropped
        self.signs: dict[str, float] = {}
        self.fitted = None

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "FamilyModel":
        self.signs = directions(x, y)
        table = scores(x, self.signs, self.dropped)
        self.columns = [c for c in table if table[c].notna().any()]
        if not self.columns:
            # No factor showed a clear effect, so every stock gets an even chance.
            return self
        if self.kind == "linear":
            self.fitted = LogisticRegression(C=0.1, max_iter=500).fit(
                table[self.columns].fillna(0.5), y
            )
        elif self.kind == "boosted":
            self.fitted = HistGradientBoostingClassifier(
                max_depth=2, max_iter=60, learning_rate=0.05, min_samples_leaf=1000
            ).fit(table[self.columns], y)
        return self

    def family_scores(self, x: pd.DataFrame) -> pd.DataFrame:
        table = scores(x, self.signs, self.dropped)
        return table.reindex(columns=self.columns)

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        table = self.family_scores(x)
        if self.kind == "equal" or not self.columns:
            chance = (
                table.fillna(0.5).mean(axis=1).to_numpy() if self.columns else np.full(len(x), 0.5)
            )
        elif self.kind == "linear":
            chance = self.fitted.predict_proba(table.fillna(0.5))[:, 1]
        else:
            chance = self.fitted.predict_proba(table)[:, 1]
        return np.column_stack([1 - chance, chance])


def explain(row: pd.Series, model: FamilyModel) -> list[dict]:
    """Each family's score for one stock, strongest push first, for the reasons shown."""
    table = model.family_scores(row.to_frame().T)
    found = []
    for family in model.columns:
        value = table[family].iloc[0]
        if pd.isna(value):
            continue
        counted = [f for f in FAMILIES[family] if model.signs.get(f, 0.0) != 0.0]
        found.append(
            {
                "family": family,
                "score": round(float(value) * 100),
                "push": "buy" if value >= 0.6 else "sell" if value <= 0.4 else "neutral",
                "factors": counted,
            }
        )
    found.sort(key=lambda item: abs(item["score"] - 50), reverse=True)
    return found
