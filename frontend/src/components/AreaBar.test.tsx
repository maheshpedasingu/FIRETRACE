// AreaBar tests. Coordinates are SYNTHETIC TEST DATA.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("passes the containing country for country downloads", () => {
    const onApply = setup();
    fireEvent.change(screen.getByLabelText("Bounding box"), { target: { value: "68.1,6.7,97.4,35.7" } });
    fireEvent.change(screen.getByLabelText("Inside country"), { target: { value: "India" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-11-14" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onApply).toHaveBeenCalledWith({
      area: { kind: "bbox", bbox: { west: 68.1, south: 6.7, east: 97.4, north: 35.7 } },
      start: "2026-01-01",
      end: "2026-11-14",
      platforms: [],
      country: "India",
    });
  });

  it("saves a point + radius area as a polygon and applies it", async () => {
    const onApply = vi.fn();
    const createArea = vi.fn(async (body: { name: string; geojson: unknown }) => ({
      id: 7, name: body.name, kind: "polygon" as const, bbox: [79.2, 15.4, 80.2, 16.4] as [number, number, number, number],
      geojson: null, country: null, created_utc: "2026-11-15T00:00:00Z",
    }));
    render(<AreaBar query={null} onApply={onApply} savedAois={[]} today={TODAY} createArea={createArea} />);
    fireEvent.change(screen.getByLabelText("Saved or example area"), { target: { value: "circle" } });
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "15.9" } });
    fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "79.7" } });
    fireEvent.change(screen.getByLabelText("Radius in km"), { target: { value: "50" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2026-11-14" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(onApply).toHaveBeenCalled());
    expect(createArea.mock.calls[0][0].name).toBe("Circle 15.9000, 79.7000, 50 km");
    const geojson = createArea.mock.calls[0][0].geojson as { coordinates: number[][][] };
    expect(geojson.coordinates[0].length).toBe(65);
    expect(onApply.mock.calls[0][0].area).toEqual({
      kind: "aoi", id: 7, name: "Circle 15.9000, 79.7000, 50 km", bbox: { west: 79.2, south: 15.4, east: 80.2, north: 16.4 },
    });
  });

  it("rejects an invalid radius without saving anything", () => {
    const createArea = vi.fn();
    render(<AreaBar query={null} onApply={vi.fn()} savedAois={[]} today={TODAY} createArea={createArea} />);
    fireEvent.change(screen.getByLabelText("Saved or example area"), { target: { value: "circle" } });
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "15.9" } });
    fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "79.7" } });
    fireEvent.change(screen.getByLabelText("Radius in km"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("alert").textContent).toContain("Radius must be between 1 and 1000 km");
    expect(createArea).not.toHaveBeenCalled();
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
