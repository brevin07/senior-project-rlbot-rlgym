import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/AuthContext";

type Mode = "signin" | "signup" | "verify";

export default function LoginPage() {
  const { login, signup, confirmSignup, resendSignupCode, loading, authError } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const onSignIn = async () => {
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await login(email, password);
      navigate("/profile", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onCreateAccount = async () => {
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await signup(email, password);
      setMessage("Verification code sent. Check your email and enter it below.");
      setMode("verify");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onVerify = async () => {
    if (!email.trim()) {
      setError("Email is required for verification.");
      return;
    }
    if (!code.trim()) {
      setError("Verification code is required.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await confirmSignup(email, code);
      setCode("");
      setMessage("Email verified. You can now sign in.");
      setMode("signin");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onResendCode = async () => {
    if (!email.trim()) {
      setError("Enter your email first.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await resendSignupCode(email);
      setMessage("A new verification code was sent.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const goToSignIn = () => {
    setMode("signin");
    setCode("");
    setError("");
    setMessage("");
  };

  const goToCreate = () => {
    setMode("signup");
    setCode("");
    setError("");
    setMessage("");
  };

  return (
    <div className="auth auth--neon">
      <div className="auth__panel auth__panel--neon">
        <div className="auth__badge">RLCOACH</div>
        <h1>{mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Verify email"}</h1>
        <p>Sign in to open your replay library and coaching dashboard.</p>

        <div className="auth__stage">
          <div className="auth__stage-label">{mode === "signin" ? "Account Access" : mode === "signup" ? "New Account" : "Email Confirmation"}</div>

          <div className="auth__form">
            <label>
              Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </label>
            {mode !== "verify" && (
              <label>
                Password
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="********" />
              </label>
            )}
            {mode === "verify" && (
              <label>
                Verification code
                <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456" />
              </label>
            )}
            {mode === "verify" && (
              <div className="auth__field-help">
                <button type="button" className="auth__link" disabled={busy || loading} onClick={onResendCode}>
                  Resend code
                </button>
              </div>
            )}
            {(error || authError) && <div className="alert">{error || authError}</div>}
            {message && (
              <div className="alert" style={{ background: "rgba(67, 188, 120, 0.16)", borderColor: "rgba(67, 188, 120, 0.5)" }}>
                {message}
              </div>
            )}
            {mode === "signin" && (
              <button className="auth__cta" disabled={busy || loading} onClick={onSignIn}>
                {busy || loading ? "Signing in..." : "Sign in"}
              </button>
            )}
            {mode === "signup" && (
              <button className="auth__cta" disabled={busy || loading} onClick={onCreateAccount}>
                {busy || loading ? "Creating..." : "Create account"}
              </button>
            )}
            {mode === "verify" && (
              <button className="auth__cta" disabled={busy || loading || !code.trim()} onClick={onVerify}>
                {busy || loading ? "Verifying..." : "Verify email"}
              </button>
            )}
          </div>

          {mode === "signin" && (
            <p className="auth__switch">
              Don&apos;t have an account?{" "}
              <button type="button" className="auth__link" onClick={goToCreate}>
                Create account
              </button>
            </p>
          )}
          {mode === "signup" && (
            <p className="auth__switch">
              Already have an account?{" "}
              <button type="button" className="auth__link" onClick={goToSignIn}>
                Sign in
              </button>
            </p>
          )}
          {mode === "verify" && (
            <p className="auth__switch">
              Verified already?{" "}
              <button type="button" className="auth__link" onClick={goToSignIn}>
                Back to sign in
              </button>
            </p>
          )}
        </div>
      </div>

      <div className="auth__visual auth__visual--neon auth__visual--product">
        <div className="hud-grid" />
        <div className="hud-ring hud-ring--one" />
        <div className="hud-ring hud-ring--two" />
        <div className="hud-sweep" />
        <div className="hud-copy">
          <h2>RocketCoach</h2>
          <p>AI-powered replay analysis and coaching platform for Rocket League players.</p>
          <div className="auth__feature-list">
            <div className="auth__feature-row">
              <span className="auth__feature-icon">🎯</span>
              <div>
                <strong>Tailor your practice</strong>
                <div>Get the best practice for your skill level with shots and game situations extracted from your replays.</div>
              </div>
            </div>
            <div className="auth__feature-row">
              <span className="auth__feature-icon">⚡</span>
              <div>
                <strong>Practice in-game, in free play</strong>
                <div>Make the most of your time and jump into quick practice sessions in free play between games.</div>
              </div>
            </div>
            <div className="auth__feature-row">
              <span className="auth__feature-icon">📋</span>
              <div>
                <strong>Create and share playlists</strong>
                <div>Group your favourite warmup shots. Or gather some difficult ones to challenge your friends. Show them that open goal you missed really wasn't that easy.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
