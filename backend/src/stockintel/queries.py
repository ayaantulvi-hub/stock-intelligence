"""Read stored records for the API. Every value carries its provenance."""

from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import Engine, text

from stockintel import (
    advice,
    backtest,
    candles,
    charts,
    experts,
    explain,
    factors,
    horizons,
    longterm,
    signals,
    stops,
    tools,
)
from stockintel.market import is_stale, latest_expected_session, sessions_between
from stockintel.profiles import PROFILES

FEEDS = {
    "universe": "SEC EDGAR",
    "prices": "Tiingo",
    "filings": "SEC EDGAR",
    "facts": "SEC EDGAR",
    "insiders": "SEC EDGAR",
    "history": "SEC EDGAR",
    "fed": "Federal Reserve",
    "economic": "FRED",
}
PROVENANCE = "d.name AS source, f.source_url, f.retrieved_at, f.data_status"
JOIN = "JOIN fetches f ON f.id = r.fetch_id JOIN data_sources d ON d.id = f.source_id"


def _rows(result) -> list[dict]:
    return [dict(row._mapping) for row in result]


def feeds(engine: Engine) -> list[dict]:
    """The latest run of each feed, and its last clean run."""
    output = []
    with engine.connect() as conn:
        for feed, source in FEEDS.items():
            latest = conn.execute(
                text("SELECT * FROM feed_runs WHERE feed = :feed ORDER BY id DESC LIMIT 1"),
                {"feed": feed},
            ).first()
            last_ok = conn.execute(
                text(
                    """SELECT max(finished_at) FROM feed_runs
                       WHERE feed = :feed AND status = 'ok'"""
                ),
                {"feed": feed},
            ).scalar()
            output.append(
                {
                    "feed": feed,
                    "source": source,
                    "status": latest.status if latest else "never_run",
                    "message": latest.message if latest else None,
                    "last_run": latest.started_at if latest else None,
                    "records_added": latest.records_added if latest else None,
                    "last_ok": last_ok,
                }
            )
    return output


def search(engine: Engine, query: str) -> list[dict]:
    with engine.connect() as conn:
        return _rows(
            conn.execute(
                text(
                    """SELECT ticker, name, exchange FROM securities
                       WHERE ticker ILIKE :prefix OR name ILIKE :anywhere
                       ORDER BY universe_rank LIMIT 20"""
                ),
                {"prefix": f"{query}%", "anywhere": f"%{query}%"},
            )
        )


def stock(engine: Engine, ticker: str) -> dict | None:
    with engine.connect() as conn:
        security = conn.execute(
            text("SELECT * FROM securities WHERE ticker = :ticker"), {"ticker": ticker.upper()}
        ).first()
        if security is None:
            return None
        bars = _rows(
            conn.execute(
                text(
                    f"""SELECT * FROM (
                          SELECT DISTINCT ON (r.market_date) r.market_date, r.market_timestamp,
                            r.open, r.high, r.low, r.close, r.volume, r.div_cash,
                            r.split_factor, {PROVENANCE}
                          FROM price_bars r {JOIN} WHERE r.security_id = :id
                          ORDER BY r.market_date DESC, r.id DESC LIMIT 30) t
                        ORDER BY market_date DESC"""
                ),
                {"id": security.id},
            )
        )
        filings = _rows(
            conn.execute(
                text(
                    f"""SELECT r.form, r.filing_date, r.report_date, r.accepted_at,
                          r.document_url, {PROVENANCE}
                        FROM filings r {JOIN} WHERE r.security_id = :id
                        ORDER BY r.filing_date DESC, r.id DESC LIMIT 20"""
                ),
                {"id": security.id},
            )
        )
    now = datetime.now(UTC)
    latest = bars[0]["market_date"] if bars else None
    return {
        "ticker": security.ticker,
        "name": security.name,
        "exchange": security.exchange,
        "latest_expected_session": latest_expected_session(now),
        "stale": is_stale(latest, now),
        "bars": bars,
        "filings": filings,
    }


def economic(engine: Engine) -> list[dict]:
    """The newest observation of each series, as currently published."""
    with engine.connect() as conn:
        return _rows(
            conn.execute(
                text(
                    f"""SELECT DISTINCT ON (r.series_id) r.series_id, r.observation_date,
                          r.realtime_start, r.value, {PROVENANCE}
                        FROM economic_observations r {JOIN}
                        ORDER BY r.series_id, r.observation_date DESC, r.realtime_start DESC"""
                )
            )
        )


def issues(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        return _rows(
            conn.execute(
                text(
                    """SELECT feed, kind, ticker, market_date, detail, detected_at
                       FROM validation_issues ORDER BY id DESC LIMIT 50"""
                )
            )
        )


def chart(engine: Engine, ticker: str, timeframe: str) -> dict | None:
    """Candles, indicators, levels and signals, computed only from stored bars."""
    with engine.connect() as conn:
        security = conn.execute(
            text("SELECT id, ticker, name FROM securities WHERE ticker = :ticker"),
            {"ticker": ticker.upper()},
        ).first()
        if security is None:
            return None
        rows = conn.execute(
            text(
                """SELECT DISTINCT ON (market_date) market_date, open, high, low, close,
                     volume, div_cash, split_factor
                   FROM price_bars WHERE security_id = :id
                   ORDER BY market_date, id DESC"""
            ),
            {"id": security.id},
        ).all()
    now = datetime.now(UTC)
    latest = rows[-1].market_date if rows else None
    stale = is_stale(latest, now)
    result = {
        "ticker": security.ticker,
        "name": security.name,
        "timeframe": timeframe,
        "stale": stale,
        "latest_bar": latest,
        "latest_expected_session": latest_expected_session(now),
        "candles": [],
        "levels": [],
        "summary": None,
        "signals": [],
        "signals_blocked": stale,
    }
    if not rows:
        return result
    frame = charts.resample(charts.adjust(pd.DataFrame([row._mapping for row in rows])), timeframe)
    close = frame["close"]
    lines = charts.macd(close)
    computed = frame.assign(
        sma20=charts.sma(close, 20),
        sma50=charts.sma(close, 50),
        sma200=charts.sma(close, 200),
        rsi=charts.rsi(close),
        macd=lines["macd"],
        macd_signal=lines["signal"],
        macd_histogram=lines["histogram"],
    )
    # Blank warm-up values stay blank. They are never filled.
    records = computed.astype(object).where(computed.notna(), None).to_dict("records")
    result["candles"] = records
    found = charts.levels(frame)
    result["levels"] = [level.__dict__ for level in found]
    result["summary"] = charts.summary(frame, found)
    if not stale:
        result["signals"] = signals.build_signals(
            charts.detect_patterns(frame), records_for(engine, timeframe)
        )
    return result


def latest_backtest(engine: Engine) -> dict | None:
    with engine.connect() as conn:
        run = conn.execute(text("SELECT * FROM backtest_runs ORDER BY id DESC LIMIT 1")).first()
        if run is None:
            return None
        results = _rows(
            conn.execute(
                text(
                    """SELECT * FROM backtest_results WHERE run_id = :id
                       ORDER BY edge DESC, horizon, signal, direction"""
                ),
                {"id": run.id},
            )
        )
    return {**dict(run._mapping), "results": results}


def records_for(engine: Engine, timeframe: str) -> dict[str, signals.TestedRecord]:
    """Tested records for signals. Only daily signals have been tested."""
    latest = latest_backtest(engine)
    if latest is None or timeframe != "daily":
        return {}
    return {
        f"{row['signal']}:{row['direction']}": signals.TestedRecord(
            row["sample_size"],
            row["oos_win_rate"] if row["oos_win_rate"] is not None else row["win_rate"],
            row["oos_baseline_win_rate"]
            if row["oos_baseline_win_rate"] is not None
            else row["baseline_win_rate"],
            row["edge"],
        )
        for row in latest["results"]
        if row["horizon"] == backtest.PRIMARY_HORIZON
    }


def stock_forecast(engine: Engine, ticker: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """SELECT f.* FROM forecasts f JOIN securities s ON s.id = f.security_id
                   WHERE s.ticker = :ticker ORDER BY f.target_session DESC LIMIT 1"""
            ),
            {"ticker": ticker.upper()},
        ).first()
    return {**dict(row._mapping), "action": action(row.rank_edge, row.rank_20d)} if row else None


def action(rank_edge: bool, rank: float | None) -> str:
    """The call shown to the user. Named only when the ranking has passed testing."""
    if not rank_edge or rank is None:
        return "No reliable edge"
    if rank >= 0.9:
        return "Buy candidate"
    return "Sell candidate" if rank <= 0.1 else "No action"


def ideas(engine: Engine, count: int = 10) -> dict:
    """The tested list if the ranking passed, and always the model's strongest leans."""
    empty = {"target_session": None, "edge": False, "buy": [], "sell": [], "top": [], "bottom": []}
    with engine.connect() as conn:
        target = conn.execute(text("SELECT max(target_session) FROM forecasts")).scalar()
        if target is None:
            return empty
        rows = _rows(
            conn.execute(
                text(
                    """SELECT s.ticker, s.name, f.rank_20d, f.rank_edge, f.last_close, f.drivers
                       FROM forecasts f JOIN securities s ON s.id = f.security_id
                       WHERE f.target_session = :target AND f.rank_20d IS NOT NULL
                       ORDER BY f.rank_20d DESC"""
                ),
                {"target": target},
            )
        )
    edge = bool(rows and rows[0]["rank_edge"])
    tests = latest_factor_tests(engine)
    blocks = experts.stored_blocks(engine)
    buyable = [row for row in rows if row["ticker"] not in blocks]

    def card(row: dict, lean: str) -> dict:
        reasons = [
            item["name"]
            for item in advice.factor_leans(row["drivers"], tests)["factors"]
            if item["lean"] == lean
        ][:3]
        return {
            "ticker": row["ticker"],
            "name": row["name"],
            "rank": row["rank_20d"],
            "price": row["last_close"],
            "reasons": reasons,
        }

    plain = [{"ticker": r["ticker"], "name": r["name"], "rank_20d": r["rank_20d"]} for r in rows]
    return {
        "target_session": target,
        "edge": edge,
        "buy": [r for r in plain if r["rank_20d"] >= 0.9 and r["ticker"] not in blocks]
        if edge
        else [],
        "sell": [row for row in plain if row["rank_20d"] <= 0.1] if edge else [],
        "top": [card(row, "Buy") for row in buyable[:count]],
        "bottom": [card(row, "Sell") for row in rows[-count:][::-1]],
    }


HOLD_SESSIONS = 20
ORDER_COUNT = 10


def orders(engine: Engine) -> dict:
    """Today's list as orders: stop price and sell-by date. The page works out the shares."""
    found = ideas(engine, ORDER_COUNT)
    target = found["target_session"]
    rows = []
    for card in found["top"]:
        levels = (suggested_levels(engine, card["ticker"]) or {}).get("levels")
        rows.append(
            {
                "ticker": card["ticker"],
                "name": card["name"],
                "price": card["price"],
                "stop": levels["stop"] if levels else None,
            }
        )
    sell_by = None
    if target is not None:
        days = sessions_between(target, target + timedelta(days=HOLD_SESSIONS * 2))
        sell_by = days[HOLD_SESSIONS] if len(days) > HOLD_SESSIONS else None
    return {"session": target, "sell_by": sell_by, "proven": found["edge"], "orders": rows}


def track_record(engine: Engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """SELECT count(*) AS scored, avg(brier) AS brier,
                     avg(baseline_brier) AS baseline_brier,
                     avg(in_range::int) AS range_hit_rate FROM forecast_scores"""
            )
        ).first()
        written = conn.execute(text("SELECT count(*) FROM forecasts")).scalar()
        evaluations = _rows(
            conn.execute(
                text("SELECT DISTINCT ON (model) * FROM model_evaluations ORDER BY model, id DESC")
            )
        )
    return {**dict(row._mapping), "written": written, "evaluations": evaluations}


def stock_story(engine: Engine, ticker: str) -> list[dict] | None:
    data = chart(engine, ticker, "daily")
    if data is None:
        return None
    return explain.story(
        data["summary"],
        data["signals"],
        data["signals_blocked"],
        stock_forecast(engine, ticker),
        latest_evaluations(engine),
        (valuation(engine, ticker, {}) or {}).get("history", []),
    )


def latest_evaluations(engine: Engine) -> dict[str, dict]:
    query = "SELECT DISTINCT ON (model) * FROM model_evaluations ORDER BY model, id DESC"
    with engine.connect() as conn:
        return {row.model: dict(row._mapping) for row in conn.execute(text(query))}


def load_facts(engine: Engine, security_id: int) -> pd.DataFrame:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT tag, unit, period_start, period_end, value, accession_number,
                     fiscal_period, form, filed, document_url
                   FROM company_facts WHERE security_id = :id"""
            ),
            {"id": security_id},
        ).all()
    return pd.DataFrame([row._mapping for row in rows])


def valuation(engine: Engine, ticker: str, changes: dict) -> dict | None:
    with engine.connect() as conn:
        security = conn.execute(
            text("SELECT id, ticker FROM securities WHERE ticker = :t"), {"t": ticker.upper()}
        ).first()
        if security is None:
            return None
        price = conn.execute(
            text(
                """SELECT close, market_date FROM price_bars WHERE security_id = :id
                   ORDER BY market_date DESC, id DESC LIMIT 1"""
            ),
            {"id": security.id},
        ).first()
        trades = _rows(
            conn.execute(
                text(
                    """SELECT owner, title, transaction_date, filed, code, shares, price,
                         planned_sale, document_url FROM insider_transactions
                       WHERE security_id = :id AND code IN ('P', 'S')
                       ORDER BY transaction_date DESC, id DESC LIMIT 20"""
                ),
                {"id": security.id},
            )
        )
    report = longterm.report(
        load_facts(engine, security.id), price.close if price else None, changes
    )
    return {
        **report,
        "ticker": security.ticker,
        "insider_trades": trades,
        "warnings": tools.warnings(report),
        "data_problems": audit_problems(engine, security.ticker),
        "next_earnings": tools.next_earnings(engine, security.ticker, datetime.now(UTC).date()),
    }


def latest_factor_tests(engine: Engine) -> dict[str, dict]:
    query = "SELECT DISTINCT ON (factor) * FROM factor_tests ORDER BY factor, id DESC"
    with engine.connect() as conn:
        return {row.factor: dict(row._mapping) for row in conn.execute(text(query))}


def stock_leans(engine: Engine, ticker: str) -> dict | None:
    forecast = stock_forecast(engine, ticker)
    if forecast is None:
        return None
    return {
        **advice.factor_leans(forecast["drivers"], latest_factor_tests(engine)),
        "overall": advice.overall(forecast["action"], forecast["rank_20d"]),
    }


def get_position(engine: Engine, ticker: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """SELECT p.shares, p.buy_price, p.target_price, p.stop_price, p.updated_at,
                     s.id AS security_id
                   FROM positions p JOIN securities s ON s.id = p.security_id
                   WHERE s.ticker = :t"""
            ),
            {"t": ticker.upper()},
        ).first()
        if row is None:
            return None
        price = conn.execute(
            text(
                """SELECT close FROM price_bars WHERE security_id = :id
                   ORDER BY market_date DESC, id DESC LIMIT 1"""
            ),
            {"id": row.security_id},
        ).scalar()
    position = {
        key: getattr(row, key) for key in ("shares", "buy_price", "target_price", "stop_price")
    }
    if price is None:
        return {**position, "price": None}
    forecast = stock_forecast(engine, ticker)
    action_name = forecast["action"] if forecast else "No reliable edge"
    report = valuation(engine, ticker, {}) or {}
    return advice.position_view(position, price, action_name, report.get("cases", []))


def save_position(engine: Engine, ticker: str, values: dict) -> bool:
    with engine.begin() as conn:
        return bool(
            conn.execute(
                text(
                    """INSERT INTO positions (security_id, shares, buy_price, target_price,
                         stop_price)
                       SELECT id, :shares, :buy_price, :target_price, :stop_price
                       FROM securities WHERE ticker = :t
                       ON CONFLICT (security_id) DO UPDATE SET shares = EXCLUDED.shares,
                         buy_price = EXCLUDED.buy_price, target_price = EXCLUDED.target_price,
                         stop_price = EXCLUDED.stop_price, updated_at = now()"""
                ),
                {**values, "t": ticker.upper()},
            ).rowcount
        )


def delete_position(engine: Engine, ticker: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """DELETE FROM positions WHERE security_id =
                   (SELECT id FROM securities WHERE ticker = :t)"""
            ),
            {"t": ticker.upper()},
        )


def stock_checklist(engine: Engine, ticker: str) -> list[dict] | None:
    data = chart(engine, ticker, "daily")
    if data is None:
        return None
    report = valuation(engine, ticker, {}) or {}
    forecast = stock_forecast(engine, ticker)
    position = get_position(engine, ticker)
    with engine.connect() as conn:
        security_id = conn.execute(
            text("SELECT id FROM securities WHERE ticker = :t"), {"t": ticker.upper()}
        ).scalar()
        net = conn.execute(
            text(
                """SELECT sum(CASE WHEN code = 'P' THEN shares * price ELSE -shares * price END)
                   FROM insider_transactions
                   WHERE security_id = :id AND price IS NOT NULL
                     AND filed >= current_date - 90
                     AND (code = 'P' OR (code = 'S' AND NOT planned_sale))"""
            ),
            {"id": security_id},
        ).scalar()
        buyers = conn.execute(
            text(
                """SELECT count(DISTINCT owner) FROM insider_transactions
                   WHERE security_id = :id AND code = 'P' AND filed >= current_date - 90"""
            ),
            {"id": security_id},
        ).scalar()
        filed = conn.execute(
            text(
                """SELECT max(filing_date) FROM filings
                   WHERE security_id = :id AND form IN ('10-Q', '10-K', '20-F')"""
            ),
            {"id": security_id},
        ).scalar()
        holdings = conn.execute(
            text(
                """SELECT p.security_id, p.shares * (SELECT b.close FROM price_bars b
                     WHERE b.security_id = p.security_id
                     ORDER BY b.market_date DESC, b.id DESC LIMIT 1) AS worth
                   FROM positions p"""
            )
        ).all()
    total = sum(row.worth or 0 for row in holdings)
    mine = next((row.worth for row in holdings if row.security_id == security_id), None)
    summary = data["summary"] or {}
    today = datetime.now(UTC).date()
    events = tools.company_events(engine, ticker, today)
    return advice.checklist(
        stale=data["stale"],
        latest_bar=data["latest_bar"],
        expected=data["latest_expected_session"],
        action=forecast["action"] if forecast else None,
        above_200=summary.get("above_200"),
        report=report,
        insider_net=net,
        insider_buyers=buyers,
        serious_events=tools.serious_events(events, today),
        last_earnings_days=(datetime.now(UTC).date() - filed).days if filed else None,
        position=position,
        portfolio_share=mine / total if mine and total and len(holdings) > 1 else None,
    )


def model_comparison(engine: Engine) -> dict | None:
    query = """SELECT * FROM model_comparisons
               WHERE run_at = (SELECT max(run_at) FROM model_comparisons)
               ORDER BY selected DESC, t_stat DESC"""
    with engine.connect() as conn:
        rows = _rows(conn.execute(text(query)))
    if not rows:
        return None
    weight_query = """SELECT factor, weight FROM factor_weights
                      WHERE run_at = (SELECT max(run_at) FROM factor_weights)
                      ORDER BY weight DESC LIMIT 12"""
    with engine.connect() as conn:
        weights = _rows(conn.execute(text(weight_query)))
    return {
        "run_at": rows[0]["run_at"],
        "models": [{**row, **PROFILES[row["model"]]} for row in rows],
        "weights": [
            {**row, "name": factors.NAMES.get(row["factor"], row["factor"])} for row in weights
        ],
    }


def suggested_levels(engine: Engine, ticker: str) -> dict | None:
    """Suggested stop and target for the latest price, with the tested distances."""
    with engine.connect() as conn:
        security = conn.execute(
            text("SELECT id FROM securities WHERE ticker = :t"), {"t": ticker.upper()}
        ).first()
        if security is None:
            return None
        rows = conn.execute(
            text(
                """SELECT DISTINCT ON (market_date) market_date, open, high, low, close,
                     volume, div_cash, split_factor
                   FROM price_bars WHERE security_id = :id
                   ORDER BY market_date, id DESC"""
            ),
            {"id": security.id},
        ).all()
        tested = _rows(
            conn.execute(
                text(
                    """SELECT stop_multiple, trades, avg_return, win_rate, worst_return,
                         stopped_share FROM stop_studies
                       WHERE run_at = (SELECT max(run_at) FROM stop_studies)
                       ORDER BY stop_multiple NULLS FIRST"""
                )
            )
        )
    if not rows:
        return {"levels": None, "tested": tested}
    frame = charts.adjust(pd.DataFrame([row._mapping for row in rows]))
    return {"levels": stops.suggest(frame), "tested": tested}


def screener(engine: Engine) -> list[dict]:
    """Every stock in the latest forecast, with its action and the model's lean."""
    query = """SELECT s.ticker, s.name, f.last_close, f.rank_20d AS rank, f.p_up, f.rank_edge
               FROM forecasts f JOIN securities s ON s.id = f.security_id
               WHERE f.target_session = (SELECT max(target_session) FROM forecasts)"""
    with engine.connect() as conn:
        rows = _rows(conn.execute(text(query)))
    blocks = experts.stored_blocks(engine)
    output = []
    for row in rows:
        name = action(row.pop("rank_edge"), row["rank"])
        lean = advice.overall(name, row["rank"])["lean"]
        if lean == "Buy" and row["ticker"] in blocks:
            lean = "Hold off"
        output.append({**row, "action": name, "lean": lean})
    return output


def stock_decision(engine: Engine, ticker: str) -> dict | None:
    data = chart(engine, ticker, "daily")
    if data is None:
        return None
    forecast = stock_forecast(engine, ticker)
    position = get_position(engine, ticker)
    review = expert_review(engine, ticker, datetime.now(UTC).date())
    answer = advice.apply_experts(
        advice.decision(
            forecast["action"] if forecast else None,
            forecast["rank_20d"] if forecast else None,
            data["stale"],
            position,
        ),
        review,
    )
    levels = suggested_levels(engine, ticker) or {}
    return advice.brief(
        answer,
        stock_story(engine, ticker) or [],
        stock_checklist(engine, ticker) or [],
        levels.get("levels"),
        position,
        review,
    )


def stock_horizons(engine: Engine, ticker: str) -> dict | None:
    """The trading answer and the investing answer for one stock."""
    data = chart(engine, ticker, "daily")
    if data is None:
        return None
    today = datetime.now(UTC).date()
    review = expert_review(engine, ticker, today)
    frame = _adjusted_bars(engine, ticker)
    earnings = tools.next_earnings(engine, ticker, today)
    return {
        "trade": horizons.trade(
            frame,
            candles.latest_tests(engine),
            data["stale"],
            (earnings - today).days if earnings else None,
        ),
        "invest": horizons.invest(review),
    }


def _adjusted_bars(engine: Engine, ticker: str) -> pd.DataFrame:
    query = """SELECT DISTINCT ON (market_date) market_date, open, high, low, close, volume,
                 div_cash, split_factor
               FROM price_bars p JOIN securities s ON s.id = p.security_id
               WHERE s.ticker = :t ORDER BY market_date, p.id DESC"""
    with engine.connect() as conn:
        rows = conn.execute(text(query), {"t": ticker.upper()}).all()
    if not rows:
        return pd.DataFrame(columns=["market_date", "open", "high", "low", "close", "volume"])
    return charts.adjust(pd.DataFrame([row._mapping for row in rows]))


def expert_review(engine: Engine, ticker: str, today) -> dict | None:
    """The expert lenses for one stock, for the person who may own it."""
    with engine.connect() as conn:
        security = conn.execute(
            text("SELECT id, sic FROM securities WHERE ticker = :t"), {"t": ticker.upper()}
        ).first()
        if security is None:
            return None
        rows = conn.execute(
            text(
                """SELECT DISTINCT ON (market_date) market_date, open, high, low, close,
                     volume, div_cash, split_factor
                   FROM price_bars WHERE security_id = :id
                   ORDER BY market_date, id DESC"""
            ),
            {"id": security.id},
        ).all()
    if not rows:
        return None
    frame = charts.adjust(pd.DataFrame([row._mapping for row in rows]))
    earnings = tools.next_earnings(engine, ticker, today)
    return experts.review(
        load_facts(engine, security.id),
        valuation(engine, ticker, {}) or {},
        frame,
        sic=security.sic,
        serious=tools.serious_events(tools.company_events(engine, ticker, today), today),
        position=get_position(engine, ticker),
        earnings_in=(earnings - today).days if earnings else None,
        outside=experts.load_outside(engine),
    )


def audit_problems(engine: Engine, ticker: str) -> list[str]:
    query = """SELECT detail FROM validation_issues
               WHERE feed = 'audit' AND ticker = :t ORDER BY id"""
    with engine.connect() as conn:
        return list(conn.execute(text(query), {"t": ticker}).scalars())


def audit_summary(engine: Engine) -> dict:
    query = """SELECT count(DISTINCT ticker) AS flagged, count(*) AS problems
               FROM validation_issues WHERE feed = 'audit'"""
    with engine.connect() as conn:
        row = conn.execute(text(query)).first()
        rows = _rows(
            conn.execute(
                text(
                    """SELECT ticker, detail FROM validation_issues WHERE feed = 'audit'
                       ORDER BY ticker LIMIT 200"""
                )
            )
        )
        total = conn.execute(text("SELECT count(*) FROM securities")).scalar()
    return {"checked": total, "flagged": row.flagged, "problems": rows}
