import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { changeLanguage } from "../../src/i18n";
import { AccountProvider } from "../../src/lib/account";
import { csvCell, toCsv } from "../../src/lib/csv";
import { actionList, type ActionList } from "../../src/lib/schemas";
import { actionListCsv } from "../../src/pages/cleanup/actionListText";
import { ChecklistPage } from "../../src/pages/cleanup/ChecklistPage";
import { pokemonFixture } from "./fixtures";

// The CSV and the printable checklist of the action list follow the chosen language (issue #31).
const data: ActionList = actionList.parse({
  list_name: "cleanup",
  count: 2,
  items: [
    {
      pokemon: pokemonFixture({ id: 1, cp: 512 }),
      action: "transfer",
      status: "open",
      reason: "Handmatig vastgestelde status",
      reason_texts: [{ code: "OVERRIDE", text: "Handmatig vastgestelde status" }],
      protection: [],
      protection_texts: [],
      still_in_inventory: true,
      blocked: null,
      needs_confirmation: null,
      executable: true,
    },
    {
      pokemon: pokemonFixture({ id: 2, cp: 777, source_pokemon_id: "12345678901234567890" }),
      action: "transfer",
      status: "open",
      reason: null,
      protection: ["Handmatig beschermd"],
      protection_texts: [{ code: "MANUAL", text: "Handmatig beschermd" }],
      still_in_inventory: true,
      blocked: "Handmatig beschermd",
      blocked_text: { code: "BLOCKED_MANUAL", text: "Handmatig beschermd" },
      needs_confirmation: null,
      executable: false,
    },
  ],
  search_hint: { note: "", safety_suffix: "", queries: [] },
});

function lines(csv: string): string[] {
  return csv.replace(/^\uFEFF/, "").trimEnd().split("\r\n");
}

afterEach(async () => {
  vi.unstubAllGlobals();
  await changeLanguage("nl");
});

describe("the CSV of the action list", () => {
  it("is Dutch in Dutch", () => {
    const [header, first, second] = lines(actionListCsv(data));
    expect(header).toBe("pokemon;vorm;cp;atk;def;sta;iv_pct;reden;bescherming;bron_pokemon_id;status;uitvoerbaar;geblokkeerd");
    expect(first).toBe("Pikachu;;512;15;15;15;100;Handmatig vastgestelde status;;18446744073709551615;open;ja;");
    expect(second).toContain(";nee;Handmatig beschermd");
  });

  it("is English in English, reasons included", async () => {
    await changeLanguage("en");
    const [header, first, second] = lines(actionListCsv(data));
    expect(header).toBe("pokemon;form;cp;atk;def;sta;iv_pct;reason;protection;source_pokemon_id;status;executable;held_back");
    expect(first).toBe("Pikachu;;512;15;15;15;100;Status set by hand;;18446744073709551615;open;yes;");
    expect(second).toBe("Pikachu;;777;15;15;15;100;;Protected by hand;12345678901234567890;open;no;Protected by hand");
  });

  it("keeps a 64-bit ID exact and never writes a formula", () => {
    expect(csvCell("18446744073709551615")).toBe("18446744073709551615");
    expect(csvCell("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
    expect(csvCell("-1+1")).toBe("'-1+1");
    expect(csvCell(-1)).toBe("-1");
    expect(csvCell('een "quote"; en meer')).toBe('"een ""quote""; en meer"');
    expect(toCsv([["a", null]]).startsWith("\uFEFF")).toBe(true);
  });
});

function renderChecklist() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/api/v1/accounts") ? [{ id: 7, nickname: "Ash" }] : data;
      return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/cleanup/checklist?account=7&sort=cp"]}>
        <AccountProvider>
          <ChecklistPage />
        </AccountProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the printable checklist", () => {
  it("lists only what can be done, and counts the rest", async () => {
    renderChecklist();
    expect(await screen.findByRole("heading", { name: "Cleanup-checklist" })).toBeInTheDocument();
    expect(screen.getByText("Handmatig vastgestelde status")).toBeInTheDocument();
    expect(screen.queryByText("12345678901234567890")).not.toBeInTheDocument();
    expect(screen.getByText(/1 Pokémon van de lijst staat hier niet op/)).toBeInTheDocument();
  });

  it("speaks English too", async () => {
    await changeLanguage("en");
    renderChecklist();
    expect(await screen.findByRole("heading", { name: "Cleanup checklist" })).toBeInTheDocument();
    expect(screen.getByText("Status set by hand")).toBeInTheDocument();
    expect(screen.getByText(/Sorted by CP, from low to high/)).toBeInTheDocument();
  });
});
