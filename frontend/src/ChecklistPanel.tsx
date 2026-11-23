import { useEffect, useState } from "react";



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
  trailing?: boolean;
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
            Buying regularly and holding up to 20 trading days, after costs. Results on past data,
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
                  <tr key={`${row.stop_multiple ?? 0}-${row.trailing ? "t" : "f"}`}>
                    <td>
                      {row.stop_multiple === null
                        ? "No stop"
                        : `${row.stop_multiple} times daily range${row.trailing ? ", trailing" : ""}`}
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


export function OrderTicket({ stop, target, keep }: {
  stop: number;
  target?: number;
  keep: string;
}) {
  const rows: [string, string][] = [
    ["Order tab", "Market"],
    ["Side", "Buy"],
    ["Shares", "Your choice"],
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

type Planned = { ticker: string; name: string; price: number; stop: number | null; max_price?: number | null };
type Plan = { session: string | null; sell_by: string | null; proven: boolean; orders: Planned[]; paused?: boolean };

export function TodaysOrders({ onOpen }: { onOpen: (ticker: string) => void }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [failed, setFailed] = useState(false);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [shares, setShares] = useState("10");
  const [saved, setSaved] = useState<string | null>(null);
  const track = async () => {
    const tickers = (plan?.orders ?? [])
      .map((row) => row.ticker)
      .filter((ticker) => !skipped.includes(ticker));
    const response = await fetch("/api/orders/track", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers, shares: Number(shares) }),
    });
    setSaved(
      response.status === 200
        ? "Saved. The tool now checks these every update and tells you Keep or Sell on My portfolio."
        : "Could not save. Check the number of shares and try again.",
    );
  };
  useEffect(() => {
    fetch("/api/orders")
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then(setPlan)
      .catch(() => setFailed(true));
  }, []);
  if (failed) return <p className="bad">Could not load today's orders. Refresh to try again.</p>;
  if (!plan) return <p>Loading…</p>;
  if (plan.orders.length === 0) return <p>No orders yet. They appear after the next forecast.</p>;
  return (
    <>
      {plan.proven ? (
        <p className="plain">
          <b>Buy these now. Sell them all on {plan.sell_by ?? "Not verified"}.</b>
        </p>
      ) : (
        <p className="bad">
          <b>Unproven ranking, not a tested buy list.</b> These are the model's top 10, but the
          model hasn't beaten chance in testing. If you practise with them, sell them all on{" "}
          {plan.sell_by ?? "Not verified"}.
        </p>
      )}
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Stock</th>
              <th>Last close</th>
              <th>Don't pay more than</th>
              <th>Stop loss price</th>
              <th>I bought it</th>
            </tr>
          </thead>
          <tbody>
            {plan.orders.map((row) => (
              <tr key={row.ticker}>
                <td>
                  <button className="link" onClick={() => onOpen(row.ticker)}>
                    {row.ticker}
                  </button>{" "}
                  {row.name}
                </td>
                <td>{row.price.toFixed(2)}</td>
                <td>{row.max_price == null ? "Not verified" : row.max_price.toFixed(2)}</td>
                <td>{row.stop === null ? "Not verified" : row.stop.toFixed(2)}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`I bought ${row.ticker}`}
                    checked={!skipped.includes(row.ticker)}
                    onChange={(event) =>
                      setSkipped(
                        event.target.checked
                          ? skipped.filter((item) => item !== row.ticker)
                          : [...skipped, row.ticker],
                      )
                    }
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <OrderSteps keep="The longest offered" />
      <div className="inputs">
        <label>
          Shares of each
          <input type="number" min="0" step="any" value={shares} onChange={(e) => setShares(e.target.value)} />
        </label>
        <button onClick={track}>Watch the ticked stocks for me</button>
      </div>
      {saved && <p>{saved}</p>}
      <small>After you buy, tap this so the tool can tell you when to sell. It saves the last close as your buy price, which you can change on the stock's page.</small>
      <p>
        <b>When to sell:</b> don't sell before that date unless the stop sells it for you. There's
        no target price. On the sell date, sell everything left with a Market order, at whatever
        the price is then.
      </p>
      <small>Don't chase: skip a stock if its live price is above "Don't pay more than". That's the last close plus half a normal day's move.</small>
    </>
  );
}

function OrderSteps({ keep }: { keep: string }) {
  return (
    <p>
      For each one: choose <b>Market</b>, enter any number of shares, turn <b>Take profit</b> off,
      turn <b>Stop loss</b> on and enter the price above, set <b>Time in force</b> to {keep.toLowerCase()},
      and leave <b>outside RTH</b> unticked. Place orders while the US market is open, 6:30pm to
      1am Dubai time.
    </p>
  );
}

export function HowMuch({ ticker, keep = "The longest offered", stop, target }: {
  ticker: string;
  keep?: string;
  stop?: number;
  target?: number;
}) {
  const [levels, setLevels] = useState<Suggested | null>(null);
  useEffect(() => {
    fetch(`/api/stocks/${encodeURIComponent(ticker)}/levels`)
      .then((response) => (response.status === 200 ? response.json() : null))
      .then((body) => setLevels(body?.levels ?? null))
      .catch(() => setLevels(null));
  }, [ticker]);
  const stopPrice = stop ?? levels?.stop;
  if (stopPrice === undefined) return null;
  return <OrderTicket stop={stopPrice} target={target} keep={keep} />;
}

export default function ChecklistPanel({ ticker }: { ticker: string }) {
  const [levels, setLevels] = useState<{ levels: Suggested | null; tested: Tested[] } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    fetch(`/api/stocks/${encodeURIComponent(ticker)}/levels`)
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then(setLevels)
      .catch(() => setFailed(true));
  }, [ticker]);

  if (failed) return <p className="bad">Exit prices failed to load. Not verified.</p>;
  if (!levels) return null;
  return <Levels data={levels.levels} tested={levels.tested} />;
}
