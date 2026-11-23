import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

// TEST FIXTURES: stored-result shapes with invented figures, not real results.
const growth = { months: ["2024-01", "2024-02", "2024-03"], strategy: [1, 1.02, 1.01], baseline: [1, 1.01, 1.03] };
const results = [
  {
    study: "ma_crossover",
    variant: "50/200",
    run_at: "2026-11-23T10:00:00Z",
    period: "2010-04-01 to 2026-11-20",
    verdict: "No reliable edge",
    metrics: {
      choice_t: -3.5,
      strategy: { sharpe: 0.9, sharpe_se: 0.25, max_drawdown: -0.29, annual_return: 0.1 },
      baseline: { sharpe: 1.02, max_drawdown: -0.39 },
      series: growth,
    },
    settings: { fast: 50, slow: 200 },
  },
  {
    study: "value_at_risk",
    variant: "ewma",
    run_at: "2026-11-23T10:00:00Z",
    period: "2012-03-27 to 2026-11-20",
    verdict: "Not rejected",
    metrics: {
      breach_rate: 0.054,
      breach_rate_after_a_breach: 0.085,
      kupiec_p: 0.24,
      christoffersen_p: 0.063,
      series: { months: ["2024-01", "2024-02"], breaches: [1, 0], average_var: [0.015, 0.016] },
    },
    settings: { level: 0.95 },
  },
];

function mockApi(overrides: Record<string, Response> = {}) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (overrides[url]) return overrides[url];
    if (url === "/api/quant") return new Response(JSON.stringify(results));
    if (url === "/api/feeds") return new Response(JSON.stringify([]));
    if (url === "/api/coverage")
      return new Response(JSON.stringify({ stocks: 480, price_rows: 100, first_day: "2010-01-04", last_day: "2026-11-20" }));
    return new Response("", { status: 404 });
  });
}

describe("Quant Lab page", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("counts tests and passes from the stored verdicts", async () => {
    mockApi();
    render(<App />);
    const heading = await screen.findByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("2 tests. 1 passed.");
    expect(screen.getAllByText("Not rejected").length).toBeGreaterThan(0);
    expect(screen.getByText(/2010 to 2026/)).toBeTruthy();
  });

  it("marks studies that haven't run instead of inventing results", async () => {
    mockApi();
    render(<App />);
    await screen.findByRole("heading", { level: 1 });
    const notRun = [...document.querySelectorAll("section.study p.muted")].filter((p) =>
      p.textContent?.includes("hasn't run yet"),
    );
    expect(notRun.map((p) => p.closest("section")?.id)).toEqual(["pairs_trading", "vol_targeting", "panic_detector"]);
  });

  it("says Not verified when the results fail to load", async () => {
    mockApi({ "/api/quant": new Response("", { status: 500 }) });
    render(<App />);
    expect(await screen.findByText(/Not verified: the results didn't load/)).toBeTruthy();
  });
});
