import type { ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router";

import { useAccount } from "../../lib/account";
import { EmptyState, Spinner } from "../ui";

/** Renders children with the active account id, or explains how to create one. */
export function RequireAccount({ children }: { children: (accountId: number) => ReactNode }) {
  const { t } = useTranslation();
  const { accountId, loading } = useAccount();
  if (loading) return <Spinner />;
  if (accountId === null) {
    return (
      <EmptyState title={t("requireAccount.title")}>
        <Trans i18nKey="requireAccount.text" components={{ accountsLink: <Link className="text-oak-400 underline" to="/admin/accounts" /> }} />
      </EmptyState>
    );
  }
  return <>{children(accountId)}</>;
}
