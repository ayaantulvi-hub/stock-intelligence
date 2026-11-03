// Every API response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stub(routes: Record<string, [number, unknown]>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const [status, body] = routes[url.split("?")[0]];
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
  });
  render(<App />);
  expect(await screen.findByText("Not verified")).toBeTruthy();
});
