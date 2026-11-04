// Every API response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stub(routes: Record<string, [number, unknown]>) {
  const empty: Record<string, [number, unknown]> = {
    "/api/ideas": [200, { target_session: null, edge: false, buy: [], sell: [] }],
    "/api/track-record": [200, { scored: 0, written: 0, brier: null, evaluations: [] }],
    "/api/model-comparison": [200, null],
    "/api/screener": [200, []],
    "/api/market-mood": [200, { mood: "Not verified", vix: null, credit_spread: null, above_200: null, stocks_measured: 0, next_fed: null }],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const [status, body] = { ...empty, ...routes }[url.split("?")[0]];
      return { status, json: async () => body };
    }),
  );
}

test("shows an error rather than a status when the API is unreachable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
  render(<App />);
  expect(await screen.findByText(/Status is not verified/)).toBeTruthy();
  expect(screen.queryByText("OK")).toBeNull();
});

test("shows a failed feed and its message", async () => {
  stub({
    "/api/status": [
      503,
      {
        database: { state: "ok" },
        migrations: { state: "ok" },
        worker: { state: "stale" },
      },
    ],
    "/api/feeds": [
      200,
      [
        {
          feed: "prices",
          source: "Tiingo",
          status: "error",
          message: "Tiingo AAPL: HTTP 500",
          last_run: "2026-07-07T23:20:00Z",
          records_added: 0,
        },
      ],
    ],
    "/api/economic": [200, []],
    "/api/backtest": [200, null],
  });
  render(<App />);
  expect(await screen.findByText("Error")).toBeTruthy();
  expect(screen.getByText(/Tiingo AAPL: HTTP 500/)).toBeTruthy();
  expect(screen.getByText("Stale")).toBeTruthy();
});

test("shows Not verified for a value the source did not publish", async () => {
  stub({
    "/api/status": [
      200,
      { database: { state: "ok" }, migrations: { state: "ok" }, worker: { state: "ok" } },
    ],
    "/api/feeds": [200, []],
    "/api/economic": [
      200,
      [
        {
          series_id: "DGS10",
          observation_date: "2026-01-01",
          value: null,
          source: "FRED",
          source_url: "https://fixture.test",
          retrieved_at: "2026-07-07T23:20:00Z",
          data_status: "end_of_day",
        },
      ],
    ],
    "/api/backtest": [200, null],
  });
  render(<App />);
  expect((await screen.findAllByText("Not verified")).length).toBeGreaterThan(0);
});

test("says No reliable edge when a tested signal has none", async () => {
  stub({
    "/api/status": [
      200,
      { database: { state: "ok" }, migrations: { state: "ok" }, worker: { state: "ok" } },
    ],
    "/api/feeds": [200, []],
    "/api/economic": [200, []],
    "/api/backtest": [
      200,
      {
        finished_at: "fixture",
        stocks: 2,
        first_date: "2020-01-02",
        last_date: "2026-07-07",
        cost_bps: 10,
        note: "Fixture warning about bias.",
        results: [
          {
            signal: "Golden cross",
            direction: "bullish",
            horizon: 20,
            sample_size: 100,
            win_rate: 0.5,
            oos_sample_size: 0,
            oos_win_rate: null,
            oos_baseline_win_rate: 0.5,
            oos_avg_return: null,
            oos_baseline_avg_return: 0.01,
            edge: false,
          },
        ],
      },
    ],
  });
  render(<App />);
  expect(await screen.findByText("No reliable edge")).toBeTruthy();
  expect(screen.getByText("Fixture warning about bias.")).toBeTruthy();
});
