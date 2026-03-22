import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiGet, apiPost } from "../api";
import { useAuth } from "../app/AuthContext";
import LineChart from "../components/LineChart";

const LIVE_PREFIX = "/api/live";

type LiveMetricsResponse = {
  active_scenario: string;
  active_source: string;
  pending_scenario: string;
  spawn_mode: string;
  current: Record<string, number>;
  events: { time?: number; type?: string }[];
};

type ScenariosResponse = { scenarios: { name: string; source: string }[] };

type HistoryResponse = { history: Record<string, number>[] };

type RecommendationsResponse = { ok: boolean; data?: { recommendations?: { title?: string; evidence?: string[] }[] } };

type MechanicsResponse = { ok: boolean; data?: { mechanic_events?: { mechanic_id?: string; score?: number; quality_label?: string }[] } };

type TrainingLaunchResponse = {
  ok: boolean;
  data?: {
    focus_id?: string;
    difficulty_tier?: string;
    difficulty_value?: number;
    bot_profile_id?: string;
    scenario_ids?: string[];
    drill_mode?: string;
    bot_required?: boolean;
    drill_run_id?: number;
  };
};

const metricMeta = [
  { key: "speed", label: "Speed" },
  { key: "hesitation_percent", label: "Hesitation %" },
  { key: "hesitation_score", label: "Hesitation Score" },
  { key: "boost_waste_percent", label: "Boost Waste %" },
  { key: "supersonic_percent", label: "Supersonic %" },
  { key: "useful_supersonic_percent", label: "Useful Supersonic %" },
  { key: "pressure_percent", label: "Pressure %" },
  { key: "whiff_rate_per_min", label: "Whiff Rate / min" },
  { key: "recovery_time_avg_s", label: "Recovery Avg (s)" },
];

function fmtNumber(v: number | undefined, digits = 2) {
  if (v == null || Number.isNaN(v)) return "--";
  return Number(v).toFixed(digits);
}

export default function LiveDashboardPage() {
  const { profile } = useAuth();
  const location = useLocation();
  const [metrics, setMetrics] = useState<LiveMetricsResponse | null>(null);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [recommendations, setRecommendations] = useState<RecommendationsResponse | null>(null);
  const [mechanics, setMechanics] = useState<MechanicsResponse | null>(null);
  const [trainingLaunch, setTrainingLaunch] = useState<TrainingLaunchResponse | null>(null);
  const [error, setError] = useState("");

  const loadLive = useCallback(async () => {
    const met = await apiGet<LiveMetricsResponse>(`${LIVE_PREFIX}/metrics/current`);
    setMetrics(met);
    const hist = await apiGet<HistoryResponse>(`${LIVE_PREFIX}/metrics/history`);
    setHistory(hist);
    const sc = await apiGet<ScenariosResponse>(`${LIVE_PREFIX}/scenarios`);
    setScenarios(sc.scenarios.map((s) => s.name));
  }, []);

  const loadRecommendations = useCallback(async () => {
    const data = await apiGet<RecommendationsResponse>(`${LIVE_PREFIX}/recommendations/current`);
    setRecommendations(data);
  }, []);

  const loadMechanics = useCallback(async () => {
    const data = await apiGet<MechanicsResponse>(`${LIVE_PREFIX}/mechanics/current`);
    setMechanics(data);
  }, []);

  const loadTrainingLaunch = useCallback(async () => {
    const data = await apiGet<TrainingLaunchResponse>(`${LIVE_PREFIX}/training/current`, { suppressErrorWindow: true });
    setTrainingLaunch(data);
  }, []);

  useEffect(() => {
    setError("");
    void loadLive().catch((err) => setError(err instanceof Error ? err.message : String(err)));
    void loadRecommendations().catch(() => {});
    void loadMechanics().catch(() => {});
    void loadTrainingLaunch().catch(() => {});
  }, [loadLive, loadRecommendations, loadMechanics, loadTrainingLaunch]);

  const applyScenario = async () => {
    if (!selectedScenario) return;
    await apiPost(`${LIVE_PREFIX}/scenario/select`, { name: selectedScenario });
    await loadLive();
  };

  const historySeries = useMemo(() => {
    const points = history?.history ?? [];
    const series: Record<string, { t: number; v: number }[]> = {};
    metricMeta.forEach((m) => (series[m.key] = []));
    points.forEach((p, idx) => {
      metricMeta.forEach((m) => {
        const val = Number(p[m.key] ?? 0);
        series[m.key].push({ t: idx, v: val });
      });
    });
    return series;
  }, [history]);

  return (
    <div className="live-dashboard">
      <header className="top">
        <div>
          <h1>Test Mechanic Events & Live Metrics</h1>
          <div className="status-text">Welcome, {profile?.username ?? "Pilot"}</div>
        </div>
        <div className="top-actions">
          <button type="button" className="ghost" onClick={() => window.open("/replay", "_blank")}>Open Replay View</button>
          <Link to="/account" state={{ from: location.pathname }} className="ghost">Account</Link>
          <Link to="/dashboard" className="ghost">Replay Dashboard</Link>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="profile-pill">
        <span>
          This page is ready now. If live services are offline, start later with:
          {" "}
          <code>powershell -ExecutionPolicy Bypass -File scripts\launch_live_analysis.ps1 -AttachOnly</code>
        </span>
      </section>

      <section className="controls">
        <label htmlFor="scenarioSelect">Scenario</label>
        <select id="scenarioSelect" value={selectedScenario} onChange={(e) => setSelectedScenario(e.target.value)}>
          <option value="">Select scenario</option>
          {scenarios.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button type="button" onClick={applyScenario}>Apply Scenario</button>
        <span className="pill">Active: {metrics?.active_scenario || "none"}</span>
        <span className="pill">Source: {metrics?.active_source || "n/a"}</span>
        <span className="pill">Spawn: {metrics?.spawn_mode || "n/a"}</span>
      </section>

      {(trainingLaunch?.data?.focus_id || trainingLaunch?.data?.drill_mode) && (
        <section className="profile-pill">
          <span>
            Active training:
            {" "}
            <strong>{trainingLaunch?.data?.focus_id || "focus"}</strong>
            {" | "}
            Tier {trainingLaunch?.data?.difficulty_tier || "n/a"}
            {" | "}
            Mode {trainingLaunch?.data?.drill_mode || "n/a"}
            {" | "}
            Bot {trainingLaunch?.data?.bot_profile_id || (trainingLaunch?.data?.bot_required ? "required" : "optional")}
          </span>
        </section>
      )}

      <section className="cards">
        {metricMeta.map((m) => (
          <div className="card" key={m.key}>
            <h3>{m.label}</h3>
            <p>{fmtNumber(Number(metrics?.current?.[m.key] ?? 0), 2)}</p>
          </div>
        ))}
      </section>

      <section className="charts">
        {metricMeta.slice(0, 6).map((m) => (
          <LineChart key={m.key} series={historySeries[m.key] ?? []} width={500} height={140} />
        ))}
      </section>

      <section className="events">
        <h2>Recent Events</h2>
        <ul>
          {(metrics?.events ?? []).slice(0, 12).map((e, idx) => (
            <li key={`${e.type}-${idx}`}>{e.type ?? "event"}</li>
          ))}
        </ul>
      </section>

      <section className="events">
        <h2>What To Work On</h2>
        <div className="controls">
          <button type="button" onClick={() => apiPost(`${LIVE_PREFIX}/recommendations/refresh`, {}).then(loadRecommendations)}>Refresh Recommendations</button>
        </div>
        <ul id="recommendations">
          {(recommendations?.data?.recommendations ?? []).slice(0, 8).map((rec, idx) => (
            <li className="rec-item" key={`${rec.title}-${idx}`}>
              <strong>{rec.title ?? "Recommendation"}</strong>
              <div className="rec-meta">{(rec.evidence ?? [])[0] ?? ""}</div>
            </li>
          ))}
        </ul>
      </section>

      <section className="events">
        <h2>Mechanic Grades (Latest Review Session)</h2>
        <div className="controls">
          <button type="button" onClick={() => apiPost(`${LIVE_PREFIX}/mechanics/recompute`, {}).then(loadMechanics)}>Refresh Mechanics</button>
        </div>
        <ul>
          {(mechanics?.data?.mechanic_events ?? []).slice(0, 10).map((ev, idx) => (
            <li key={`${ev.mechanic_id}-${idx}`}>
              {ev.mechanic_id ?? "event"} | {fmtNumber(ev.score ?? 0, 1)} | {ev.quality_label ?? "neutral"}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
