import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "../../src/i18n";
import { originText } from "../../src/lib/origin";

// Only origins checked against a real export get a name (issue #32).
describe("the origin of a Pokémon", () => {
  afterEach(async () => {
    await changeLanguage("nl");
  });

  it("names the checked origins", () => {
    expect(originText("egg", 2)).toBe("Uitgebroed uit een ei");
    expect(originText("raid", 3)).toBe("Gevangen in een raid");
    expect(originText("rocket", 6)).toBe("Gevangen na een gevecht met Team GO Rocket");
    expect(originText("max_battle", 13)).toBe("Gevangen in een Max Battle");
  });

  it("shows an unchecked number as onbekend with the code, never a guess", () => {
    expect(originText(null, 4)).toBe("onbekend (code 4)");
    expect(originText("wild", 1)).toBe("onbekend (code 1)");
    expect(originText(null, null)).toBe("onbekend (niet in de export)");
  });

  it("speaks English too", async () => {
    await changeLanguage("en");
    expect(originText("egg", 2)).toBe("Hatched from an egg");
    expect(originText(null, 13)).toBe("unknown (code 13)");
  });
});
