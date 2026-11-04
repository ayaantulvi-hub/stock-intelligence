"""Candlestick patterns, tested on past prices, for short-term trades of 1 to 5 days.

Patterns use only the candles up to and including the day they appear. Each is a written
rule, so results can be tested. A trade enters at the next day's open, after costs, and is
compared with what all stocks did over the same days.

This runs on daily candles. It can't time moves within a day.

Run weekly: python -m stockintel.candles
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from stockintel.backtest import MIN_SAMPLE, MIN_Z, eligibility, eligible_days
from stockintel.db import get_engine

HORIZONS = (1, 5)
COST = 0.001
BULL, BEAR, NEUTRAL = "bullish", "bearish", "neutral"


@dataclass(frozen=True)
class Candle:
    id: str
    name: str
    direction: str
    candles: int
    meaning: str


PATTERNS = (
    Candle("hammer", "Hammer", BULL, 1, "Sellers pushed it down, but buyers took it back up."),
    Candle("inverted_hammer", "Inverted hammer", BULL, 1, "Buyers tried to lift it after a fall."),
    Candle("dragonfly_doji", "Dragonfly doji", BULL, 1, "A deep drop was fully bought back."),
    Candle("bull_spinning", "Bullish spinning top", BULL, 1, "The fall is losing strength."),
    Candle("hanging_man", "Hanging man", BEAR, 1, "After a rise, sellers showed up in size."),
    Candle("shooting_star", "Shooting star", BEAR, 1, "A rise was rejected and sold back down."),
    Candle("gravestone_doji", "Gravestone doji", BEAR, 1, "A rise was fully sold back."),
    Candle("bear_spinning", "Bearish spinning top", BEAR, 1, "The rise is losing strength."),
    Candle("bull_kicker", "Bullish kicker", BULL, 2, "A sudden jump reversed a falling day."),
    Candle("bull_engulfing", "Bullish engulfing", BULL, 2, "Buyers wiped out the day before."),
    Candle("bull_harami", "Bullish harami", BULL, 2, "The fall stalled inside the last candle."),
    Candle("piercing", "Piercing line", BULL, 2, "Buyers took back over half of a bad day."),
    Candle("tweezer_bottom", "Tweezer bottom", BULL, 2, "Two days stopped at the same low."),
    Candle("bear_kicker", "Bearish kicker", BEAR, 2, "A sudden drop reversed a rising day."),
    Candle("bear_engulfing", "Bearish engulfing", BEAR, 2, "Sellers wiped out the day before."),
    Candle("bear_harami", "Bearish harami", BEAR, 2, "The rise stalled inside the last candle."),
    Candle("dark_cloud", "Dark cloud cover", BEAR, 2, "Sellers took back over half of a good day."),
    Candle("tweezer_top", "Tweezer top", BEAR, 2, "Two days stopped at the same high."),
    Candle("morning_star", "Morning star", BULL, 3, "A fall paused, then buyers took over."),
    Candle("morning_doji", "Morning doji star", BULL, 3, "A fall froze, then buyers took over."),
    Candle("bull_baby", "Bullish abandoned baby", BULL, 3, "A rare gap down and straight back."),
    Candle("white_soldiers", "Three white soldiers", BULL, 3, "Three strong days up in a row."),
    Candle("bull_strike", "Bullish three line strike", BULL, 4, "One day undid a three-day fall."),
    Candle("evening_star", "Evening star", BEAR, 3, "A rise paused, then sellers took over."),
    Candle("evening_doji", "Evening doji star", BEAR, 3, "A rise froze, then sellers took over."),
    Candle("bear_baby", "Bearish abandoned baby", BEAR, 3, "A rare gap up and straight back."),
    Candle("black_crows", "Three black crows", BEAR, 3, "Three strong days down in a row."),
    Candle("bear_strike", "Bearish three line strike", BEAR, 4, "One day undid a three-day rise."),
    Candle("inside_up", "Three inside up", BULL, 3, "A harami that the next day confirmed."),
    Candle("outside_up", "Three outside up", BULL, 3, "An engulfing that the next day confirmed."),
    Candle("inside_down", "Three inside down", BEAR, 3, "A harami that the next day confirmed."),
    Candle("outside_down", "Three outside down", BEAR, 3, "An engulfing the next day confirmed."),
    Candle("doji", "Doji", NEUTRAL, 1, "Buyers and sellers ended level, so it shows indecision."),
    Candle("marubozu", "Marubozu", NEUTRAL, 1, "One side was in control all day."),
)
BY_ID = {item.id: item for item in PATTERNS}


def detect(frame: pd.DataFrame) -> pd.DataFrame:
    """One true or false column per pattern, one row per day."""
    o, h, l_, c = (frame[name].astype(float) for name in ("open", "high", "low", "close"))
    body = (c - o).abs()
    span = (h - l_).where(h > l_)
    top, bottom = pd.concat([o, c], axis=1).max(axis=1), pd.concat([o, c], axis=1).min(axis=1)
    upper, lower = h - top, bottom - l_
    usual = body.rolling(10).mean().shift(1)
    white, black = c > o, c < o
    long_body = body > usual
    small = body <= 0.3 * span
    doji = body <= 0.1 * span
    # The trend before the pattern, so a shape is read in its setting.
    fell = c.shift(1) < c.shift(6)
    rose = c.shift(1) > c.shift(6)
    fell2, rose2 = c.shift(2) < c.shift(7), c.shift(2) > c.shift(7)
    fell3, rose3 = c.shift(3) < c.shift(8), c.shift(3) > c.shift(8)
    po, pc, ph, pl = o.shift(1), c.shift(1), h.shift(1), l_.shift(1)
    pbody, pwhite, pblack, plong = (
        body.shift(1),
        white.shift(1, fill_value=False),
        black.shift(1, fill_value=False),
        long_body.shift(1, fill_value=False),
    )
    pmid = (po + pc) / 2
    a = {
        "o": o.shift(2),
        "c": c.shift(2),
        "h": h.shift(2),
        "l": l_.shift(2),
        "white": white.shift(2, fill_value=False),
        "black": black.shift(2, fill_value=False),
        "long": long_body.shift(2, fill_value=False),
    }
    amid = (a["o"] + a["c"]) / 2
    b_small = small.shift(1, fill_value=False)
    b_doji = doji.shift(1, fill_value=False)
    b_top = top.shift(1)
    b_bottom = bottom.shift(1)

    hammer_shape = small & (lower >= 2 * body) & (upper <= 0.1 * span) & ~doji
    star_shape = small & (upper >= 2 * body) & (lower <= 0.1 * span) & ~doji
    spinning = small & ~doji & (upper >= body) & (lower >= body)
    engulf_up = pblack & white & (o <= pc) & (c >= po) & (body > pbody)
    engulf_down = pwhite & black & (o >= pc) & (c <= po) & (body > pbody)
    inside = (top <= po.combine(pc, max)) & (bottom >= po.combine(pc, min))
    harami_up = pblack & plong & white & inside & small
    harami_down = pwhite & plong & black & inside & small
    close_lows = (l_ - pl).abs() <= 0.002 * c
    close_highs = (h - ph).abs() <= 0.002 * c

    def rising_opens(side):
        return (
            side
            & side.shift(1, fill_value=False)
            & side.shift(2, fill_value=False)
            & long_body
            & long_body.shift(1, fill_value=False)
            & long_body.shift(2, fill_value=False)
        )

    soldiers = (
        rising_opens(white)
        & (c > pc)
        & (pc > c.shift(2))
        & (o >= po)
        & (o <= pc)
        & (po >= o.shift(2))
        & (po <= c.shift(2))
        & (upper <= 0.2 * span)
    )
    crows = (
        rising_opens(black)
        & (c < pc)
        & (pc < c.shift(2))
        & (o <= po)
        & (o >= pc)
        & (po <= o.shift(2))
        & (po >= c.shift(2))
        & (lower <= 0.2 * span)
    )
    three_down = pblack & a["black"] & black.shift(3, fill_value=False)
    three_down = three_down & (pc < a["c"]) & (a["c"] < c.shift(3))
    three_up = pwhite & a["white"] & white.shift(3, fill_value=False)
    three_up = three_up & (pc > a["c"]) & (a["c"] > c.shift(3))

    found = {
        "hammer": fell & hammer_shape,
        "inverted_hammer": fell & star_shape,
        "dragonfly_doji": fell & doji & (upper <= 0.1 * span) & (lower >= 0.6 * span),
        "bull_spinning": fell & spinning,
        "hanging_man": rose & hammer_shape,
        "shooting_star": rose & star_shape,
        "gravestone_doji": rose & doji & (lower <= 0.1 * span) & (upper >= 0.6 * span),
        "bear_spinning": rose & spinning,
        "bull_kicker": pblack & plong & white & long_body & (o > po),
        "bull_engulfing": fell & engulf_up,
        "bull_harami": fell & harami_up,
        "piercing": fell & pblack & plong & white & (o < pc) & (c > pmid) & (c < po),
        "tweezer_bottom": fell & pblack & white & close_lows,
        "bear_kicker": pwhite & plong & black & long_body & (o < po),
        "bear_engulfing": rose & engulf_down,
        "bear_harami": rose & harami_down,
        "dark_cloud": rose & pwhite & plong & black & (o > pc) & (c < pmid) & (c > po),
        "tweezer_top": rose & pwhite & black & close_highs,
        "morning_star": fell2
        & a["black"]
        & a["long"]
        & b_small
        & ~b_doji
        & (b_top < a["c"])
        & white
        & (c > amid),
        "morning_doji": fell2
        & a["black"]
        & a["long"]
        & b_doji
        & (b_top < a["c"])
        & white
        & (c > amid),
        "bull_baby": fell2 & a["black"] & b_doji & (ph < a["l"]) & white & (l_ > ph),
        "white_soldiers": fell3 & soldiers,
        "bull_strike": three_down & white & (c > o.shift(3)) & (o <= pc),
        "evening_star": rose2
        & a["white"]
        & a["long"]
        & b_small
        & ~b_doji
        & (b_bottom > a["c"])
        & black
        & (c < amid),
        "evening_doji": rose2
        & a["white"]
        & a["long"]
        & b_doji
        & (b_bottom > a["c"])
        & black
        & (c < amid),
        "bear_baby": rose2 & a["white"] & b_doji & (pl > a["h"]) & black & (h < pl),
        "black_crows": rose3 & crows,
        "bear_strike": three_up & black & (c < o.shift(3)) & (o >= pc),
        "inside_up": (fell & harami_up).shift(1, fill_value=False) & white & (c > a["o"]),
        "outside_up": (fell & engulf_up).shift(1, fill_value=False) & white & (c > pc),
        "inside_down": (rose & harami_down).shift(1, fill_value=False) & black & (c < a["o"]),
        "outside_down": (rose & engulf_down).shift(1, fill_value=False) & black & (c < pc),
        "doji": doji.fillna(False),
        "marubozu": (body >= 0.9 * span) & long_body,
    }
    return pd.DataFrame({key: value.fillna(False).astype(bool) for key, value in found.items()})


def collect(frame: pd.DataFrame, allowed: np.ndarray | None) -> tuple[dict, pd.DataFrame]:
    """Each pattern's trades, and every stock-day's return as the comparison."""
    days = pd.to_datetime(frame["market_date"])
    entry = frame["open"].shift(-1).astype(float)
    returns = {
        horizon: frame["close"].shift(-horizon).astype(float) / entry - 1 for horizon in HORIZONS
    }
    usable = pd.Series(True if allowed is None else allowed, index=frame.index)
    table = pd.DataFrame({"date": days.to_numpy()})
    for horizon in HORIZONS:
        table[f"r{horizon}"] = returns[horizon].where(usable).to_numpy()
    signals = detect(frame)
    trades: dict = {}
    for item in PATTERNS:
        if item.direction == NEUTRAL:
            continue
        hits = signals[item.id] & usable
        if hits.any():
            trades[item.id] = table[hits.to_numpy()]
    return trades, table


def summarise(pattern: Candle, horizon: int, trades: pd.DataFrame, usual: pd.Series) -> dict | None:
    rows = trades[["date", f"r{horizon}"]].dropna()
    if rows.empty:
        return None
    sign = 1 if pattern.direction == BULL else -1
    made = sign * rows[f"r{horizon}"] - COST
    extra = sign * (rows[f"r{horizon}"] - rows["date"].map(usual)) - COST
    # Trades on the same days aren't independent, so test one average per week.
    weeks = extra.groupby(pd.to_datetime(rows["date"]).dt.to_period("W")).mean()
    spread = weeks.std()
    t_stat = (
        float(weeks.mean() / (spread / np.sqrt(len(weeks)))) if len(weeks) > 1 and spread else 0.0
    )
    return {
        "pattern": pattern.id,
        "horizon": horizon,
        "signals": len(rows),
        "win_rate": float((made > 0).mean()),
        "avg_return": float(made.mean()),
        "extra_return": float(extra.mean()),
        "t_stat": t_stat,
    }


def study(frames: dict, allowed: dict | None = None) -> list[dict]:
    collected: dict = {}
    baseline = []
    for ticker, frame in frames.items():
        trades, table = collect(frame, None if allowed is None else allowed.get(ticker))
        baseline.append(table)
        for key, rows in trades.items():
            collected.setdefault(key, []).append(rows)
    if not baseline:
        return []
    everything = pd.concat(baseline)
    output = []
    for horizon in HORIZONS:
        usual = everything.groupby("date")[f"r{horizon}"].mean()
        for key, parts in collected.items():
            result = summarise(BY_ID[key], horizon, pd.concat(parts), usual)
            if result:
                output.append(result)
    return output


def proven(test: dict | None) -> bool:
    return bool(
        test
        and test["signals"] >= MIN_SAMPLE
        and test["t_stat"] >= MIN_Z
        and test["extra_return"] > 0
    )


def latest_tests(engine: Engine, horizon: int = 5) -> dict[str, dict]:
    query = """SELECT pattern, signals, win_rate, avg_return, extra_return, t_stat
               FROM candle_tests WHERE horizon = :h
                 AND run_at = (SELECT max(run_at) FROM candle_tests)"""
    with engine.connect() as conn:
        rows = conn.execute(text(query), {"h": horizon}).all()
    return {row.pattern: dict(row._mapping) for row in rows}


def run(engine: Engine) -> list[dict]:
    from stockintel.forecast import load_frames

    sizes = eligibility(engine)
    with engine.connect() as conn:
        ciks = dict(conn.execute(text("SELECT ticker, cik FROM securities")).all())
    frames = load_frames(engine)
    allowed = {
        ticker: eligible_days(frame["market_date"], sizes.get(ciks[ticker], set()))
        for ticker, frame in frames.items()
    }
    results = study(frames, allowed)
    now = datetime.now(UTC)
    with engine.begin() as conn:
        for row in results:
            conn.execute(
                text(
                    """INSERT INTO candle_tests (run_at, pattern, horizon, signals, win_rate,
                         avg_return, extra_return, t_stat)
                       VALUES (:run_at, :pattern, :horizon, :signals, :win_rate, :avg_return,
                         :extra_return, :t_stat)"""
                ),
                {**row, "run_at": now},
            )
    for row in sorted(results, key=lambda item: -item["t_stat"])[:12]:
        print(row)
    print("patterns tested", len(results))
    return results


if __name__ == "__main__":
    run(get_engine())
