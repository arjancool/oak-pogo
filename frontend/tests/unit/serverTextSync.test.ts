import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "../../src/i18n";
import { type ServerText, serverText } from "../../src/lib/serverText";
import { storedText } from "../../src/lib/storedText";
import samples from "./fixtures/serverTextsSync.json";

// Sentences about imports, synchronisation, the account, Game Data and events, as the backend
// made them for the synthetic sample export, broken exports and datasets and the event calendar.
const groups = samples as Record<string, ServerText[]>;
const cases = Object.entries(groups).flatMap(([group, items]) => items.map((item) => [group, item.code ?? item.text, item] as const));
const DUTCH = /\b(de|het|een|niet|geen|bevat|ontbreekt|wordt|zijn|naar|bij|voor|deze|dit|regel|kolom|bron|verwacht|slechts|eigen|meldingen|opgeslagen)\b/i;

afterEach(async () => {
  await changeLanguage("nl");
});

describe("sentences about imports, sync, Game Data and events", () => {
  it("covers every group", () => {
    expect(Object.keys(groups).sort()).toEqual(["account", "events", "gamedata", "imports", "sync"]);
  });

  it.each(cases)("%s %s reads exactly as the server's Dutch", (group, _code, item) => {
    expect(serverText(group, item)).toBe(item.text);
  });

  it.each(cases)("%s %s has an English sentence without gaps", async (group, _code, item) => {
    await changeLanguage("en");
    const english = serverText(group, item);
    expect(english).not.toContain("{{");
    expect(english).not.toMatch(DUTCH);
  });

  it("formats numbers for the language", async () => {
    const drop = groups.imports?.find((item) => item.code === "SUSPICIOUS_DROP" && item.data?.previous === 1500);
    expect(serverText("imports", drop)).toContain("(1500)");
    await changeLanguage("en");
    expect(serverText("imports", drop)).toBe(
      "The export has 67 Pokémon, 1,433 fewer than the current inventory (1,500). Confirm that this is a complete export before OAK marks them as gone.",
    );
  });

  it("uses the singular and plural forms", async () => {
    await changeLanguage("en");
    expect(serverText("imports", { code: "ISSUES_TRUNCATED", text: "1 melding niet opgeslagen.", data: { count: 1 } })).toBe("1 message not stored.");
    expect(serverText("imports", { code: "ISSUES_TRUNCATED", text: "", data: { count: 1003 } })).toBe("1,003 messages not stored.");
  });

  it("shows the import's own message as the sync status", async () => {
    await changeLanguage("en");
    const status = groups.sync?.find((item) => item.code === "LAST_IMPORT_ERROR");
    expect(serverText("sync", status)).toBe("Invalid JSON at line 1, column 15.");
    // An import stored before OAK kept the data of its message: only the Dutch text is known.
    const old = { code: "LAST_IMPORT_ERROR", text: "Ongeldige JSON op regel 1, kolom 15.", data: { imports: { text: "Ongeldige JSON op regel 1, kolom 15." } } };
    expect(serverText("sync", old)).toBe("Ongeldige JSON op regel 1, kolom 15.");
  });

  it("tells the export's own section message apart from the classification", async () => {
    await changeLanguage("en");
    expect(storedText("imports", "ACCOUNT_SECTION_MISSING", "Sectie 'account' ontbreekt.", { context: "section" })).toBe("Section 'account' is missing.");
    expect(storedText("imports", "ACCOUNT_SECTION_MISSING", "De accountsectie ontbreekt, dus …", {})).toBe(
      "The account section is missing, so OAK cannot confirm that the export belongs to this account.",
    );
  });

  it("keeps the stored Dutch text of a message stored without data", async () => {
    await changeLanguage("en");
    // Before OAK kept the data, both messages above were stored with the same code and no data.
    expect(storedText("imports", "ACCOUNT_SECTION_MISSING", "Sectie 'account' ontbreekt.", null)).toBe("Sectie 'account' ontbreekt.");
    expect(storedText("imports", "SUSPICIOUS_DROP", "De export bevat 70 Pokémon …", undefined)).toBe("De export bevat 70 Pokémon …");
    expect(storedText("imports", "EMPTY_BODY", null, {})).toBe("");
  });
});
