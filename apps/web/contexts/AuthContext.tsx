"use client";

import React, { createContext, useContext, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { User, authApi } from "../lib/api/auth";
import { getAuthToken } from "../lib/api/client";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAdmin: boolean;
  refreshUser: () => Promise<void>;
  signIn: (loginUser: User) => Promise<User | null>;
  logout: (redirectTo?: string) => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  isAdmin: false,
  refreshUser: async () => {},
  signIn: async () => null,
  logout: () => {},
});

// Canonical current-user cache key - every component that needs "who is
// logged in" reads this same query instead of independently hitting /auth/me/.
export const CURRENT_USER_QUERY_KEY = ["current-user"];

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const queryClient = useQueryClient();

  // Identity boundary: if the authenticated identity differs from the one the
  // cache was built for (login as someone else, role/account swap, login
  // after an anonymous visit), drop every other cached query before the new
  // identity can render - user-specific data must never survive an identity
  // change. Runs synchronously with the identity update, so no render ever
  // sees the new user alongside the old user's data.
  const purgeOnIdentityChange = (nextId: number | string | null) => {
    const previous = queryClient.getQueryData<{ id?: number | string } | null>(CURRENT_USER_QUERY_KEY);
    // Only purge if transitioning between two different authenticated identities.
    // Initial page load transitioning from undefined/null to an authenticated user
    // must NOT wipe the active queries that were just mounted and fetched.
    if (previous && previous.id && nextId && previous.id !== nextId) {
      queryClient.removeQueries({
        predicate: (q) => q.queryKey[0] !== CURRENT_USER_QUERY_KEY[0],
      });
    }
  };

  const { data: user = null, isLoading: loading } = useQuery({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: async () => {
      const fresh = await authApi.me().catch(() => null);
      purgeOnIdentityChange(fresh?.id ?? null);
      return fresh;
    },
    enabled: typeof window !== "undefined" ? !!getAuthToken() : false,
    staleTime: 60 * 1000,
  });

  const refreshUser = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY });
  }, [queryClient]);


  // Called by the login flows with the user object the login response
  // already returned. When it carries the same fields /auth/me/ returns, it
  // seeds the shared current-user cache directly, so the post-login
  // navigation needs no extra /auth/me/ round trip. Otherwise (social/2FA
  // responses without every field) fall back to one revalidation.
  const signIn = useCallback(async (loginUser: User): Promise<User | null> => {
    if (loginUser && "is_active" in loginUser && "avatar" in loginUser) {
      purgeOnIdentityChange(loginUser.id);
      queryClient.setQueryData(CURRENT_USER_QUERY_KEY, loginUser);
      return loginUser;
    }
    await queryClient.invalidateQueries({ queryKey: CURRENT_USER_QUERY_KEY });
    return queryClient.getQueryData<User | null>(CURRENT_USER_QUERY_KEY) ?? null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient]);

  const handleLogout = useCallback((redirectTo?: string) => {
    // Drop all cached (user-scoped) data before clearing the token, in
    // addition to the full-page redirect authApi.logout performs.
    queryClient.clear();
    queryClient.setQueryData(CURRENT_USER_QUERY_KEY, null);
    authApi.logout(redirectTo);
  }, [queryClient]);

  const isAdmin = !!user && ["admin", "super-admin"].includes(user.role);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAdmin,
        refreshUser,
        signIn,
        logout: handleLogout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
