/** Formatting in the active language. Timestamps arrive in UTC and are shown in the configured
 * time zone. */
import i18n from "i18next";

let timeZone = "Europe/Amsterdam";
let locale = "nl-NL";
let numberFormat = new Intl.NumberFormat(locale);

export function setTimeZone(zone: string): void {
  timeZone = zone;
}

/** Called by the translations when the language changes. */
export function setLocale(tag: string): void {
  locale = tag;
  numberFormat = new Intl.NumberFormat(locale);
}

export function num(value: number | null | undefined, fallback?: string): string {
  if (value === null || value === undefined) return fallback ?? i18n.t("common.unknown");
  return numberFormat.format(value);
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "–";
  return `${value.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}

export function level(value: number | null | undefined): string {
  if (value === null || value === undefined) return "?";
  return Number.isInteger(value) ? String(value) : value.toLocaleString(locale, { minimumFractionDigits: 1 });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleString(locale, { timeZone, dateStyle: "medium", timeStyle: "short" });
}

export function date(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString(locale, { timeZone, day: "numeric", month: "short", year: "numeric" });
}

export function relative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return i18n.t("common.never");
  const seconds = Math.round((now.getTime() - new Date(iso).getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
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
  return i18n.t("common.justNow");
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
  return `${size.toLocaleString(locale, { maximumFractionDigits: 1 })} ${units[unit]}`;
}

/** A time span such as an event, in the active language: "8 nov, 14:00–17:00". */
export function period(startIso: string, endIso: string): string {
  const format = new Intl.DateTimeFormat(locale, { timeZone, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return format.formatRange(new Date(startIso), new Date(endIso));
}
