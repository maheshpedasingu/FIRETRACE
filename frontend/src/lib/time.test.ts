// Time formatting tests. Timestamps are SYNTHETIC TEST DATA.
import { describe, expect, it } from "vitest";
import { formatUtc } from "./time";

describe("formatUtc", () => {
  it("formats offset timestamps in UTC to the minute", () => {
    expect(formatUtc("2026-11-14T07:19:51.561570+00:00")).toBe("2026-11-14 07:19 UTC");
    expect(formatUtc("2026-11-14T12:49:00+05:30")).toBe("2026-11-14 07:19 UTC");
  });

  it("treats timestamps without an offset as UTC and handles missing values", () => {
    expect(formatUtc("2026-11-14T07:19:51.561570")).toBe("2026-11-14 07:19 UTC");
    expect(formatUtc(null)).toBe("—");
    expect(formatUtc("not a date")).toBe("—");
  });
});
