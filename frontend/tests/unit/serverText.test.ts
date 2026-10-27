import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "../../src/i18n";
import { type ServerText, serverText } from "../../src/lib/serverText";
import samples from "./fixtures/serverTexts.json";

// Reasons, warnings, protections and score parts from an analysis of the synthetic sample export.
const groups = samples as Record<string, ServerText[]>;
const cases = Object.entries(groups).flatMap(([group, items]) => items.map((item) => [group, item.code ?? "", item] as const));

afterEach(async () => {
  await changeLanguage("nl");
});

describe("sentences from the server", () => {
  it.each(cases)("%s %s reads exactly as the server's Dutch", (group, _code, item) => {
    expect(serverText(group, item)).toBe(item.text);
  });

  it.each(cases)("%s %s has an English sentence without gaps", async (group, _code, item) => {
    await changeLanguage("en");
    const english = serverText(group, item);
    expect(english).not.toContain("{{");
    expect(english).not.toMatch(/\b(voor|tegen|gevangen|exemplaar|bewaard|Bewaarscore|soortrang)\b/);
  });

  it("falls back to the server's Dutch when data is missing or the code is new", async () => {
    await changeLanguage("en");
    expect(serverText("reasons", { code: "WEAK_PVP", text: "Oud" })).toBe("Oud");
    expect(serverText("reasons", { code: "SOMETHING_NEW", text: "Nieuw" })).toBe("Nieuw");
    expect(serverText("reasons", { text: "Zonder code" })).toBe("Zonder code");
    expect(serverText("reasons", "Gewone tekst")).toBe("Gewone tekst");
  });

  it("explains a vintage Pokémon a bulk action skipped", async () => {
    const item: ServerText = { code: "VINTAGE_BULK", text: "Vintage 2017: nooit via een bulkactie", data: { year: 2017 } };
    expect(serverText("guard", item)).toBe(item.text);
    await changeLanguage("en");
    expect(serverText("guard", item)).toBe("Vintage 2017: never through a bulk action");
  });

  it("explains a rare size in the keep score and the warnings", async () => {
    const warning: ServerText = { code: "SIZE", text: "XXL: de grootste maken de meeste kans bij een showcase", data: { context: "xxl" } };
    const trait: ServerText = { code: "SIZE", text: "XXS", data: { context: "xxs" } };
    expect(serverText("warnings", warning)).toBe(warning.text);
    expect(serverText("traits", trait)).toBe("XXS");
    await changeLanguage("en");
    expect(serverText("warnings", warning)).toBe("XXL: the biggest ones have the best chance in a showcase");
    expect(serverText("traits", trait)).toBe("XXS");
  });

  it("formats numbers for the language", async () => {
    const item: ServerText = { code: "IV", text: "", data: { theirs: 93.75, mine: 62 } };
    expect(serverText("differences", item)).toBe("IV 93,8% tegen 62,0%");
    await changeLanguage("en");
    expect(serverText("differences", item)).toBe("IV 93.8% vs 62.0%");
  });
});
