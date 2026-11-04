"""Long-term engine: business numbers, value estimates and Bull, Base and Bear cases.

Every figure comes from stored SEC facts and links to its filing. A missing figure stays
None, shown as "Not verified". The DCF cases are arithmetic on stated assumptions, which
the user can change. They are not forecasts of what will happen.
"""

import pandas as pd

CAPEX_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
)
REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RevenuesNetOfInterestExpense",
    "SalesRevenueNet",
    "RegulatedAndUnregulatedOperatingRevenue",
    "Revenue",
    "RevenueAndOperatingIncome",
    "RevenueFromContractsWithCustomers",
    "RevenueFromSaleOfGoods",
)
INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic")
CASH_FLOW_TAGS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "CashFlowsFromUsedInOperatingActivities",
)
EQUITY_TAGS = ("StockholdersEquity", "Equity")
CASH_TAGS = ("CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents")
DEBT_TAGS = ("LongTermDebtNoncurrent", "LongTermDebt", "NoncurrentBorrowings")
YEARLY_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F")
# Some Canadian companies attach their yearly accounts to a 6-K, not the 40-F itself.
ATTACHED_YEARLY = "6-K"
# An American depositary receipt can stand for several shares or a fraction of one, and the
# ratio is not in these figures. A price times shares would be wrong for these filers.
RECEIPT_FORMS = ("20-F", "20-F/A")
YEARS = 10
GROWTH_CAP = 0.15
CASE_GAP = 0.05
BANK_GROSS_INCOME = "GrossProfit (gross income of a bank)"
DEFAULTS = {"discount_rate": 0.09, "terminal_growth": 0.025}


def _annual_flow(facts: pd.DataFrame, tag: str) -> pd.DataFrame:
    """Full-year figures, one per year, as first reported."""
    rows = facts[(facts["tag"] == tag) & facts["period_start"].notna()].copy()
    if rows.empty:
        return rows
    days = (pd.to_datetime(rows["period_end"]) - pd.to_datetime(rows["period_start"])).dt.days
    rows = rows[days.between(350, 380) & rows["form"].isin((*YEARLY_FORMS, ATTACHED_YEARLY))]
    return rows.sort_values("filed").drop_duplicates("period_end").sort_values("period_end")


def _year_end(facts: pd.DataFrame, tag: str) -> pd.DataFrame:
    rows = facts[(facts["tag"] == tag) & facts["period_start"].isna()]
    yearly = rows["form"].isin(YEARLY_FORMS)
    if "fiscal_period" in rows:
        yearly = yearly | ((rows["form"] == ATTACHED_YEARLY) & (rows["fiscal_period"] == "FY"))
    rows = rows[yearly]
    return rows.sort_values("filed").drop_duplicates("period_end").sort_values("period_end")


def _source(row) -> dict:
    return {
        "tag": row["tag"],
        "value": float(row["value"]),
        "period_end": row["period_end"],
        "filed": row["filed"],
        "form": row["form"],
        "url": row["document_url"],
    }


def _latest(table: pd.DataFrame):
    return None if table.empty else table.iloc[-1]


def _metric(name: str, value: float | None, kind: str, sources: list) -> dict:
    return {"name": name, "value": value, "kind": kind, "sources": [_source(s) for s in sources]}


def _best_flow(facts: pd.DataFrame, tags: tuple[str, ...]) -> pd.DataFrame:
    """Companies change labels over time, so join them, preferring earlier tags for a year."""
    tables = [_annual_flow(facts, tag) for tag in tags]
    tables = [table for table in tables if len(table)]
    if not tables:
        return pd.DataFrame()
    joined = pd.concat(tables).drop_duplicates("period_end")
    return joined.sort_values("period_end")


def _largest_flow(facts: pd.DataFrame, tags: tuple[str, ...]) -> pd.DataFrame:
    """For revenue, some labels are only a part of the total, so take the largest each year."""
    tables = [_annual_flow(facts, tag) for tag in tags]
    tables = [table for table in tables if len(table)]
    if not tables:
        return pd.DataFrame()
    joined = pd.concat(tables).sort_values("value", ascending=False)
    return joined.drop_duplicates("period_end").sort_values("period_end")


def _bank_revenue(facts: pd.DataFrame) -> pd.DataFrame:
    """Banks have no revenue line. Their usual measure is net interest plus other income."""
    interest = _annual_flow(facts, "InterestIncomeExpenseNet")
    other = _annual_flow(facts, "NoninterestIncome")
    if len(interest) and len(other):
        joined = interest.merge(
            other[["period_end", "value"]], on="period_end", suffixes=("", "_other")
        )
        joined["value"] = joined["value"] + joined["value_other"]
        joined["tag"] = "InterestIncomeExpenseNet + NoninterestIncome"
        return joined.drop(columns="value_other")
    # Foreign banks report this total as gross income, under the gross profit label.
    gross = _annual_flow(facts, "GrossProfit")
    interest = _annual_flow(facts, "InterestRevenueExpense")
    if len(gross) and len(interest):
        joined = gross.merge(
            interest[["period_end", "value"]], on="period_end", suffixes=("", "_interest")
        )
        joined = joined[joined["value_interest"].abs() >= joined["value"] * 0.3]
        return joined.drop(columns="value_interest").assign(tag=BANK_GROSS_INCOME)
    return pd.DataFrame()


def revenue_table(facts: pd.DataFrame) -> pd.DataFrame:
    bank = _bank_revenue(facts)
    largest = _largest_flow(facts, REVENUE_TAGS)
    if bank.empty:
        return largest
    return pd.concat([bank, largest]).drop_duplicates("period_end").sort_values("period_end")


def _best_end(facts: pd.DataFrame, tags: tuple[str, ...]) -> pd.DataFrame:
    tables = [_year_end(facts, tag) for tag in tags]
    tables = [table for table in tables if len(table)]
    if not tables:
        return pd.DataFrame()
    return pd.concat(tables).drop_duplicates("period_end").sort_values("period_end")


def _same_year(first, second) -> bool:
    return first is not None and second is not None and first["period_end"] == second["period_end"]


def _ratio(top, bottom) -> float | None:
    # A ratio of two different years would be meaningless, so it stays Not verified.
    if not _same_year(top, bottom) or bottom["value"] == 0:
        return None
    return float(top["value"] / bottom["value"])


def report(facts: pd.DataFrame, price: float | None, changes: dict | None = None) -> dict:
    changes = changes or {}
    empty = {
        "available": False,
        "metrics": [],
        "cases": [],
        "assumptions": {},
        "price": price,
        "history": [],
    }
    if facts.empty:
        return empty

    revenues = revenue_table(facts)
    revenue = _latest(revenues)
    gross = _latest(_annual_flow(facts, "GrossProfit"))
    if revenue is not None and revenue["tag"] == BANK_GROSS_INCOME:
        gross = None
    income = _latest(_best_flow(facts, INCOME_TAGS))
    cash_flow = _latest(_best_flow(facts, CASH_FLOW_TAGS))
    capex = _latest(_best_flow(facts, CAPEX_TAGS))
    equity = _latest(_best_end(facts, EQUITY_TAGS))
    cash = _latest(_best_end(facts, CASH_TAGS))
    debt = _latest(_best_end(facts, DEBT_TAGS))
    shares_rows = facts[facts["tag"] == "EntityCommonStockSharesOutstanding"]
    shares = None if shares_rows.empty else shares_rows.sort_values("filed").iloc[-1]
    newest = income if income is not None else revenue
    receipts = newest is not None and newest["form"] in RECEIPT_FORMS
    if receipts:
        shares = None

    growth = None
    growth_sources = []
    if len(revenues) >= 4:
        last, first = revenues.iloc[-1], revenues.iloc[-4]
        if first["value"] > 0 and last["value"] > 0:
            growth = float((last["value"] / first["value"]) ** (1 / 3) - 1)
            growth_sources = [first, last]

    free_cash = None
    if _same_year(cash_flow, capex):
        free_cash = float(cash_flow["value"] - capex["value"])
    currency = None if revenue is None else revenue["unit"]
    in_dollars = currency == "USD" or currency is None
    # Shares trade in dollars. Figures in another currency can't be compared with the price.
    market_value = (
        float(price * shares["value"]) if price and shares is not None and in_dollars else None
    )

    def share_of(value):
        return None if value is None or not market_value else value / market_value

    def plain(name, row):
        value = None if row is None else float(row["value"])
        return _metric(name, value, "money", [] if row is None else [row])

    income_table = _best_flow(facts, INCOME_TAGS)
    history = []
    if len(revenues) and len(income_table):
        joined = revenues[["period_end", "value"]].merge(
            income_table[["period_end", "value", "document_url"]],
            on="period_end",
            how="outer",
            suffixes=("_revenue", "_income"),
        )
        history = [
            {
                "period_end": row["period_end"],
                "revenue": None if pd.isna(row["value_revenue"]) else float(row["value_revenue"]),
                "net_income": None if pd.isna(row["value_income"]) else float(row["value_income"]),
                "url": None if pd.isna(row["document_url"]) else row["document_url"],
            }
            for _, row in joined.sort_values("period_end").tail(5).iterrows()
        ]

    metrics = [
        plain("Net income", income),
        plain("Gross profit", gross),
        plain("Operating cash flow", cash_flow),
        plain("Total assets", _latest(_year_end(facts, "Assets"))),
        plain("Long-term debt", debt),
        plain("Cash", cash),
        _metric(
            "Revenue",
            None if revenue is None else float(revenue["value"]),
            "money",
            [r for r in [revenue] if r is not None],
        ),
        _metric("Revenue growth a year, 3 years", growth, "percent", growth_sources),
        _metric(
            "Gross margin",
            _ratio(gross, revenue),
            "percent",
            [r for r in [gross, revenue] if r is not None],
        ),
        _metric(
            "Net profit margin",
            _ratio(income, revenue),
            "percent",
            [r for r in [income, revenue] if r is not None],
        ),
        _metric(
            "Return on equity",
            _ratio(income, equity),
            "percent",
            [r for r in [income, equity] if r is not None],
        ),
        _metric(
            "Debt to equity",
            _ratio(debt, equity),
            "ratio",
            [r for r in [debt, equity] if r is not None],
        ),
        _metric(
            "Free cash flow", free_cash, "money", [r for r in [cash_flow, capex] if r is not None]
        ),
        _metric(
            "Free cash flow yield",
            share_of(free_cash),
            "percent",
            [r for r in [cash_flow, capex, shares] if r is not None],
        ),
        _metric(
            "Earnings yield",
            share_of(None if income is None else float(income["value"])),
            "percent",
            [r for r in [income, shares] if r is not None],
        ),
    ]

    can_value = bool(
        free_cash
        and free_cash > 0
        and shares is not None
        and shares["value"] > 0
        and price
        and in_dollars
    )
    start = 0.0 if growth is None else min(max(growth, 0.0), GROWTH_CAP)
    assumptions = {
        "bear_growth": max(start - CASE_GAP, 0.0),
        "base_growth": start,
        "bull_growth": start + CASE_GAP,
        **DEFAULTS,
        **changes,
    }
    cases = []
    if can_value and assumptions["discount_rate"] > assumptions["terminal_growth"]:
        debt_value = 0.0 if debt is None else float(debt["value"])
        cash_value = 0.0 if cash is None else float(cash["value"])
        for name in ("Bear", "Base", "Bull"):
            per_share = discounted_value(
                free_cash,
                assumptions[f"{name.lower()}_growth"],
                assumptions["discount_rate"],
                assumptions["terminal_growth"],
                debt_value,
                cash_value,
                float(shares["value"]),
            )
            cases.append({"name": name, "value": per_share, "against_price": per_share / price - 1})
    return {
        "available": True,
        "price": price,
        "currency": currency or "USD",
        "metrics": metrics,
        "history": history,
        "assumptions": assumptions,
        "cases": cases,
        "receipts": receipts,
        "valuation_inputs": [
            _source(r) for r in [cash_flow, capex, debt, cash, shares] if r is not None
        ],
    }


def discounted_value(
    free_cash: float,
    growth: float,
    discount: float,
    terminal: float,
    debt: float,
    cash: float,
    shares: float,
) -> float:
    """Value per share: cash flows that fade to terminal growth, discounted to today."""
    present, flow = 0.0, free_cash
    for year in range(1, YEARS + 1):
        rate = growth + (terminal - growth) * (year - 1) / (YEARS - 1)
        flow *= 1 + rate
        present += flow / (1 + discount) ** year
    end_value = flow * (1 + terminal) / (discount - terminal)
    present += end_value / (1 + discount) ** YEARS
    return (present - debt + cash) / shares


def point_in_time(facts: pd.DataFrame) -> pd.DataFrame:
    """Yearly factor inputs, each dated the day after filing, so nothing is used early."""
    if facts.empty:
        return pd.DataFrame()

    def series(table: pd.DataFrame, name: str) -> pd.DataFrame:
        return table[["period_end", "value", "filed"]].rename(
            columns={"value": name, "filed": f"filed_{name}"}
        )

    revenue_free = _annual_flow(facts, "GrossProfit")
    parts = [
        series(revenue_free, "gross"),
        series(_best_flow(facts, INCOME_TAGS), "income"),
        series(_best_flow(facts, CASH_FLOW_TAGS), "cash_flow"),
        series(_year_end(facts, "Assets"), "assets"),
        series(_best_end(facts, EQUITY_TAGS), "equity"),
    ]
    table = None
    for part in parts:
        table = part if table is None else table.merge(part, on="period_end", how="outer")
    if table is None or table.empty:
        return pd.DataFrame()
    table = table.sort_values("period_end")
    filed_columns = [column for column in table if column.startswith("filed_")]
    table["available"] = pd.to_datetime(table[filed_columns].max(axis=1)) + pd.Timedelta(days=1)
    table["profitability"] = table["gross"] / table["assets"]
    table["investment"] = table["assets"] / table["assets"].shift(1) - 1
    table["accruals"] = (table["income"] - table["cash_flow"]) / table["assets"]
    table["income_change"] = (table["income"] - table["income"].shift(1)) / table["assets"]
    return (
        table[["available", "equity", "profitability", "investment", "accruals", "income_change"]]
        .dropna(subset=["available"])
        .sort_values("available")
    )


def shares_history(facts: pd.DataFrame) -> pd.DataFrame:
    if facts.empty:
        return pd.DataFrame()
    rows = facts[facts["tag"] == "EntityCommonStockSharesOutstanding"]
    rows = rows[~rows["form"].isin(RECEIPT_FORMS)]
    if rows.empty:
        return pd.DataFrame()
    table = rows.sort_values("filed").drop_duplicates("period_end")
    return pd.DataFrame(
        {
            "available": pd.to_datetime(table["filed"]) + pd.Timedelta(days=1),
            "shares": table["value"].to_numpy(),
        }
    )


def quarterly_changes(facts: pd.DataFrame) -> pd.DataFrame:
    """Each quarter against the same quarter a year before, dated the day after filing."""
    if facts.empty:
        return pd.DataFrame()

    def quarters(tags) -> pd.DataFrame:
        rows = facts[facts["tag"].isin(tags) & facts["period_start"].notna()].copy()
        if rows.empty:
            return rows
        days = (pd.to_datetime(rows["period_end"]) - pd.to_datetime(rows["period_start"])).dt.days
        rows = rows[days.between(80, 100)].sort_values("filed").drop_duplicates("period_end")
        rows["period_end"] = pd.to_datetime(rows["period_end"]).astype("datetime64[ns]")
        return rows.sort_values("period_end")

    def change(rows: pd.DataFrame, name: str) -> pd.DataFrame:
        if rows.empty:
            return pd.DataFrame(columns=["period_end", "available", name])
        earlier = rows[["period_end", "value"]].rename(columns={"value": "before"})
        earlier["period_end"] = earlier["period_end"] + pd.Timedelta(days=364)
        merged = pd.merge_asof(
            rows, earlier, on="period_end", direction="nearest", tolerance=pd.Timedelta(days=20)
        )
        merged[name] = (merged["value"] - merged["before"]) / merged["before"].abs()
        merged["available"] = pd.to_datetime(merged["filed"]) + pd.Timedelta(days=1)
        return merged[["period_end", "available", name]]

    income = change(quarters(list(INCOME_TAGS[:1])), "income_q")
    sales = change(quarters(REVENUE_TAGS), "revenue_q")
    table = income.merge(sales, on="period_end", how="outer", suffixes=("", "_sales"))
    table["available"] = table["available"].fillna(table["available_sales"])
    return (
        table[["available", "income_q", "revenue_q"]]
        .dropna(subset=["available"])
        .sort_values("available")
    )
