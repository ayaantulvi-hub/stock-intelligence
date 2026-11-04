import { useEffect, useState } from "react";

type Check = { topic: string; state: string; text: string };
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

function Sizer() {
  const [values, setValues] = useState({ account: "", risk: "1", price: "", stop: "" });
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
  const [failed, setFailed] = useState(false);

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
                  <td>{check.text}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Sizer />
    </div>
  );
}
