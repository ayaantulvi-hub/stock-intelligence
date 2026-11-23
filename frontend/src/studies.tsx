import { useEffect, useState, type ReactNode } from "react";
import {
  getJson,
  PASSING,
  type Breaches,
  type Growth,
  type Panic,
  type Result,
  type Summary,
} from "./api";
import { BarStrip, LineChart, TableView } from "./charts";
import { fixed, monthLabel, NOT_VERIFIED, pct } from "./format";

/** Study definitions and the figures each study view shows, all computed from stored results. */

export type Source = [string, string];
export type Tone = "blue" | "orange" | "amber" | "green" | "red" | "plain";
export type Tile = { value: string; label: string; tone: Tone };
export type View = { tiles: Tile[]; chart: ReactNode; caption: string; finding: string; note: string };

export type StudyInfo = {
  key: string;
  code: string;
  title: string;
  tagline: string;
  tags: [string, string];
  sources: Source[];
};

export const STUDIES: StudyInfo[] = [
  {
    key: "value_at_risk",
    code: "VAR",
    title: "Value at Risk",
    tagline: "Counting bad days isn't enough. When they happen matters too.",
    tags: ["Monte Carlo · 10,000 paths", "Tests · Kupiec + Christoffersen"],
    sources: [
      ["Kupiec (1995), Christoffersen (1998)", "https://it.mathworks.com/help/risk/overview-of-var-backtesting.html"],
      ["RiskMetrics decay 0.94", "https://metricgate.com/docs/ewma-volatility-riskmetrics/"],
      ["Hull & White (1998)", "https://ideas.repec.org/a/rsk/journ4/2161156.html"],
      ["Filtered historical simulation review (Bank of England)", "https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2015/filtered-historical-simulation-value-at-risk-models-and-their-competitors.pdf"],
    ],
  },
  {
    key: "pairs_trading",
    code: "PAIRS",
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
    code: "VOL",
    title: "Volatility targeting",
    tagline: "Hold less when markets are jumpy. Does the risk-adjusted return improve?",
    tags: ["Stats · realised variance, EWMA", "Test · alpha, Newey-West"],
    sources: [
      ["Moreira & Muir (2017)", "https://www.nber.org/papers/w22208"],
      [
        "DeMiguel et al. (2024)",
        "https://lbsresearch.london.edu/id/eprint/3716/1/The%20Journal%20of%20Finance%20-%202024%20-%20DeMIGUEL%20-%20A%20Multifactor%20Perspective%20on%20Volatility%E2%80%90Managed%20Portfolios.pdf",
      ],
      ["Bongaerts, Kang & van Dijk (2020)", "https://ideas.repec.org/a/taf/ufajxx/v76y2020i4p54-71.html"],
      ["Harvey et al. (2018)", "https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf"],
      ["Cederburg et al. (2020)", "https://www.lehigh.edu/~xuy219/research/COWY.pdf"],
    ],
  },
  {
    key: "ma_crossover",
    code: "TREND",
    title: "Trend following",
    tagline: "Own a stock only while its 50-day average sits above its 200-day.",
    tags: ["Rule · 50/200 crossover", "Test · vs holding everything"],
    sources: [["Lo (2002), Sharpe ratio errors", "https://ideas.repec.org/a/taf/ufajxx/v58y2002i4p36-52.html"]],
  },
  {
    key: "panic_detector",
    code: "PANIC",
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

export const NAMES: Record<string, string> = {
  historical: "Historical",
  normal: "Normal",
  ewma: "EWMA",
  "filtered historical": "Filtered historical",
  "gjr-garch t": "GJR-GARCH-t",
  distance: "Distance",
  cointegration: "Cointegration",
  "50/200": "Crossover",
  "variance-managed (Moreira-Muir)": "Variance-managed",
  "volatility target": "Volatility target",
  "conditional (Bongaerts et al.)": "Conditional",
  "daily EWMA (Harvey et al.)": "Daily EWMA",
  "absorption ratio shift": "Absorption ratio",
};

export const VAR_MODELS = ["historical", "normal", "ewma", "filtered historical", "gjr-garch t"];
export const VOL_VARIANTS = [
  "variance-managed (Moreira-Muir)",
  "volatility target",
  "conditional (Bongaerts et al.)",
  "daily EWMA (Harvey et al.)",
];

const money = (v: number) => `$${v.toFixed(2)}`;
const strategy = (r?: Result) => r?.metrics.strategy as Summary | undefined;
const baseline = (r?: Result) => r?.metrics.baseline as Summary | undefined;
const find = (rows: Result[], variant: string) => rows.find((r) => r.variant === variant);
/** Average yearly return after costs: the stored average before costs minus the stored average
 * cost. Both are simple averages, so this matches them exactly (unlike the compounded rate). */
export const averageNet = (r?: Result) => {
  const gross = r?.metrics.gross_annual_return;
  const drag = r?.metrics.cost_drag_annual;
  return typeof gross === "number" && typeof drag === "number" ? gross - drag : null;
};
export const anyPass = (rows: Result[]) => rows.some((r) => PASSING.has(r.verdict));
/** True when the strategy's worst fall was smaller than the baseline's. */
const shallower = (r?: Result) => {
  const a = strategy(r)?.max_drawdown;
  const c = baseline(r)?.max_drawdown;
  return typeof a === "number" && typeof c === "number" && a > c;
};

export function useLoad<T>(url: string): { data: T | null; failed: boolean } {
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
export function view(key: string, rows: Result[]): View | null {
  if (key === "value_at_risk") {
    const order = VAR_MODELS.map((v) => find(rows, v)).filter(Boolean) as Result[];
    const series = order.map((r) => r.metrics.series as Breaches | undefined);
    const max = Math.max(1, ...series.flatMap((s) => s?.breaches ?? []));
    const passed = order.filter((r) => PASSING.has(r.verdict)).map((r) => NAMES[r.variant]);
    const failed = order.filter((r) => !PASSING.has(r.verdict)).map((r) => NAMES[r.variant]);
    const byAfter = order
      .filter((r) => typeof r.metrics.breach_rate_after_a_breach === "number")
      .sort((x, y) => (x.metrics.breach_rate_after_a_breach as number) - (y.metrics.breach_rate_after_a_breach as number));
    const calmest = byAfter[0];
    const worst = byAfter[byAfter.length - 1];
    const joint = order
      .filter((r) => typeof r.metrics.conditional_coverage_p === "number")
      .sort((x, y) => (y.metrics.conditional_coverage_p as number) - (x.metrics.conditional_coverage_p as number))[0];
    return {
      tiles: [
        { value: `${passed.length} of ${order.length}`, label: "models passed both tests", tone: passed.length ? "green" : "red" },
        {
          value: `${pct(worst?.metrics.breach_rate_after_a_breach, 0)} vs ${pct(calmest?.metrics.breach_rate_after_a_breach, 0)}`,
          label: `breach the day after a breach: ${worst ? NAMES[worst.variant] : NOT_VERIFIED} vs ${calmest ? NAMES[calmest.variant] : NOT_VERIFIED} (5% if independent)`,
          tone: "orange",
        },
        {
          value: `p = ${fixed(joint?.metrics.conditional_coverage_p, 3)}`,
          label: `best joint-test score: ${joint ? NAMES[joint.variant] : NOT_VERIFIED} (passes above 0.05)`,
          tone: "amber",
        },
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
      caption: `breaches of the 95% one-day VaR per month · equal-weight portfolio · ${order[0]?.period ?? NOT_VERIFIED}`,
      finding:
        passed.length && failed.length
          ? `${passed.join(", ")} passed; ${failed.join(", ")} rejected.`
          : passed.length
            ? "Every model passed both tests."
            : "Every model was rejected.",
      note: `${passed.length} of ${order.length} passed`,
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
          value: `${pct(coint?.metrics.gross_annual_return)} → ${pct(averageNet(coint))}`,
          label: "average a year, before → after costs",
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
    const managed = VOL_VARIANTS.map((v) => find(rows, v)).filter(Boolean) as Result[];
    const first = managed[0];
    // Versions start on different dates, so each is ranked by its gain over holding the market
    // during its own years, never by its raw level.
    const gain = (r: Result, key: "sharpe" | "max_drawdown") => {
      const a = strategy(r)?.[key];
      const c = baseline(r)?.[key];
      return typeof a === "number" && typeof c === "number" ? a - c : -Infinity;
    };
    const bestSharpe = [...managed].sort((x, y) => gain(y, "sharpe") - gain(x, "sharpe"))[0];
    const shallowest = [...managed].sort((x, y) => gain(y, "max_drawdown") - gain(x, "max_drawdown"))[0];
    const bestT = [...managed].sort((x, y) => ((y.metrics.choice_t as number) ?? -Infinity) - ((x.metrics.choice_t as number) ?? -Infinity))[0];
    return {
      tiles: [
        {
          value: `${fixed(strategy(bestSharpe)?.sharpe)} vs ${fixed(baseline(bestSharpe)?.sharpe)}`,
          label: `Sharpe ratio, biggest gain: ${bestSharpe ? NAMES[bestSharpe.variant] : NOT_VERIFIED} vs holding, same years`,
          tone: "blue",
        },
        {
          value: `${pct(strategy(shallowest)?.max_drawdown)} vs ${pct(baseline(shallowest)?.max_drawdown)}`,
          label: `worst fall, biggest cut: ${shallowest ? NAMES[shallowest.variant] : NOT_VERIFIED} vs holding, same years`,
          tone: shallower(shallowest) ? "green" : "red",
        },
        {
          value: `t = ${fixed(bestT?.metrics.choice_t)}`,
          label: `best alpha test score: ${bestT ? NAMES[bestT.variant] : NOT_VERIFIED} (needs 3)`,
          tone: "amber",
        },
      ],
      chart: managed.length ? <VolChart rows={managed} /> : null,
      caption: `capped at 2× · costs on every change · ${first?.period ?? NOT_VERIFIED}`,
      finding: anyPass(rows)
        ? "A version added risk-adjusted return."
        : shallower(shallowest)
          ? "No extra return, but smaller crashes."
          : "No extra return, and no smaller crashes.",
      note: `best alpha t = ${fixed(bestT?.metrics.choice_t)}`,
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


/** The one statistic that decided each variant's verdict, as a label and value. */
export function decidingStat(r: Result): [string, string] {
  if (r.study === "value_at_risk") return ["Christoffersen p", fixed(r.metrics.christoffersen_p, 3)];
  if (r.study === "panic_detector") {
    const choice = r.metrics.choice as Record<string, number> | undefined;
    return ["t, choice years", fixed(choice?.t)];
  }
  return [r.study === "vol_targeting" ? "alpha t, choice years" : "t, choice years", fixed(r.metrics.choice_t)];
}

/** Growth of $1 for one managed version, picked with a switch, against the unmanaged market:
 * two lines at a time stay readable however many versions there are. */
function VolChart({ rows }: { rows: Result[] }) {
  const [pick, setPick] = useState(rows[0].variant);
  const chosen = rows.find((r) => r.variant === pick) ?? rows[0];
  const g = chosen.metrics.series as Growth | undefined;
  return (
    <>
      <div className="variant-switch" role="radiogroup" aria-label="Version shown">
        {rows.map((r) => (
          <button key={r.variant} role="radio" aria-checked={r.variant === chosen.variant} className={r.variant === chosen.variant ? "on" : ""} onClick={() => setPick(r.variant)}>
            {NAMES[r.variant] ?? r.variant}
          </button>
        ))}
      </div>
      {g ? (
        <LineChart
          key={chosen.variant}
          title="Growth of $1 above the Fed funds rate, after costs"
          months={g.months}
          series={[
            { name: NAMES[chosen.variant] ?? chosen.variant, values: g.strategy, role: "s1" },
            { name: "Unmanaged", values: g.baseline, role: "s2" },
          ]}
          format={money}
          baseline={1}
        />
      ) : (
        <p className="muted">{NOT_VERIFIED}: no stored series for this version.</p>
      )}
    </>
  );
}
