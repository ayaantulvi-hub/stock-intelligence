// The API responses here are test fixtures, stubbed in place of fetch.
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("shows an error rather than a status when the API is unreachable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
  render(<App />);
  expect(await screen.findByText(/Status is not verified/)).toBeTruthy();
  expect(screen.queryByText("OK")).toBeNull();
});

test("shows a stale worker and a failed database as reported by a 503", async () => {
  const body = {
    healthy: false,
    checked_at: "fixture",
    database: { state: "error", detail: "OperationalError" },
    migrations: { state: "not_verified", current: null, expected: "0001" },
    worker: { state: "stale", last_heartbeat: null, age_seconds: null },
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 503, json: async () => body }));
  render(<App />);
  expect(await screen.findByText("Error")).toBeTruthy();
  expect(screen.getByText("Stale")).toBeTruthy();
  expect(screen.getByText("Not verified")).toBeTruthy();
});
