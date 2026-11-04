import { useEffect, useState } from "react";

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
                <tr key={check.topic}>
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
