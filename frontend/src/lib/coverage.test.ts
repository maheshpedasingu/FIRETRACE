import { describe, expect, it } from "vitest";
import { coveredCount } from "./coverage";

// SYNTHETIC TEST DATA
describe("coveredCount", () => {
  it("shows unknown, not zero, when a platform has no coverage and no detections", () => {
    expect(coveredCount(0, { detections: 0, months_complete: 0, months_partial: 0 })).toBe(null);
  });
  it("keeps a real zero when the area was covered", () => {
    expect(coveredCount(0, { detections: 0, months_complete: 1, months_partial: 0 })).toBe(0);
    expect(coveredCount(0, { detections: 0, months_complete: 0, months_partial: 1 })).toBe(0);
  });
  it("keeps detections without coverage as a lower bound", () => {
    expect(coveredCount(5, { detections: 5, months_complete: 0, months_partial: 0 })).toBe(5);
  });
});
