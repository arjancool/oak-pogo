import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";

import { api } from "./api";
import type { AuthStatus, User } from "./types";

interface AuthContextValue {
  status: AuthStatus | undefined;
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["auth", "status"],
    queryFn: () => api.get<AuthStatus>("/api/v1/auth/status"),
    staleTime: 60_000,
  });
  const loginMutation = useMutation({
    mutationFn: (body: { username: string; password: string }) => api.post<AuthStatus>("/api/v1/auth/login", body),
  });
  const setupMutation = useMutation({
    mutationFn: (body: { username: string; password: string }) => api.post<AuthStatus>("/api/v1/auth/setup", body),
  });

  const value: AuthContextValue = {
    status: status.data,
    user: status.data?.user ?? null,
    loading: status.isLoading,
    login: async (username, password) => {
      const result = await loginMutation.mutateAsync({ username, password });
      client.setQueryData(["auth", "status"], result);
    },
    setup: async (username, password) => {
      const result = await setupMutation.mutateAsync({ username, password });
      client.setQueryData(["auth", "status"], result);
    },
    logout: async () => {
      await api.post("/api/v1/auth/logout");
      client.clear();
      await client.invalidateQueries({ queryKey: ["auth", "status"] });
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth outside AuthProvider");
  return context;
}
