// Every chart response here is a labelled test fixture. The chart library needs a real
// canvas, so it is replaced with a stub, and browser rendering is checked separately.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ChartPanel from "./ChartPanel";

vi.mock("lightweight-charts", () => {
  const series = { setData: vi.fn(), createPriceLine: vi.fn() };
  const chart = {
    addSeries: () => series,
    priceScale: () => ({ applyOptions: vi.fn() }),
    timeScale: () => ({
      setVisibleLogicalRange: vi.fn(),
      subscribeVisibleLogicalRangeChange: vi.fn(),
    }),
    remove: vi.fn(),
  };
  return {
    createChart: () => chart,
    CandlestickSeries: {},
    HistogramSeries: {},
    LineSeries: {},
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const base = {
  stale: false,
  signals_blocked: false,
  latest_bar: "2026-07-07",
  latest_expected_session: "2026-07-07",
  candles: [],
  levels: [],
  signals: [],
};

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ status, json: async () => body }),
  );
}

test("blocks signals on stale data", async () => {
  respond(200, { ...base, stale: true, signals_blocked: true, latest_bar: "2026-06-01" });
  render(<ChartPanel ticker="AAA" />);
  expect(await screen.findByText(/Signals blocked/)).toBeTruthy();
});

test("shows an untested signal as Unproven with its cancellation level", async () => {
  respond(200, {
    ...base,
    signals: [
      {
        name: "Golden cross",
        label: "Unproven",
        direction: "bullish",
        market_date: "2026-07-07",
        detail: "fixture",
        cancellation_level: 95,
        sample_size: 0,
        win_rate: null,
      },
    ],
  });
  render(<ChartPanel ticker="AAA" />);
  expect(await screen.findByText("Unproven")).toBeTruthy();
  expect(screen.getByText("Not tested yet")).toBeTruthy();
  expect(screen.getByText("95.00")).toBeTruthy();
});

test("shows an error when the chart fails", async () => {
  respond(500, {});
  render(<ChartPanel ticker="AAA" />);
  expect(await screen.findByText(/Chart failed to load/)).toBeTruthy();
});

test("shows Not verified when no prices are stored", async () => {
  respond(200, base);
  render(<ChartPanel ticker="AAA" />);
  expect(await screen.findByText(/Not verified: no complete prices/)).toBeTruthy();
});
