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

test("the month Time Machine shows the three outcomes and the real record", async () => {
  const { HoldReplay } = await import("./ForecastPanel");
  reply({ as_of: "2026-11-09", own_stop: false, replay: { replays: 10000, days: 20, p_stop: 0.12, p_gain: 0.56, median: 0.018, average: 0.01, low: -0.11, high: 0.14, entry: 100, stop: 90, verdict: "Close to a coin flip: 56% of replays ended up.", record: { holds: 504, p_gain: 0.58, median: 0.02 } } });
  render(<HoldReplay ticker="AAA" />);
  expect(await screen.findByText(/Ended up 56%/)).toBeTruthy();
  expect(screen.getByText(/Hit the stop 12%/)).toBeTruthy();
  expect(screen.getByText(/the site's suggested stop/)).toBeTruthy();
  expect(screen.getByText(/ended up 58% of the time \(504 holds\)/)).toBeTruthy();
});
