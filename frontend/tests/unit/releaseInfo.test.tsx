import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ReleaseStatus } from "../../src/lib/types";
import { ReleaseInfo } from "../../src/pages/admin/SettingsPage";

// The newest OAK release next to the running version (issue #29).
function release(status: "newer" | "same" | "ahead", version: string): ReleaseStatus {
  return {
    enabled: true,
    current: "2.0.0",
    checked_at: "2026-11-05T10:00:00+00:00",
    status,
    latest: { version, published_at: "2026-10-27T20:45:35Z", url: `https://github.com/arjancool/oak-pogo/releases/tag/v${version}` },
    reason: null,
  };
}

describe("the newest release", () => {
  it("links to a newer release", () => {
    render(<ReleaseInfo release={release("newer", "2.1.0")} />);
    const link = screen.getByRole("link", { name: "Versie 2.1.0 is beschikbaar, van 27 okt 2026" });
    expect(link).toHaveAttribute("href", "https://github.com/arjancool/oak-pogo/releases/tag/v2.1.0");
  });

  it("says when the running version is the newest", () => {
    render(<ReleaseInfo release={release("same", "2.0.0")} />);
    expect(screen.getByText("Je hebt de nieuwste versie (2.0.0, 27 okt 2026)")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows onbekend with the reason when GitHub is not reachable", () => {
    const reason = { code: "RELEASE_UNREACHABLE", text: "GitHub was niet bereikbaar: ConnectError", data: { error: "ConnectError" } };
    render(<ReleaseInfo release={{ enabled: true, current: "2.0.0", checked_at: "2026-11-05T10:00:00+00:00", status: "unknown", latest: null, reason }} />);
    expect(screen.getByText("onbekend (GitHub was niet bereikbaar: ConnectError)")).toBeInTheDocument();
  });

  it("says the check is switched off", () => {
    render(<ReleaseInfo release={{ enabled: false, current: "2.0.0" }} />);
    expect(screen.getByText("niet opgevraagd (OAK_RELEASE_CHECK=false)")).toBeInTheDocument();
  });
});
