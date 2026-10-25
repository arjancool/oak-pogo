import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import { setTimeZone } from "./format";
import type { AppSettings } from "./types";

export function useAppSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const settings = await api.get<AppSettings>("/api/v1/settings");
      setTimeZone(settings.timezone);
      return settings;
    },
    staleTime: 5 * 60_000,
  });
}

/** Build a sprite URL from the configured template, or null when sprites are disabled. */
export function spriteUrl(template: string | null | undefined, dex: number, shiny: boolean): string | null {
  if (!template) return null;
  return template.replaceAll("{dex}", String(dex)).replaceAll("{shiny_path}", shiny ? "shiny/" : "");
}
