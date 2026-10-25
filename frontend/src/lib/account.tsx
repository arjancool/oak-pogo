import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api } from "./api";
import type { Account } from "./types";

const STORAGE_KEY = "oak.activeAccount";

interface AccountContextValue {
  accounts: Account[];
  account: Account | null;
  accountId: number | null;
  setAccountId: (id: number) => void;
  loading: boolean;
  refetch: () => void;
}

const AccountContext = createContext<AccountContextValue | null>(null);

function stored(): number | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value ? Number(value) : null;
  } catch {
    return null;
  }
}

export function AccountProvider({ children }: { children: ReactNode }) {
  const query = useQuery({ queryKey: ["accounts"], queryFn: () => api.get<Account[]>("/api/v1/accounts") });
  const [selected, setSelected] = useState<number | null>(stored);
  const accounts = useMemo(() => query.data ?? [], [query.data]);

  useEffect(() => {
    if (accounts.length && !accounts.some((a) => a.id === selected)) {
      setSelected(accounts[0]?.id ?? null);
    }
  }, [accounts, selected]);

  const setAccountId = useCallback((id: number) => {
    setSelected(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
      // Private mode: the choice simply is not remembered.
    }
  }, []);

  const account = accounts.find((a) => a.id === selected) ?? null;
  const value: AccountContextValue = {
    accounts,
    account,
    accountId: account?.id ?? null,
    setAccountId,
    loading: query.isLoading,
    refetch: () => void query.refetch(),
  };
  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

export function useAccount(): AccountContextValue {
  const context = useContext(AccountContext);
  if (!context) throw new Error("useAccount outside AccountProvider");
  return context;
}
