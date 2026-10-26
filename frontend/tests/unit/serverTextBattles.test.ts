import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "../../src/i18n";
import { type ServerText, serverText } from "../../src/lib/serverText";
import samples from "./fixtures/serverTextsBattles.json";

// Methods, notes, reasons and labels from the battle pages, the Pokémon analysis and the Pokédex,
// taken from the backend with the synthetic sample export and the test Game Data.
const groups = samples as Record<string, ServerText[]>;
const cases = Object.entries(groups).flatMap(([group, items]) => items.map((item) => [group, item.code ?? "", item] as const));
const DUTCH = /\b(de|het|een|en|van|met|Met|niet|geen|Geen|onbekend|inzetbaar|Beste|mag|voor|na|boven|zonder)\b/;

afterEach(async () => {
  await changeLanguage("nl");
});

describe("battle and analysis sentences from the server", () => {
  it("has samples for every group", () => {
    expect(Object.keys(groups).sort()).toEqual(["analysis", "battles", "pokedex", "readiness"]);
    for (const items of Object.values(groups)) expect(items.length).toBeGreaterThan(0);
  });

  it.each(cases)("%s %s reads exactly as the server's Dutch", (group, _code, item) => {
    expect(serverText(group, item)).toBe(item.text);
  });

  it.each(cases)("%s %s has an English sentence without gaps or Dutch", async (group, _code, item) => {
    await changeLanguage("en");
    const english = serverText(group, item);
    expect(english).not.toContain("{{");
    expect(english).not.toMatch(DUTCH);
  });

  it("formats numbers for the language", async () => {
    const stats: ServerText = { code: "GYM_STATS", text: "", data: { hp: 222, defense: 125 } };
    const shadow: ServerText = { code: "GYM_SHADOW", text: "", data: { multiplier: 0.8 } };
    await changeLanguage("en");
    expect(serverText("battles", stats)).toBe("222 HP and an effective Defense of 125.");
    expect(serverText("battles", shadow)).toContain("Defense × 0.80 according to");
  });

  it("falls back to the server's Dutch for an older server", async () => {
    await changeLanguage("en");
    expect(serverText("readiness", "Direct inzetbaar")).toBe("Direct inzetbaar");
    expect(serverText("battles", { code: "GYM_VALUE", text: "Verdedigingswaarde 67 van 100." })).toBe("Verdedigingswaarde 67 van 100.");
  });
});
