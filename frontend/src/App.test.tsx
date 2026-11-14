// The health payload below is SYNTHETIC TEST DATA, not a real backend response.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const SYNTHETIC_HEALTH = {
  status: "ok",
  app: "FIRETRACE",
  version: "0.1.0-synthetic",
  server_time_utc: "2000-01-01T00:00:00Z",
  firms_map_key_configured: false,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows backend status from the health endpoint", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(SYNTHETIC_HEALTH), { status: 200 })),
    );
    render(<App />);
    expect(screen.getByText("FIRETRACE")).toBeTruthy();
    expect(await screen.findByText("0.1.0-synthetic")).toBeTruthy();
    expect(screen.getByText("not configured")).toBeTruthy();
  });

  it("reports an unreachable backend instead of failing silently", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 503 })));
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("HTTP 503");
  });
});
