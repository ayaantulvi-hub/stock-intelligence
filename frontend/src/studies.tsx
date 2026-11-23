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


/** The one statistic that decided each variant's verdict, as a label and value. */
export function decidingStat(r: Result): [string, string] {
  if (r.study === "value_at_risk") return ["Christoffersen p", fixed(r.metrics.christoffersen_p, 3)];
  if (r.study === "panic_detector") {
    const choice = r.metrics.choice as Record<string, number> | undefined;
    return ["t, choice years", fixed(choice?.t)];
  }
  return [r.study === "vol_targeting" ? "alpha t, choice years" : "t, choice years", fixed(r.metrics.choice_t)];
}
