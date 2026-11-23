import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../src/lib/api";
import { CleanupPage } from "../../src/pages/cleanup/CleanupPage";

// The filter in the Cleanup Manager that shows or hides the only copy of a species.
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

describe("the filter for the only copy of a species", () => {
  beforeEach(() => vi.mocked(api.get).mockClear());

  it("sends nothing until a choice is made, then only_copy", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <CleanupPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const select = await screen.findByRole("combobox", { name: "Enige exemplaren van een soort" });
    await waitFor(() => expect(lastParams()).toMatchObject({ only_copy: null }));
    expect([...select.querySelectorAll("option")].map((o) => o.textContent)).toEqual([
      "Enige exemplaren: alle",
      "Enige exemplaren: alleen",
      "Enige exemplaren: zonder",
    ]);

    fireEvent.change(select, { target: { value: "false" } });
    await waitFor(() => expect(lastParams()).toMatchObject({ only_copy: "false" }));
    fireEvent.change(select, { target: { value: "true" } });
    await waitFor(() => expect(lastParams()).toMatchObject({ only_copy: "true" }));
  });
});
