"""Print Time Machine results for a few stocks: python -m stockintel.replay_check CAT MU ..."""

import sys

from stockintel import queries
from stockintel.db import get_engine

if __name__ == "__main__":
    engine = get_engine()
    for ticker in sys.argv[1:]:
        found = queries.replay_hold(engine, ticker)
        result = (found or {}).get("replay")
        if not result:
            print(f"REPLAY|{ticker}|Not verified")
            continue
        record = result["record"]
        print(
            f"REPLAY|{ticker}|entry {result['entry']:.2f}|stop {result['stop'] or 0:.2f}"
            f"|up {result['p_gain']:.0%}|stopped {result['p_stop']:.0%}"
            f"|middle {result['median']:+.1%}|range {result['low']:+.0%} to {result['high']:+.0%}"
            f"|real {record['p_gain']:.0%} up of {record['holds']}"
        )
