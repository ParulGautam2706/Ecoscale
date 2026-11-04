import { describe, expect, it } from "vitest";
import { fmt, pct } from "./format";

describe("format helpers", () => {
  it("formats numbers and handles missing values", () => {
    expect(fmt(null)).toBe("—");
    expect(fmt(1234.567, 1)).toMatch(/1,?234\.6/);
  });
  it("formats percentages", () => {
    expect(pct(0.256)).toBe("25.6%");
    expect(pct(undefined)).toBe("—");
  });
});
