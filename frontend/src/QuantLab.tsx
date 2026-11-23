import { useEffect, useState } from "react";

/** Latest stored result for each quant study variant, from /api/quant. */
type Row = {
  study: string;
  variant: string;
  run_at: string;
  period: string;
  verdict: string;
  metrics: Record<string, unknown>;
  settings: Record<string, unknown>;
};

type Summary = {
  sharpe: number | null;
  sharpe_se: number | null;
  max_drawdown: number | null;
  annual_return: number | null;
  annual_volatility: number | null;
};

const NOT_VERIFIED = "Not verified";

function pct(value: unknown, digits = 1): string {
  return typeof value === "number" ? `${(value * 100).toFixed(digits)}%` : NOT_VERIFIED;
}

function num(value: unknown, digits = 2): string {
  return typeof value === "number" ? value.toFixed(digits) : NOT_VERIFIED;
}

const STUDIES: Record<string, { title: string; question: string; sources: [string, string][] }> = {
  ma_crossover: {
    title: "Moving-average crossover",
    question:
      "Does owning a stock only while its 50-day average is above its 200-day average beat holding every stock?",
    sources: [["Lo (2002), the statistics of Sharpe ratios", "https://ideas.repec.org/a/taf/ufajxx/v58y2002i4p36-52.html"]],
  },
  vol_targeting: {
    title: "Volatility targeting",
    question: "Does holding less when the market has been jumpy, and more when calm, improve returns for the risk taken?",
    sources: [
      ["Moreira & Muir (2017)", "https://www.nber.org/papers/w22208"],
      [
        "DeMiguel et al. (2024)",
        "https://lbsresearch.london.edu/id/eprint/3716/1/The%20Journal%20of%20Finance%20-%202024%20-%20DeMIGUEL%20-%20A%20Multifactor%20Perspective%20on%20Volatility%E2%80%90Managed%20Portfolios.pdf",
      ],
    ],
  },
  pairs_trading: {
    title: "Pairs trading (statistical arbitrage)",
    question:
      "When two related stocks drift apart, does betting on them coming back together make money after costs?",
    sources: [
      ["Gatev, Goetzmann & Rouwenhorst (2006)", "https://econpapers.repec.org/RePEc:oup:rfinst:v:19:y:2006:i:3:p:797-827"],
      ["Do & Faff (2010)", "https://ideas.repec.org/a/taf/ufajxx/v66y2010i4p83-95.html"],
    ],
  },
  value_at_risk: {
    title: "Monte Carlo Value at Risk",
    question: "If a model says '95% of days will lose less than this', is reality worse more often than 5% of the time?",
    sources: [
      ["Kupiec (1995) and Christoffersen (1998) tests", "https://it.mathworks.com/help/risk/overview-of-var-backtesting.html"],
      ["RiskMetrics decay of 0.94", "https://metricgate.com/docs/ewma-volatility-riskmetrics/"],
    ],
  },
  panic_detector: {
    title: "Market panic detector",
    question: "When stocks start moving as one, does the market do worse over the next month?",
    sources: [
      [
        "Kritzman et al., absorption ratio (summary)",
        "https://www.liverpool.ac.uk/media/livacuk/schoolofmanagement/research/economics/Application,Absorption,Ratio.pdf",
      ],
    ],
  },
};

function Verdict({ text }: { text: string }) {
  const good = text === "Edge" || text === "Not rejected";
  return <b className={good ? "ok" : "bad"}>{text}</b>;
}

function StrategyTable({ rows }: { rows: Row[] }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Version</th>
            <th>Verdict</th>
            <th>Sharpe (± error)</th>
            <th>Benchmark Sharpe</th>
            <th>Yearly return</th>
            <th>Worst fall</th>
            <th>Benchmark worst fall</th>
            <th>Test score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const s = row.metrics.strategy as Summary | undefined;
            const b = row.metrics.baseline as Summary | undefined;
            return (
              <tr key={row.variant}>
                <td>{row.variant}</td>
                <td>
                  <Verdict text={row.verdict} />
                </td>
                <td>
                  {num(s?.sharpe)} ± {num(s?.sharpe_se)}
                </td>
                <td>{b?.sharpe == null ? "None (no-trade benchmark)" : num(b.sharpe)}</td>
                <td>{pct(s?.annual_return)}</td>
                <td>{pct(s?.max_drawdown)}</td>
                <td>{pct(b?.max_drawdown)}</td>
                <td>t = {num(row.metrics.choice_t)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RiskTable({ rows }: { rows: Row[] }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Simulation</th>
            <th>Verdict</th>
            <th>Days breached</th>
            <th>Breach rate (target 5%)</th>
            <th>Breach-rate test</th>
            <th>Bunching test</th>
            <th>Extra loss on a breach</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.variant}>
              <td>{row.variant}</td>
              <td>
                <Verdict text={row.verdict} />
              </td>
              <td>
                {String(row.metrics.breaches ?? NOT_VERIFIED)} of {String(row.metrics.days ?? NOT_VERIFIED)}
              </td>
              <td>{pct(row.metrics.breach_rate)}</td>
              <td>p = {num(row.metrics.kupiec_p, 3)}</td>
              <td>p = {num(row.metrics.christoffersen_p, 3)}</td>
              <td>{pct(row.metrics.average_excess_loss_on_breach, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PanicTable({ rows }: { rows: Row[] }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Signal</th>
            <th>Verdict</th>
            <th>Next-month gap after a warning</th>
            <th>Test score</th>
            <th>Held-back years gap</th>
            <th>Days with a warning</th>
            <th>Worst months that had a warning</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const choice = row.metrics.choice as Record<string, number> | undefined;
            const holdout = row.metrics.holdout as Record<string, number> | undefined;
            return (
              <tr key={row.variant}>
                <td>{row.variant}</td>
                <td>
                  <Verdict text={row.verdict} />
                </td>
                <td>{pct(choice?.gap_after_shift, 2)}</td>
                <td>t = {num(choice?.t)}</td>
                <td>{pct(holdout?.gap_after_shift, 2)}</td>
                <td>{pct(row.metrics.share_of_days_with_shift)}</td>
                <td>{pct(row.metrics.share_of_worst_5pct_months_after_shift)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function QuantLab() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    fetch("/api/quant")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setRows)
      .catch(() => setFailed(true));
  }, []);
  if (failed) return <p className="bad">Not verified: the quant results didn't load.</p>;
  if (!rows) return <p>Loading…</p>;
  if (rows.length === 0) return <p>No quant study has run yet. Results appear after the weekly test.</p>;
  const byStudy = new Map<string, Row[]>();
  rows.forEach((row) => byStudy.set(row.study, [...(byStudy.get(row.study) ?? []), row]));
  return (
    <section>
      <h2>Quant lab</h2>
      <p>
        Each idea is tested on past data after trading costs. To pass it needs a test score of at least 3 on
        the earlier years and must still work on the last two years, which were held back. Today's stock list
        leaves out companies that failed, which flatters every result here.
      </p>
      {Object.entries(STUDIES).map(([key, info]) => {
        const studyRows = byStudy.get(key);
        return (
          <article key={key} className="card">
            <h3>{info.title}</h3>
            <p>{info.question}</p>
            {!studyRows && <p>{NOT_VERIFIED}: not run yet.</p>}
            {studyRows && key === "value_at_risk" && <RiskTable rows={studyRows} />}
            {studyRows && key === "panic_detector" && <PanicTable rows={studyRows} />}
            {studyRows && key !== "value_at_risk" && key !== "panic_detector" && <StrategyTable rows={studyRows} />}
            {studyRows && (
              <p className="small-print">
                Period {studyRows[0].period}. Last run {new Date(studyRows[0].run_at).toLocaleDateString()}.
              </p>
            )}
            <p className="small-print">
              Sources:{" "}
              {info.sources.map(([label, url], i) => (
                <span key={url}>
                  {i > 0 && "; "}
                  <a href={url} target="_blank" rel="noreferrer">
                    {label}
                  </a>
                </span>
              ))}
            </p>
          </article>
        );
      })}
    </section>
  );
}
