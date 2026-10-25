import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmTransferDialog } from "../../src/components/cleanup/ConfirmTransferDialog";
import { CleanupBadge, PokemonSprite, ScoreMeter, StatusBadges, pokemonName } from "../../src/components/pokemon";
import { Button, Dialog, Pagination, SortHeader } from "../../src/components/ui";
import { spriteUrl } from "../../src/lib/settings";
import { pokemonFixture } from "./fixtures";

function withQuery(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function stubSettings(template: string | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(
        JSON.stringify({ sprite_source: template ? "custom" : "none", sprite_url_template: template, sprite_notice: "", timezone: "Europe/Amsterdam", base_url: "" }),
        { status: 200 },
      ),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("pokemonName", () => {
  it("adds the form label when there is one", () => {
    expect(pokemonName({ species_name: "Raichu", species_id: 26, form_label: "Alola" })).toBe("Raichu (Alola)");
    expect(pokemonName({ species_name: null, species_id: 26, form_label: null })).toBe("#26");
  });
});

describe("spriteUrl", () => {
  it("is null when sprites are disabled", () => {
    expect(spriteUrl(null, 25, false)).toBeNull();
    expect(spriteUrl("", 25, true)).toBeNull();
  });

  it("fills in the dex number and shiny path", () => {
    const template = "https://example.org/{shiny_path}{dex}.png";
    expect(spriteUrl(template, 25, false)).toBe("https://example.org/25.png");
    expect(spriteUrl(template, 25, true)).toBe("https://example.org/shiny/25.png");
  });
});

describe("PokemonSprite", () => {
  it("shows a generated dex badge when no sprite source is configured", async () => {
    stubSettings(null);
    const { container } = render(withQuery(<PokemonSprite dex={25} types={["electric"]} />));
    expect(await screen.findByText("025")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("loads an external image only when the owner configured one", async () => {
    stubSettings("https://example.org/{dex}.png");
    const { container } = render(withQuery(<PokemonSprite dex={25} />));
    await waitFor(() => expect(container.querySelector("img")?.getAttribute("src")).toBe("https://example.org/25.png"));
  });
});

describe("StatusBadges", () => {
  it("never calls a missing Pokémon transferred", () => {
    render(<StatusBadges pokemon={pokemonFixture({ inventory_status: "not_in_inventory", hundo: false })} />);
    expect(screen.getByText("Niet meer in inventaris")).toBeInTheDocument();
    expect(screen.queryByText(/transfer/i)).toBeNull();
  });

  it("shows shundo instead of separate shiny and hundo badges", () => {
    render(<StatusBadges pokemon={pokemonFixture({ shiny: true, hundo: true, shundo: true })} />);
    expect(screen.getByText("Shundo")).toBeInTheDocument();
    expect(screen.queryByText("Shiny")).toBeNull();
    expect(screen.queryByText("Hundo")).toBeNull();
  });
});

describe("CleanupBadge", () => {
  it("shows a dash without analysis", () => {
    render(<CleanupBadge status={null} />);
    expect(screen.getByText("–")).toBeInTheDocument();
  });
});

describe("Pagination", () => {
  it("shows the range and moves between pages", async () => {
    const onPage = vi.fn();
    render(<Pagination page={1} pageSize={50} total={120} onPage={onPage} />);
    expect(screen.getByText("1–50 van 120")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vorige" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Volgende" }));
    expect(onPage).toHaveBeenCalledWith(2);
  });
});

describe("vintage and scores", () => {
  it("shows a vintage badge with the catch year", () => {
    render(<StatusBadges pokemon={pokemonFixture({ vintage_year: 2017, caught_year: 2017, hundo: false })} />);
    expect(screen.getByText("Vintage 2017")).toBeInTheDocument();
  });

  it("marks an unknown catch date instead of assuming the Pokémon is new", () => {
    render(<StatusBadges pokemon={pokemonFixture({ caught_year: null, catch_date_known: false, hundo: false })} />);
    expect(screen.getByText("Vangstdatum onbekend")).toBeInTheDocument();
  });

  it("shows a score or 'onbekend'", () => {
    const { rerender } = render(<ScoreMeter label="Bewaarscore" value={64} />);
    expect(screen.getByText("64")).toBeInTheDocument();
    rerender(<ScoreMeter label="Bewaarscore" value={null} />);
    expect(screen.getByText("onbekend")).toBeInTheDocument();
  });
});

describe("ConfirmTransferDialog", () => {
  it("confirms only the Pokémon the user ticked one by one", async () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmTransferDialog
        items={[
          { pokemon_id: 1, name: "Pikachu", cp: 500, caught_year: 2024, kinds: ["favorite"], message: "Favoriet", new_reasons: [] },
          {
            pokemon_id: 2,
            name: "Eevee",
            cp: 400,
            caught_year: null,
            kinds: ["unknown_date", "protected"],
            message: "Vangstdatum onbekend; Beschermd: Beschermende tag 'Familie'",
            new_reasons: ["Beschermende tag 'Familie'"],
          },
        ]}
        onCancel={() => undefined}
        onConfirm={onConfirm}
      />,
    );
    expect(screen.getByText("Nieuw sinds je vorige bevestiging: Beschermende tag 'Familie'")).toBeInTheDocument();
    const confirm = screen.getByRole("button", { name: "0 bevestigen" });
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getAllByRole("checkbox")[0] as HTMLElement);
    await userEvent.click(screen.getByRole("button", { name: "1 bevestigen" }));
    expect(onConfirm).toHaveBeenCalledWith([1]);
  });
});

describe("SortHeader", () => {
  it("sorts descending first, then ascending", async () => {
    const onSort = vi.fn();
    const { rerender } = render(<SortHeader label="%" sortKey="percent" sort="-suitability" onSort={onSort} />);
    await userEvent.click(screen.getByRole("button", { name: "%" }));
    expect(onSort).toHaveBeenLastCalledWith("-percent");
    rerender(<SortHeader label="%" sortKey="percent" sort="-percent" onSort={onSort} />);
    await userEvent.click(screen.getByRole("button", { name: "%" }));
    expect(onSort).toHaveBeenLastCalledWith("percent");
  });

  it("sorts ascending first for a rank", async () => {
    const onSort = vi.fn();
    const { rerender } = render(<SortHeader label="IV-rang" sortKey="iv_rank" sort="-suitability" onSort={onSort} ascendingFirst />);
    await userEvent.click(screen.getByRole("button", { name: "IV-rang" }));
    expect(onSort).toHaveBeenLastCalledWith("iv_rank");
    rerender(<SortHeader label="IV-rang" sortKey="iv_rank" sort="iv_rank" onSort={onSort} ascendingFirst />);
    await userEvent.click(screen.getByRole("button", { name: "IV-rang" }));
    expect(onSort).toHaveBeenLastCalledWith("-iv_rank");
  });
});

function DialogHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Openen</Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Je nieuwe webhook-URL" footer={<Button onClick={() => setOpen(false)}>Ik heb hem opgeslagen</Button>}>
        <Button>Kopiëren</Button>
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  it("is named by its title, keeps focus inside and gives it back on Escape", async () => {
    const root = document.body.appendChild(Object.assign(document.createElement("div"), { id: "root" }));
    try {
      render(<DialogHarness />, { container: root });
      const opener = screen.getByRole("button", { name: "Openen" });
      await userEvent.click(opener);

      const dialog = screen.getByRole("dialog", { name: "Je nieuwe webhook-URL" });
      expect(dialog).toHaveAttribute("aria-modal", "true");
      expect(root).toHaveAttribute("inert");
      expect(screen.getByRole("button", { name: "Kopiëren" })).toHaveFocus();

      await userEvent.tab();
      expect(screen.getByRole("button", { name: "Ik heb hem opgeslagen" })).toHaveFocus();
      await userEvent.tab();
      expect(screen.getByRole("button", { name: "Sluiten" })).toHaveFocus();
      await userEvent.tab({ shift: true });
      expect(screen.getByRole("button", { name: "Ik heb hem opgeslagen" })).toHaveFocus();

      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(root).not.toHaveAttribute("inert");
      expect(opener).toHaveFocus();
    } finally {
      root.remove();
    }
  });

  it("returns focus after closing with a footer button", async () => {
    render(<DialogHarness />);
    const opener = screen.getByRole("button", { name: "Openen" });
    await userEvent.click(opener);
    await userEvent.click(screen.getByRole("button", { name: "Ik heb hem opgeslagen" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});
