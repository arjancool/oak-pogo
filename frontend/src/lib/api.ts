/**
 * Thin fetch wrapper for the OAK API.
 *
 * Responses are parsed as plain JSON. Pokémon IDs and tag IDs are already strings in the API,
 * and the Zod schemas in ./schemas.ts reject anything else, so a 64-bit identifier can never
 * pass through a JavaScript Number.
 */
import i18n from "i18next";
import type { z } from "zod";

import { serverText } from "./serverText";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  /** The values in the server's message and its context. Only set for an error OAK itself sent. */
  readonly data: Record<string, unknown> | undefined;

  constructor(status: number, code: string, message: string, details?: unknown, data?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.data = data;
  }
}

const CSRF_COOKIE = "oak_csrf";
const UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;

/** What to tell the user when a response carries no OAK error, for example a proxy's HTML page. */
const STATUS_MESSAGES = {
  401: "errors.http.401",
  403: "errors.http.403",
  408: "errors.http.408",
  413: "errors.http.413",
  429: "errors.http.429",
  502: "errors.http.502",
  503: "errors.http.503",
  504: "errors.http.504",
} as const;

function statusMessage(status: number): string {
  const key = STATUS_MESSAGES[status as keyof typeof STATUS_MESSAGES];
  return i18n.t(key ?? "errors.http.other");
}

type ErrorBody = { code?: string; message?: string; details?: unknown; data?: unknown };

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
    if (!parsed.ok) throw new ApiError(status, "INVALID_RESPONSE", i18n.t("errors.invalidResponse"));
    return parsed.value as T;
  }
  const error = parsed.ok ? errorBody(parsed.value) : undefined;
  if (error && typeof error.code === "string" && typeof error.message === "string") {
    const data = typeof error.data === "object" && error.data !== null && !Array.isArray(error.data) ? (error.data as Record<string, unknown>) : {};
    throw new ApiError(status, error.code, error.message, error.details, data);
  }
  const fallback = `${statusMessage(status)} (HTTP ${status})`;
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
    const aborted = () => new ApiError(0, "ABORTED", i18n.t("errors.uploadAborted"));
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
        reject(error instanceof ApiError ? error : new ApiError(xhr.status, "INVALID_RESPONSE", i18n.t("errors.invalidResponse")));
      }
    });
    xhr.onerror = settle(() => reject(new ApiError(0, "NETWORK", i18n.t("errors.network"))));
    xhr.ontimeout = settle(() => reject(new ApiError(0, "TIMEOUT", i18n.t("errors.uploadTimeout"))));
    xhr.onabort = settle(() => reject(aborted()));
    options.signal?.addEventListener("abort", onAbortSignal);
    xhr.send(form);
  });
}

/**
 * What to tell the user about a failed request. An error from OAK has a code and the values in its
 * message, so it reads in the chosen language; without a text in the catalog under
 * "server.errors" the server's Dutch message is shown (ADR-0025).
 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.data === undefined) return error.message;
    return serverText("errors", { code: error.code, text: error.message, data: error.data });
  }
  if (error instanceof Error) return error.message;
  return i18n.t("errors.unknown");
}
