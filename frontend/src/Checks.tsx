import { useEffect, useState } from "react";

function useJson<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    fetch(url)
      .then((response) => {
        if (response.status !== 200) throw new Error();
        return response.json();
      })
      .then(setData)
      .catch(() => setFailed(true));
  }, [url]);
  return { data, failed };
}

type Reading = { factor: string; name: string; value: number; percentile: number };
type Check = {
  run_at: string;
  edge: boolean;
  t_stat: number | null;
  holdout_gain: number | null;
  test_dates: number;
  chance: number | null;
  state: string;
  readings: Reading[];
};

export function MarketCheck() {
  const { data, failed } = useJson<{ check: Check | null }>("/api/market-check");
  if (failed) return <p className="bad">Could not load the market check.</p>;
  if (!data) return null;
  const check = data.check;
  if (!check) return <p>Market check: not run yet. It runs every Saturday.</p>;
  const tone = check.state === "Favourable" ? "ok" : check.state === "Cautious" ? "bad" : "";
  return (
    <section className="market-check">
      <h3>
        Market check: <span className={tone}>{check.state}</span>
      </h3>
      <p>
        {check.chance === null
          ? "Not verified."
          : `The economy-wide readings below give about a ${Math.round(check.chance * 100)}% chance that the average stock rises over the next month.`}{" "}
        {check.edge ? (
          <b>This passed its test, so a cautious reading holds off new buys.</b>
        ) : (
          <b>This hasn't passed its test ({check.test_dates} past months checked), so it's shown for information and doesn't change any decision.</b>
        )}
      </p>
      <details>
        <summary>The readings ({check.readings.length})</summary>
        <table>
          <thead>
            <tr><th>Reading</th><th>Now</th><th>Higher than this share of the past</th></tr>
          </thead>
          <tbody>
            {check.readings.map((r) => (
              <tr key={r.factor}>
                <td>{r.name}</td>
                <td>{Math.abs(r.value) < 10 ? r.value.toFixed(2) : r.value.toFixed(0)}</td>
                <td>{r.percentile}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

type FamilyTest = { family: string; change: number; t_stat: number; verdict: string };
type Bin = { model: string; low: number; high: number; rate: number; n: number };

export function DecisionTests() {
  const { data, failed } = useJson<{ families: FamilyTest[]; calibration: Bin[] }>("/api/decision-tests");
  if (failed) return <p className="bad">Could not load the decision tests.</p>;
  if (!data) return null;
  return (
    <section>
      <h2>Which factor families earn their place?</h2>
      <p>Each family is left out in turn, on past years. If results get worse without it, it helps. A family that makes results worse is dropped from the ranking.</p>
      {data.families.length === 0 ? (
        <p>Not tested yet. It runs every Saturday.</p>
      ) : (
        <table>
          <thead><tr><th>Family</th><th>Result</th><th>Strength of evidence</th></tr></thead>
          <tbody>
            {data.families.map((f) => (
              <tr key={f.family} className={f.verdict === "Helps" ? "row-buy" : f.verdict === "Hurts" ? "row-sell" : ""}>
                <td>{f.family}</td>
                <td><b>{f.verdict === "Hurts" ? "Hurts, so dropped" : f.verdict}</b></td>
                <td>{f.t_stat.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h2>How often each ranking really beat the average stock</h2>
      {data.calibration.length === 0 ? (
        <p>Not measured yet.</p>
      ) : (
        <>
          <p>From years the model ({data.calibration[0].model}) never trained on. If the model works, the right-hand numbers rise from top to bottom.</p>
          <table>
            <thead><tr><th>Ranking</th><th>Beat the average</th><th>Cases</th></tr></thead>
            <tbody>
              {data.calibration.map((b) => (
                <tr key={b.low}>
                  <td>Top {Math.round((1 - b.high) * 100)}% to {Math.round((1 - b.low) * 100)}%</td>
                  <td>{Math.round(b.rate * 100)}%</td>
                  <td>{b.n.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
