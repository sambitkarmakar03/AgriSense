import { useCallback, useEffect, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";
import { api, API_READY_EVENT, AUTH_EXPIRED_EVENT, ApiError, clearAccessToken, getAccessToken, saveAccessToken } from "../api/client";
import { AuthContext } from "./AuthContext";
import type { AuthContextValue } from "./AuthContext";
import type { Credentials, Registration } from "./AuthContext";
import type { User } from "../api/client";

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(() => Boolean(getAccessToken()));

  const logout = useCallback(() => {
    clearAccessToken();
    setUser(null);
  }, []);

  const restoreSession = useCallback(async () => {
    if (!getAccessToken()) return;
    try {
      setUser(await api.me());
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) logout();
      // Keep a token on connectivity/server errors; the wake banner will retry restoration.
    } finally { setIsLoading(false); }
  }, [logout]);

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  useEffect(() => {
    window.addEventListener(AUTH_EXPIRED_EVENT, logout);
    const handleApiReady = () => {
      if (getAccessToken()) {
        setIsLoading(true);
        void restoreSession();
      }
    };
    window.addEventListener(API_READY_EVENT, handleApiReady);
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, logout);
      window.removeEventListener(API_READY_EVENT, handleApiReady);
    };
  }, [logout, restoreSession]);

  const login = useCallback(async (credentials: Credentials) => {
    const response = await api.login(credentials);
    saveAccessToken(response.access_token);
    setUser(response.user);
  }, []);

  const register = useCallback(async (data: Registration) => {
    const response = await api.register(data);
    saveAccessToken(response.access_token);
    setUser(response.user);
  }, []);

  const value: AuthContextValue = useMemo(() => ({ user, isLoading, login, register, logout }), [user, isLoading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
