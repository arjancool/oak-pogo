import { describe, expect, it } from "vitest";

import { bigId, pokemonSummary } from "../../src/lib/schemas";
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
