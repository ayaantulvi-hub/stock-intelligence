"""Print the latest stored quant results and data coverage, for the README and write-ups.

Only aggregate figures are printed: no prices, so the output is safe for a public job log and
within the data providers' terms. Run: python -m stockintel.results_summary
"""

from stockintel import queries
from stockintel.db import get_engine


def main() -> None:
    engine = get_engine()
    print(f"RESULT coverage: {queries.coverage(engine)}")
    for row in queries.quant_results(engine):
        metrics = {k: v for k, v in row["metrics"].items() if k != "series"}
        print(
            f"RESULT quant: {{'study': {row['study']!r}, 'variant': {row['variant']!r}, "
            f"'verdict': {row['verdict']!r}, 'period': {row['period']!r}, 'metrics': {metrics!r}}}"
        )


if __name__ == "__main__":
    main()
