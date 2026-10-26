import { describe, expect, it } from "vitest";

import { bigId, pokedexSpecies, pokemonSummary } from "../../src/lib/schemas";
import { pokemonFixture } from "./fixtures";

describe("64-bit identifiers", () => {
  it("accepts the largest unsigned 64-bit ID as an exact string", () => {
    const parsed = pokemonSummary.parse(pokemonFixture({ source_pokemon_id: "18446744073709551615" }));
    expect(parsed.source_pokemon_id).toBe("18446744073709551615");
  });

  it("rejects a numeric ID, because JSON.parse already lost precision", () => {
    const raw = JSON.parse('{"id": 18446744073709551615}') as { id: number };
    expect(String(raw.id)).not.toBe("18446744073709551615");
    const result = pokemonSummary.safeParse({ ...pokemonFixture(), source_pokemon_id: raw.id });
    expect(result.success).toBe(false);
  });

  it("rejects tag IDs that are not decimal strings", () => {
    expect(bigId.safeParse("12345").success).toBe(true);
    expect(bigId.safeParse("-1").success).toBe(false);
    expect(bigId.safeParse("1e20").success).toBe(false);
    expect(bigId.safeParse("123456789012345678901").success).toBe(false);
    expect(pokemonSummary.safeParse(pokemonFixture({ tag_ids: ["1", "2"] })).success).toBe(true);
    expect(pokemonSummary.safeParse({ ...pokemonFixture(), tag_ids: [1] }).success).toBe(false);
  });
});

describe("Pokédex", () => {
  const step = {
    from_key: "147:DRATININORMAL",
    to_key: "148:DRAGONAIRNORMAL",
    to_name: "Dragonair",
    candy: 25,
    candy_purified: 22,
    item: null,
    item_name: null,
    item_cost: null,
    lure: null,
    lure_name: null,
    buddy_km: null,
    conditions: [],
    quest: null,
    no_candy_cost_via_trade: false,
  };
  const page = (sourceId: unknown) => ({
    game_data_version: 3,
    dex: 148,
    name: "Dragonair",
    forms: [{ key: "148:DRAGONAIRNORMAL", name: "Dragonair" }],
    form: {
      key: "148:DRAGONAIRNORMAL",
      name: "Dragonair",
      label: null,
      types: ["dragon"],
      stats: { atk: 163, def: 138, sta: 156 },
      class: null,
      family: "FAMILY_DRATINI",
      deployable: true,
      tradable: true,
      transferable: true,
      buddy_km: 5,
      third_move: { stardust: 50000, candy: 50 },
      shadow: null,
      mega: [],
    },
    moves: { fast: [], charged: [] },
    cp_table: [{ level: 20, label: { code: "RAID_RESEARCH", text: "Raid en onderzoek" }, cp: 1000 }],
    leagues: [],
    gym: null,
    evolves_from: [{ key: "147:DRATININORMAL", dex: 147, name: "Dratini" }],
    evolves_to: [],
    collection: {
      account_id: 1,
      owned_total: 0,
      owned: [],
      candidate_total: 1,
      candidates: [
        {
          pokemon: { ...pokemonFixture(), source_pokemon_id: sourceId },
          steps: [{ ...step, item_have: null }],
          total_candy: 25,
          cp_after: 900,
          hp_after: 100,
        },
      ],
      candy: { family: "FAMILY_DRATINI", quantity: null },
      items_known: false,
    },
  });

  it("keeps the IDs of candidates exact, and candy may be unknown", () => {
    const parsed = pokedexSpecies.parse(page("18446744073709551615"));
    expect(parsed.collection?.candidates[0]?.pokemon.source_pokemon_id).toBe("18446744073709551615");
    expect(parsed.collection?.candy.quantity).toBeNull();
    expect(pokedexSpecies.safeParse(page(1)).success).toBe(false);
  });
});
