import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LatestVersion, Summary } from "../../src/pages/admin/GameDataPage";
import type { GameDataVersion, RemoteCheck } from "../../src/lib/types";

// The date of the data per source and the last check for a newer version (issue #28).
const version: GameDataVersion = {
  id: 4,
  status: "active",
  origin: "download",
  created_at: "2026-10-28T08:00:00+00:00",
  activated_at: "2026-10-28T08:00:00+00:00",
  summary: {},
  sources: [],
  dates: [
    { source: "pokeminers", date: "2026-08-28T12:00:00+00:00", reason: null },
    {
      source: "pvpoke",
      date: null,
      reason: { code: "DATE_UNREACHABLE", text: "De datum van de bron was niet bereikbaar: ConnectError", data: { error: "ConnectError" } },
    },
  ],
  error: null,
};

function check(overrides: Partial<RemoteCheck>): RemoteCheck {
  return {
    checked_at: "2026-10-28T09:00:00+00:00",
    available: false,
    changed_sources: [],
    repair_needed: false,
    error: null,
    latest: { date: "2026-08-28T12:00:00+00:00", reason: null },
    ...overrides,
  };
}

describe("the date of the Game Data", () => {
  it("shows the date per source, or onbekend with the reason", () => {
    render(<Summary version={version} />);
    expect(screen.getByText("Game Master van")).toBeInTheDocument();
    expect(screen.getByText("28 aug 2026")).toBeInTheDocument();
    expect(screen.getByText("onbekend (De datum van de bron was niet bereikbaar: ConnectError)")).toBeInTheDocument();
  });

  it("keeps the result of the last check on the page", () => {
    const { rerender } = render(<LatestVersion check={check({})} active={version} />);
    expect(screen.getByText(/Nieuwste bij PokeMiners: Game Master van 28 aug 2026/)).toBeInTheDocument();
    expect(screen.getByText("Je hebt de nieuwste versie.")).toBeInTheDocument();
    rerender(<LatestVersion check={check({ available: true, changed_sources: ["pokeminers"] })} active={version} />);
    expect(screen.getByText("Er is een nieuwere versie (pokeminers).")).toBeInTheDocument();
  });

  it("says when the newest date is unknown, and why", () => {
    const reason = { code: "DATE_INVALID", text: "De bron gaf geen datum die OAK kan lezen.", data: {} };
    render(<LatestVersion check={check({ latest: { date: null, reason } })} active={version} />);
    expect(screen.getByText(/Game Master van onbekend \(De bron gaf geen datum die OAK kan lezen\.\)/)).toBeInTheDocument();
  });

  it("does not call an older check current after a newer version became active", () => {
    render(<LatestVersion check={check({ checked_at: "2026-10-27T09:00:00+00:00", available: true })} active={version} />);
    expect(screen.queryByText(/Er is een nieuwere versie/)).not.toBeInTheDocument();
    expect(screen.getByText(/Controleer opnieuw/)).toBeInTheDocument();
  });

  it("tells the owner to check when there is no result yet", () => {
    render(<LatestVersion check={null} active={version} />);
    expect(screen.getByText(/Nog niet gecontroleerd/)).toBeInTheDocument();
  });
});
