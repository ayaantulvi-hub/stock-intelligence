// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PortfolioPage, ReliabilityPage, Screener } from "./Pages";

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
  fireEvent.click(await screen.findByText("BBB"));
  expect(open).toHaveBeenCalledWith("BBB");
  fireEvent.click(screen.getByRole("button", { name: "Buy" }));
  expect(screen.queryByText("BBB")).toBeNull();
});
