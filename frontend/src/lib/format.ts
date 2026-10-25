/** Dutch formatting. Timestamps arrive in UTC and are shown in the configured time zone. */

let timeZone = "Europe/Amsterdam";

export function setTimeZone(zone: string): void {
  timeZone = zone;
}

const numberFormat = new Intl.NumberFormat("nl-NL");

export function num(value: number | null | undefined, fallback = "onbekend"): string {
  return value === null || value === undefined ? fallback : numberFormat.format(value);
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "–";
  return `${value.toLocaleString("nl-NL", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

export function level(value: number | null | undefined): string {
  if (value === null || value === undefined) return "?";
  return Number.isInteger(value) ? String(value) : value.toLocaleString("nl-NL", { minimumFractionDigits: 1 });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("nl-NL", { timeZone, dateStyle: "medium", timeStyle: "short" });
}

export function date(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("nl-NL", { timeZone, day: "numeric", month: "short", year: "numeric" });
}

export function relative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "nooit";
  const seconds = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat("nl-NL", { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return rtf.format(-Math.round(seconds / size), unit);
  }
  return "zojuist";
}

export function ivs(a: number | null, d: number | null, s: number | null): string {
  if (a === null || d === null || s === null) return "?/?/?";
  return `${a}/${d}/${s}`;
}

export function bytes(value: number | null | undefined): string {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toLocaleString("nl-NL", { maximumFractionDigits: 1 })} ${units[unit]}`;
}
