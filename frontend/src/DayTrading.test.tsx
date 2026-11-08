// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { DayTradingPage, shares, stepText, windowState } from "./DayTrading";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const stock = { ticker: "SPY", price: 500, levels: [], setups: [], step: {} };

test("window countdown and states", () => {
  const start = "2026-11-09T14:50:00Z";
  const end = "2026-11-09T15:30:00Z";
  expect(windowState(Date.parse("2026-11-09T14:40:00Z"), start, end).text).toMatch(/Opens in 10 min/);
  expect(windowState(Date.parse("2026-11-09T15:00:00Z"), start, end).open).toBe(true);
  expect(windowState(Date.parse("2026-11-09T16:00:00Z"), start, end).text).toBe("Closed for today.");
});

test("each step says what it's waiting for", () => {
  expect(stepText(stock, false)).toMatch(/Outside the trading window/);
  expect(stepText(stock, true)).toMatch(/Step 1 of 3/);
  expect(stepText({ ...stock, step: { touched: { level: "Previous day high", side: "short" } } }, true)).toMatch(/Previous day high.*sell short/);
});

test("shares come from 1% risk and the stop distance", () => {
  expect(shares(10000, 0.01, 500, 499)).toBe(100);
  expect(shares(0, 0.01, 500, 499)).toBeNull();
});

test("a feed error is shown and no levels or setups appear", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ status: 200, json: async () => ({ error: "Alpaca bars: HTTP 403", test: null }) })));
  render(<DayTradingPage />);
  expect(await screen.findByText(/Live prices unavailable: Alpaca bars: HTTP 403/)).toBeTruthy();
  expect(screen.getAllByText(/Not tested yet/)).toHaveLength(2);
  expect(screen.queryByText(/Key levels today/)).toBeNull();
});

test("the Time Machine shows the odds and the verdict", async () => {
  const { ReplayBox } = await import("./DayTrading");
  render(
    <ReplayBox
      replay={{ replays: 10000, sessions: 59, p_target: 0.294, p_stop: 0.255, p_neither: 0.451, avg_r: 0.02, close_low: 350, close_high: 375,
        verdict: "Close to a coin flip: target first in 29% of replays.", history: { sessions: 59, triggered: 33, target: 13, stop: 15, avg_r: -0.05 } }}
    />,
  );
  expect(screen.getByText(/Target first 29%/)).toBeTruthy();
  expect(screen.getByText(/Close to a coin flip/)).toBeTruthy();
  expect(screen.getByText(/triggered 33 times/)).toBeTruthy();
});

test("missing replay history says Not verified", async () => {
  const { ReplayBox } = await import("./DayTrading");
  render(<ReplayBox replay={null} />);
  expect(screen.getByText(/Not verified/)).toBeTruthy();
});
