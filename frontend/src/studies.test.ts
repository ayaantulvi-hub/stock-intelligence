import { describe, expect, it } from "vitest";
import type { Result } from "./api";
import { protection } from "./studies";

// TEST FIXTURE: a strategy that always moves exactly half as much as the market.
function halfTheMarket(): Result {
  const baselineMonths = Array.from({ length: 60 }, (_, i) => ((i * 37) % 11) / 100 - 0.05);
  const grow = (rets: number[]) => rets.reduce((acc, r) => [...acc, acc[acc.length - 1] * (1 + r)], [1]);
  return {
    study: "vol_targeting",
    variant: "volatility target",
    run_at: "2026-11-23T00:00:00Z",
    period: "2010-01-01 to 2014-12-31",
    verdict: "No reliable edge",
    metrics: {
      strategy: { max_drawdown: -0.1 },
      baseline: { max_drawdown: -0.2 },
      series: { months: [], strategy: grow(baselineMonths.map((r) => r / 2)), baseline: grow(baselineMonths) },
    },
    settings: {},
  } as unknown as Result;
}

describe("crash protection", () => {
  it("measures the share of the fall and of the gain from the stored monthly series", () => {
    const [row] = protection([halfTheMarket()]);
    expect(row.downShare).toBeCloseTo(0.5, 9);
    expect(row.upShare).toBeCloseTo(0.5, 9);
    expect([row.worstFall, row.baselineFall]).toEqual([-0.1, -0.2]);
  });

  it("leaves studies without a growth series out of the measure instead of guessing", () => {
    const r = halfTheMarket();
    r.metrics.series = undefined;
    expect(protection([r])[0].downShare).toBeNull();
  });
});
