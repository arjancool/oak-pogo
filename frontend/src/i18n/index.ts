/** Translations (ADR-0025). Dutch is the source language: every key starts in nl.json, and a
 * test checks that every other language has the same keys. */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { setLocale } from "../lib/format";
import en from "./en.json";
import nl from "./nl.json";

export const LANGUAGES = { nl: "Nederlands", en: "English" } as const;
export type Language = keyof typeof LANGUAGES;
// For a browser that prefers neither language.
export const DEFAULT_LANGUAGE: Language = "nl";

const STORAGE_KEY = "oak.language";
const LOCALES: Record<Language, string> = { nl: "nl-NL", en: "en-GB" };

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: { translation: typeof nl };
  }
}

export function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && Object.hasOwn(LANGUAGES, value);
}

/** Number and date formatting for a language. A browser locale of the same language wins, so
 * an English user in the United States keeps their own date order. */
export function localeFor(language: Language, preferred: readonly string[] = navigator.languages ?? []): string {
  return preferred.find((tag) => tag.toLowerCase().split("-")[0] === language) ?? LOCALES[language];
}

/** The first language of the browser that OAK has, or Dutch (ADR-0025). */
export function browserLanguage(preferred: readonly string[] = navigator.languages ?? []): Language {
  for (const tag of preferred) {
    const base = tag.toLowerCase().split("-")[0];
    if (isLanguage(base)) return base;
  }
  return DEFAULT_LANGUAGE;
}

/** A language chosen on this device wins; on a first visit OAK follows the browser. The choice
 * saved with the user wins over both once the user is known (lib/auth.tsx). */
export function initialLanguage(stored: Language | null, preferred?: readonly string[]): Language {
  return stored ?? browserLanguage(preferred);
}

function storedLanguage(): Language | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return isLanguage(value) ? value : null;
  } catch {
    return null;
  }
}

function apply(language: Language): void {
  setLocale(localeFor(language));
  document.documentElement.lang = language;
}

void i18n.use(initReactI18next).init({
  resources: { nl: { translation: nl }, en: { translation: en } },
  lng: initialLanguage(storedLanguage()),
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: Object.keys(LANGUAGES),
  // React escapes text itself.
  interpolation: { escapeValue: false },
  initAsync: false,
});
apply(isLanguage(i18n.language) ? i18n.language : DEFAULT_LANGUAGE);
i18n.on("languageChanged", (language) => {
  if (isLanguage(language)) apply(language);
});

/** Switch the language on this device. The caller saves it with the user as well. */
export async function changeLanguage(language: Language): Promise<void> {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Without storage the choice still holds for this visit, and the server keeps it per user.
  }
  await i18n.changeLanguage(language);
}

export default i18n;
