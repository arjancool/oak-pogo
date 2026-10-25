import { describe, expect, it } from "vitest";

import { conditionText } from "../../src/pages/battles/shared";

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
});
