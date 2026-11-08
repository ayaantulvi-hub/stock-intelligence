// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { CongressTrades, SourceChecks, StockCrowd } from "./Crowd";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const reply = (body: unknown) => vi.stubGlobal("fetch", vi.fn(async () => ({ status: 200, json: async () => body })));

test("Congress trades show who, the range and the delay, buys in green", async () => {
  reply({ trades: [{ member: "Jane Doe", owner: "Spouse", ticker: "AAPL", asset: "Apple (AAPL) [ST]", action: "Buy", trade_date: "2026-10-20", filed_date: "2026-11-01", amount: "$1,001 - $15,000", days_to_file: 12, url: "https://fixture.test", owned: true }], reports_read: 3, reports_unread: 1, newest_filing: "2026-11-01", note: "House members only." });
  render(<CongressTrades />);
  expect(await screen.findByText(/\(you own this\)/)).toBeTruthy();
  expect(screen.getByText(/12 days later/)).toBeTruthy();
  expect(screen.getByText("Jane Doe (spouse)").closest("tr")?.className).toBe("row-buy");
});

test("missing short interest says Not verified", async () => {
  reply({ short_interest: null, congress: [] });
  render(<StockCrowd ticker="AAA" />);
  expect(await screen.findByText(/Short interest: Not verified/)).toBeTruthy();
});

test("a source disagreement is shown with its detail", async () => {
  reply({ conflicts: [{ ticker: "BBB", market_date: "2026-11-06", detail: "Tiingo 50.00, Alpaca (IEX) 55.00" }], last_check: "2026-11-08T12:00:00Z", overrides: [{ rule: "Expert checks", run_at: "", blocked: 5, blocked_mean: null, others: 40, others_mean: 0.01, verdict: "Not enough history yet" }] });
  render(<SourceChecks />);
  expect(await screen.findByText(/Tiingo 50.00, Alpaca \(IEX\) 55.00/)).toBeTruthy();
  expect(screen.getByText("Not enough history yet")).toBeTruthy();
});
