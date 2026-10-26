import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "../../src/i18n";
import nl from "../../src/i18n/nl.json";
import { conditionText } from "../../src/pages/battles/shared";

afterEach(async () => {
  await changeLanguage("nl");
});

describe("cup rules in Dutch", () => {
  it("describes the Fantasy Cup the way the game does", () => {
    expect(conditionText({ include: true, kind: "type", values: ["steel", "dragon", "fairy"], count: 3, alone: true })).toBe(
      "Alleen Pokémon met het type staal, draak of fee.",
    );
    expect(conditionText({ include: false, kind: "tag", values: ["mega"], count: 1, alone: true })).toBe("Geen Mega-evoluties.");
  });

  it("tells a species list apart from an extra species list", () => {
    expect(conditionText({ include: true, kind: "id", values: [], count: 250, alone: true })).toBe("Alleen 250 aangewezen soorten.");
    expect(conditionText({ include: true, kind: "id", values: [], count: 4, alone: false })).toBe("Daarnaast mogen 4 aangewezen soorten mee.");
    expect(conditionText({ include: false, kind: "id", values: [], count: 3, alone: true })).toBe("3 aangewezen soorten mogen niet mee.");
  });

  it("explains the Little Cup evolution rule and Pokédex ranges", () => {
    expect(conditionText({ include: true, kind: "evolution", values: [1], count: 1, alone: true })).toBe(
      "Alleen Pokémon die nog kunnen evolueren en zelf geen eerdere vorm hebben.",
    );
    expect(conditionText({ include: true, kind: "dex", values: [1, 151, 252, 386], count: 4, alone: true })).toBe(
      "Alleen Pokédex-nummers 1 t/m 151 of 252 t/m 386.",
    );
  });

  it("has a type name for use inside a rule for every type", () => {
    expect(Object.keys(nl.battles.shared.typeInRule).sort()).toEqual(Object.keys(nl.labels.types).sort());
  });
});

describe("cup rules in English", () => {
  it("joins types with 'or' and keeps their capitals", async () => {
    await changeLanguage("en");
    expect(conditionText({ include: true, kind: "type", values: ["steel", "dragon", "fairy"], count: 3, alone: true })).toBe(
      "Only Pokémon of type Steel, Dragon or Fairy.",
    );
    expect(conditionText({ include: false, kind: "tag", values: ["mega"], count: 1, alone: true })).toBe("No Mega Evolutions.");
    expect(conditionText({ include: true, kind: "tag", values: ["starter", "regional"], count: 2, alone: true })).toBe(
      "Only starter Pokémon or regional Pokémon.",
    );
  });

  it("uses singular and plural for species lists", async () => {
    await changeLanguage("en");
    expect(conditionText({ include: true, kind: "id", values: [], count: 250, alone: true })).toBe("Only 250 listed species.");
    expect(conditionText({ include: true, kind: "id", values: [], count: 1, alone: false })).toBe("1 listed species is also allowed.");
    expect(conditionText({ include: false, kind: "id", values: [], count: 3, alone: true })).toBe("3 listed species are not allowed.");
  });

  it("explains the Little Cup evolution rule and Pokédex ranges", async () => {
    await changeLanguage("en");
    expect(conditionText({ include: true, kind: "evolution", values: [1], count: 1, alone: true })).toBe(
      "Only Pokémon that can still evolve and have no earlier form.",
    );
    expect(conditionText({ include: true, kind: "dex", values: [1, 151, 252, 386], count: 4, alone: true })).toBe(
      "Only Pokédex numbers 1 to 151 or 252 to 386.",
    );
  });
});
