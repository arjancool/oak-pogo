import { describe, expect, it } from "vitest";

import { bytes, dateTime, ivs, level, num, pct, relative, setTimeZone } from "../../src/lib/format";

describe("format", () => {
  it("formats numbers in Dutch and shows unknown values explicitly", () => {
    expect(num(1234567)).toBe("1.234.567");
    expect(num(null)).toBe("onbekend");
    expect(num(undefined, "–")).toBe("–");
    expect(num(0)).toBe("0");
  });

  it("formats percentages and levels", () => {
    expect(pct(97.77)).toBe("97,8%");
    expect(pct(null)).toBe("–");
    expect(level(40)).toBe("40");
    expect(level(20.5)).toBe("20,5");
    expect(level(null)).toBe("?");
  });

  it("formats IV triples and keeps missing IVs visible", () => {
    expect(ivs(15, 0, 7)).toBe("15/0/7");
    expect(ivs(15, null, 7)).toBe("?/?/?");
  });

  it("formats byte sizes", () => {
    expect(bytes(0)).toBe("0 B");
    expect(bytes(512)).toBe("512 B");
    expect(bytes(1536)).toBe("1,5 KB");
    expect(bytes(5 * 1024 * 1024)).toBe("5 MB");
  });

  it("describes relative times", () => {
    const now = new Date("2026-10-23T12:00:00Z");
    expect(relative(null, now)).toBe("nooit");
    expect(relative("2026-10-23T11:59:30Z", now)).toBe("zojuist");
    expect(relative("2026-10-23T11:00:00Z", now)).toBe("1 uur geleden");
    expect(relative("2026-10-21T12:00:00Z", now)).toBe("eergisteren");
  });

  it("shows timestamps in the configured time zone", () => {
    setTimeZone("Europe/Amsterdam");
    expect(dateTime("2026-07-01T10:00:00Z")).toContain("12:00");
    setTimeZone("UTC");
    expect(dateTime("2026-07-01T10:00:00Z")).toContain("10:00");
    setTimeZone("Europe/Amsterdam");
    expect(dateTime(null)).toBe("–");
  });
});
