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
    key: "market_century",
    code: "100Y",
    title: "100 years of the market",
    tagline: "Same rules, a hundred years of data. Does a small edge finally show?",
    tags: ["Data · US market since 1926", "Test · alpha, Newey-West"],
    sources: [
      ["Kenneth R. French Data Library", "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"],
      ["Moreira & Muir (2017)", "https://www.nber.org/papers/w22208"],
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
    key: "momentum",
    code: "MOM",
    title: "Momentum",
    tagline: "Buy last year's winners, sell last year's losers. Does the trend carry on?",
    tags: ["Rank · return months t-12 to t-2", "Test · walk-forward, after costs"],
    sources: [
      ["Fama-French momentum factor definition", "https://mba.tuck.dartmouth.edu/pages/faculty/Ken.French/Data_Library/det_mom_factor.html"],
      ["McLean & Pontiff (2016)", "https://rpc.cfainstitute.org/research/cfa-digest/2016/06/does-academic-research-destroy-stock-return-predictability-digest-summary"],
    ],
  },
  {
    key: "low_volatility",
    code: "LOWV",
    title: "Low volatility",
    tagline: "The calmest stocks: less risk, but do they give up any return?",
    tags: ["Rank · 3 years of weekly volatility", "Test · alpha, Newey-West"],
    sources: [["Blitz & van Vliet (2007)", "https://core.ac.uk/download/18510017.pdf"]],
  },
  {
    key: "factor_momentum",
    code: "FMOM",
    title: "Factor momentum",
    tagline: "Back the investing styles that worked last year, bet against the ones that didn't.",
    tags: ["Data · 11 factors, US and developed markets", "Test · walk-forward, after costs"],
    sources: [
      ["Ehsani & Linnainmaa (2022)", "https://www.nber.org/papers/w25551"],
      ["Kenneth R. French Data Library", "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html"],
    ],
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
  "trend 50/200": "Trend 50/200",
  "12-1 long-short": "Momentum 12-1",
  "calmest 10%": "Calmest 10%",
  "time-series, 11 factors": "Time-series, 11 factors",
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
const moneyLong = (v: number) => (v >= 100 ? `$${Math.round(v).toLocaleString("en-GB")}` : `$${v.toFixed(2)}`);
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
  if (key === "market_century") {
    const versions = [...VOL_VARIANTS, "trend 50/200"].map((v) => find(rows, v)).filter(Boolean) as Result[];
    const targeting = versions.filter((r) => r.variant !== "trend 50/200");
    const bestT = [...targeting].sort((x, y) => ((y.metrics.choice_t as number) ?? -Infinity) - ((x.metrics.choice_t as number) ?? -Infinity))[0];
    const cut = (r: Result) => {
      const a = strategy(r)?.max_drawdown;
      const c = baseline(r)?.max_drawdown;
      return typeof a === "number" && typeof c === "number" ? a - c : -Infinity;
    };
    const shallowest = [...versions].sort((x, y) => cut(y) - cut(x))[0];
    const holdoutPositive = versions.filter((r) => typeof r.metrics.holdout_gain_daily === "number" && (r.metrics.holdout_gain_daily as number) > 0);
    return {
      tiles: [
        {
          value: `t = ${fixed(bestT?.metrics.choice_t)}`,
          label: `strongest alpha evidence: ${bestT ? NAMES[bestT.variant] : NOT_VERIFIED} (needs 3)`,
          tone: "amber",
        },
        {
          value: `${pct(strategy(shallowest)?.max_drawdown)} vs ${pct(baseline(shallowest)?.max_drawdown)}`,
          label: `worst fall, biggest cut: ${shallowest ? NAMES[shallowest.variant] : NOT_VERIFIED} vs holding`,
          tone: shallower(shallowest) ? "green" : "red",
        },
        {
          value: `${holdoutPositive.length} of ${versions.length}`,
          label: "versions positive on the two held-back years",
          tone: holdoutPositive.length ? "blue" : "red",
        },
      ],
      chart: versions.length ? <VolChart rows={versions} log /> : null,
      caption: `US market excess return, daily · ${versions[0]?.period ?? NOT_VERIFIED} · log scale`,
      finding: anyPass(rows)
        ? "With a century of data, a version passed."
        : "Evidence grew with more data, but nothing reached the bar.",
      note: `best alpha t = ${fixed(bestT?.metrics.choice_t)}`,
    };
  }
  if (key === "momentum") {
    const r = rows[0];
    const g = r?.metrics.series as Growth | undefined;
    return {
      tiles: [
        { value: `${fixed(strategy(r)?.sharpe)} ± ${fixed(strategy(r)?.sharpe_se)}`, label: "Sharpe ratio, after costs", tone: "blue" },
        { value: `${pct(r?.metrics.gross_annual_return)} → ${pct(averageNet(r))}`, label: "average a year, before → after costs", tone: "orange" },
        { value: pct(strategy(r)?.max_drawdown), label: "worst fall", tone: "red" },
      ],
      chart: g ? <LineChart title="Growth of $1 committed, after costs" months={g.months} series={[{ name: "Momentum", values: g.strategy, role: "s1" }]} format={money} baseline={1} /> : null,
      caption: `top 30% minus bottom 30% · equal weight · monthly · ${r?.period ?? NOT_VERIFIED}`,
      finding: anyPass(rows) ? "Winners kept winning, after costs." : "Winners didn't reliably keep winning after costs.",
      note: `t = ${fixed(r?.metrics.choice_t)} · needs 3`,
    };
  }
  if (key === "low_volatility") {
    const r = rows[0];
    const g = r?.metrics.series as Growth | undefined;
    return {
      tiles: [
        { value: `${fixed(strategy(r)?.sharpe)} vs ${fixed(baseline(r)?.sharpe)}`, label: "Sharpe ratio, calmest 10% vs all stocks", tone: "blue" },
        {
          value: `${pct(strategy(r)?.max_drawdown)} vs ${pct(baseline(r)?.max_drawdown)}`,
          label: "worst fall, calmest 10% vs all stocks",
          tone: shallower(r) ? "green" : "red",
        },
        { value: `t = ${fixed(r?.metrics.choice_t)}`, label: "alpha test score (needs 3)", tone: "amber" },
      ],
      chart: g ? (
        <LineChart
          title="Growth of $1 above the Fed funds rate, after costs"
          months={g.months}
          series={[
            { name: "Calmest 10%", values: g.strategy, role: "s1" },
            { name: "All stocks", values: g.baseline, role: "s2" },
          ]}
          format={money}
          baseline={1}
        />
      ) : null,
      caption: `calmest 10% by 156 weekly returns · equal weight · monthly · ${r?.period ?? NOT_VERIFIED}`,
      finding: anyPass(rows)
        ? "Calm stocks earned more for their risk."
        : shallower(r)
          ? "Smaller falls, but no extra return for the risk."
          : "No extra return for the risk.",
      note: `alpha t = ${fixed(r?.metrics.choice_t)}`,
    };
  }
  if (key === "factor_momentum") {
    const r = rows[0];
    const g = r?.metrics.series as Growth | undefined;
    const paper = r?.metrics.paper_period as Record<string, number> | undefined;
    const after = r?.metrics.after_publication as Record<string, number> | undefined;
    return {
      tiles: [
        { value: `t = ${fixed(r?.metrics.choice_t)}`, label: "test score on the choice years (needs 3)", tone: anyPass(rows) ? "green" : "amber" },
        { value: `${fixed(paper?.sharpe)} (t = ${fixed(paper?.t)})`, label: "Sharpe ratio over the paper's own years, from 1964", tone: "blue" },
        { value: `${fixed(after?.sharpe)} (t = ${fixed(after?.t)})`, label: "Sharpe ratio after the paper's data ends, 2016 on", tone: "orange" },
      ],
      chart: g ? (
        <LineChart
          title="Growth of $1 committed, after costs"
          months={g.months}
          series={[{ name: "Factor momentum", values: g.strategy, role: "s1" }]}
          format={(v) => (v >= 100 ? `$${Math.round(v).toLocaleString("en-GB")}` : `$${v.toFixed(2)}`)}
          baseline={1}
          log
        />
      ) : null,
      caption: `long factors up over the past year, short those down · equal weight · monthly · ${r?.period ?? NOT_VERIFIED} · log scale`,
      finding: anyPass(rows) ? "It passed, and stayed positive after publication." : "It didn't clear the bar.",
      note: `t = ${fixed(r?.metrics.choice_t)} · 1964 on t = ${fixed(paper?.t)}`,
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
  const byAlpha =
    r.study === "vol_targeting" || r.study === "low_volatility" || (r.study === "market_century" && r.variant !== "trend 50/200");
  return [byAlpha ? "alpha t, choice years" : "t, choice years", fixed(r.metrics.choice_t)];
}

/** Growth of $1 for one managed version, picked with a switch, against the unmanaged market:
 * two lines at a time stay readable however many versions there are. */
function VolChart({ rows, log = false }: { rows: Result[]; log?: boolean }) {
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
          title={log ? "Growth of $1 above Treasury bills, after costs" : "Growth of $1 above the Fed funds rate, after costs"}
          months={g.months}
          series={[
            { name: NAMES[chosen.variant] ?? chosen.variant, values: g.strategy, role: "s1" },
            { name: log ? "Market" : "Unmanaged", values: g.baseline, role: "s2" },
          ]}
          format={log ? moneyLong : money}
          baseline={1}
          log={log}
        />
      ) : (
        <p className="muted">{NOT_VERIFIED}: no stored series for this version.</p>
      )}
    </>
  );
}

/** Crash protection, measured from stored monthly growth series: in the baseline's worst 10%
 * of months, the strategy's average return as a share of the baseline's (its share of the
 * fall), and the same for the best 10% (its share of the gain). Descriptive only: it was added
 * after the results were seen, so it is never part of the pass count. */
export type Protection = {
  study: string;
  label: string;
  period: string;
  worstFall: number | null;
  baselineFall: number | null;
  downShare: number | null;
  upShare: number | null;
};

export const PROTECTION_STUDIES = ["ma_crossover", "vol_targeting", "low_volatility", "market_century"];

function monthly(growth: number[]): number[] {
  return growth.slice(1).map((v, i) => v / growth[i] - 1);
}

function share(strategyMonths: number[], baselineMonths: number[], worst: boolean): number | null {
  const order = baselineMonths.map((v, i) => [v, i]).sort((a, b) => (worst ? a[0] - b[0] : b[0] - a[0]));
  const picked = order.slice(0, Math.max(1, Math.round(order.length * 0.1))).map(([, i]) => i);
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  const b = mean(picked.map((i) => baselineMonths[i]));
  return b === 0 ? null : mean(picked.map((i) => strategyMonths[i])) / b;
}

export function protection(rows: Result[]): Protection[] {
  return rows
    .filter((r) => PROTECTION_STUDIES.includes(r.study))
    .map((r) => {
      const g = r.metrics.series as Growth | undefined;
      const ok = g && g.strategy.length > 24 && g.baseline.length === g.strategy.length;
      const sm = ok ? monthly(g.strategy) : [];
      const bm = ok ? monthly(g.baseline) : [];
      return {
        study: r.study,
        label: NAMES[r.variant] ?? r.variant,
        period: r.period,
        worstFall: strategy(r)?.max_drawdown ?? null,
        baselineFall: baseline(r)?.max_drawdown ?? null,
        downShare: ok ? share(sm, bm, true) : null,
        upShare: ok ? share(sm, bm, false) : null,
      };
    });
}
