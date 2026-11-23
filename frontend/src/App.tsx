import { useEffect, useState, type ReactNode } from "react";
import {
  getJson,
  PASSING,
  type Breaches,
  type Coverage,
  type Feed,
  type Growth,
  type Panic,
  type Result,
  type Summary,
} from "./api";
import { BarStrip, LineChart, TableView } from "./charts";
import { fixed, NOT_VERIFIED, pct } from "./format";

type Source = [string, string];

const SOURCES: Record<string, Source[]> = {
  ma_crossover: [["Lo (2002), the statistics of Sharpe ratios", "https://ideas.repec.org/a/taf/ufajxx/v58y2002i4p36-52.html"]],
  vol_targeting: [
    ["Moreira & Muir (2017)", "https://www.nber.org/papers/w22208"],
    [
      "DeMiguel et al. (2024)",
      "https://lbsresearch.london.edu/id/eprint/3716/1/The%20Journal%20of%20Finance%20-%202024%20-%20DeMIGUEL%20-%20A%20Multifactor%20Perspective%20on%20Volatility%E2%80%90Managed%20Portfolios.pdf",
    ],
  ],
  pairs_trading: [
    ["Gatev, Goetzmann & Rouwenhorst (2006)", "https://econpapers.repec.org/RePEc:oup:rfinst:v:19:y:2006:i:3:p:797-827"],
    ["Do & Faff (2010)", "https://ideas.repec.org/a/taf/ufajxx/v66y2010i4p83-95.html"],
  ],
  value_at_risk: [
    ["Kupiec (1995) and Christoffersen (1998) tests", "https://it.mathworks.com/help/risk/overview-of-var-backtesting.html"],
    ["RiskMetrics decay of 0.94", "https://metricgate.com/docs/ewma-volatility-riskmetrics/"],
  ],
  panic_detector: [
    [
      "Kritzman et al., absorption ratio (summary)",
      "https://www.liverpool.ac.uk/media/livacuk/schoolofmanagement/research/economics/Application,Absorption,Ratio.pdf",
    ],
  ],
};

const STUDIES: { key: string; name: string; question: string }[] = [
  { key: "value_at_risk", name: "Value at Risk", question: "When a model says 95% of days will lose less than this, does reality agree?" },
  { key: "pairs_trading", name: "Pairs trading", question: "When two related stocks drift apart, does betting on them closing the gap pay after costs?" },
  { key: "vol_targeting", name: "Volatility targeting", question: "Does holding less when markets are jumpy improve returns for the risk taken?" },
  { key: "ma_crossover", name: "Trend following", question: "Does owning a stock only while its 50-day average is above its 200-day average beat holding everything?" },
  { key: "panic_detector", name: "Panic detector", question: "When stocks start moving as one, does the market do worse over the next month?" },
];

const money = (v: number) => `$${v.toFixed(2)}`;

const VARIANT_NAMES: Record<string, string> = {
  historical: "Historical bootstrap",
  normal: "Normal curve",
  ewma: "EWMA normal (recent days weigh more)",
  distance: "Distance method",
  cointegration: "Cointegration method",
  "50/200": "50/200-day crossover",
  "variance-managed (Moreira-Muir)": "Variance-managed (Moreira-Muir)",
  "volatility target": "Volatility target",
  "absorption ratio shift": "Absorption-ratio warning",
};

function useLoad<T>(url: string): { data: T | null; failed: boolean } {
  const [state, setState] = useState<{ data: T | null; failed: boolean }>({ data: null, failed: false });
  useEffect(() => {
    let alive = true;
    getJson<T>(url)
      .then((data) => alive && setState({ data, failed: false }))
      .catch(() => alive && setState({ data: null, failed: true }));
    return () => {
      alive = false;
    };
  }, [url]);
  return state;
}

function Verdict({ text }: { text: string }) {
  const pass = PASSING.has(text);
  return (
    <span className={`verdict ${pass ? "pass" : "fail"}`}>
      <span aria-hidden="true">{pass ? "✓" : "–"}</span> {text}
    </span>
  );
}

function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="facts">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Method({ result }: { result: Result }) {
  const sources = SOURCES[result.study] ?? [];
  return (
    <details className="method">
      <summary>How this was tested</summary>
      <p>
        Period {result.period}. Last run {new Date(result.run_at).toLocaleDateString("en-GB")}.
      </p>
      <ul className="settings">
        {Object.entries(result.settings).map(([k, v]) => (
          <li key={k}>
            {k.replaceAll("_", " ")}: <strong>{String(v)}</strong>
          </li>
        ))}
      </ul>
      {sources.length > 0 && (
        <p>
          Sources:{" "}
          {sources.map(([label, url], i) => (
            <span key={url}>
              {i > 0 && "; "}
              <a href={url} target="_blank" rel="noreferrer">
                {label}
              </a>
            </span>
          ))}
        </p>
      )}
    </details>
  );
}

function StrategyVariant({ result, baselineName }: { result: Result; baselineName: string }) {
  const s = result.metrics.strategy as Summary | undefined;
  const b = result.metrics.baseline as Summary | undefined;
  const series = result.metrics.series as Growth | undefined;
  const flat = b?.sharpe == null;
  return (
    <div className="variant">
      <div className="variant-head">
        <h3>{VARIANT_NAMES[result.variant] ?? result.variant}</h3>
        <Verdict text={result.verdict} />
      </div>
      <Facts
        items={[
          ["Sharpe ratio", <>{fixed(s?.sharpe)} <small>± {fixed(s?.sharpe_se)}</small></>],
          [flat ? "Benchmark" : `${baselineName} Sharpe`, flat ? "No trade" : fixed(b?.sharpe)],
          ["Yearly return", pct(s?.annual_return)],
          ["Worst fall", <>{pct(s?.max_drawdown)} {!flat && <small>vs {pct(b?.max_drawdown)}</small>}</>],
          ["Test score", <>t = {fixed(result.metrics.choice_t)} <small className="below">needs 3</small></>],
        ]}
      />
      {series && (
        <LineChart
          title={`Growth of $1 after costs, ${(VARIANT_NAMES[result.variant] ?? result.variant).toLowerCase()}${flat ? "" : ` against ${baselineName.toLowerCase()}`}`}
          months={series.months}
          series={[
            { name: "Strategy", values: series.strategy, role: "s1" },
            ...(flat ? [] : [{ name: baselineName, values: series.baseline, role: "s2" as const }]),
          ]}
          format={money}
          baseline={1}
        />
      )}
      <Method result={result} />
    </div>
  );
}

function RiskStudy({ rows }: { rows: Result[] }) {
  const order = ["historical", "normal", "ewma"];
  const sorted = [...rows].sort((a, b) => order.indexOf(a.variant) - order.indexOf(b.variant));
  const all = sorted.map((r) => r.metrics.series as Breaches | undefined);
  const max = Math.max(1, ...all.flatMap((s) => s?.breaches ?? []));
  const names = VARIANT_NAMES;
  return (
    <>
      <div className="scroll">
        <table className="compare">
          <thead>
            <tr>
              <th scope="col">Simulation</th>
              <th scope="col">Breach rate</th>
              <th scope="col">After a breach</th>
              <th scope="col">Rate test</th>
              <th scope="col">Bunching test</th>
              <th scope="col">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.variant}>
                <th scope="row">{names[r.variant] ?? r.variant}</th>
                <td>{pct(r.metrics.breach_rate)}</td>
                <td>{pct(r.metrics.breach_rate_after_a_breach)}</td>
                <td>p = {fixed(r.metrics.kupiec_p, 3)}</td>
                <td>p = {fixed(r.metrics.christoffersen_p, 3)}</td>
                <td>
                  <Verdict text={r.verdict} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">
        Target: 5% of days, and a breach no more likely the day after a breach. Each bar below is one month's
        breaches, on the same scale, so runs of bad days stand out.
      </p>
      {sorted.map((r, k) =>
        all[k] ? (
          <BarStrip key={r.variant} title={names[r.variant] ?? r.variant} months={all[k]!.months} values={all[k]!.breaches} max={max} />
        ) : null,
      )}
      {all[0] && (
        <TableView
          caption="Value at Risk breaches per month"
          months={all[0].months}
          series={sorted.map((r, k) => ({ name: names[r.variant] ?? r.variant, values: all[k]?.breaches ?? [], role: "s1" }))}
          format={(v) => String(v)}
        />
      )}
      {sorted[0] && <Method result={sorted[0]} />}
    </>
  );
}

function PanicStudy({ result }: { result: Result }) {
  const series = result.metrics.series as Panic | undefined;
  const choice = result.metrics.choice as Record<string, number> | undefined;
  const holdout = result.metrics.holdout as Record<string, number> | undefined;
  return (
    <div className="variant">
      <div className="variant-head">
        <h3>{VARIANT_NAMES[result.variant] ?? result.variant}</h3>
        <Verdict text={result.verdict} />
      </div>
      <Facts
        items={[
          ["Next month after a warning", pct(choice?.gap_after_shift, 2, true)],
          ["Test score", <>t = {fixed(choice?.t)} <small className="below">needs −3</small></>],
          ["Held-back years", pct(holdout?.gap_after_shift, 2, true)],
          ["Days with a warning", pct(result.metrics.share_of_days_with_shift, 0)],
          ["Worst months warned", pct(result.metrics.share_of_worst_5pct_months_after_shift, 0)],
        ]}
      />
      {series && (
        <LineChart
          title="Average correlation between stocks, by month; shading marks months with warnings"
          months={series.months}
          series={[{ name: "Average correlation", values: series.average_correlation, role: "s1" }]}
          format={(v) => v.toFixed(2)}
          shade={series.warning_share}
        />
      )}
      <Method result={result} />
    </div>
  );
}

function Study({ info, rows }: { info: (typeof STUDIES)[number]; rows: Result[] | undefined }) {
  return (
    <section className="study" id={info.key} aria-labelledby={`${info.key}-title`}>
      <p className="study-name">{info.name}</p>
      <h2 id={`${info.key}-title`}>{info.question}</h2>
      {!rows && <p className="muted">{NOT_VERIFIED}: this study hasn't run yet.</p>}
      {rows && info.key === "value_at_risk" && <RiskStudy rows={rows} />}
      {rows && info.key === "panic_detector" && rows.map((r) => <PanicStudy key={r.variant} result={r} />)}
      {rows &&
        !["value_at_risk", "panic_detector"].includes(info.key) &&
        rows.map((r) => (
          <StrategyVariant
            key={r.variant}
            result={r}
            baselineName={info.key === "vol_targeting" ? "Unmanaged" : "Hold all"}
          />
        ))}
    </section>
  );
}

function Ledger({ results }: { results: Result[] }) {
  const passed = results.filter((r) => PASSING.has(r.verdict)).length;
  const years = results.map((r) => r.period.match(/\d{4}/g)?.map(Number) ?? []).flat();
  const span = years.length ? `${Math.min(...years)} to ${Math.max(...years)}` : NOT_VERIFIED;
  return (
    <header className="hero">
      <p className="kicker">Quant lab</p>
      <h1>
        <span className="line">{results.length} tests.</span>{" "}
        <span className={passed ? "line pass" : "line"}>{passed} passed.</span>
      </h1>
      <p className="lede">
        Five classic quant ideas, built from first principles and tested on large US stocks, {span}, after
        trading costs. To pass, an idea needs a t-score of 3 on the earlier years and must still work on two
        years held back. Most published ideas fail that bar, and this page shows the failures as well as the
        passes.
      </p>
      <ol className="ledger">
        {STUDIES.flatMap((info) =>
          results
            .filter((r) => r.study === info.key)
            .map((r) => (
              <li key={`${r.study}-${r.variant}`}>
                <a href={`#${info.key}`}>
                  {info.name} <span className="muted">{VARIANT_NAMES[r.variant] ?? r.variant}</span>
                </a>
                <Verdict text={r.verdict} />
              </li>
            )),
        )}
      </ol>
    </header>
  );
}

function DataStatus() {
  const feeds = useLoad<Feed[]>("/api/feeds");
  const coverage = useLoad<Coverage>("/api/coverage");
  return (
    <section className="study" id="data" aria-labelledby="data-title">
      <p className="study-name">Data</p>
      <h2 id="data-title">What the results stand on</h2>
      {coverage.failed && <p className="muted">{NOT_VERIFIED}: coverage didn't load.</p>}
      {coverage.data && (
        <Facts
          items={[
            ["Stocks", coverage.data.stocks.toLocaleString()],
            ["Daily price rows", coverage.data.price_rows.toLocaleString()],
            ["From", coverage.data.first_day ?? NOT_VERIFIED],
            ["To", coverage.data.last_day ?? NOT_VERIFIED],
          ]}
        />
      )}
      {feeds.failed && <p className="muted">{NOT_VERIFIED}: feed status didn't load.</p>}
      {feeds.data && (
        <div className="scroll">
          <table className="compare">
            <thead>
              <tr>
                <th scope="col">Feed</th>
                <th scope="col">Source</th>
                <th scope="col">Last run</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {feeds.data.map((f) => (
                <tr key={f.feed}>
                  <th scope="row">{f.feed}</th>
                  <td>{f.source}</td>
                  <td>{f.last_run ? new Date(f.last_run).toLocaleString("en-GB") : "Never"}</td>
                  <td className={f.status === "ok" ? "" : "warn"}>{f.status === "ok" ? "OK" : `${f.status.replaceAll("_", " ")}${f.message ? `: ${f.message}` : ""}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="note">
        Limits: the stock list is today's companies, so ones that failed are missing and every result is
        flattered. Costs (0.10% a trade, 0.5% a year to borrow) are assumptions. Prices come from Tiingo and
        cannot be republished, so this page is private. This product uses the FRED® API but is not endorsed or
        certified by the Federal Reserve Bank of St. Louis.
      </p>
    </section>
  );
}

export default function App() {
  const { data, failed } = useLoad<Result[]>("/api/quant");
  const byStudy = new Map<string, Result[]>();
  data?.forEach((r) => byStudy.set(r.study, [...(byStudy.get(r.study) ?? []), r]));
  return (
    <>
      <nav className="bar" aria-label="Sections">
        <a className="brand" href="#top">
          Quant Lab
        </a>
        <div className="links">
          {STUDIES.map((s) => (
            <a key={s.key} href={`#${s.key}`}>
              {s.name}
            </a>
          ))}
          <a href="#data">Data</a>
        </div>
      </nav>
      <main id="top">
        {failed && <p className="error">{NOT_VERIFIED}: the results didn't load. Check that the API is running.</p>}
        {!data && !failed && <p className="muted loading">Loading results…</p>}
        {data && data.length === 0 && <p className="muted">No study has run yet. Results appear after the weekly run.</p>}
        {data && data.length > 0 && <Ledger results={data} />}
        {data && STUDIES.map((info) => <Study key={info.key} info={info} rows={byStudy.get(info.key)} />)}
        <DataStatus />
      </main>
    </>
  );
}

