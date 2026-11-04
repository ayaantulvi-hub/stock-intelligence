// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import Glossary from "./Glossary";

vi.mock("./PositionPanel", () => ({ default: () => null }));
vi.mock("./ChecklistPanel", () => ({ default: () => null }));
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
    "/api/stocks/AAA/leans": {
      factors: [
        {
          factor: "insider",
          name: "Insider trades",
          percentile: 95,
          lean: "Buy",
          evidence: "Paper only: not tested in this app yet",
          meaning: "Fixture factor meaning.",
          proven: false,
        },
      ],
      proven_buy: 0,
      proven_sell: 0,
      paper_buy: 1,
      paper_sell: 0,
      overall: { decision: "No reliable edge", lean: "Buy", proven: false, rank: 0.85 },
    },
    "/api/stocks/AAA/story": [
      {
        topic: "Long-term trend",
        tone: "good",
        text: "Up: fixture.",
        why: "Fixture reason.",
        meaning: "Fixture meaning.",
        evidence: "Fixture numbers.",
        on_chart: "Fixture chart note.",
      },
    ],
  });
  render(<ForecastPanel ticker="AAA" />);
  expect(await screen.findByText("Up: fixture.")).toBeTruthy();
  expect(screen.getByText("Fixture reason.")).toBeTruthy();
  expect(screen.getByText("Fixture numbers.")).toBeTruthy();
  expect(screen.getByText("Fixture meaning.")).toBeTruthy();
  expect(screen.getByText("Fixture factor meaning.")).toBeTruthy();
  expect(screen.getByText("Insider trades")).toBeTruthy();
  expect(screen.getByText("Buy")).toBeTruthy();
  expect(screen.getByText("Fixture chart note.")).toBeTruthy();
  expect(screen.getAllByText("No reliable edge").length).toBe(2);
  expect(screen.getByText(/leans Buy, ranking this stock higher than 85%/)).toBeTruthy();
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
    "/api/model-comparison": {
      models: [
        {
          model: "Fixture model",
          t_stat: 1.2,
          spread: 0.01,
          holdout_spread: -0.02,
          worst_year: 2022,
          worst_year_spread: -0.03,
          calm_spread: 0.01,
          stressed_spread: null,
          selected: true,
          edge: false,
          good: "Fixture good.",
          bad: "Fixture bad.",
          caution: "Fixture caution.",
        },
      ],
    },
  });
  render(<IdeasPanel />);
  expect(await screen.findByText("No reliable edge")).toBeTruthy();
  cleanup();
  render(<IdeasPanel part="record" />);
  expect(screen.queryByText("Buy candidates")).toBeNull();
  expect(await screen.findByText("Fixture model (chosen)")).toBeTruthy();
  expect(screen.getByText("-2.0%")).toBeTruthy();
});

test("explains support and resistance in everyday words", async () => {
  render(<Glossary />);
  expect(screen.getByText(/Think of a floor/)).toBeTruthy();
  expect(screen.getByText(/Think of a ceiling/)).toBeTruthy();
});
