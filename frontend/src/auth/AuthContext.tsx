import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { authApi } from '../api';
import { AuthContext } from './context';
import type { AuthContextValue } from './context';
import {
  clearSession,
  getStoredUser,
  getToken,
  hasCapability,
  storeSession,
} from './session';
import type { AuthUser } from './session';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(getStoredUser);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const restore = async () => {
      if (!getToken()) {
        setInitializing(false);
        return;
      }
      try {
        // Revalidate against the server so a revoked or expired token does not
        // leave a stale identity in the UI.
        const current = await authApi.me();
        if (!cancelled) {
          storeSession(getToken(), current);
          setUser(current);
        }
      } catch {
        if (!cancelled) {
          clearSession();
          setUser(null);
        }
      } finally {
        if (!cancelled) setInitializing(false);
      }
    };
    restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const { token, user: authenticated } = await authApi.login(username, password);
    storeSession(token, authenticated);
    setUser(authenticated);
  }, []);

  const signOut = useCallback(async () => {
    await authApi.logout();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      initializing,
      signIn,
      signOut,
      can: (capability: string) => hasCapability(user, capability),
    }),
    [user, initializing, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
