import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, buildUrl, csrfToken, errorMessage, uploadWithProgress } from "../../src/lib/api";

function clearCookies() {
  for (const part of document.cookie.split("; ")) {
    const name = part.split("=")[0];
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  clearCookies();
});

describe("buildUrl", () => {
  it("drops empty values and joins lists", () => {
    expect(buildUrl("/api/v1/pokemon", { account_id: 3, q: "", species: null, types: ["fire", "water"], shiny: true })).toBe(
      "/api/v1/pokemon?account_id=3&types=fire%2Cwater&shiny=true",
    );
  });

  it("keeps a path without parameters unchanged", () => {
    expect(buildUrl("/api/v1/accounts")).toBe("/api/v1/accounts");
  });
});

describe("csrf", () => {
  it("reads the CSRF cookie", () => {
    document.cookie = "other=1; path=/";
    document.cookie = "oak_csrf=abc%2B123; path=/";
    expect(csrfToken()).toBe("abc+123");
  });

  it("sends the CSRF header on writes but not on reads", async () => {
    document.cookie = "oak_csrf=token-1; path=/";
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.get("/api/v1/accounts");
    await api.post("/api/v1/accounts", { nickname: "Test" });
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    const readHeaders = calls[0]?.[1].headers as Record<string, string>;
    const writeHeaders = calls[1]?.[1].headers as Record<string, string>;
    expect(readHeaders["X-CSRF-Token"]).toBeUndefined();
    expect(writeHeaders["X-CSRF-Token"]).toBe("token-1");
    expect(writeHeaders["Content-Type"]).toBe("application/json");
  });
});

describe("errors", () => {
  it("turns the API error envelope into an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Niet gevonden." } }), { status: 404 })),
    );
    const error = await api.get("/api/v1/pokemon/999").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).code).toBe("NOT_FOUND");
    expect(errorMessage(error)).toBe("Niet gevonden.");
  });

  it("returns undefined for 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    await expect(api.delete("/api/v1/accounts/1/webhook")).resolves.toBeUndefined();
  });
});

describe("responses that are not OAK JSON", () => {
  it("turns a proxy HTML page into a readable error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<!doctype html><h1>502 Bad Gateway</h1>", { status: 502 })));
    const error = await api.get("/api/v1/accounts").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("De proxy kon OAK niet bereiken. (HTTP 502)");
  });

  it("refuses a successful answer that is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>login</html>", { status: 200 })));
    const error = await api.get("/api/v1/accounts").catch((e: unknown) => e);
    expect((error as ApiError).code).toBe("INVALID_RESPONSE");
  });
});

type ProgressEventLike = { lengthComputable: boolean; loaded: number; total: number };

/** Just enough of XMLHttpRequest to drive each way an upload can end. */
class FakeXhr {
  static last: FakeXhr | null = null;
  status = 0;
  responseText = "";
  timeout = 0;
  sent = false;
  headers: Record<string, string> = {};
  upload: { onprogress: ((event: ProgressEventLike) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    FakeXhr.last = this;
  }
  open() {}
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  send() {
    this.sent = true;
  }
  abort() {
    this.onabort?.();
  }
  respond(status: number, text: string) {
    this.status = status;
    this.responseText = text;
    this.onload?.();
  }
}

function startUpload(signal?: AbortSignal) {
  FakeXhr.last = null;
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  const progress: number[] = [];
  const promise = uploadWithProgress<{ status: string }>("/api/v1/imports/upload", new FormData(), (f) => progress.push(f), { signal });
  return { promise, xhr: FakeXhr.last as FakeXhr | null, progress };
}

describe("uploadWithProgress", () => {
  it("resolves with the JSON answer and reports progress", async () => {
    document.cookie = "oak_csrf=token-2; path=/";
    const { promise, xhr, progress } = startUpload();
    expect(xhr?.headers["X-CSRF-Token"]).toBe("token-2");
    expect(xhr?.timeout).toBeGreaterThan(0);
    xhr?.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 });
    xhr?.respond(202, JSON.stringify({ status: "queued" }));
    await expect(promise).resolves.toEqual({ status: "queued" });
    expect(progress).toEqual([0.5]);
  });

  it("keeps the OAK error message", async () => {
    const { promise, xhr } = startUpload();
    xhr?.respond(413, JSON.stringify({ error: { code: "PAYLOAD_TOO_LARGE", message: "Het bestand is groter dan de ingestelde limiet." } }));
    await expect(promise).rejects.toMatchObject({ status: 413, code: "PAYLOAD_TOO_LARGE" });
  });

  it("settles on an HTML error page from a proxy", async () => {
    const { promise, xhr } = startUpload();
    xhr?.respond(413, "<!doctype html><h1>413 Request Entity Too Large</h1>");
    await expect(promise).rejects.toMatchObject({
      status: 413,
      code: "HTTP_ERROR",
      message: "Het bestand is te groot voor de server of voor de proxy ervoor. (HTTP 413)",
    });
  });

  it("settles on an empty error answer", async () => {
    const { promise, xhr } = startUpload();
    xhr?.respond(504, "");
    await expect(promise).rejects.toMatchObject({ status: 504, message: "OAK reageerde niet op tijd. (HTTP 504)" });
  });

  it("settles on a network error, a timeout and an abort", async () => {
    const network = startUpload();
    network.xhr?.onerror?.();
    await expect(network.promise).rejects.toMatchObject({ code: "NETWORK" });

    const slow = startUpload();
    slow.xhr?.ontimeout?.();
    await expect(slow.promise).rejects.toMatchObject({ code: "TIMEOUT" });

    const controller = new AbortController();
    const cancelled = startUpload(controller.signal);
    controller.abort();
    await expect(cancelled.promise).rejects.toMatchObject({ code: "ABORTED" });
  });

  it("does not start when the signal was already aborted", async () => {
    const controller = new AbortController();
    controller.abort();
    const { promise, xhr } = startUpload(controller.signal);
    await expect(promise).rejects.toMatchObject({ code: "ABORTED" });
    expect(xhr).toBeNull();
  });
});
