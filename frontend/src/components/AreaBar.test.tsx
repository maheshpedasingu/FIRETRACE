// AreaBar tests. Coordinates are SYNTHETIC TEST DATA.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AreaBar } from "./AreaBar";

const TODAY = new Date("2026-11-14T12:00:00Z");

afterEach(cleanup);

function setup() {
  const onApply = vi.fn();
  render(<AreaBar query={null} onApply={onApply} savedAois={[]} today={TODAY} />);
  return onApply;
}

describe("AreaBar", () => {
  it("rejects an invalid bbox with a visible reason", () => {
    const onApply = setup();
    fireEvent.change(screen.getByLabelText("Bounding box"), { target: { value: "0,10,5,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("alert").textContent).toContain("South must be less than north");
    expect(onApply).not.toHaveBeenCalled();
  });

  it("applies a western/southern hemisphere bbox and selected platforms", () => {
    const onApply = setup();
    fireEvent.change(screen.getByLabelText("Bounding box"), { target: { value: "-65,-15,-45,-3" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-11-14" } });
    fireEvent.click(screen.getByLabelText(/NOAA-20/));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onApply).toHaveBeenCalledWith({
      area: { kind: "bbox", bbox: { west: -65, south: -15, east: -45, north: -3 } },
      start: "2026-11-01",
      end: "2026-11-14",
      platforms: ["NOAA-20"],
    });
  });

  it("rejects future end dates and notes antimeridian crossing", () => {
    const onApply = setup();
    fireEvent.change(screen.getByLabelText("Bounding box"), { target: { value: "176,-21,-178,-15" } });
    expect(screen.getByText("Crosses the 180° meridian.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-12-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("alert").textContent).toContain("future");
    expect(onApply).not.toHaveBeenCalled();
  });
});
