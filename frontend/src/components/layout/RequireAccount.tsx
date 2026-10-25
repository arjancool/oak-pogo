import type { ReactNode } from "react";
import { Link } from "react-router";

import { useAccount } from "../../lib/account";
import { EmptyState, Spinner } from "../ui";

/** Renders children with the active account id, or explains how to create one. */
export function RequireAccount({ children }: { children: (accountId: number) => ReactNode }) {
  const { accountId, loading } = useAccount();
  if (loading) return <Spinner />;
  if (accountId === null) {
    return (
      <EmptyState title="Nog geen traineraccount">
        Maak eerst een traineraccount aan onder{" "}
        <Link className="text-oak-400 underline" to="/admin/accounts">
          Beheer → Traineraccounts
        </Link>
        . Daarna kun je PGSharp koppelen of een export uploaden.
      </EmptyState>
    );
  }
  return <>{children(accountId)}</>;
}
