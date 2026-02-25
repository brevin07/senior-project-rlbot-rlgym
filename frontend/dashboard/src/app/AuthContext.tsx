import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../api";

const REPLAY_PREFIX = "/api/replay";

export type AuthUser = { id: number; email: string };
export type Profile = {
  id: number;
  username: string;
  rank_tier: string;
  platform: string;
  aliases: string[];
};

type AuthState = {
  auth: AuthUser | null;
  profile: Profile | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setupProfile: (payload: {
    username: string;
    rank_tier: string;
    platform: string;
    aliases: string[];
  }) => Promise<void>;
  updateProfile: (payload: {
    username: string;
    rank_tier: string;
    platform: string;
    aliases: string[];
  }) => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthUser | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ ok: boolean; auth?: AuthUser | null; profile?: Profile | null }>(
        `${REPLAY_PREFIX}/auth/me`
      );
      setAuth(res.ok ? (res.auth ?? null) : null);
      setProfile(res.ok ? (res.profile ?? null) : null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiPost<{ ok: boolean; auth: AuthUser; profile: Profile | null }>(
      `${REPLAY_PREFIX}/auth/login`,
      { email, password }
    );
    setAuth(res.auth ?? null);
    setProfile(res.profile ?? null);
  }, []);

  const signup = useCallback(async (email: string, password: string) => {
    const res = await apiPost<{ ok: boolean; auth: AuthUser; profile: Profile | null }>(
      `${REPLAY_PREFIX}/auth/signup`,
      { email, password }
    );
    setAuth(res.auth ?? null);
    setProfile(res.profile ?? null);
  }, []);

  const logout = useCallback(async () => {
    await apiPost(`${REPLAY_PREFIX}/auth/logout`, {});
    setAuth(null);
    setProfile(null);
  }, []);

  const setupProfile = useCallback(async (payload: { username: string; rank_tier: string; platform: string; aliases: string[] }) => {
    const res = await apiPost<{ ok: boolean; profile: Profile }>(
      `${REPLAY_PREFIX}/profile/setup`,
      payload
    );
    setProfile(res.profile ?? null);
  }, []);

  const updateProfile = useCallback(async (payload: { username: string; rank_tier: string; platform: string; aliases: string[] }) => {
    const res = await apiPost<{ ok: boolean; profile: Profile }>(
      `${REPLAY_PREFIX}/profile/update`,
      payload
    );
    setProfile(res.profile ?? null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ auth, profile, loading, refresh, login, signup, logout, setupProfile, updateProfile }),
    [auth, profile, loading, refresh, login, signup, logout, setupProfile, updateProfile]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("AuthProvider missing");
  }
  return ctx;
}
