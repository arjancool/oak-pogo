import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useTranslation } from "react-i18next";

import i18n, { changeLanguage, LANGUAGES, localeFor } from "../../src/i18n";
import en from "../../src/i18n/en.json";
import nl from "../../src/i18n/nl.json";
import { dateTime, num, relative } from "../../src/lib/format";

type Tree = { [key: string]: string | Tree };

function keys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string" ? [`${prefix}${key}`] : keys(value, `${prefix}${key}.`),
  );
}

function values(tree: Tree): string[] {
  return Object.values(tree).flatMap((value) => (typeof value === "string" ? [value] : values(value)));
}

const catalogs: Record<string, Tree> = { nl, en };

afterEach(async () => {
  await changeLanguage("nl");
});

describe("translations", () => {
  it("has a catalog for every language", () => {
    expect(Object.keys(catalogs).sort()).toEqual(Object.keys(LANGUAGES).sort());
  });

  it.each(Object.keys(LANGUAGES).filter((language) => language !== "nl"))("%s has exactly the Dutch keys", (language) => {
    const catalog = catalogs[language];
    expect(catalog).toBeDefined();
    expect(keys(catalog as Tree).sort()).toEqual(keys(nl).sort());
  });

  it("has no empty texts", () => {
    for (const catalog of Object.values(catalogs)) {
      expect(values(catalog).filter((text) => text.trim() === "")).toEqual([]);
    }
  });

  it("starts in Dutch", () => {
    expect(i18n.language).toBe("nl");
    expect(num(null)).toBe("onbekend");
    expect(document.documentElement.lang).toBe("nl");
  });

  it("switches texts and formatting together", async () => {
    await changeLanguage("en");
    expect(num(null)).toBe("unknown");
    expect(relative(null)).toBe("never");
    expect(num(1234567)).toBe("1,234,567");
    expect(dateTime("2026-10-25T12:00:00Z")).toMatch(/2026/);
    expect(document.documentElement.lang).toBe("en");
    function Label() {
      const { t } = useTranslation();
      return <span>{t("nav.events")}</span>;
    }
    render(<Label />);
    expect(screen.getByText("Upcoming events")).toBeInTheDocument();
  });

  it("follows the browser's own variant of the chosen language", () => {
    expect(localeFor("en", ["en-US", "nl-NL"])).toBe("en-US");
    expect(localeFor("nl", ["en-US", "nl-BE"])).toBe("nl-BE");
    expect(localeFor("en", ["nl-NL"])).toBe("en-GB");
  });
});

describe("labels for API codes", () => {
  it("follow the active language and still behave like a plain map", async () => {
    const { typeNames, leagueNames, statusLabels, label } = await import("../../src/lib/i18n");
    expect(typeNames.fairy).toBe("Fee");
    expect(label(statusLabels, "KEEP")).toBe("Bewaren");
    expect(label(statusLabels, "NEW_CODE")).toBe("NEW_CODE");
    expect(typeNames.unknown).toBeUndefined();
    expect("fairy" in typeNames).toBe(true);
    await changeLanguage("en");
    expect(typeNames.fairy).toBe("Fairy");
    expect(Object.entries(leagueNames)).toEqual([
      ["great", "Great League"],
      ["ultra", "Ultra League"],
      ["master", "Master League"],
    ]);
    expect(Object.keys(typeNames)).toHaveLength(18);
  });
});

describe("tags inside a translated sentence", () => {
  it("never use the name of a void HTML element, because that renders an empty element", () => {
    const voids = ["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"];
    for (const catalog of Object.values(catalogs)) {
      for (const text of values(catalog)) {
        for (const name of voids) expect(text, text).not.toContain(`<${name}>`);
      }
    }
  });
});
