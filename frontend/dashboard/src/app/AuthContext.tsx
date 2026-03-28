import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, setApiAuthTokenProvider } from "../api";
import {
  cognitoConfirmSignup,
  cognitoDeleteCurrentUser,
  cognitoLogin,
  cognitoResendSignupCode,
  cognitoRestoreSession,
  cognitoSignOut,
  cognitoSignup,
  getCognitoConfigError,
} from "./cognito";

const REPLAY_PREFIX = "/api/replay";
const AUTH_BOOTSTRAP_TIMEOUT_MS = 8000;

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
  devBypassAuth: boolean;
  refresh: () => Promise<Profile | null>;
  login: (email: string, password: string) => Promise<Profile | null>;
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
  deleteAccount: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  let timer: number | null = null;
  try {
    return await Promise.race<T>([
      promise,
      new Promise<T>((_, reject) => {
        timer = window.setTimeout(() => reject(new Error(`${label} timed out after ${Math.round(timeoutMs / 1000)}s.`)), timeoutMs);
      }),
    ]);
  } finally {
    if (timer != null) {
      window.clearTimeout(timer);
    }
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const devBypassAuth = String(import.meta.env.VITE_DEV_BYPASS_AUTH ?? "").trim() === "1";
  const [auth, setAuth] = useState<AuthUser | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [idToken, setIdToken] = useState("");

  const refresh = useCallback(async (): Promise<Profile | null> => {
    const res = await apiGet<{ ok: boolean; auth?: AuthUser | null; profile?: Profile | null }>(
      `${REPLAY_PREFIX}/auth/me`
    );
    setAuth(res.ok ? (res.auth ?? null) : null);
    setProfile(res.ok ? (res.profile ?? null) : null);
    return res.ok ? (res.profile ?? null) : null;
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
        const configError = getCognitoConfigError();
        if (configError && !devBypassAuth) {
          if (!canceled) {
            setAuth(null);
            setProfile(null);
            setAuthError(configError);
          }
          return;
        }
        const restored = devBypassAuth
          ? null
          : await withTimeout(cognitoRestoreSession(), AUTH_BOOTSTRAP_TIMEOUT_MS, "Cognito session restore");
        if (restored?.idToken) {
          if (!canceled) {
            setIdToken(restored.idToken);
          }
          await withTimeout(
            apiPost(`${REPLAY_PREFIX}/auth/cognito/login`, { id_token: restored.idToken }),
            AUTH_BOOTSTRAP_TIMEOUT_MS,
            "Cognito login handoff"
          );
        }
        await withTimeout(refresh(), AUTH_BOOTSTRAP_TIMEOUT_MS, "Dashboard auth refresh");
        if (!canceled) {
          setAuthError(null);
        }
      } catch (err) {
        setIdToken("");
        cognitoSignOut();
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
  }, [devBypassAuth, refresh]);

  const login = useCallback(async (email: string, password: string): Promise<Profile | null> => {
    setLoading(true);
    setAuthError(null);
    try {
      const tokens = await cognitoLogin(email, password);
      setIdToken(tokens.idToken);
      await apiPost(`${REPLAY_PREFIX}/auth/cognito/login`, { id_token: tokens.idToken });
      const fetchedProfile = await refresh();
      return fetchedProfile;
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

  const deleteAccount = useCallback(async () => {
    await apiPost(`${REPLAY_PREFIX}/auth/delete_account`, {});
    try {
      await cognitoDeleteCurrentUser();
    } catch {
      // Local deletion already completed; the user can retry Cognito cleanup by signing in again if needed.
    }
    setIdToken("");
    cognitoSignOut();
    setAuth(null);
    setProfile(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      auth,
      profile,
      loading,
      authError,
      devBypassAuth,
      refresh,
      login,
      signup,
      confirmSignup,
      resendSignupCode,
      logout,
      setupProfile,
      updateProfile,
      deleteAccount,
    }),
    [auth, profile, loading, authError, devBypassAuth, refresh, login, signup, confirmSignup, resendSignupCode, logout, setupProfile, updateProfile, deleteAccount]
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
