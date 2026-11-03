// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import Glossary from "./Glossary";
import { FactorsPanel, ForecastPanel, IdeasPanel } from "./ForecastPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stub(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({ status: 200, json: async () => routes[url] })),
  );
}

const factors = [
  {
    id: "mom_12_1",
    name: "12-month momentum",
    group: "Momentum",
    source: "Fixture paper",
    status: "live",
    effect: null,
    url: null,
    high_means: "Rose more than most",
  },
  {
    id: "value",
    name: "Book-to-market value",
    group: "Value",
    source: "Fixture paper 2",
    status: "Needs SEC company facts",
    effect: null,
    url: null,
    high_means: null,
  },
];

const forecast = {
      action: "No reliable edge",
      target_session: "2026-07-08",
      as_of_session: "2026-07-07",
      created_at: "2026-07-08T00:00:00Z",
      last_close: 100,
      p_up: 0.5,
      p_flat: 0.1,
      p_down: 0.4,
      range_low: 95,
      range_high: 105,
      rank_20d: 0.5,
      next_day_edge: false,
      confidence: "None",
      drivers: [{ factor: "mom_12_1", percentile: 91 }],
};

test("lists every factor, with missing ones Not verified", async () => {
  stub({ "/api/stocks/AAA/forecast": forecast, "/api/factors": factors });
  render(<FactorsPanel ticker="AAA" />);
  expect(await screen.findByText("91")).toBeTruthy();
  expect(screen.getByText("Needs SEC company facts")).toBeTruthy();
});

test("simple view gives the call and explains the data in plain English", async () => {
  stub({
    "/api/stocks/AAA/forecast": forecast,
    "/api/stocks/AAA/story": [
      { topic: "Long-term trend", tone: "good", text: "Up: fixture.", why: "Fixture reason." },
    ],
  });
  render(<ForecastPanel ticker="AAA" />);
  expect(await screen.findByText("Up: fixture.")).toBeTruthy();
  expect(screen.getByText("Fixture reason.")).toBeTruthy();
  expect(screen.getAllByText("No reliable edge").length).toBe(2);
});

test("names no stocks when the model has no edge", async () => {
  stub({
    "/api/ideas": { target_session: "2026-07-08", edge: false, buy: [], sell: [] },
    "/api/track-record": {
      scored: 0,
      written: 0,
      brier: null,
      baseline_brier: null,
      range_hit_rate: null,
      evaluations: [],
    },
  });
  render(<IdeasPanel />);
  expect(await screen.findByText("No reliable edge")).toBeTruthy();
  expect(screen.queryByText("Buy candidates")).toBeNull();
});

test("explains support and resistance in everyday words", async () => {
  render(<Glossary />);
  expect(screen.getByText(/Think of a floor/)).toBeTruthy();
  expect(screen.getByText(/Think of a ceiling/)).toBeTruthy();
});
