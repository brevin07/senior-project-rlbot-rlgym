import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/AuthContext";

type Mode = "signin" | "signup" | "verify" | "forgot";

const MOCK_MECHANICS = [
  { id: "challenge", label: "Challenge", score: 38, quality: "bad" },
  { id: "fifty_fifty", label: "50/50 Control", score: 54, quality: "neutral" },
  { id: "aerial_offense", label: "Aerial Offense", score: 47, quality: "neutral" },
  { id: "shadow_defense", label: "Shadow Defense", score: 78, quality: "good" },
  { id: "carrying_dribbling", label: "Carry + Dribble", score: 82, quality: "good" },
];

const MOCK_EVENTS = [
  { time: "1:24", mechanic: "Challenge", quality: "bad", score: 34 },
  { time: "2:07", mechanic: "50/50 Control", quality: "neutral", score: 58 },
  { time: "3:41", mechanic: "Shadow Defense", quality: "good", score: 79 },
  { time: "5:02", mechanic: "Aerial Offense", quality: "neutral", score: 49 },
];

function ScoreRing({ score, quality }: { score: number; quality: string }) {
  const color =
    quality === "good" ? "var(--success)"
    : quality === "neutral" ? "var(--warning)"
    : "var(--danger)";
  const clamp = Math.max(0, Math.min(100, score));
  const gap = 100 - clamp;
  return (
    <svg viewBox="0 0 36 36" width="52" height="52" className="ap-ring">
      <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--surface-3)" strokeWidth="3.2" />
      <circle
        cx="18"
        cy="18"
        r="15.9"
        fill="none"
        stroke={color}
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeDasharray={`${clamp} ${gap}`}
        transform="rotate(-90 18 18)"
      />
      <text
        x="18"
        y="18"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="8"
        fontWeight="700"
        fill="var(--text-primary)"
      >
        {score}
      </text>
    </svg>
  );
}

export default function LoginPage() {
  const {
    login,
    signup,
    confirmSignup,
    resendSignupCode,
    forgotPassword,
    confirmForgotPassword,
    loading,
    authError,
    devBypassAuth,
  } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [resetCodeSent, setResetCodeSent] = useState(false);

  const onSignIn = async () => {
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const p = await login(email, password);
      navigate(!p?.username ? "/profile" : "/dashboard", { replace: true });
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
      setMessage("Verification code sent. Check your email.");
      setMode("verify");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onVerify = async () => {
    if (!email.trim()) {
      setError("Email is required.");
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
      setMessage("A new code was sent.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onRequestPasswordReset = async () => {
    if (!email.trim()) {
      setError("Email is required.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await forgotPassword(email);
      setResetCodeSent(true);
      setMessage("Password reset code sent. Check your email.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onConfirmPasswordReset = async () => {
    if (!email.trim()) {
      setError("Email is required.");
      return;
    }
    if (!code.trim()) {
      setError("Reset code is required.");
      return;
    }
    if (!resetPassword) {
      setError("New password is required.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await confirmForgotPassword(email, code, resetPassword);
      setCode("");
      setResetPassword("");
      setResetCodeSent(false);
      setMode("signin");
      setMessage("Password updated. You can now sign in.");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const goToSignIn = () => {
    setMode("signin");
    setCode("");
    setResetPassword("");
    setResetCodeSent(false);
    setError("");
    setMessage("");
  };

  const goToCreate = () => {
    setMode("signup");
    setCode("");
    setResetPassword("");
    setResetCodeSent(false);
    setError("");
    setMessage("");
  };

  const goToForgot = () => {
    setMode("forgot");
    setCode("");
    setResetPassword("");
    setResetCodeSent(false);
    setError("");
    setMessage("");
  };

  if (devBypassAuth) {
    return (
      <div className="login-page">
        <div className="login-form-col">
          <div className="login-brand">RLCOACH</div>
          <h1 className="login-title">Dev mode</h1>
          <p className="login-sub">Authentication bypassed for local development.</p>
          <div className="alert login-alert" style={{ background: "rgba(67,188,120,0.16)", borderColor: "rgba(67,188,120,0.5)" }}>
            Cognito checks are disabled.
          </div>
          <button className="login-cta" onClick={() => navigate("/dashboard", { replace: true })}>
            Continue to dashboard
          </button>
        </div>
        <div className="login-preview-col">
          <AppPreview />
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-form-col">
        <div className="login-brand">RLCOACH</div>

        <h1 className="login-title">
          {mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : mode === "verify" ? "Verify email" : "Forgot password"}
        </h1>
        <p className="login-sub">
          {mode === "signin"
            ? "Access your replay library and coaching dashboard."
            : mode === "signup"
            ? "Start improving with AI-powered replay analysis."
            : mode === "verify"
            ? "Enter the code we sent to your email."
            : resetCodeSent
            ? "Enter the reset code from your email and choose a new password."
            : "We’ll send a reset code to your email so you can choose a new password."}
        </p>

        <div className="login-form">
          <label className="login-label">
            Email
            <input
              className="login-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                if (mode === "signin") void onSignIn();
                if (mode === "forgot" && !resetCodeSent) void onRequestPasswordReset();
              }}
            />
          </label>

          {(mode === "signin" || mode === "signup") && (
            <label className="login-label">
              Password
              <input
                className="login-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                onKeyDown={(e) => e.key === "Enter" && mode === "signin" && void onSignIn()}
              />
            </label>
          )}

          {mode === "verify" && (
            <label className="login-label">
              Verification code
              <input
                className="login-input"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                onKeyDown={(e) => e.key === "Enter" && void onVerify()}
              />
              <button
                type="button"
                className="login-link"
                style={{ marginTop: 6 }}
                disabled={busy || loading}
                onClick={onResendCode}
              >
                Resend code
              </button>
            </label>
          )}

          {mode === "forgot" && resetCodeSent && (
            <>
              <label className="login-label">
                Reset code
                <input
                  className="login-input"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="123456"
                />
              </label>
              <label className="login-label">
                New password
                <input
                  className="login-input"
                  type="password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  placeholder="New password"
                  onKeyDown={(e) => e.key === "Enter" && void onConfirmPasswordReset()}
                />
                <button
                  type="button"
                  className="login-link"
                  style={{ marginTop: 6 }}
                  disabled={busy || loading}
                  onClick={onRequestPasswordReset}
                >
                  Resend reset code
                </button>
              </label>
            </>
          )}

          {(error || authError) && <div className="alert login-alert">{error || authError}</div>}
          {message && (
            <div className="alert login-alert" style={{ background: "rgba(67,188,120,0.16)", borderColor: "rgba(67,188,120,0.5)" }}>
              {message}
            </div>
          )}

          {mode === "signin" && (
            <button className="login-cta" disabled={busy || loading} onClick={onSignIn}>
              {busy || loading ? "Signing in..." : "Sign in"}
            </button>
          )}
          {mode === "signup" && (
            <button className="login-cta" disabled={busy || loading} onClick={onCreateAccount}>
              {busy || loading ? "Creating..." : "Create account"}
            </button>
          )}
          {mode === "verify" && (
            <button className="login-cta" disabled={busy || loading || !code.trim()} onClick={onVerify}>
              {busy || loading ? "Verifying..." : "Verify email"}
            </button>
          )}
          {mode === "forgot" && !resetCodeSent && (
            <button className="login-cta" disabled={busy || loading} onClick={onRequestPasswordReset}>
              {busy || loading ? "Sending..." : "Send reset code"}
            </button>
          )}
          {mode === "forgot" && resetCodeSent && (
            <button className="login-cta" disabled={busy || loading || !code.trim() || !resetPassword} onClick={onConfirmPasswordReset}>
              {busy || loading ? "Updating..." : "Update password"}
            </button>
          )}
        </div>

        <div className="login-switch">
          {mode === "signin" && (
            <>
              Don&apos;t have an account?{" "}
              <button type="button" className="login-link" onClick={goToCreate}>Create account</button>
              {" "}•{" "}
              <button type="button" className="login-link" onClick={goToForgot}>Forgot password?</button>
            </>
          )}
          {mode === "signup" && (
            <>
              Already have an account?{" "}
              <button type="button" className="login-link" onClick={goToSignIn}>Sign in</button>
            </>
          )}
          {mode === "verify" && (
            <>
              Already verified?{" "}
              <button type="button" className="login-link" onClick={goToSignIn}>Back to sign in</button>
            </>
          )}
          {mode === "forgot" && (
            <>
              Remembered it?{" "}
              <button type="button" className="login-link" onClick={goToSignIn}>Back to sign in</button>
            </>
          )}
        </div>

        <div className="login-features">
          <div className="login-feature-row">
            <i className="fa-solid fa-chart-line" />
            <span>Upload a replay and every mechanic gets an individual score out of 100</span>
          </div>
          <div className="login-feature-row">
            <i className="fa-solid fa-film" />
            <span>3D playback pauses at key moments with event-specific coaching advice</span>
          </div>
          <div className="login-feature-row">
            <i className="fa-solid fa-dumbbell" />
            <span>Your weakest mechanic becomes a personalised bot training session</span>
          </div>
        </div>
      </div>

      <div className="login-preview-col">
        <AppPreview />
      </div>
    </div>
  );
}

function AppPreview() {
  return (
    <div className="app-preview">
      <div className="app-preview-eyebrow">
        <i className="fa-solid fa-rocket" /> What you get inside
      </div>

      <div className="ap-card">
        <div className="ap-card-header">
          <span className="ap-card-title">Mechanic Grades</span>
          <span className="ap-card-sub">latest replay - 4-16-26</span>
        </div>
        <div className="ap-mech-grid">
          {MOCK_MECHANICS.map((m) => (
            <div key={m.id} className="ap-mech-item">
              <ScoreRing score={m.score} quality={m.quality} />
              <span className="ap-mech-name">{m.label}</span>
              <span className={`ap-mech-badge ap-mech-badge--${m.quality}`}>
                {m.quality === "good" ? "Strong" : m.quality === "neutral" ? "Mixed" : "Needs Work"}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="ap-card">
        <div className="ap-card-header">
          <span className="ap-card-title">Coach Timeline</span>
          <span className="ap-card-sub">click any event to jump to that moment</span>
        </div>
        <div className="ap-event-list">
          {MOCK_EVENTS.map((ev, i) => (
            <div key={i} className={`ap-event-row ap-event-row--${ev.quality}`}>
              <span className="ap-event-time">{ev.time}</span>
              <span className={`quality-badge quality-${ev.quality}`}>
                {ev.quality === "good" ? "Good" : ev.quality === "neutral" ? "Neutral" : "Bad"}
              </span>
              <span className="ap-event-name">{ev.mechanic}</span>
              <span className="ap-event-score">{ev.score}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="ap-card ap-card--inline">
        <div>
          <div className="ap-card-title">Score Trend</div>
          <div className="ap-card-sub" style={{ marginTop: 2 }}>5 replays - going up</div>
        </div>
        <div className="ap-sparkline-wrap">
          <svg viewBox="0 0 180 44" preserveAspectRatio="none" className="ap-sparkline">
            <defs>
              <linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#d38c58" stopOpacity="0.3" />
                <stop offset="100%" stopColor="#d38c58" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d="M0,36 L36,30 L72,22 L108,17 L144,12 L180,7 L180,44 L0,44 Z" fill="url(#sg)" />
            <polyline
              points="0,36 36,30 72,22 108,17 144,12 180,7"
              fill="none"
              stroke="#d38c58"
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {([[0, 36], [36, 30], [72, 22], [108, 17], [144, 12], [180, 7]] as [number, number][]).map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r="3" fill="#d38c58" />
            ))}
          </svg>
        </div>
      </div>
    </div>
  );
}
