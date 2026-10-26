import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { App } from "./App";
import "./i18n";
import { ApiError } from "./lib/api";
import { AuthProvider } from "./lib/auth";
import "./styles.css";

const MAX_RETRIES = 2;
const STALE_MS = 15_000;
const CLIENT_ERROR_LIMIT = 500;

/** Retry only what can succeed a second time: network failures and server errors. A 4xx
 * answer or a response that fails its schema check is final. */
function shouldRetry(count: number, error: unknown): boolean {
  if (count >= MAX_RETRIES) return false;
  if (error instanceof ApiError) return error.status === 0 || error.status >= CLIENT_ERROR_LIMIT;
  return error instanceof TypeError;
}

const queryClient = new QueryClient({
  // A failed query is shown on the page; logging it as well makes a schema mismatch visible
  // in the browser console instead of a page that silently stays empty.
  queryCache: new QueryCache({
    onError: (error) => {
      if (!(error instanceof ApiError && error.status < CLIENT_ERROR_LIMIT)) console.error("OAK query failed", error);
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: STALE_MS,
      refetchOnWindowFocus: false,
      retry: shouldRetry,
    },
  },
});

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
