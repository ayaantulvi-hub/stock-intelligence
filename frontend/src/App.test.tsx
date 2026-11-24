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

describe("Quant Lab terminal", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.location.hash = "";
  });

  const open = async (hash = "") => {
    window.location.hash = hash;
    mockApi();
    render(<App />);
    return screen.findAllByRole("heading", { level: 1 });
  };

  it("counts tests and passes from the stored verdicts", async () => {
    const [heading] = await open();
    expect(heading.textContent).toBe("What held up.");
    expect(document.querySelector(".hero .lede")?.textContent).toContain("1 of 2 tests cleared a bar set before testing");
    expect(document.querySelectorAll(".held-up li")).toHaveLength(1);
    expect(document.querySelector(".hero .meta")?.textContent).toBe("2010–2026");
    expect(screen.getAllByText("Not rejected").length).toBeGreaterThan(0);
  });

  it("marks studies that haven't run instead of inventing results", async () => {
    await open();
    const notRun = [...document.querySelectorAll(".side a")].filter((a) => a.querySelector('[aria-label="not run"]'));
    expect(notRun.map((a) => a.getAttribute("href"))).toEqual(["#pairs_trading", "#vol_targeting", "#market_century", "#momentum", "#low_volatility", "#factor_momentum", "#panic_detector"]);
    cleanup();
    await open("#pairs_trading");
    expect(screen.getByText(/this study hasn't run yet/)).toBeTruthy();
  });

  it("shows the real repository code, not a rewrite", async () => {
    await open("#ma_crossover");
    const panel = document.querySelector("figure.code");
    expect(panel?.textContent).toContain("def ma_crossover");
    expect(panel?.querySelector("a")?.getAttribute("href")).toContain("backend/src/stockintel/quant/studies.py");
  });

  it("builds the findings from verdicts", async () => {
    await open();
    const marks = [...document.querySelectorAll(".findings li .mark")].map((m) => m.getAttribute("aria-label"));
    expect(marks).toEqual(["passed", "not run", "not run", "not run", "failed", "not run", "not run", "not run", "not run"]);
    expect(document.querySelector(".findings")?.textContent).toContain("didn't beat holding everything");
  });

  it("switches the explanation between plain English and quant detail", async () => {
    await open("#value_at_risk");
    const box = () => document.querySelector(".explain .body");
    expect(box()?.textContent).toContain("how much could we lose");
    screen.getByRole("radio", { name: "Quant detail" }).click();
    await screen.findByText(/Christoffersen independence/);
    expect(box()?.querySelector("table")?.textContent).toContain("0.063");
  });

  it("says Not verified when the results fail to load", async () => {
    mockApi({ "/api/quant": new Response("", { status: 500 }) });
    render(<App />);
    expect(await screen.findByText(/Not verified: the results didn't load/)).toBeTruthy();
  });
});
