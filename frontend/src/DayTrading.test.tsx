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
  expect(screen.getByText(/Not tested yet/)).toBeTruthy();
  expect(screen.queryByText(/Key levels today/)).toBeNull();
});
