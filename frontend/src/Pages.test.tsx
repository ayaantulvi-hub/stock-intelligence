// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PortfolioPage, PracticePage, ReliabilityPage, Screener } from "./Pages";

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
  respond({
    days: 0,
    grade: "Too early to say",
    overall: { count: 0, brier: null, baseline: null, range_hit: null },
    calibration: [],
    recent: {},
    sectors: [],
  });
  render(<ReliabilityPage />);
  expect(await screen.findByText("Too early to say")).toBeTruthy();
  expect(screen.getByText(/nothing has been scored/)).toBeTruthy();
});

test("a refused practice trade shows the reason", async () => {
  const state = { cash: 10000, total: 10000, return_percent: 0, holdings: [], trades: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, options?: RequestInit) =>
      options?.method === "POST"
        ? { status: 422, json: async () => ({ detail: "Not enough practice cash." }) }
        : { status: 200, json: async () => state },
    ),
  );
  render(<PracticePage />);
  fireEvent.change(await screen.findByLabelText("Ticker"), { target: { value: "AAA" } });
  fireEvent.change(screen.getByLabelText("Shares"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("Why?"), { target: { value: "Fixture" } });
  fireEvent.click(screen.getByText("Place practice trade"));
  expect(await screen.findByText("Not enough practice cash.")).toBeTruthy();
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
  fireEvent.click(await screen.findByText("BBB"));
  expect(open).toHaveBeenCalledWith("BBB");
  fireEvent.click(screen.getByRole("button", { name: "Buy" }));
  expect(screen.queryByText("BBB")).toBeNull();
});
