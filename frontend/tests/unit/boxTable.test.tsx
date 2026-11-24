import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../src/lib/api";
import { BoxPage } from "../../src/pages/pokemon/BoxPage";

// The table on the Pokémon Box page: columns can be hidden and rows ticked. This guards the
// switch to TanStack Table 9, where the table only registers what it uses.
vi.mock("../../src/lib/account", () => ({ useAccount: () => ({ accountId: 1, loading: false }) }));
vi.mock("../../src/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/lib/api")>();
  const { pokemonFixture } = await import("./fixtures");
  const items = [pokemonFixture(), pokemonFixture({ id: 2, source_pokemon_id: "2", species_id: 1, species_name: "Bulbasaur", cp: 300 })];
  const get = (path: string) =>
    Promise.resolve(
      path === "/api/v1/pokemon"
        ? { total: items.length, page: 1, page_size: 50, items, game_data_version: 1 }
        : { species: [], years: [], families: [], types: [], tags: [] },
    );
  return { ...actual, api: { ...actual.api, get: vi.fn(get), post: vi.fn() } };
});

const COLUMNS_KEY = "oak.boxColumns";

function renderBox() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BoxPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function headers(): string[] {
  return screen.getAllByRole("columnheader").map((th) => th.textContent ?? "");
}

function row(name: string): HTMLElement {
  const tr = screen.getByRole("link", { name: new RegExp(name) }).closest("tr");
  if (!tr) throw new Error(`no row for ${name}`);
  return tr;
}

describe("the table in the Pokémon Box", () => {
  beforeEach(() => window.localStorage.clear());

  it("shows a row for every Pokémon in the order of the server", async () => {
    renderBox();
    await screen.findByRole("link", { name: /Pikachu/ });
    const names = screen.getAllByRole("row").slice(1).map((tr) => within(tr).getByRole("link").textContent ?? "");
    expect(names).toHaveLength(2);
    expect(names[0]).toContain("Pikachu");
    expect(names[1]).toContain("Bulbasaur");
    expect(within(row("Pikachu")).getByText("512")).toBeInTheDocument();
    // A header given as text and one given as a component both show up.
    expect(headers()).toHaveLength(14);
    expect(headers()).toEqual(expect.arrayContaining(["IV's", "Aanvallen", "Type", "CP", "Level"]));
  });

  it("hides a column from the column menu and remembers it", async () => {
    renderBox();
    await screen.findByRole("link", { name: /Pikachu/ });
    expect(headers()).toContain("Level");

    const menu = screen.getByText("Kolommen").closest("details");
    if (!menu) throw new Error("no column menu");
    fireEvent.click(screen.getByText("Kolommen"));
    // The selection and the name always stay, so they are not in the menu.
    expect(within(menu).getAllByRole("checkbox")).toHaveLength(12);
    expect(within(menu).queryByRole("checkbox", { name: "Pokémon" })).toBeNull();

    fireEvent.click(within(menu).getByRole("checkbox", { name: "Level" }));
    expect(headers()).not.toContain("Level");
    expect(within(row("Pikachu")).getAllByRole("cell")).toHaveLength(13);
    expect(JSON.parse(window.localStorage.getItem(COLUMNS_KEY) ?? "{}")).toEqual({ level: false });

    fireEvent.click(within(menu).getByRole("checkbox", { name: "Level" }));
    expect(headers()).toContain("Level");
    expect(within(row("Pikachu")).getAllByRole("cell")).toHaveLength(14);
  });

  it("starts with the columns hidden earlier", async () => {
    window.localStorage.setItem(COLUMNS_KEY, JSON.stringify({ cp: false }));
    renderBox();
    await screen.findByRole("link", { name: /Pikachu/ });
    expect(headers()).not.toContain("CP");
    expect(within(row("Pikachu")).queryByText("512")).toBeNull();
  });

  it("filters with the same filter button as the Cleanup Manager", async () => {
    renderBox();
    await screen.findByRole("link", { name: /Pikachu/ });
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.click(screen.getByRole("button", { name: "Favoriet: geen filter" }));
    await waitFor(() =>
      expect(vi.mocked(api.get).mock.calls.filter(([path]) => path === "/api/v1/pokemon").at(-1)?.[1]).toMatchObject({ favorite: "true" }),
    );
    expect(screen.getByRole("button", { name: "Filters (1)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Favoriet: alleen deze" })).toBeInTheDocument();
  });

  it("ticks one row, and all rows with the box in the header", async () => {
    renderBox();
    await screen.findByRole("link", { name: /Pikachu/ });

    fireEvent.click(within(row("Pikachu")).getByRole("checkbox"));
    expect(screen.getByText("1 geselecteerd")).toBeInTheDocument();
    expect(within(row("Pikachu")).getByRole("checkbox")).toBeChecked();
    expect(within(row("Bulbasaur")).getByRole("checkbox")).not.toBeChecked();

    const [header] = screen.getAllByRole("columnheader");
    if (!header) throw new Error("no header");
    fireEvent.click(within(header).getByRole("checkbox"));
    expect(screen.getByText("2 geselecteerd")).toBeInTheDocument();
    expect(within(row("Bulbasaur")).getByRole("checkbox")).toBeChecked();
  });
});
