// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import LongTermPanel from "./LongTermPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const body = {
  available: true,
  price: 100,
  cases: [
    { name: "Bear", value: 80, against_price: -0.2 },
    { name: "Base", value: 110, against_price: 0.1 },
    { name: "Bull", value: 150, against_price: 0.5 },
  ],
  assumptions: {
    bear_growth: 0.02,
    base_growth: 0.07,
    bull_growth: 0.12,
    discount_rate: 0.09,
    terminal_growth: 0.025,
  },
  metrics: [
    {
      name: "Gross margin",
      value: 0.5,
      kind: "percent",
      sources: [
        { tag: "GrossProfit", value: 1, period_end: "2025-12-31", form: "10-K", url: "https://fixture.test/a" },
      ],
    },
    { name: "Debt to equity", value: null, kind: "ratio", sources: [] },
  ],
  history: [
    { period_end: "2025-12-31", revenue: 2e9, net_income: 5e8, url: "https://fixture.test/b" },
  ],
  insider_trades: [],
};

test("shows cases with sourced figures and lets assumptions change", async () => {
  const fetchMock = vi.fn(async () => ({ status: 200, json: async () => body }));
  vi.stubGlobal("fetch", fetchMock);
  render(<LongTermPanel ticker="AAA" />);
  expect(await screen.findByText("$110.00")).toBeTruthy();
  const link = screen.getByText(/10-K 2025-12-31/) as HTMLAnchorElement;
  expect(link.href).toBe("https://fixture.test/a");
  expect(screen.getAllByText(/Not verified/).length).toBeGreaterThan(0);
  expect(screen.getByText("$500.0 million")).toBeTruthy();
  fireEvent.change(screen.getByLabelText(/Base growth/), { target: { value: "10" } });
  await waitFor(() =>
    expect(String(fetchMock.mock.calls.at(-1))).toContain("base_growth=0.1"),
  );
});

test("says Not verified when no figures are stored", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ status: 200, json: async () => ({ available: false }) })),
  );
  render(<LongTermPanel ticker="AAA" />);
  expect(await screen.findByText(/no SEC company figures/)).toBeTruthy();
});
