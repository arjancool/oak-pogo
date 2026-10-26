import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { changeLanguage, isLanguage, LANGUAGES } from "../i18n";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { AuthStatus, User } from "../lib/types";
import { Select } from "./ui";

/** Choose the language. Once logged in, the choice is saved with the user, so it follows them
 * to other devices. */
export function LanguageSelect({ className }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const client = useQueryClient();
  return (
    <Select
      aria-label={t("language.label")}
      value={i18n.language}
      className={className}
      onChange={async (event) => {
        const language = event.target.value;
        if (!isLanguage(language)) return;
        await changeLanguage(language);
        if (!user) return;
        try {
          const updated = await api.put<User>("/api/v1/auth/me/preferences", { preferences: { language } });
          client.setQueryData<AuthStatus>(["auth", "status"], (old) => (old ? { ...old, user: updated } : old));
        } catch (error) {
          // The language still changes on this device; only remembering it for the user failed.
          console.error("OAK could not save the language", error);
        }
      }}
    >
      {Object.entries(LANGUAGES).map(([code, name]) => (
        <option key={code} value={code}>
          {name}
        </option>
      ))}
    </Select>
  );
}
