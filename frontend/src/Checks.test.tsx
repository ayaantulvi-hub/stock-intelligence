// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { DecisionTests, MarketCheck } from "./Checks";
import { FamilyBars } from "./ForecastPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const reply = (body: unknown) => vi.stubGlobal("fetch", vi.fn(async () => ({ status: 200, json: async () => body })));

test("an untested market check says it changes nothing", async () => {
  reply({ check: { run_at: "", edge: false, t_stat: 0.4, holdout_gain: null, test_dates: 140, chance: 0.55, state: "Neutral", readings: [{ factor: "curve_3m", name: "Yield curve", value: 0.4, percentile: 30 }] } });
  render(<MarketCheck />);
  expect(await screen.findByText(/hasn't passed its test \(140 past months checked\)/)).toBeTruthy();
  expect(screen.getByText(/55% chance/)).toBeTruthy();
});

test("a family that hurts is shown as dropped, in red", async () => {
  reply({ families: [{ family: "Trend", change: -0.01, t_stat: -2.5, verdict: "Hurts" }], calibration: [] });
  render(<DecisionTests />);
  expect((await screen.findByText("Hurts, so dropped")).closest("tr")?.className).toBe("row-sell");
});

test("family bars are green for buy and red for sell", () => {
  render(<FamilyBars families={[{ family: "Value", score: 80, push: "buy", factors: [] }, { family: "Risk", score: 20, push: "sell", factors: [] }]} />);
  expect(screen.getByText("Value").closest("tr")?.className).toBe("row-buy");
  expect(screen.getByText("Risk").closest("tr")?.className).toBe("row-sell");
});
