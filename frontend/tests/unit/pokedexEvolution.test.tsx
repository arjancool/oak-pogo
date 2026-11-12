import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { PokedexSpecies } from "../../src/lib/schemas";
import { Evolution } from "../../src/pages/pokedex/PokedexPage";

// A name from the Game Data is escaped in <Trans>, and shown as it is (issue #55).
function species(toName: string): PokedexSpecies {
  return {
    evolves_from: [],
    evolves_to: [
      {
        dex: 865,
        from_key: "FARFETCHD_GALARIAN",
        to_key: "SIRFETCHD",
        to_name: toName,
        candy: 50,
        candy_purified: null,
        item: null,
        item_name: null,
        item_names: null,
        item_cost: null,
        lure: null,
        lure_name: null,
        lure_names: null,
        buddy_km: null,
        conditions: [],
        quest: null,
        no_candy_cost_via_trade: false,
      },
    ],
  } as unknown as PokedexSpecies;
}

describe("evolution names in the Pokédex", () => {
  it("shows an apostrophe as it is", () => {
    render(
      <MemoryRouter>
        <Evolution data={species("Sirfetch'd")} onPick={() => undefined} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Sirfetch'd" })).toBeInTheDocument();
    expect(screen.queryByText(/&#39;/)).not.toBeInTheDocument();
  });

  it("never turns a name into markup", () => {
    const { container } = render(
      <MemoryRouter>
        <Evolution data={species("<b>vet</b>")} onPick={() => undefined} />
      </MemoryRouter>,
    );
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByRole("button", { name: "<b>vet</b>" })).toBeInTheDocument();
  });
});
