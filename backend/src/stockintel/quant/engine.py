"""A vectorised daily backtest: target weights in, net returns out.

Timing rule (no look-ahead): weights decided with data up to day t's close are held from day
t's close to day t+1's close, so they earn day t+1's return. Trading costs are charged on the
change in weights, and short positions pay a yearly borrowing fee.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from stockintel.quant.metrics import DAYS_PER_YEAR, summary

COST_BPS = 10.0  # Per unit of weight traded, each way. An assumption, as in the main backtests.
BORROW_BPS_A_YEAR = 50.0  # Yearly fee on short positions. An assumption for easy-to-borrow stocks.


@dataclass
class Result:
    gross: pd.Series  # Daily return before costs.
    net: pd.Series  # Daily return after costs.
    held: pd.DataFrame  # Weights held during each day.
    turnover: pd.Series  # Sum of absolute weight changes traded at each close.

    def summary(self) -> dict:
        return summary(self.net, self.turnover)


def run(
    weights: pd.DataFrame,
    returns: pd.DataFrame,
    cost_bps: float = COST_BPS,
    borrow_bps: float = BORROW_BPS_A_YEAR,
) -> Result:
    """Backtest target weights decided at each close.

    weights: dates x assets, the position wanted after each day's close (NaN = 0).
    returns: dates x assets, simple close-to-close returns. Missing returns count as 0 for a
    position, which is why callers should only give weights to stocks that trade.
    """
    weights = weights.reindex(index=returns.index, columns=returns.columns).fillna(0.0)
    held = weights.shift(1).fillna(0.0)  # Decided at yesterday's close, earning today.
    gross = (held * returns.fillna(0.0)).sum(axis=1)
    traded = weights.diff().abs().sum(axis=1)
    traded.iloc[0] = weights.iloc[0].abs().sum()
    # The trade at day t's close is paid on day t+1, the first day the new position is held.
    cost = traded.shift(1).fillna(0.0) * cost_bps / 10_000
    borrow = held.clip(upper=0).abs().sum(axis=1) * borrow_bps / 10_000 / DAYS_PER_YEAR
    net = gross - cost - borrow
    return Result(gross=gross, net=net, held=held, turnover=traded)


def look_ahead_check(make_weights, returns: pd.DataFrame, cut: int) -> bool:
    """True if weights up to day `cut` stay the same when every later return is changed.

    Later returns are reversed in order and flipped in sign, so each one is guaranteed to
    differ. make_weights(returns) -> weights. A strategy that peeks at the future fails this.
    """
    original = make_weights(returns)
    changed_returns = returns.copy()
    later = changed_returns.iloc[cut + 1 :].to_numpy()
    changed_returns.iloc[cut + 1 :] = -later[::-1] - np.sign(later[::-1]) * 1e-3
    changed = make_weights(changed_returns)
    return bool(
        np.allclose(
            original.iloc[: cut + 1].fillna(0).to_numpy(),
            changed.iloc[: cut + 1].fillna(0).to_numpy(),
        )
    )
