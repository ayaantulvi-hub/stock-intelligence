// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { BigPicture, HoldingsToday, MarketStrip, PortfolioPage, ReliabilityPage, Screener, TradingPlan, WhatChanged, countdown } from "./Pages";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function respond(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => ({ status, json: async () => body })));
}

test("empty portfolio explains what to do", async () => {
  respond({ worth: 0, cost: 0, profit: 0, risks: [], sectors: [], holdings: [] });
  render(<PortfolioPage />);
  expect(await screen.findByText(/tap "I own this"/)).toBeTruthy();
});

test("reliability says too early and shows missing scores as Not verified", async () => {
  const body = {
    days: 0,
    grade: "Too early to say",
    overall: { count: 0, brier: null, baseline: null, range_hit: null },
    calibration: [],
    recent: {},
    sectors: [],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      status: url === "/api/reliability" ? 200 : 500,
      json: async () => body,
    })),
  );
  render(<ReliabilityPage />);
  expect(await screen.findByText("Too early to say")).toBeTruthy();
  expect(screen.getByText(/nothing has been scored/)).toBeTruthy();
});

test("screener filters by lean and opens a stock", async () => {
  const row = (ticker: string, lean: string) => ({
    ticker,
    name: `${ticker} Fixture`,
    last_close: 100,
    rank: 0.5,
    p_up: 0.5,
    action: "No reliable edge",
    lean,
  });
  respond([row("AAA", "Buy"), row("BBB", "Sell")]);
  const open = vi.fn();
  render(<Screener onOpen={open} />);
  fireEvent.click(await screen.findByText("AAA"));
  expect(open).toHaveBeenCalledWith("AAA");
  expect(screen.queryByText("BBB")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "All" }));
  expect(screen.getByText("BBB")).toBeTruthy();
});

test("your stocks today says plainly what to sell", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status: 200,
      json: async () => [
        { ticker: "AAA", name: "A", price: 10, buy_price: 9, sell_by: null, call: "Sell now", reason: "Fixture reason.", kind: "sell" },
        { ticker: "BBB", name: "B", price: 10, buy_price: 9, sell_by: null, call: "Keep", reason: "No warning signs today.", kind: "buy" },
      ],
    })),
  );
  render(<HoldingsToday />);
  expect(await screen.findByText("Sell 1 now, keep the rest.")).toBeTruthy();
  expect(screen.getByText("Sell now").closest("tr")?.className).toBe("row-sell");
  expect(screen.getByText("Keep").closest("tr")?.className).toBe("row-buy");
});

test("the big picture shows the reading, meaning and source", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status: 200,
      json: async () => ({
        cards: [
          { title: "Yield curve", reading: "Fixture reading", state: "bad", meaning: "Fixture meaning.", source: "Fixture source", url: "https://fred.stlouisfed.org", date: "2026-11-03" },
        ],
        actions: [],
        judged: [
          { url: "https://www.bbc.co.uk/j", title: "Fixture story", scope: "industry", industries: ["Chips"], effect: "negative", size: "big", why: "Fixture reasoning." },
        ],
        warnings: [{ subject: "Chips", bad: 4, outlets: 2, title: "Fixture bad headline", url: "https://www.bbc.co.uk/x" }],
        news: {
          market: [
            {
              subject: "Inflation",
              tone: "More negative than usual",
              articles: [{ title: "Fixture headline", url: "https://www.reuters.com/x", domain: "reuters.com", seen_at: "2026-11-05T10:00:00Z" }],
            },
          ],
          industries: [],
          companies: [],
        },
      }),
    })),
  );
  render(<BigPicture />);
  expect(await screen.findByText("Fixture reading")).toBeTruthy();
  expect(screen.getByText("Fixture meaning.")).toBeTruthy();
  expect(screen.getByText("None stored in the last 60 days.")).toBeTruthy();
  expect(screen.getByText("Fixture headline")).toBeTruthy();
  expect(screen.getByText("Fixture bad headline")).toBeTruthy();
  expect(screen.getByText(/Fixture reasoning/)).toBeTruthy();
  expect(screen.getByText("More negative than usual")).toBeTruthy();
});

test("what changed leads with decisions and folds the rest", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status: 200,
      json: async () => ({
        latest: "2026-11-05",
        previous: "2026-11-04",
        decisions: [
          { ticker: "AAA", topic: "Decision", was: "Leans buy", now: "Wait", why: "Moved.", tone: "sell", action: "Keep. Fixture.", yours: true },
        ],
        details: [
          { ticker: "BBB", topic: "Short trade", was: "No trade", now: "Leans buy", why: "x", tone: "buy", action: "No action.", yours: false },
        ],
      }),
    })),
  );
  render(<WhatChanged />);
  expect(await screen.findByText("1 decision changed, 1 on stocks you own")).toBeTruthy();
  expect(screen.getByText("Keep. Fixture.").closest("tr")?.className).toBe("row-sell");
  expect(screen.getByText("Smaller changes (1)")).toBeTruthy();
});

test("what changed says so when no decision did", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status: 200,
      json: async () => ({ latest: "2026-11-05", previous: "2026-11-04", decisions: [], details: [] }),
    })),
  );
  render(<WhatChanged />);
  expect(await screen.findByText("No decisions changed")).toBeTruthy();
});

test("the countdown reads plainly and stops at zero", () => {
  expect(countdown(26 * 3600000 + 5 * 60000)).toBe("1d 2h 5m");
  expect(countdown(3 * 3600000 + 60000)).toBe("3h 1m");
  expect(countdown(125000)).toBe("2m 5s");
  expect(countdown(0)).toBeNull();
});

test("the market strip shows today's move and compares your stocks", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status: 200,
      json: async () => ({
        markets: [
          { name: "S&P 500", ticker: "SPY", price: 495, change: -0.01, at: "2026-11-05T15:00:00Z" },
          { name: "Dow Jones", ticker: "DIA", price: null, change: null, at: null },
        ],
        versus: { since: "2026-11-04", yours: -0.066, market: -0.02 },
      }),
    })),
  );
  render(<MarketStrip />);
  expect(await screen.findByText("-1.00%")).toBeTruthy();
  expect(screen.getByText("Not verified")).toBeTruthy();
  expect(screen.getByText("-6.60%")).toBeTruthy();
});

test("the trading plan shows broken rules in red", async () => {
  respond({
    paused: false,
    week: {},
    checks: [
      { rule: "A stop on every holding", state: "fail", text: "No stop on AAA." },
      { rule: "Risk per holding", state: "pass", text: "Fine." },
    ],
  });
  render(<TradingPlan />);
  expect(await screen.findByText(/1 plan rule is broken/)).toBeTruthy();
  expect(screen.getByText(/No stop on AAA/).closest("li")?.className).toBe("bad");
});
