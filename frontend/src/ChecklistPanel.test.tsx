// Every response here is a labelled test fixture, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ChecklistPanel, { sharesForRisk } from "./ChecklistPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("risk sets the size", () => {
  expect(sharesForRisk(10000, 1, 100, 50)).toEqual({
    shares: 2,
    cost: 200,
    loss: 100,
    limited: false,
  });
});

test("a tight stop cannot push one stock past 10%", () => {
  const result = sharesForRisk(10000, 1, 100, 99);
  expect(result?.shares).toBe(10);
  expect(result?.limited).toBe(true);
});

test("a stop above the price gives no answer", () => {
  expect(sharesForRisk(10000, 1, 100, 120)).toBeNull();
});

test("shows checks with their state", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      status: 200,
      json: async () => [
        { topic: "Debt", state: "unknown", text: "Fixture." },
        { topic: "Data", state: "pass", text: "Fixture fresh." },
      ],
    })),
  );
  render(<ChecklistPanel ticker="AAA" />);
  expect(await screen.findByText("Not verified")).toBeTruthy();
  expect(screen.getByText("Pass")).toBeTruthy();
});
