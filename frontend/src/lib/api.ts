/**
 * Thin fetch wrapper for the OAK API.
 *
 * Responses are parsed as plain JSON. Pokémon IDs and tag IDs are already strings in the API,
 * and the Zod schemas in ./schemas.ts reject anything else, so a 64-bit identifier can never
 * pass through a JavaScript Number.
 */
import type { z } from "zod";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const CSRF_COOKIE = "oak_csrf";
const UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;

/** What to tell the user when a response carries no OAK error, for example a proxy's HTML page. */
const STATUS_MESSAGES: Record<number, string> = {
  401: "Je bent niet meer ingelogd. Log opnieuw in.",
  403: "Je hebt geen toegang tot deze actie.",
  408: "De server wachtte te lang op de upload.",
  413: "Het bestand is te groot voor de server of voor de proxy ervoor.",
  429: "Te veel verzoeken. Probeer het over een minuut opnieuw.",
  502: "De proxy kon OAK niet bereiken.",
  503: "OAK is tijdelijk niet beschikbaar.",
  504: "OAK reageerde niet op tijd.",
};

type ErrorBody = { code?: string; message?: string; details?: unknown };

function parseJson(text: string): { ok: true; value: unknown } | { ok: false } {
  if (!text) return { ok: true, value: undefined };
  try {
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false };
  }
}

function errorBody(value: unknown): ErrorBody | undefined {
  if (typeof value !== "object" || value === null || !("error" in value)) return undefined;
  const error = (value as { error: unknown }).error;
  return typeof error === "object" && error !== null ? (error as ErrorBody) : undefined;
}

/**
 * Turn a response body into the result or an ApiError. Never throws anything else, so a proxy that
 * answers with HTML or nothing at all still ends in a message the user can act on (audit A13).
 */
export function readResponse<T>(status: number, text: string): T {
  const parsed = parseJson(text);
  if (status >= 200 && status < 300) {
    if (!parsed.ok) throw new ApiError(status, "INVALID_RESPONSE", "De server gaf een antwoord dat OAK niet kan lezen.");
    return parsed.value as T;
  }
  const error = parsed.ok ? errorBody(parsed.value) : undefined;
  const fallback = `${STATUS_MESSAGES[status] ?? "De server gaf een fout."} (HTTP ${status})`;
  throw new ApiError(status, error?.code ?? "HTTP_ERROR", error?.message ?? fallback, error?.details);
}

export function csrfToken(): string | null {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : null;
}

type Params = Record<string, string | number | boolean | null | undefined | string[]>;

export function buildUrl(path: string, params?: Params): string {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    url.searchParams.set(key, Array.isArray(value) ? value.join(",") : String(value));
  }
  return url.pathname + url.search;
}

async function request<T>(method: string, path: string, options: { params?: Params; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    const token = csrfToken();
    if (token) headers["X-CSRF-Token"] = token;
  }
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const response = await fetch(buildUrl(path, options.params), { method, headers, body, credentials: "same-origin" });
  if (response.status === 204) return undefined as T;
  return readResponse<T>(response.status, await response.text());
}

export const api = {
  get: <T>(path: string, params?: Params) => request<T>("GET", path, { params }),
  post: <T>(path: string, body?: unknown, params?: Params) => request<T>("POST", path, { body, params }),
  put: <T>(path: string, body?: unknown, params?: Params) => request<T>("PUT", path, { body, params }),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, { body }),
  delete: <T>(path: string, body?: unknown, params?: Params) => request<T>("DELETE", path, { body, params }),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, { form }),
};

/** Fetch and validate with a Zod schema. Used where an ID-bearing payload enters the app. */
export async function getParsed<S extends z.ZodType>(schema: S, path: string, params?: Params): Promise<z.infer<S>> {
  return schema.parse(await api.get<unknown>(path, params));
}

/**
 * Upload with progress events. fetch() cannot report upload progress, so this uses XHR.
 * Every way an upload can end (an answer of any kind, a network error, a timeout or an abort)
 * settles the promise.
 */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress: (fraction: number) => void,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<T> {
  return new Promise((resolve, reject) => {
    const aborted = () => new ApiError(0, "ABORTED", "De upload is geannuleerd.");
    if (options.signal?.aborted) {
      reject(aborted());
      return;
    }
    const xhr = new XMLHttpRequest();
    const onAbortSignal = () => xhr.abort();
    const settle = (finish: () => void) => () => {
      options.signal?.removeEventListener("abort", onAbortSignal);
      finish();
    };
    xhr.open("POST", path);
    xhr.timeout = options.timeoutMs ?? UPLOAD_TIMEOUT_MS;
    const token = csrfToken();
    if (token) xhr.setRequestHeader("X-CSRF-Token", token);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = settle(() => {
      try {
        resolve(readResponse<T>(xhr.status, xhr.responseText));
      } catch (error) {
        reject(error instanceof ApiError ? error : new ApiError(xhr.status, "INVALID_RESPONSE", "De server gaf een antwoord dat OAK niet kan lezen."));
      }
    });
    xhr.onerror = settle(() => reject(new ApiError(0, "NETWORK", "Netwerkfout tijdens het uploaden. Controleer de verbinding en probeer het opnieuw.")));
    xhr.ontimeout = settle(() => reject(new ApiError(0, "TIMEOUT", "De upload duurde te lang en is gestopt.")));
    xhr.onabort = settle(() => reject(aborted()));
    options.signal?.addEventListener("abort", onAbortSignal);
    xhr.send(form);
  });
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Onbekende fout.";
}
