import { useEffect, useState } from "react";
import { leanRow } from "./leanRow";

type Check = { topic: string; state: string; text: string; meaning?: string };
const MARKS: Record<string, [string, string]> = {
  pass: ["Pass", "ok"],
  caution: ["Caution", "bad"],
  unknown: ["Not verified", ""],
};

// The fixed-risk rule: decide the most you can lose, then size the trade to fit it.
export function sharesForRisk(account: number, riskPercent: number, price: number, stop: number) {
  if (!(account > 0) || !(riskPercent > 0) || !(price > stop) || !(stop > 0)) return null;
  const allowedLoss = account * (riskPercent / 100);
  const byRisk = Math.floor(allowedLoss / (price - stop));
  // Also keep to the 10% limit on one stock.
  const byLimit = Math.floor((account * 0.1) / price);
  const shares = Math.min(byRisk, byLimit);
  return { shares, cost: shares * price, loss: shares * (price - stop), limited: byLimit < byRisk };
}

type Suggested = {
  price: number;
  stop: number;
  target: number;
  risk_percent: number;
  target_percent: number;
  stop_reason: string;
  target_reason: string;
  ceiling_warning: string | null;
};
type Tested = {
  stop_multiple: number | null;
  trades: number;
  avg_return: number;
  win_rate: number;
  worst_return: number;
  stopped_share: number;
};

function Levels({ data, tested }: { data: Suggested | null; tested: Tested[] }) {
  return (
    <>
      <h3>Suggested exit prices</h3>
      <small>
        A stop is a price where you sell to limit a loss. A target is a price where you take a
        profit. Neither can be known to be best in advance. These follow a rule, not a prediction.
      </small>
      {!data ? (
        <p>Not verified: not enough price history.</p>
      ) : (
        <>
          <div className="glance">
            <div>
              <small>Suggested stop</small>
              <strong className="bad">{data.stop.toFixed(2)}</strong>
              <small>{data.risk_percent.toFixed(1)}% below the price</small>
            </div>
            <div>
              <small>Suggested target</small>
              <strong className="ok">{data.target.toFixed(2)}</strong>
              <small>{data.target_percent.toFixed(1)}% above the price</small>
            </div>
          </div>
          <p>
            <strong>Why this stop:</strong> {data.stop_reason}
          </p>
          <p>
            <strong>Why this target:</strong> {data.target_reason}
            {data.ceiling_warning && ` ${data.ceiling_warning}`}
          </p>
        </>
      )}
      {tested.length > 0 && (
        <>
          <h3>How different stops would have done</h3>
          <small>
            Buying regularly and holding up to 60 trading days, after costs. Results on past data,
            and not on any one stock.
          </small>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Stop distance</th>
                  <th>Average return</th>
                  <th>Won</th>
                  <th>Worst trade</th>
                  <th>Stop was hit</th>
                  <th>Trades</th>
                </tr>
              </thead>
              <tbody>
                {tested.map((row) => (
                  <tr key={row.stop_multiple ?? 0}>
                    <td>
                      {row.stop_multiple === null
                        ? "No stop"
                        : `${row.stop_multiple} times daily range`}
                    </td>
                    <td>{(row.avg_return * 100).toFixed(1)}%</td>
                    <td>{(row.win_rate * 100).toFixed(0)}%</td>
                    <td>{(row.worst_return * 100).toFixed(0)}%</td>
                    <td>{(row.stopped_share * 100).toFixed(0)}%</td>
                    <td>{row.trades.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function Sizer({ suggested }: { suggested: Suggested | null }) {
  const [values, setValues] = useState({ account: "", risk: "1", price: "", stop: "" });
  useEffect(() => {
    if (suggested) {
      setValues((current) => ({
        ...current,
        price: suggested.price.toFixed(2),
        stop: suggested.stop.toFixed(2),
      }));
    }
  }, [suggested]);
  const result = sharesForRisk(
    Number(values.account),
    Number(values.risk),
    Number(values.price),
    Number(values.stop),
  );
  const fields: [keyof typeof values, string][] = [
    ["account", "Total money to invest"],
    ["risk", "Most to lose on this trade (%)"],
    ["price", "Buy price per share"],
    ["stop", "Stop price"],
  ];
  return (
    <>
      <h3>How much to buy</h3>
      <small>
        Choose the most you can afford to lose first. Many professionals risk about 1% or less on
        one trade, so one mistake can't do serious damage. A stop can't guarantee your exit price.
      </small>
      <div className="inputs">
        {fields.map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              type="number"
              step="any"
              min="0"
              value={values[key]}
              onChange={(event) => setValues({ ...values, [key]: event.target.value })}
            />
          </label>
        ))}
      </div>
      {result && (
        <p>
          <strong>
            {result.shares} shares, costing ${result.cost.toFixed(2)}.
          </strong>{" "}
          If it hits your stop, you lose about ${result.loss.toFixed(2)}.
          {result.limited && " The 10% limit on one stock reduced this."}
        </p>
      )}
    </>
  );
}

const MONEY_KEY = "stock-intelligence-total-money";

function remembered() {
  try {
    return window.localStorage.getItem(MONEY_KEY) ?? "";
  } catch {
    return "";
  }
}

export function OrderTicket({ shares, stop, target, keep }: {
  shares: number;
  stop: number;
  target?: number;
  keep: string;
}) {
  const rows: [string, string][] = [
    ["Order tab", "Market"],
    ["Side", "Buy"],
    ["Shares", String(shares)],
    target === undefined
      ? ["Take profit price", "Switch off"]
      : ["Take profit price (switch on)", target.toFixed(2)],
    ["Stop loss price (switch on)", stop.toFixed(2)],
    ["Time in force", keep],
    ["Fill order outside RTH", "Leave unticked"],
  ];
  return (
    <div className="ticket">
      <h4>Fill in your order like this</h4>
      <table>
        <tbody>
          {rows.map(([field, value]) => (
            <tr key={field}>
              <td>{field}</td>
              <td>
                <b>{value}</b>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <small>RTH means regular trading hours: 6:30pm to 1am Dubai time in winter.</small>
    </div>
  );
}

type Planned = { ticker: string; name: string; price: number; stop: number | null };
type Plan = { session: string | null; sell_by: string | null; proven: boolean; orders: Planned[] };

export function TodaysOrders({ onOpen }: { onOpen: (ticker: string) => void }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [money, setMoney] = useState(remembered);
  const [failed, setFailed] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/orders")
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then(setPlan)
      .catch(() => setFailed(true));
  }, []);
  const change = (value: string) => {
    setMoney(value);
    try {
      window.localStorage.setItem(MONEY_KEY, value);
    } catch {
      // The answer still works this visit. It just won't be remembered.
    }
  };
  if (failed) return <p className="bad">Could not load today's orders. Refresh to try again.</p>;
  if (!plan || plan.orders.length === 0) return null;
  const each = Number(money) / plan.orders.length;
  const picked = plan.orders.find((row) => row.ticker === (chosen ?? plan.orders[0].ticker));
  return (
    <section className="orders">
      <h3>Today's orders: hold for about a month</h3>
      <p>
        This is a 20-trading-day hold. It isn't day trading or a long-term investment. Buy these for{" "}
        {plan.session} and sell them all on <b>{plan.sell_by ?? "Not verified"}</b>.
        {!plan.proven && " The model hasn't passed its test yet, so this is a guess."}
      </p>
      <label>
        Your total money to invest ($)
        <input type="number" min="0" step="any" value={money} onChange={(e) => change(e.target.value)} />
      </label>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Stock</th>
              <th>Order tab</th>
              <th>Shares</th>
              <th>Stop loss price</th>
              <th>Take profit</th>
            </tr>
          </thead>
          <tbody>
            {plan.orders.map((row) => (
              <tr key={row.ticker} className={row.ticker === picked?.ticker ? "row-buy" : ""}>
                <td>
                  <button className="link" onClick={() => setChosen(row.ticker)}>
                    {row.ticker}
                  </button>
                </td>
                <td>Market</td>
                <td>{each > 0 ? Math.floor(each / row.price) : "Enter your money"}</td>
                <td>{row.stop === null ? "Not verified" : row.stop.toFixed(2)}</td>
                <td>Off</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {picked && picked.stop !== null && each >= picked.price && (
        <>
          <h4>
            Your order for {picked.ticker}{" "}
            <button className="link" onClick={() => onOpen(picked.ticker)}>
              See why
            </button>
          </h4>
          <OrderTicket
            shares={Math.floor(each / picked.price)}
            stop={picked.stop}
            keep="The longest offered"
          />
        </>
      )}
      <small>
        Tap a stock to see its order filled in. Shares split your money equally, using the last close. If the live price is more than 5%
        away, skip that stock. Time in force: the longest offered. Outside RTH: unticked.
      </small>
    </section>
  );
}

export function HowMuch({ ticker, keep = "GTC, or the longest offered", stop, target }: {
  ticker: string;
  keep?: string;
  stop?: number;
  target?: number;
}) {
  const [money, setMoney] = useState(remembered);
  const [levels, setLevels] = useState<Suggested | null>(null);

  useEffect(() => {
    fetch(`/api/stocks/${encodeURIComponent(ticker)}/levels`)
      .then((response) => (response.status === 200 ? response.json() : null))
      .then((body) => setLevels(body?.levels ?? null))
      .catch(() => setLevels(null));
  }, [ticker]);

  const change = (value: string) => {
    setMoney(value);
    try {
      window.localStorage.setItem(MONEY_KEY, value);
    } catch {
      // The answer still works this visit. It just won't be remembered.
    }
  };
  const stopPrice = stop ?? levels?.stop;
  const result =
    levels && stopPrice !== undefined && sharesForRisk(Number(money), 1, levels.price, stopPrice);
  return (
    <div className="how-much">
      <label>
        Your total money to invest ($)
        <input
          type="number"
          min="0"
          step="any"
          value={money}
          onChange={(event) => change(event.target.value)}
        />
      </label>
      {result && result.shares > 0 && (
        <p>
          <strong>
            Up to {result.shares} {result.shares === 1 ? "share" : "shares"}, about $
            {result.cost.toFixed(2)}.
          </strong>{" "}
          That keeps this stock under 10% of your money, and a fall to the stop would lose about $
          {result.loss.toFixed(2)}, or {((result.loss / Number(money)) * 100).toFixed(1)}% of it.
        </p>
      )}
      {result && result.shares > 0 && stopPrice !== undefined && (
        <OrderTicket shares={result.shares} stop={stopPrice} target={target} keep={keep} />
      )}
      {result && result.shares === 0 && (
        <p>
          One share costs more than the 10% limit allows with this much money. Consider a smaller
          priced stock, a fund, or fractional shares.
        </p>
      )}
    </div>
  );
}

export default function ChecklistPanel({ ticker }: { ticker: string }) {
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [levels, setLevels] = useState<{ levels: Suggested | null; tested: Tested[] } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(`/api/stocks/${encodeURIComponent(ticker)}/levels`)
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then(setLevels)
      .catch(() => setFailed(true));
  }, [ticker]);

  useEffect(() => {
    setFailed(false);
    fetch(`/api/stocks/${encodeURIComponent(ticker)}/checklist`)
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then(setChecks)
      .catch(() => setFailed(true));
  }, [ticker]);

  if (failed) return <p className="bad">Checklist failed to load. Not verified.</p>;
  if (!checks) return null;
  return (
    <div>
      <h3>Before you trade</h3>
      <small>The questions a careful investor asks. These are not added into a score.</small>
      <div className="scroll">
        <table className="checks">
          <tbody>
            {checks.map((check) => {
              const [label, tone] = MARKS[check.state];
              return (
                <tr key={check.topic} className={leanRow(check.state)}>
                  <td>{check.topic}</td>
                  <td className={tone}>{label}</td>
                  <td>
                    {check.text}
                    {check.meaning && <small>{check.meaning}</small>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {levels && <Levels data={levels.levels} tested={levels.tested} />}
      <Sizer suggested={levels?.levels ?? null} />
    </div>
  );
}
