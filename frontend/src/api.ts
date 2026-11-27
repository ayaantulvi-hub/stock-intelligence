/** Types and loading for the API. Nothing here invents a value: missing data stays null. */

export type Summary = {
  days: number;
  start: string | null;
  end: string | null;
  annual_return: number | null;
  annual_volatility: number | null;
  sharpe: number | null;
  sharpe_se: number | null;
  max_drawdown: number | null;
  sortino?: number | null;
  calmar?: number | null;
};

export type Growth = { months: string[]; strategy: number[]; baseline: number[] };
export type Breaches = { months: string[]; breaches: number[]; average_var: number[] };
export type Panic = {
  months: string[];
  average_correlation: (number | null)[];
  absorption_ratio: (number | null)[];
  warning_share: (number | null)[];
  market: number[];
};

export type Result = {
  study: string;
  variant: string;
  run_at: string;
  period: string;
  verdict: string;
  metrics: Record<string, unknown> & { series?: unknown };
  settings: Record<string, unknown>;
};

export type Feed = {
  feed: string;
  source: string;
  status: string;
  message: string | null;
  last_run: string | null;
  records_added: number | null;
  last_ok: string | null;
};

export type Coverage = {
  stocks: number;
  with_industry?: number;
  price_rows: number;
  first_day: string | null;
  last_day: string | null;
};

export async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

export const PASSING = new Set(["Edge", "Not rejected"]);
