import { afterEach, describe, expect, it } from "vitest";

import { changeLanguage } from "../../src/i18n";
import en from "../../src/i18n/en.json";
import { ApiError, errorMessage, readResponse } from "../../src/lib/api";
import samples from "./fixtures/serverErrors.json";

// Error bodies the backend sent for requests that fail, from its test fixtures.
type Sample = { status: number; error: { code: string; message: string; details: unknown; data: Record<string, unknown> } };
const cases = (samples as Sample[]).map((sample) => [sample.error.code, sample.error.data.context ?? "", sample] as const);

function failure(sample: Sample): unknown {
  try {
    readResponse(sample.status, JSON.stringify({ error: sample.error }));
  } catch (error) {
    return error;
  }
  throw new Error("readResponse accepted an error response");
}

afterEach(async () => {
  await changeLanguage("nl");
});

describe("error messages from the server", () => {
  it.each(cases)("%s %s reads exactly as the server's Dutch", (_code, _context, sample) => {
    const error = failure(sample);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).data).toEqual(sample.error.data);
    expect(errorMessage(error)).toBe(sample.error.message);
  });

  it.each(cases)("%s %s has an English message without gaps", async (_code, _context, sample) => {
    await changeLanguage("en");
    const english = errorMessage(failure(sample));
    expect(english).not.toContain("{{");
    expect(english).not.toBe(sample.error.message);
  });

  it("has English texts without Dutch words", () => {
    const dutch = /\b(niet|een|het|de|van|moet|kan|geen|bestand|gevonden|onbekend\w*|ongeldig\w*|deze|dit|je|liggen|tekens|wachtwoord|gebruiker\w*)\b/i;
    expect(Object.values(en.server.errors).filter((text) => dutch.test(text))).toEqual([]);
  });

  it("formats the numbers in a message for the language", async () => {
    const sample = (samples as Sample[]).find((item) => item.error.data.field === "ready_cp_fraction");
    expect(sample).toBeDefined();
    expect(errorMessage(failure(sample as Sample))).toBe("ready_cp_fraction moet tussen 0,5 en 1 liggen.");
    await changeLanguage("en");
    expect(errorMessage(failure(sample as Sample))).toBe("ready_cp_fraction must be between 0.5 and 1.");
  });

  it("falls back to the server's Dutch for a message the catalog does not know", async () => {
    await changeLanguage("en");
    const unknown = { code: "NOT_FOUND", message: "Iets nieuws niet gevonden.", details: null, data: { context: "something_new" } };
    expect(errorMessage(failure({ status: 404, error: unknown }))).toBe("Iets nieuws niet gevonden.");
    const incomplete = { code: "UNKNOWN_SORT", message: "Onbekende sortering 'x'.", details: null, data: {} };
    expect(errorMessage(failure({ status: 422, error: incomplete }))).toBe("Onbekende sortering 'x'.");
    const external = { code: "HTTP_ERROR", message: "Method Not Allowed", details: null, data: {} };
    expect(errorMessage(failure({ status: 405, error: external }))).toBe("Method Not Allowed");
  });

  it("keeps the interface's own message for an error that did not come from OAK", async () => {
    await changeLanguage("en");
    expect(() => readResponse(502, "<html>Bad Gateway</html>")).toThrow("The proxy could not reach OAK. (HTTP 502)");
    expect(errorMessage(new ApiError(0, "NETWORK", "Network error"))).toBe("Network error");
  });
});
