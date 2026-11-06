import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "../../src/i18n";
import { itemName } from "../../src/lib/itemName";

// Item names follow the chosen language; English is the game's own text (issue #31).
describe("item names", () => {
  afterEach(async () => {
    await changeLanguage("nl");
  });

  const incubator = { nl: "Onbeperkte broedmachine", en: "Incubator ∞" };

  it("uses the name in the chosen language", async () => {
    expect(itemName(incubator, "Onbeperkte broedmachine")).toBe("Onbeperkte broedmachine");
    await changeLanguage("en");
    expect(itemName(incubator, "Onbeperkte broedmachine")).toBe("Incubator ∞");
  });

  it("falls back to the name the server gave", () => {
    expect(itemName(null, "Sinnoh Stone")).toBe("Sinnoh Stone");
    expect(itemName(undefined, null)).toBe("");
  });
});
