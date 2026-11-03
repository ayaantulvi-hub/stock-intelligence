"""Signal engine. A signal is only called Bullish or Bearish once testing supports it."""

from dataclasses import dataclass

from stockintel.charts import Pattern

MIN_SAMPLE = 30


@dataclass(frozen=True)
class TestedRecord:
    sample_size: int
    win_rate: float
    baseline_win_rate: float
    edge: bool


def label(pattern: Pattern, record: TestedRecord | None) -> str:
    if pattern.state == "forming":
        return "Forming"
    if record is None or record.sample_size < MIN_SAMPLE:
        return "Unproven"
    if not record.edge:
        return "Neutral"
    return "Bullish" if pattern.direction == "bullish" else "Bearish"


def build_signals(patterns: list[Pattern], records: dict[str, TestedRecord]) -> list[dict]:
    """Turn patterns into signals. Backtests arrive in Milestone 4, so records are empty now."""
    output = []
    for pattern in patterns:
        record = records.get(f"{pattern.name}:{pattern.direction}")
        output.append(
            {
                "name": pattern.name,
                "label": label(pattern, record),
                "direction": pattern.direction,
                "market_date": pattern.market_date,
                "detail": pattern.detail,
                "cancellation_level": pattern.cancellation_level,
                "sample_size": record.sample_size if record else 0,
                "win_rate": record.win_rate if record else None,
                "baseline_win_rate": record.baseline_win_rate if record else None,
            }
        )
    return output
