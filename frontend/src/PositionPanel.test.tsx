// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import PositionPanel from "./PositionPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const saved = {
  shares: 10,
  buy_price: 200,
  target_price: 300,
  stop_price: 180,
  price: 265.64,
  cost: 2000,
  worth: 2656.4,
  profit: 656.4,
  profit_percent: 32.8,
  break_even: 200.2,
  above_break_even: true,
  plan: "The price is between your stop and your target.",
  call: "No sell call: testing has not shown the model can time this.",
  cases: [{ name: "Base", value: 250, from_cost: 0.25 }],
};

test("saves a position and shows profit, break-even and the plan", async () => {
  const fetchMock = vi.fn(async (_url: string, options?: RequestInit) => ({
    status: 200,
    json: async () => (options?.method === "PUT" ? saved : null),
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(<PositionPanel ticker="AAA" />);
  fireEvent.click(await screen.findByText("I own this"));
  fireEvent.change(screen.getByLabelText("Shares"), { target: { value: "10" } });
  fireEvent.change(screen.getByLabelText("Price paid"), { target: { value: "200" } });
  fireEvent.click(screen.getByText("Save"));
  expect(await screen.findByText(/\+\$656.40/)).toBeTruthy();
  expect(screen.getByText("200.20")).toBeTruthy();
  expect(screen.getByText(/between your stop and your target/)).toBeTruthy();
  expect(screen.getByText(/No sell call/)).toBeTruthy();
});

test("shows an error when the save fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, options?: RequestInit) => ({
      status: options?.method === "PUT" ? 500 : 200,
      json: async () => null,
    })),
  );
  render(<PositionPanel ticker="AAA" />);
  fireEvent.click(await screen.findByText("I own this"));
  fireEvent.change(screen.getByLabelText("Shares"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("Price paid"), { target: { value: "1" } });
  fireEvent.click(screen.getByText("Save"));
  expect(await screen.findByText(/Could not load or save/)).toBeTruthy();
});
