import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, setApiAuthTokenProvider } from "../api";
import {
  cognitoConfirmSignup,
  cognitoLogin,
  cognitoResendSignupCode,
  cognitoRestoreSession,
  cognitoSignOut,
  cognitoSignup,
} from "./cognito";

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
  authError: string | null;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  confirmSignup: (email: string, code: string) => Promise<void>;
  resendSignupCode: (email: string) => Promise<void>;
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
  const [authError, setAuthError] = useState<string | null>(null);
  const [idToken, setIdToken] = useState("");

  const refresh = useCallback(async () => {
    const res = await apiGet<{ ok: boolean; auth?: AuthUser | null; profile?: Profile | null }>(
      `${REPLAY_PREFIX}/auth/me`
    );
    setAuth(res.ok ? (res.auth ?? null) : null);
    setProfile(res.ok ? (res.profile ?? null) : null);
  }, []);

  useEffect(() => {
    setApiAuthTokenProvider(() => (idToken ? idToken : null));
    return () => setApiAuthTokenProvider(null);
  }, [idToken]);

  useEffect(() => {
    let canceled = false;
    const restore = async () => {
      setLoading(true);
      try {
        const restored = await cognitoRestoreSession();
        if (restored?.idToken) {
          if (!canceled) {
            setIdToken(restored.idToken);
          }
          await apiPost(`${REPLAY_PREFIX}/auth/cognito/login`, { id_token: restored.idToken });
        }
        await refresh();
        if (!canceled) {
          setAuthError(null);
        }
      } catch (err) {
        if (!canceled) {
          setAuth(null);
          setProfile(null);
          setAuthError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!canceled) {
          setLoading(false);
        }
      }
    };
    void restore();
    return () => {
      canceled = true;
    };
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    setAuthError(null);
    try {
      const tokens = await cognitoLogin(email, password);
      setIdToken(tokens.idToken);
      await apiPost(`${REPLAY_PREFIX}/auth/cognito/login`, { id_token: tokens.idToken });
      await refresh();
    } catch (err) {
      setAuth(null);
      setProfile(null);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  const signup = useCallback(async (email: string, password: string) => {
    await cognitoSignup(email, password);
  }, []);

  const confirmSignup = useCallback(async (email: string, code: string) => {
    await cognitoConfirmSignup(email, code);
  }, []);

  const resendSignupCode = useCallback(async (email: string) => {
    await cognitoResendSignupCode(email);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost(`${REPLAY_PREFIX}/auth/logout`, {});
    } catch {
      // ignore
    }
    setIdToken("");
    cognitoSignOut();
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
    () => ({
      auth,
      profile,
      loading,
      authError,
      refresh,
      login,
      signup,
      confirmSignup,
      resendSignupCode,
      logout,
      setupProfile,
      updateProfile,
    }),
    [auth, profile, loading, authError, refresh, login, signup, confirmSignup, resendSignupCode, logout, setupProfile, updateProfile]
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
