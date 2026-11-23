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
import Code from "./Code";
import { explain, type Mode } from "./explain";
import { fixed, monthLabel, NOT_VERIFIED, pct } from "./format";
import snippets from "./snippets.json";

type Source = [string, string];
type Tone = "blue" | "orange" | "amber" | "green" | "red" | "plain";
type Tile = { value: string; label: string; tone: Tone };
type View = { tiles: Tile[]; chart: ReactNode; caption: string; finding: string; note: string };

type StudyInfo = {
  key: string;
  title: string;
  tagline: string;
  tags: [string, string];
  sources: Source[];
};

const STUDIES: StudyInfo[] = [
  {
    key: "value_at_risk",
    title: "Value at Risk",
    tagline: "Counting bad days isn't enough. When they happen matters too.",
    tags: ["Monte Carlo · 10,000 paths", "Tests · Kupiec + Christoffersen"],
    sources: [
      ["Kupiec (1995), Christoffersen (1998)", "https://it.mathworks.com/help/risk/overview-of-var-backtesting.html"],
      ["RiskMetrics decay 0.94", "https://metricgate.com/docs/ewma-volatility-riskmetrics/"],
    ],
  },
  {
    key: "pairs_trading",
    title: "Pairs trading",
    tagline: "Find two stocks that move together, and bet on the gap closing.",
    tags: ["Stats · cointegration", "Test · walk-forward, after costs"],
    sources: [
      ["Gatev, Goetzmann & Rouwenhorst (2006)", "https://econpapers.repec.org/RePEc:oup:rfinst:v:19:y:2006:i:3:p:797-827"],
      ["Do & Faff (2010)", "https://ideas.repec.org/a/taf/ufajxx/v66y2010i4p83-95.html"],
    ],
  },
  {
    key: "vol_targeting",
    title: "Volatility targeting",
    tagline: "Hold less when markets are jumpy. Does the risk-adjusted return improve?",
    tags: ["Stats · realised variance", "Test · alpha, Newey-West"],
    sources: [
      ["Moreira & Muir (2017)", "https://www.nber.org/papers/w22208"],
      [
        "DeMiguel et al. (2024)",
        "https://lbsresearch.london.edu/id/eprint/3716/1/The%20Journal%20of%20Finance%20-%202024%20-%20DeMIGUEL%20-%20A%20Multifactor%20Perspective%20on%20Volatility%E2%80%90Managed%20Portfolios.pdf",
      ],
    ],
  },
  {
    key: "ma_crossover",
    title: "Trend following",
    tagline: "Own a stock only while its 50-day average sits above its 200-day.",
    tags: ["Rule · 50/200 crossover", "Test · vs holding everything"],
    sources: [["Lo (2002), Sharpe ratio errors", "https://ideas.repec.org/a/taf/ufajxx/v58y2002i4p36-52.html"]],
  },
  {
    key: "panic_detector",
    title: "Panic detector",
    tagline: "When every stock starts moving as one, is trouble coming?",
    tags: ["Linear algebra · eigenvalues", "Test · next-month return"],
    sources: [
      [
        "Kritzman et al., absorption ratio",
        "https://www.liverpool.ac.uk/media/livacuk/schoolofmanagement/research/economics/Application,Absorption,Ratio.pdf",
      ],
    ],
  },
];

const NAMES: Record<string, string> = {
  historical: "Historical",
  normal: "Normal",
  ewma: "EWMA",
  distance: "Distance",
  cointegration: "Cointegration",
  "50/200": "Crossover",
  "variance-managed (Moreira-Muir)": "Variance-managed",
  "volatility target": "Volatility target",
  "absorption ratio shift": "Absorption ratio",
};

const money = (v: number) => `$${v.toFixed(2)}`;
const strategy = (r?: Result) => r?.metrics.strategy as Summary | undefined;
const baseline = (r?: Result) => r?.metrics.baseline as Summary | undefined;
const find = (rows: Result[], variant: string) => rows.find((r) => r.variant === variant);
const anyPass = (rows: Result[]) => rows.some((r) => PASSING.has(r.verdict));
/** True when the strategy's worst fall was smaller than the baseline's. */
const shallower = (r?: Result) => {
  const a = strategy(r)?.max_drawdown;
  const c = baseline(r)?.max_drawdown;
  return typeof a === "number" && typeof c === "number" && a > c;
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

/** Each study's tiles, chart, caption and one-line finding, all computed from stored results.
 * Wording that depends on a result is chosen from the verdict, never typed in as a result. */
function view(key: string, rows: Result[]): View | null {
  if (key === "value_at_risk") {
    const order = ["historical", "normal", "ewma"].map((v) => find(rows, v)).filter(Boolean) as Result[];
    const ewma = find(rows, "ewma");
    const hist = find(rows, "historical");
    const series = order.map((r) => r.metrics.series as Breaches | undefined);
    const max = Math.max(1, ...series.flatMap((s) => s?.breaches ?? []));
    const passed = order.filter((r) => PASSING.has(r.verdict)).map((r) => NAMES[r.variant]);
    const failed = order.filter((r) => !PASSING.has(r.verdict)).map((r) => NAMES[r.variant]);
    return {
      tiles: [
        { value: pct(ewma?.metrics.breach_rate), label: "EWMA breach rate, target 5%", tone: "blue" },
        {
          value: `${pct(hist?.metrics.breach_rate_after_a_breach, 0)} vs ${pct(ewma?.metrics.breach_rate_after_a_breach, 0)}`,
          label: "chance of a breach the day after one, historical vs EWMA",
          tone: "orange",
        },
        { value: `p = ${fixed(ewma?.metrics.christoffersen_p, 3)}`, label: "EWMA bunching test, passes above 0.05", tone: "amber" },
      ],
      chart: (
        <>
          {order.map((r, k) =>
            series[k] ? (
              <BarStrip key={r.variant} title={`${NAMES[r.variant]}: ${r.verdict}`} months={series[k]!.months} values={series[k]!.breaches} max={max} />
            ) : null,
          )}
          {series[0] && (
            <TableView
              caption="Breaches per month"
              months={series[0].months}
              series={order.map((r, k) => ({ name: NAMES[r.variant], values: series[k]?.breaches ?? [], role: "s1" as const }))}
              format={(v) => String(v)}
            />
          )}
        </>
      ),
      caption: `breaches of the 95% one-day VaR per month · equal-weight portfolio · ${ewma?.period ?? NOT_VERIFIED}`,
      finding:
        passed.length && failed.length
          ? `${passed.join(" and ")} passed. ${failed.join(" and ")} failed the timing test.`
          : passed.length
            ? "Every model passed both tests."
            : "Every model was rejected.",
      note: `EWMA ${pct(ewma?.metrics.breach_rate)} · p = ${fixed(ewma?.metrics.christoffersen_p, 3)}`,
    };
  }
  if (key === "pairs_trading") {
    const coint = find(rows, "cointegration");
    const dist = find(rows, "distance");
    const cg = coint?.metrics.series as Growth | undefined;
    const dg = dist?.metrics.series as Growth | undefined;
    const lines = [
      ...(cg ? [{ name: "Cointegration", values: cg.strategy, role: "s1" as const }] : []),
      ...(dg ? [{ name: "Distance", values: dg.strategy, role: "s2" as const }] : []),
    ];
    return {
      tiles: [
        { value: `${fixed(strategy(coint)?.sharpe)} ± ${fixed(strategy(coint)?.sharpe_se)}`, label: "cointegration Sharpe ratio, after costs", tone: "blue" },
        {
          value: `${pct(coint?.metrics.gross_annual_return)} → ${pct(strategy(coint)?.annual_return)}`,
          label: "a year, before → after costs",
          tone: "orange",
        },
        { value: pct(strategy(coint)?.max_drawdown), label: "worst fall, for a bet meant to be market-neutral", tone: "red" },
      ],
      chart: lines.length ? <LineChart title="Growth of $1 after costs" months={(cg ?? dg)!.months} series={lines} format={money} baseline={1} /> : null,
      caption: `${String(coint?.metrics.trades ?? NOT_VERIFIED)} trades · top 20 pairs a window · same industry · ${coint?.period ?? NOT_VERIFIED}`,
      finding: anyPass(rows) ? "A method cleared the bar after costs." : "Neither method cleared the bar after costs.",
      note: `cointegration t = ${fixed(coint?.metrics.choice_t)} · needs 3`,
    };
  }
  if (key === "vol_targeting") {
    const managed = find(rows, "variance-managed (Moreira-Muir)");
    const target = find(rows, "volatility target");
    const mg = managed?.metrics.series as Growth | undefined;
    const tg = target?.metrics.series as Growth | undefined;
    return {
      tiles: [
        { value: `${fixed(strategy(managed)?.sharpe)} vs ${fixed(baseline(managed)?.sharpe)}`, label: "Sharpe ratio, managed vs unmanaged", tone: "blue" },
        {
          value: `${pct(strategy(managed)?.max_drawdown)} vs ${pct(baseline(managed)?.max_drawdown)}`,
          label: "worst fall, managed vs unmanaged",
          tone: shallower(managed) ? "green" : "red",
        },
        { value: `t = ${fixed(managed?.metrics.choice_t)}`, label: "alpha test score, needs 3", tone: "amber" },
      ],
      chart: mg ? (
        <LineChart
          title="Growth of $1 above the Fed funds rate, after costs"
          months={mg.months}
          series={[
            { name: "Variance-managed", values: mg.strategy, role: "s1" },
            ...(tg ? [{ name: "Volatility target", values: tg.strategy, role: "s3" as const }] : []),
            { name: "Unmanaged", values: mg.baseline, role: "s2" },
          ]}
          format={money}
          baseline={1}
        />
      ) : null,
      caption: `monthly rebalance on last month's risk · capped at 2× · ${managed?.period ?? NOT_VERIFIED}`,
      finding: anyPass(rows)
        ? "It added risk-adjusted return."
        : shallower(managed)
          ? "No extra return, but smaller crashes."
          : "No extra return, and no smaller crashes.",
      note: `worst fall ${pct(strategy(managed)?.max_drawdown)} vs ${pct(baseline(managed)?.max_drawdown)}`,
    };
  }
  if (key === "ma_crossover") {
    const r = rows[0];
    const g = r?.metrics.series as Growth | undefined;
    return {
      tiles: [
        { value: `${fixed(strategy(r)?.sharpe)} vs ${fixed(baseline(r)?.sharpe)}`, label: "Sharpe ratio, crossover vs holding everything", tone: "blue" },
        {
          value: `${pct(strategy(r)?.max_drawdown)} vs ${pct(baseline(r)?.max_drawdown)}`,
          label: "worst fall, crossover vs holding everything",
          tone: shallower(r) ? "green" : "red",
        },
        { value: `t = ${fixed(r?.metrics.choice_t)}`, label: "gain over holding, needs +3", tone: "amber" },
      ],
      chart: g ? (
        <LineChart
          title="Growth of $1 after costs"
          months={g.months}
          series={[
            { name: "Crossover", values: g.strategy, role: "s1" },
            { name: "Hold all", values: g.baseline, role: "s2" },
          ]}
          format={money}
          baseline={1}
        />
      ) : null,
      caption: `equal weight in stocks above their trend, cash otherwise · ${r?.period ?? NOT_VERIFIED}`,
      finding: anyPass(rows) ? "It beat holding everything." : "It didn't beat holding everything.",
      note: `t = ${fixed(r?.metrics.choice_t)}`,
    };
  }
  if (key === "panic_detector") {
    const r = rows[0];
    const s = r?.metrics.series as Panic | undefined;
    const choice = r?.metrics.choice as Record<string, number> | undefined;
    const peak = typeof r?.metrics.average_correlation_max_date === "string" ? r.metrics.average_correlation_max_date : null;
    return {
      tiles: [
        { value: fixed(r?.metrics.average_correlation_max), label: `highest average correlation, ${peak ?? NOT_VERIFIED}`, tone: "orange" },
        {
          value: `${pct(r?.metrics.share_of_worst_5pct_months_after_shift, 0)} vs ${pct(r?.metrics.share_of_days_with_shift, 0)}`,
          label: "worst months that had a warning vs days with a warning",
          tone: "amber",
        },
        { value: `t = ${fixed(choice?.t)}`, label: "next-month return gap after a warning, needs 3", tone: "blue" },
      ],
      chart: s ? (
        <LineChart
          title="Average correlation between stocks; shading marks warnings"
          months={s.months}
          series={[{ name: "Average correlation", values: s.average_correlation, role: "s1" }]}
          format={(v) => v.toFixed(2)}
          shade={s.warning_share}
        />
      ) : null,
      caption: `63-day windows · top fifth of eigenvectors · ${r?.period ?? NOT_VERIFIED}`,
      finding: anyPass(rows) ? "Its warnings came before falls." : "Its warnings didn't predict the next month.",
      note: `peak ${fixed(r?.metrics.average_correlation_max)}${peak ? ` · ${monthLabel(peak.slice(0, 7))}` : ""}`,
    };
  }
  return null;
}

function Verdicts({ rows }: { rows: Result[] }) {
  return (
    <ul className="verdicts">
      {rows.map((r) => {
        const pass = PASSING.has(r.verdict);
        return (
          <li key={r.variant} className={pass ? "pass" : "fail"}>
            <span aria-hidden="true">{pass ? "✓" : "✕"}</span> {NAMES[r.variant] ?? r.variant}: {r.verdict}
          </li>
        );
      })}
    </ul>
  );
}

function Project({ index, info, rows, mode }: { index: number; info: StudyInfo; rows: Result[] | undefined; mode: Mode }) {
  const content = rows ? view(info.key, rows) : null;
  const words = rows ? explain(info.key, rows) : null;
  const snippet = (snippets as Record<string, { file: string; code: string }>)[info.key];
  return (
    <section className="project" id={info.key} aria-labelledby={`${info.key}-title`}>
      <p className="eyebrow">Project {String(index + 1).padStart(2, "0")}</p>
      <h2 id={`${info.key}-title`}>{info.title}</h2>
      <p className="tagline">{info.tagline}</p>
      <div className="tags">
        <span className="tag blue">{info.tags[0]}</span>
        <span className="tag orange">{info.tags[1]}</span>
      </div>
      {!rows && <p className="muted not-run">{NOT_VERIFIED}: this study hasn't run yet.</p>}
      {rows && content && (
        <>
          <div className="panel chart-panel">{content.chart}</div>
          <div className="tiles">
            {content.tiles.map((t) => (
              <div key={t.label} className="tile">
                <strong className={`tone-${t.tone}`}>{t.value}</strong>
                <span>{t.label}</span>
              </div>
            ))}
          </div>
          <p className="caption">{content.caption}</p>
          <Verdicts rows={rows} />
          {words && (
            <div className={`explain ${mode}`} aria-live="polite">
              <p className="explain-label">{mode === "plain" ? "In plain English" : "Quant detail"}</p>
              {mode === "plain" ? words.plain : words.quant}
            </div>
          )}
        </>
      )}
      {snippet && <Code file={snippet.file} code={snippet.code} />}
      <p className="sources">
        Follows{" "}
        {info.sources.map(([label, url], i) => (
          <span key={url}>
            {i > 0 && ", "}
            <a href={url} target="_blank" rel="noreferrer">
              {label}
            </a>
          </span>
        ))}
      </p>
    </section>
  );
}

function Scorecard({ byStudy }: { byStudy: Map<string, Result[]> }) {
  return (
    <section className="scorecard" id="summary" aria-labelledby="summary-title">
      <h2 id="summary-title">What the statistics actually said.</h2>
      <ol>
        {STUDIES.map((info) => {
          const rows = byStudy.get(info.key);
          const content = rows ? view(info.key, rows) : null;
          const pass = rows ? anyPass(rows) : false;
          return (
            <li key={info.key} className={rows ? (pass ? "pass" : "fail") : "none"}>
              <span className="mark" aria-label={rows ? (pass ? "passed" : "failed") : "not run"}>
                {rows ? (pass ? "✓" : "✕") : "–"}
              </span>
              <div>
                <a className="study-link" href={`#${info.key}`}>
                  {info.title}
                </a>
                <p className="finding">{content ? content.finding : `${NOT_VERIFIED}: not run yet.`}</p>
              </div>
              <span className="side">{content?.note}</span>
            </li>
          );
        })}
      </ol>
      <p className="closing">
        Finding a pattern is easy.
        <br />
        Testing tells you which ones are real.
      </p>
    </section>
  );
}

function DataStatus() {
  const feeds = useLoad<Feed[]>("/api/feeds");
  const coverage = useLoad<Coverage>("/api/coverage");
  return (
    <section className="project data" id="data" aria-labelledby="data-title">
      <h2 id="data-title">What it stands on</h2>
      {coverage.failed && <p className="muted">{NOT_VERIFIED}: coverage didn't load.</p>}
      {coverage.data && (
        <div className="tiles">
          <div className="tile">
            <strong className="tone-plain">{coverage.data.stocks.toLocaleString("en-GB")}</strong>
            <span>stocks</span>
          </div>
          <div className="tile">
            <strong className="tone-plain">{coverage.data.price_rows.toLocaleString("en-GB")}</strong>
            <span>daily price rows</span>
          </div>
          <div className="tile">
            <strong className="tone-plain">
              {coverage.data.first_day?.slice(0, 4) ?? NOT_VERIFIED} to {coverage.data.last_day?.slice(0, 4) ?? NOT_VERIFIED}
            </strong>
            <span>years covered</span>
          </div>
        </div>
      )}
      {feeds.failed && <p className="muted">{NOT_VERIFIED}: feed status didn't load.</p>}
      {feeds.data && feeds.data.length > 0 && (
        <div className="panel scroll">
          <table>
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
                  <td className={f.status === "ok" ? "tone-green" : "tone-amber"}>
                    {f.status === "ok" ? "OK" : `${f.status.replaceAll("_", " ")}${f.message ? `: ${f.message}` : ""}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="fine">
        Every test pays 0.10% a trade and 0.5% a year to borrow shares, and needs a t-score of 3 on the earlier years plus a
        positive result on the two held-back years. The stock list is today's companies, so ones that failed are missing and
        results are flattered. Prices come from Tiingo and are not republished. This product uses the FRED® API but is not
        endorsed or certified by the Federal Reserve Bank of St. Louis.
      </p>
    </section>
  );
}

function readMode(): Mode {
  try {
    return localStorage.getItem("explain-mode") === "quant" ? "quant" : "plain";
  } catch {
    return "plain";
  }
}

function ModeSwitch({ mode, setMode }: { mode: Mode; setMode: (m: Mode) => void }) {
  return (
    <div className="switch" role="radiogroup" aria-label="Explanations">
      {(["plain", "quant"] as const).map((m) => (
        <button key={m} role="radio" aria-checked={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>
          {m === "plain" ? "Plain English" : "Quant detail"}
        </button>
      ))}
    </div>
  );
}

export default function App() {
  const { data, failed } = useLoad<Result[]>("/api/quant");
  const [mode, setModeState] = useState<Mode>(readMode);
  const setMode = (m: Mode) => {
    setModeState(m);
    try {
      localStorage.setItem("explain-mode", m);
    } catch {
      /* Remembering the choice is a convenience only. */
    }
  };
  const byStudy = new Map<string, Result[]>();
  data?.forEach((r) => byStudy.set(r.study, [...(byStudy.get(r.study) ?? []), r]));
  const passed = data?.filter((r) => PASSING.has(r.verdict)).length ?? 0;
  const years = (data ?? []).flatMap((r) => r.period.match(/\d{4}/g)?.map(Number) ?? []);
  return (
    <>
      <nav className="bar" aria-label="Sections">
        <a className="brand" href="#top">
          QUANT LAB<span className="dot">.</span>
        </a>
        <div className="links">
          {STUDIES.map((s) => (
            <a key={s.key} href={`#${s.key}`}>
              {s.title}
            </a>
          ))}
          <a href="#summary">Summary</a>
          <a href="#data">Data</a>
        </div>
        <ModeSwitch mode={mode} setMode={setMode} />
      </nav>
      <main id="top">
        {failed && <p className="error">{NOT_VERIFIED}: the results didn't load. Check that the API is running.</p>}
        {!data && !failed && <p className="muted loading">Loading results…</p>}
        {data && data.length === 0 && <p className="muted loading">No study has run yet. Results appear after the weekly run.</p>}
        {data && data.length > 0 && (
          <header className="hero">
            <h1>
              {data.length} tests.
              <br />
              {passed} passed.
            </h1>
            <p className="tagline">
              Five classic quant ideas, built from scratch and tested the hard way: after costs, on years they never saw,
              with a t-score of 3 to pass.
            </p>
            <p className="caption">
              daily prices · large US companies · {years.length ? `${Math.min(...years)} to ${Math.max(...years)}` : NOT_VERIFIED}
            </p>
          </header>
        )}
        {data && STUDIES.map((info, i) => <Project key={info.key} index={i} info={info} rows={byStudy.get(info.key)} mode={mode} />)}
        {data && data.length > 0 && <Scorecard byStudy={byStudy} />}
        <DataStatus />
      </main>
    </>
  );
}
