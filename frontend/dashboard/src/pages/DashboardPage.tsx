import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../api";
import { useAuth } from "../app/AuthContext";

const REPLAY_PREFIX = "/api/replay";
const LIVE_PREFIX = "/api/live";

type ReplayStatus = {
  status?: string;
  progress?: number;
  message?: string;
  replay_name?: string;
  checklist?: Record<string, boolean>;
};

type LibraryResponse = {
  ok: boolean;
  data?: {
    sessions?: { session_id: string; replay_name: string; created_at?: string }[];
  };
};

type LiveMetricsResponse = {
  active_scenario: string;
  active_source: string;
  pending_scenario: string;
  spawn_mode: string;
  current: Record<string, unknown>;
  events: unknown[];
};

type ScenariosResponse = { scenarios: { name: string; source: string }[] };

export default function DashboardPage() {
  const { profile } = useAuth();
  const [library, setLibrary] = useState<LibraryResponse | null>(null);
  const [status, setStatus] = useState<ReplayStatus | null>(null);
  const [metrics, setMetrics] = useState<LiveMetricsResponse | null>(null);
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [error, setError] = useState("");
  const pollRef = useRef<number | null>(null);

  const loadAll = async () => {
    setError("");
    try {
      const lib = await apiGet<LibraryResponse>(`${REPLAY_PREFIX}/replay/library`);
      setLibrary(lib);
      const st = await apiGet<ReplayStatus>(`${REPLAY_PREFIX}/replay/status`);
      setStatus(st);
      const met = await apiGet<LiveMetricsResponse>(`${LIVE_PREFIX}/metrics/current`);
      setMetrics(met);
      const sc = await apiGet<ScenariosResponse>(`${LIVE_PREFIX}/scenarios`);
      setScenarios(sc.scenarios.map((s) => s.name));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    if (status?.status && status.status !== "ready" && status.status !== "idle") {
      if (!pollRef.current) {
        pollRef.current = window.setInterval(async () => {
          try {
            const st = await apiGet<ReplayStatus>(`${REPLAY_PREFIX}/replay/status`);
            setStatus(st);
          } catch {
            // ignore
          }
        }, 1500);
      }
    } else if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [status?.status]);

  const uploadReplay = async (file: File) => {
    setError("");
    const form = new FormData();
    form.append("file", file, file.name);
    const res = await fetch(`${REPLAY_PREFIX}/replay/upload`, {
      method: "POST",
      body: form,
      credentials: "include"
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    await loadAll();
  };

  const openSaved = async (sessionId: string) => {
    await apiPost(`${REPLAY_PREFIX}/replay/open_saved`, { session_id: sessionId });
    await loadAll();
  };

  const applyScenario = async () => {
    if (!selectedScenario) return;
    await apiPost(`${LIVE_PREFIX}/scenario/select`, { name: selectedScenario });
    await loadAll();
  };

  const sessions = library?.data?.sessions ?? [];
  const checklist = status?.checklist ?? {};

  return (
    <div className="dashboard">
      <header className="dash-header">
        <div>
          <div className="dash-title">RLCoach Command</div>
          <div className="dash-subtitle">Welcome, {profile?.username ?? "Pilot"}</div>
        </div>
        <div className="dash-status">
          <span className="pill pill--ok">Live</span>
          <span className="pill">Replay</span>
          <Link className="ghost" to="/account">Account</Link>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <div className="dash-grid">
        <section className="card">
          <h3>Replay Library</h3>
          <div className="upload">
            <input
              type="file"
              accept=".replay"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  void uploadReplay(file).catch((err) => setError(err instanceof Error ? err.message : String(err)));
                }
              }}
            />
            <button onClick={loadAll}>Refresh</button>
          </div>
          <ul className="list">
            {sessions.slice(0, 6).map((s) => (
              <li key={s.session_id}>
                <div>
                  <strong>{s.replay_name}</strong>
                  <div className="muted">{s.created_at ?? ""}</div>
                </div>
                <button onClick={() => openSaved(s.session_id)}>Open</button>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <h3>Replay Processing</h3>
          <div className="progress">
            <div className="progress__bar" style={{ width: `${Math.round((status?.progress ?? 0) * 100)}%` }} />
          </div>
          <div className="muted">{status?.message ?? "No replay loaded."}</div>
          <div className="checklist">
            {Object.entries(checklist).map(([k, v]) => (
              <div key={k} className={v ? "ok" : ""}>{v ? "●" : "○"} {k.replace(/_/g, " ")}</div>
            ))}
          </div>
        </section>

        <section className="card card--visual">
          <h3>3D Visualizer</h3>
          <div className="visual-frame">
            <iframe title="Replay Visualizer" src="/legacy/replay/" />
          </div>
        </section>

        <section className="card">
          <h3>Live Metrics</h3>
          <div className="stack">
            <select value={selectedScenario} onChange={(e) => setSelectedScenario(e.target.value)}>
              <option value="">Select scenario</option>
              {scenarios.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button onClick={applyScenario}>Apply Scenario</button>
          </div>
          <pre className="code">{JSON.stringify(metrics?.current ?? {}, null, 2)}</pre>
        </section>

        <section className="card">
          <h3>Live Feed</h3>
          <ul className="list">
            {(metrics?.events ?? []).slice(0, 6).map((e, idx) => (
              <li key={idx}>
                <div>{JSON.stringify(e)}</div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card card--visual">
          <h3>Live Scene</h3>
          <div className="visual-frame">
            <iframe title="Live Dashboard" src="/legacy/live/" />
          </div>
        </section>
      </div>
    </div>
  );
}
