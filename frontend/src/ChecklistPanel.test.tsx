// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ChecklistPanel, { HowMuch, OrderTicket, sharesForRisk, TodaysOrders } from "./ChecklistPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("risk sets the size", () => {
  expect(sharesForRisk(10000, 1, 100, 50)).toEqual({
    shares: 2,
    cost: 200,
    loss: 100,
    limited: false,
  });
});

test("a tight stop cannot push one stock past 10%", () => {
  const result = sharesForRisk(10000, 1, 100, 99);
  expect(result?.shares).toBe(10);
  expect(result?.limited).toBe(true);
});

test("a stop above the price gives no answer", () => {
  expect(sharesForRisk(10000, 1, 100, 120)).toBeNull();
});

test("shows checks with their state", async () => {
  const levels = {
    levels: {
      price: 100,
      stop: 90,
      target: 120,
      risk_percent: 10,
      target_percent: 20,
      stop_reason: "Fixture stop reason.",
      target_reason: "Fixture target reason.",
      ceiling_warning: null,
    },
    tested: [
      {
        stop_multiple: null,
        trades: 100,
        avg_return: 0.03,
        win_rate: 0.6,
        worst_return: -0.5,
        stopped_share: 0,
      },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      status: 200,
      json: async () =>
        url.endsWith("/levels")
          ? levels
          : [
              { topic: "Debt", state: "unknown", text: "Fixture." },
              { topic: "Data", state: "pass", text: "Fixture fresh." },
            ],
    })),
  );
  render(<ChecklistPanel ticker="AAA" />);
  expect(await screen.findByText("Not verified")).toBeTruthy();
  expect(screen.getByText("Pass")).toBeTruthy();
  expect(await screen.findByText("90.00")).toBeTruthy();
  expect(screen.getByText("Fixture stop reason.")).toBeTruthy();
  expect(screen.getByText("No stop")).toBeTruthy();
});

test("the stock page order leaves shares to you", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ status: 200, json: async () => ({ levels: { price: 100, stop: 90 } }) })),
  );
  render(<HowMuch ticker="AAA" />);
  expect(await screen.findByText("Your choice")).toBeTruthy();
  expect(screen.getByText("90.00")).toBeTruthy();
  expect(screen.getByText("Switch off")).toBeTruthy();
});

test("the order ticket uses the field names in the trading screen", () => {
  render(<OrderTicket stop={350.5} target={460} keep="Week" />);
  expect(screen.getByText("Take profit price (switch on)")).toBeTruthy();
  expect(screen.getByText("460.00")).toBeTruthy();
  expect(screen.getByText("350.50")).toBeTruthy();
});

test("today's orders say when to sell and give each stop", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status: 200,
      json: async () => ({
        session: "2026-11-04",
        sell_by: "2026-12-03",
        proven: false,
        orders: [{ ticker: "AAA", name: "Fixture", price: 400, stop: 350 }],
      }),
    })),
  );
  render(<TodaysOrders onOpen={() => {}} />);
  expect(await screen.findByText(/Sell them all on 2026-12-03/)).toBeTruthy();
  expect(screen.getByText("350.00")).toBeTruthy();
});
