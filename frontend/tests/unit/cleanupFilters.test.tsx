import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../src/lib/api";
import { CleanupPage } from "../../src/pages/cleanup/CleanupPage";

// The filters in the Cleanup Manager, behind the same filter button as in the Pokémon Box.
vi.mock("../../src/lib/account", () => ({ useAccount: () => ({ accountId: 1, loading: false }) }));
vi.mock("../../src/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../src/lib/api")>();
  const page = {
    total: 0,
    page: 1,
    page_size: 50,
    items: [],
    analysis: { run_id: 1, computed_at: null, engine_version: "test", game_data_version: 1, rules_hash: null, stale: false, pending: false, counts: {} },
  };
  return { ...actual, api: { ...actual.api, get: vi.fn(() => Promise.resolve(page)), post: vi.fn() } };
});

function lastParams(): Record<string, unknown> {
  const calls = vi.mocked(api.get).mock.calls.filter(([path]) => path === "/api/v1/cleanup/recommendations");
  return (calls.at(-1)?.[1] ?? {}) as Record<string, unknown>;
}

function renderCleanup(url = "/cleanup") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[url]}>
        <CleanupPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the filters in the Cleanup Manager", () => {
  beforeEach(() => vi.mocked(api.get).mockClear());

  it("hides the only copies of a species with two clicks", async () => {
    renderCleanup();
    const button = await screen.findByRole("button", { name: "Filters" });
    await waitFor(() => expect(lastParams()).toMatchObject({ only_copy: null, favorite: null, vintage: null, gym: null }));
    expect(screen.queryByRole("button", { name: /^Enig exemplaar/ })).toBeNull();

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(screen.getByRole("button", { name: "Enig exemplaar: geen filter" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ only_copy: "true" }));
    fireEvent.click(screen.getByRole("button", { name: "Enig exemplaar: alleen deze" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ only_copy: "false" }));
    expect(screen.getByRole("button", { name: "Filters (1)" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Wissen" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ only_copy: null }));
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
  });

  it("opens with the filters from the link, and a gym choice looks at every status", async () => {
    renderCleanup("/cleanup?favorite=false&vintage=true");
    await waitFor(() => expect(lastParams()).toMatchObject({ favorite: "false", vintage: "true", status: "TRANSFER_CANDIDATE" }));
    expect(screen.getByRole("button", { name: "Filters (2)" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Favoriet: juist niet" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Beste gymverdediger per soort" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ gym: "best", status: null }));
    expect(screen.getByRole("button", { name: "Beste gymverdediger per soort" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Beste gymverdediger per soort" }));
    await waitFor(() => expect(lastParams()).toMatchObject({ gym: null }));
  });
});
