import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import "../../src/i18n";
import { RequireAccount } from "../../src/components/layout/RequireAccount";

vi.mock("../../src/lib/account", () => ({ useAccount: () => ({ accountId: null, loading: false }) }));

describe("without a trainer account", () => {
  it("links to the place where you create one, with the link text inside the link", () => {
    render(
      <MemoryRouter>
        <RequireAccount>{() => null}</RequireAccount>
      </MemoryRouter>,
    );
    const link = screen.getByRole("link", { name: "Beheer → Traineraccounts" });
    expect(link.getAttribute("href")).toBe("/admin/accounts");
  });
});
