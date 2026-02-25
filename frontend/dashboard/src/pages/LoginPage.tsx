import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../app/AuthContext";

export default function LoginPage() {
  const { login, signup } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError("");
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(email, password);
      }
      navigate("/profile", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <div className="auth__panel">
        <div className="auth__header">
          <div className="auth__badge">RLCOACH</div>
          <h1>{mode === "login" ? "Welcome back" : "Create your RLCoach"}</h1>
          <p>Secure access to live and replay analytics.</p>
        </div>
        <div className="auth__tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Sign in</button>
          <button className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>Create account</button>
        </div>
        <div className="auth__form">
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </label>
          {error && <div className="alert">{error}</div>}
          <button disabled={busy} onClick={submit}>
            {busy ? "Working..." : mode === "login" ? "Enter Dashboard" : "Create Account"}
          </button>
        </div>
      </div>
      <div className="auth__visual">
        <div className="hud-orbit" />
        <div className="hud-grid" />
        <div className="hud-copy">
          <h2>Telemetry in motion</h2>
          <p>Analyze your replays, track progress, and refine mechanics with live metrics and 3D playback.</p>
        </div>
      </div>
    </div>
  );
}
