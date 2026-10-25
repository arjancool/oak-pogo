import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

/**
 * The full first-use flow from the specification: owner setup, trainer account, webhook,
 * a PGSharp export through the webhook, the Pokémon Box, cleanup protection and a repeated
 * import that must not create duplicates. Uses the synthetic sample export (67 Pokémon and
 * 3 eggs) and the Game Data test subset.
 */

const SAMPLE = fileURLToPath(new URL("../../../fixtures/pgsharp/PGSStats.sample.json", import.meta.url));
const SAMPLE_POKEMON = 67;
const SAMPLE_FAVORITES = 7;
const SAMPLE_VINTAGE = 13;
const SAMPLE_MAGIKARP = 6;
const PASSWORD = "e2e wachtwoord voor de test";
const IMPORT_TIMEOUT = 45_000;

test.describe.configure({ mode: "serial" });

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

async function waitForImports(page: Page, count: number) {
  await expect(async () => {
    await page.goto("/admin/sync");
    await expect(page.getByText("Volledig verwerkt")).toHaveCount(count, { timeout: 2_000 });
  }).toPass({ timeout: IMPORT_TIMEOUT });
}

test("PGSharp export via webhook ends up in the Pokémon Box without duplicates", async ({ page, request }) => {
  const errors = trackErrors(page);

  // 1. First use: create the owner.
  await page.goto("/");
  await expect(page).toHaveURL(/\/setup$/);
  await page.getByLabel("Gebruikersnaam").fill("eigenaar");
  await page.getByLabel("Wachtwoord", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Herhaal wachtwoord").fill(PASSWORD);
  await page.getByRole("button", { name: "Eigenaar aanmaken", exact: true }).click();
  await expect(page.getByText("Nog geen traineraccount")).toBeVisible();

  // 2. Create a trainer account.
  await page.getByRole("link", { name: "Traineraccounts", exact: true }).click();
  await page.getByLabel("Naam", { exact: true }).fill("Hoofdaccount");
  await page.getByRole("button", { name: "Aanmaken", exact: true }).click();
  await expect(page.getByText("nog niet gekoppeld")).toBeVisible();

  // 3. Generate the webhook URL. It is shown exactly once.
  await page.getByRole("link", { name: "PGSharp Sync", exact: true }).click();
  await page.getByRole("button", { name: "Webhook-URL maken", exact: true }).click();
  //    The dialog is named by its title and keeps keyboard focus inside (audit A14).
  const dialog = page.getByRole("dialog", { name: "Je nieuwe webhook-URL" });
  await expect(dialog).toContainText("Kopieer deze URL nu");
  const focusInside = () => dialog.evaluate((el) => el.contains(el.ownerDocument.activeElement));
  expect(await focusInside()).toBe(true);
  for (const key of ["Tab", "Tab", "Tab", "Shift+Tab", "Shift+Tab", "Shift+Tab", "Shift+Tab"]) {
    await page.keyboard.press(key);
    expect(await focusInside(), key).toBe(true);
  }
  const webhookUrl = (await dialog.locator("code").innerText()).trim();
  expect(webhookUrl).toMatch(/\/api\/v1\/ingest\/pgsharp\/oakwh_/);
  await dialog.getByRole("button", { name: "Ik heb hem opgeslagen", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Nieuwe URL maken", exact: true })).toBeFocused();
  await expect(page.getByText("oakwh_").first()).toContainText("••••");

  // 4. PGSharp sends the export.
  const body = readFileSync(SAMPLE);
  const first = await request.post(webhookUrl, { data: body, headers: { "Content-Type": "application/json" } });
  expect(first.status()).toBe(202);
  expect((await first.json()).status).toBe("queued");
  await waitForImports(page, 1);

  // 5. The Box shows every Pokémon, without the eggs.
  await page.getByRole("link", { name: "Pokémon Box", exact: true }).click();
  await expect(page.getByText(`1–50 van ${SAMPLE_POKEMON}`)).toBeVisible();
  await expect(page.getByRole("link", { name: "Mewtwo" })).toBeVisible();
  await page.getByLabel("Zoeken").fill("magikarp");
  await expect(page.getByText(`1–${SAMPLE_MAGIKARP} van ${SAMPLE_MAGIKARP}`)).toBeVisible();

  // 6. Vintage Pokémon (2016–2019) are protected; favorites are not protected for being favorite
  //    and are never a direct transfer candidate (ADR-0019).
  await expect(async () => {
    await page.goto("/pokemon?vintage=true");
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(SAMPLE_VINTAGE, { timeout: 2_000 });
    for (const row of await rows.all()) {
      await expect(row.getByText("Beschermd", { exact: true }).last()).toBeVisible({ timeout: 2_000 });
      await expect(row.getByText(/^Vintage 20(16|17|18|19)$/)).toBeVisible({ timeout: 2_000 });
    }
  }).toPass({ timeout: IMPORT_TIMEOUT });
  await page.goto("/pokemon?favorite=true");
  await expect(page.locator("tbody tr")).toHaveCount(SAMPLE_FAVORITES);
  await expect(page.locator("tbody").getByText("Transfer-kandidaat")).toHaveCount(0);
  await page.goto("/cleanup?status=ALL&favorite=true");
  await expect(page.getByText("Bewaarscore", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Bruikbaarheid", { exact: true }).first()).toBeVisible();

  // 7. The same export again is recognised as a duplicate and changes nothing.
  const again = await request.post(webhookUrl, { data: body, headers: { "Content-Type": "application/json" } });
  expect(again.status()).toBe(202);
  expect((await again.json()).status).toBe("duplicate");
  await page.goto("/admin/sync");
  await expect(page.getByText("Al eerder ontvangen")).toBeVisible();

  // 8. A newer export of the same inventory is imported, but creates no duplicate Pokémon.
  const newer = JSON.parse(body.toString("utf-8")) as Record<string, unknown>;
  newer.time = "2026-10-23 12:00:00 CEST";
  const third = await request.post(webhookUrl, { data: newer });
  expect(third.status()).toBe(202);
  await waitForImports(page, 2);
  await page.goto("/pokemon");
  await expect(page.getByText(`1–50 van ${SAMPLE_POKEMON}`)).toBeVisible();

  // 9. A wrong token is rejected without revealing anything.
  const wrong = await request.post(webhookUrl.replace(/.{6}$/, "xxxxxx"), { data: newer });
  expect(wrong.status()).toBe(404);

  expect(errors).toEqual([]);
});

test("every page renders without errors", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/login");
  await page.getByLabel("Gebruikersnaam").fill("eigenaar");
  await page.getByLabel("Wachtwoord").fill(PASSWORD);
  await page.getByRole("button", { name: "Inloggen", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Overzicht" })).toBeVisible();

  const pages: [string, string][] = [
    ["/", "Overzicht"],
    ["/pokemon", "Pokémon Box"],
    ["/pokedex", "Pokédex"],
    ["/pokedex/149", "Pokédex"],
    ["/compare", "Vergelijken"],
    ["/cleanup", "Cleanup Manager"],
    ["/planner", "investeringsplanner"],
    ["/events", "Komende events"],
    ["/battles/great", "Great League"],
    ["/battles/cups", "Cups"],
    ["/battles/fantasy-1500", "Fantasy Cup"],
    ["/battles/team-builder", "Team Builder"],
    ["/battles/raids", "Raids"],
    ["/battles/rocket", "Team GO Rocket"],
    ["/battles/max", "Max Battles"],
    ["/battles/gyms", "Gymverdedigers"],
    ["/trainer", "Trainerstatistieken"],
    ["/items", "Item Bag"],
    ["/resources", "Stardust & Candy"],
    ["/history", "Historie"],
    ["/admin/accounts", "Traineraccounts"],
    ["/admin/sync", "PGSharp Sync"],
    ["/admin/gamedata", "Game Data"],
    ["/admin/settings", "Instellingen"],
    ["/admin/backups", "Back-ups"],
  ];
  for (const [path, heading] of pages) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading }), path).toBeVisible();
    await page.waitForLoadState("networkidle");
  }

  // The owner adds a user and later sets a new password for them.
  await page.goto("/admin/settings");
  const users = page.locator("section").filter({ has: page.getByRole("heading", { name: "Gebruikers", exact: true }) });
  await users.getByLabel("Gebruikersnaam").fill("tweede");
  await users.getByLabel("Wachtwoord", { exact: true }).fill("een wachtwoord voor tweede");
  await users.getByRole("button", { name: "Toevoegen", exact: true }).click();
  await expect(page.getByText("Gebruiker aangemaakt.")).toBeVisible();
  await page.getByRole("button", { name: "Wachtwoord opnieuw instellen", exact: true }).click();
  const reset = page.getByRole("dialog", { name: "Wachtwoord van tweede opnieuw instellen" });
  await reset.getByLabel("Nieuw wachtwoord", { exact: true }).fill("een nieuw wachtwoord voor tweede");
  await reset.getByLabel("Herhaal nieuw wachtwoord").fill("een nieuw wachtwoord voor tweede");
  await reset.getByRole("button", { name: "Opnieuw instellen", exact: true }).click();
  await expect(page.getByText(/Nieuw wachtwoord ingesteld voor tweede/)).toBeVisible();

  // Gym defenders: one list of Pokémon the Game Data allows in a gym. Mewtwo is Legendary.
  await page.goto("/battles/gyms");
  await expect(page.getByText(/sterkste verdedigers/)).toBeVisible();
  await expect(page.locator("ol").getByRole("link", { name: "Mewtwo" })).toHaveCount(0);

  // Open the detail page of the first Pokémon in the Box.
  await page.goto("/pokemon");
  await page.getByRole("link", { name: "Mewtwo" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Mewtwo");
  await page.waitForLoadState("networkidle");

  // Sort the Great League table on IV rank: the best rank comes first and the URL keeps the choice.
  await page.goto("/battles/great");
  await page.getByRole("button", { name: "IV-rang", exact: true }).click();
  await expect(page).toHaveURL(/sort=iv_rank/);
  await expect
    .poll(async () => {
      const ranks = (await page.locator("tbody tr td:nth-child(4)").allInnerTexts()).map((text) => Number(text.replace(/\D/g, "")));
      return ranks.length > 1 && ranks.every((rank, i) => i === 0 || (ranks[i - 1] ?? 0) <= rank);
    })
    .toBe(true);

  // Sort the raid counters on current DPS, lowest first. The number keeps the DPS position.
  await page.goto("/battles/raids");
  await expect(page.getByRole("heading", { name: "Beste algemene raid-aanvallers" })).toBeVisible();
  await page.getByRole("button", { name: "DPS nu", exact: true }).click();
  await expect(page).toHaveURL(/sort=dps/);
  const dps = (await page.locator("tbody tr td:nth-child(3)").allInnerTexts()).map((text) => Number(text.replace(/\./g, "").replace(",", ".")));
  expect(dps.length).toBeGreaterThan(1);
  expect(dps).toEqual([...dps].sort((a, b) => a - b));
  const ranks = (await page.locator("tbody tr td:nth-child(1)").allInnerTexts()).map(Number);
  expect([...ranks].sort((a, b) => a - b)).toEqual(ranks.map((_, i) => i + 1));
  expect(ranks[0]).toBeGreaterThan(1);

  expect(errors).toEqual([]);
});

test("planner and upload handle what the server sends back", async ({ page }) => {
  const errors = trackErrors(page);
  // The browser logs the mocked 413 below as a failed resource; that line is expected.
  const unexpected = () => errors.filter((message) => !message.startsWith("Failed to load resource"));
  await page.goto("/login");
  await page.getByLabel("Gebruikersnaam").fill("eigenaar");
  await page.getByLabel("Wachtwoord").fill(PASSWORD);
  await page.getByRole("button", { name: "Inloggen", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Overzicht" })).toBeVisible();

  // The planner leaves evolutions out once they are no longer allowed, also from a cached
  // result and after switching league (audit A12).
  const calls: string[] = [];
  await page.route("**/api/v1/battles/league/*?**", async (route) => {
    const url = new URL(route.request().url());
    const league = url.pathname.split("/").pop() ?? "";
    const readiness = url.searchParams.get("readiness") ?? "";
    calls.push(`${league}:${readiness}`);
    const candidate = {
      pokemon_id: 1,
      species_id: 129,
      shiny: false,
      types: ["water"],
      name: "PlanMagikarp",
      form_label: null,
      cp: 100,
      target: `gyarados-${league}`,
      is_evolution: true,
      iv_rank: 1,
      percent: 100,
      best_cp: 1499,
      readiness: "evolution",
      species_rank: 5,
      cost: { stardust: 1000, candy: 400, xl_candy: 0 },
      moveset_quality: "good",
      recommended_moveset: [],
      suitability: 90,
    };
    // A server that ignores the filter: the planner must still drop the evolution itself.
    await route.fulfill({ json: { items: [candidate] } });
  });
  const magikarp = page.getByRole("link", { name: /PlanMagikarp/ });
  const evolutions = page.getByRole("checkbox", { name: "Evoluties toestaan" });
  await page.goto("/planner");
  await expect(magikarp).toBeVisible();
  await evolutions.uncheck();
  await expect(magikarp).toHaveCount(0);
  await expect.poll(() => calls).toContain("great:power_up");
  await evolutions.check();
  await expect(magikarp).toBeVisible();
  await evolutions.uncheck();
  await page.getByLabel("Doel").selectOption("ultra");
  await expect.poll(() => calls).toContain("ultra:power_up");
  await expect(magikarp).toHaveCount(0);
  await evolutions.check();
  await expect(magikarp).toBeVisible();
  await page.unroute("**/api/v1/battles/league/*?**");

  // A proxy's HTML error page ends the upload with a readable message (audit A13).
  await page.route("**/api/v1/imports/upload", (route) =>
    route.fulfill({ status: 413, contentType: "text/html", body: "<!doctype html><h1>413 Request Entity Too Large</h1>" }),
  );
  await page.goto("/admin/sync");
  await page.getByTestId("upload-input").setInputFiles({ name: "synthetic.json", mimeType: "application/json", buffer: Buffer.from("{}") });
  await expect(page.getByRole("alert")).toContainText("te groot");
  await expect(page.getByLabel("Uploadvoortgang")).toHaveCount(0);

  expect(unexpected()).toEqual([]);
});
