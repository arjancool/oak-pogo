/**
 * Sentences the server builds, such as cleanup reasons, shown in the chosen language (ADR-0025).
 *
 * The server sends a code with the data that goes into the sentence, plus the Dutch sentence. The
 * catalog has the sentence per code under "server.<group>.<code>". When the catalog has no text for
 * the code, or the data lacks a value the text needs (for example an analysis from an older OAK),
 * the Dutch sentence from the server is shown: never a sentence with a gap in it.
 *
 * Conventions for the data:
 * - "context" picks a variant, for example REASON_note next to REASON (i18next context).
 * - "count" picks the plural form.
 * - A server text, or a list of them, inside the data becomes a sentence too; a list is joined
 *   with commas. It uses the catalog group named after its key when there is one.
 * - "league" also gives "leagueName", "type" gives "typeName", and "starts_at" with "ends_at"
 *   give "period".
 */
import i18n from "i18next";

import { period } from "./format";
import { label, leagueNames, typeNames } from "./i18n";

export interface ServerText {
  code?: string;
  text: string;
  data?: Record<string, unknown>;
}

const PLACEHOLDER = /{{\s*([\w.]+)\s*(?:,[^}]*)?}}/g;

function isServerText(value: unknown): value is ServerText {
  return typeof value === "object" && value !== null && "text" in value && typeof (value as ServerText).text === "string";
}

function template(key: string, context: unknown, count: unknown): string | undefined {
  const base = typeof context === "string" && context ? `${key}_${context}` : key;
  const language = i18n.resolvedLanguage ?? i18n.language;
  const candidates = typeof count === "number" ? [`${base}_other`, base] : [base];
  for (const candidate of candidates) {
    const value: unknown = i18n.getResource(language, "translation", candidate) ?? i18n.getResource("nl", "translation", candidate);
    if (typeof value === "string") return value;
  }
  return undefined;
}

/** A nested server text uses the group named after its data key when the catalog has one. */
function nestedGroup(key: string, parent: string): string {
  return typeof i18n.getResource("nl", "translation", `server.${key}`) === "object" ? key : parent;
}

function values(group: string, data: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...data };
  for (const [key, value] of Object.entries(data)) {
    if (Array.isArray(value) && value.every(isServerText)) {
      out[key] = value.map((item) => serverText(nestedGroup(key, group), item)).join(", ");
    } else if (isServerText(value)) {
      out[key] = serverText(nestedGroup(key, group), value);
    }
  }
  if (typeof data.league === "string") out.leagueName = label(leagueNames, data.league);
  if (typeof data.type === "string") out.typeName = label(typeNames, data.type);
  if (typeof data.starts_at === "string" && typeof data.ends_at === "string") out.period = period(data.starts_at, data.ends_at);
  return out;
}

export function serverText(group: string, item: ServerText | string | null | undefined): string {
  if (item === null || item === undefined) return "";
  if (typeof item === "string") return item;
  if (!item.code) return item.text;
  const key = `server.${group}.${item.code}`;
  const data = item.data ?? {};
  const text = template(key, data.context, data.count);
  if (text === undefined) return item.text;
  const prepared = values(group, data);
  const needed = [...text.matchAll(PLACEHOLDER)].map((match) => match[1] ?? "");
  if (needed.some((name) => prepared[name] === undefined || prepared[name] === null)) return item.text;
  return i18n.t(key as "common.unknown", { ...prepared, context: data.context as string | undefined, interpolation: { escapeValue: false } });
}
