import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import QuantLab from "./QuantLab";

// TEST FIXTURE: one stored result per kind of study, not real figures.
const rows = [
  {
    study: "pairs_trading",
    variant: "distance",
    run_at: "2026-11-23T10:00:00Z",
    period: "2011-03-31 to 2026-11-20",
    verdict: "No reliable edge",
    metrics: { choice_t: -0.69, strategy: { sharpe: -0.11, sharpe_se: 0.25, max_drawdown: -0.22, annual_return: -0.01 }, baseline: { sharpe: null, max_drawdown: 0 } },
    settings: {},
  },
  {
    study: "value_at_risk",
    variant: "ewma",
    run_at: "2026-11-23T10:00:00Z",
    period: "2012-03-27 to 2026-11-20",
    verdict: "Not rejected",
    metrics: { breaches: 200, days: 3686, breach_rate: 0.0543, kupiec_p: 0.24, christoffersen_p: 0.063 },
    settings: {},
  },
];

describe("QuantLab", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows each study's verdict and marks studies that haven't run", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(rows)));
    render(<QuantLab />);
    expect(await screen.findByText("No reliable edge")).toBeTruthy();
    expect(screen.getByText("Not rejected")).toBeTruthy();
    expect(screen.getByText("200 of 3686")).toBeTruthy();
    expect(screen.getAllByText(/not run yet/).length).toBe(3);
  });

  it("says Not verified when the API fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 500 }));
    render(<QuantLab />);
    expect(await screen.findByText(/Not verified: the quant results didn't load/)).toBeTruthy();
  });
});
