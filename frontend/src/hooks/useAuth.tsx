import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { apiClient } from "../lib/api";
import type { AuthStatus } from "../lib/types";

interface AuthContextValue {
  status: AuthStatus | undefined;
  loading: boolean;
  login: (password: string) => Promise<void>;
  setup: (password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["auth"],
    queryFn: apiClient.authStatus,
    staleTime: 30_000,
    retry: false,
  });

  useEffect(() => {
    const handler = () => {
      void queryClient.invalidateQueries({ queryKey: ["auth"] });
    };
    window.addEventListener("beetser:unauthorized", handler);
    return () => window.removeEventListener("beetser:unauthorized", handler);
  }, [queryClient]);

  const loginMutation = useMutation({
    mutationFn: (password: string) => apiClient.login(password),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  const setupMutation = useMutation({
    mutationFn: (password: string) => apiClient.setup(password),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  const logoutMutation = useMutation({
    mutationFn: () => apiClient.logout(),
    onSuccess: () => queryClient.clear(),
  });

  const changePasswordMutation = useMutation({
    mutationFn: ({ currentPassword, newPassword }: { currentPassword: string; newPassword: string }) =>
      apiClient.changePassword(currentPassword, newPassword),
  });

  const login = useCallback(
    async (password: string) => {
      await loginMutation.mutateAsync(password);
    },
    [loginMutation],
  );

  const setup = useCallback(
    async (password: string) => {
      await setupMutation.mutateAsync(password);
    },
    [setupMutation],
  );

  const logout = useCallback(async () => {
    await logoutMutation.mutateAsync();
  }, [logoutMutation]);

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      await changePasswordMutation.mutateAsync({ currentPassword, newPassword });
    },
    [changePasswordMutation],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status: statusQuery.data,
      loading: statusQuery.isLoading,
      login,
      setup,
      logout,
      changePassword,
    }),
    [statusQuery.data, statusQuery.isLoading, login, setup, logout, changePassword],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
