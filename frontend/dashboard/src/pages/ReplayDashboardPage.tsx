import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiGet, apiPost } from "../api";
import { useAuth } from "../app/AuthContext";
import ReplayVisualizer from "../components/replay/ReplayVisualizer";
import LineChart from "../components/LineChart";

const REPLAY_PREFIX = "/api/replay";

type ReplayStatus = {
  status?: string;
  progress?: number;
  message?: string;
  replay_name?: string;
  checklist?: Record<string, boolean>;
  duplicate?: { existing_session_id?: string };
  analysis_ready?: boolean;
};

type ReplaySession = {
  session_id: string;
  replay_name: string;
  players: string[];
  duration_s: number;
  timeline: {
    t: number;
    seconds_remaining?: number;
    is_overtime?: boolean;
    is_goal_pause?: boolean;
    is_kickoff_pause?: boolean;
    is_inactive_phase?: boolean;
    active_play?: boolean;
    ball: {
      x: number;
      y: number;
      z: number;
      qx?: number;
      qy?: number;
      qz?: number;
      qw?: number;
      vx?: number;
      vy?: number;
      vz?: number;
    };
    players: {
      name: string;
      x: number;
      y: number;
      z: number;
      boost?: number;
      steer?: number;
      throttle?: number;
      handbrake?: number;
      jump?: number;
      double_jump?: number;
      qx?: number;
      qy?: number;
      qz?: number;
      qw?: number;
      yaw?: number;
      pitch?: number;
      roll?: number;
      vx?: number;
      vy?: number;
      vz?: number;
    }[];
  }[];
  boost_pads?: { x: number; y: number; z: number; size: string }[];
  replay_meta: Record<string, unknown>;
  analysis_player?: string;
  analysis_locked?: boolean;
  analysis_ready?: boolean;
};

type LibraryResponse = {
  ok: boolean;
  data?: {
    sessions?: { session_id: string; replay_name: string; created_at?: string }[];
    cleanup?: { duplicate_names_removed?: number };
  };
};

type ProgressResponse = {
  ok: boolean;
  data?: { points?: { x_time_unix: number; overall_mechanics_score: number; whiff_rate_per_min: number }[] };
};

type MechanicsResponse = {
  ok: boolean;
  data?: { mechanic_events?: { time?: number; mechanic_id?: string; quality_label?: string; score?: number }[] };
};

type RecommendationsResponse = {
  ok: boolean;
  data?: { items?: { title?: string; summary?: string }[] };
};

type MetricsData = {
  ok: boolean;
  data?: {
    metrics_timeline?: { t: number; [k: string]: number }[];
    events?: { time?: number; type?: string; reason?: string }[];
  };
};

const metricMeta = [
  { key: "speed", label: "Speed" },
  { key: "hesitation_percent", label: "Hesitation %" },
  { key: "boost_waste_percent", label: "Boost Waste %" },
  { key: "supersonic_percent", label: "Supersonic %" },
  { key: "useful_supersonic_percent", label: "Useful Supersonic %" },
  { key: "pressure_percent", label: "Pressure %" },
  { key: "whiff_rate_per_min", label: "Whiff Rate / min" },
  { key: "approach_efficiency", label: "Approach Efficiency" },
  { key: "recovery_time_avg_s", label: "Recovery Avg (s)" },
];

function fmtNumber(v: number | undefined, digits = 2) {
  if (v == null || Number.isNaN(v)) return "--";
  return Number(v).toFixed(digits);
}

function fmtDuration(seconds?: number) {
  if (!seconds || Number.isNaN(seconds)) return "0:00";
  const s = Math.round(seconds);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function englishEventName(mid?: string) {
  const map: Record<string, string> = {
    kickoff: "kickoff",
    shadow_defense: "shadow defense",
    challenge: "challenge",
    flicking: "flick",
    carrying_dribbling: "carry and dribble",
    flicking_carry_offense: "flick",
    aerial_offense: "aerial offense",
    aerial_defense: "aerial defense",
    fifty_fifty_control: "50/50 control",
  };
  const key = String(mid || "");
  return map[key] || key || "mechanic";
}

export default function ReplayDashboardPage() {
  const { profile, logout } = useAuth();
  const [status, setStatus] = useState<ReplayStatus | null>(null);
  const [session, setSession] = useState<ReplaySession | null>(null);
  const [library, setLibrary] = useState<LibraryResponse | null>(null);
  const [mechanics, setMechanics] = useState<MechanicsResponse | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationsResponse | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [activeTab, setActiveTab] = useState<"analysis" | "improve">("analysis");
  const [error, setError] = useState("");
  const [showLibrary, setShowLibrary] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [seekTime, setSeekTime] = useState<number | null>(null);
  const [eventExplain, setEventExplain] = useState<{ title: string; body: string } | null>(null);
  const [eventExplainLoading, setEventExplainLoading] = useState(false);
  const [loadingOverlay, setLoadingOverlay] = useState({
    open: false,
    title: "Preparing Replay",
    status: "Waiting...",
    progress: 0,
    checklist: {
      upload_received: false,
      replay_parsed: false,
      timeline_ready: false,
      analysis_ready: false,
      dashboard_ready: false,
    } as Record<string, boolean>,
    duplicateSessionId: "",
  });

  const loadReplayData = useCallback(async () => {
    const st = await apiGet<ReplayStatus>(`${REPLAY_PREFIX}/replay/status`);
    setStatus(st);
    try {
      const sess = await apiGet<{ ok: boolean; data?: ReplaySession }>(`${REPLAY_PREFIX}/replay/session`);
      const data = sess?.data;
      if (data) {
        setSession(data);
        setSelectedPlayer((prev) => prev || data.analysis_player || data.players?.[0] || "");
      }
    } catch {
      setSession(null);
    }
  }, []);

  const loadLibrary = useCallback(async () => {
    const lib = await apiGet<LibraryResponse>(`${REPLAY_PREFIX}/replay/library`);
    setLibrary(lib);
  }, []);

  const loadMechanics = useCallback(async () => {
    const data = await apiGet<MechanicsResponse>(`${REPLAY_PREFIX}/mechanics/current`);
    setMechanics(data);
  }, []);

  const loadRecommendations = useCallback(async () => {
    const data = await apiGet<RecommendationsResponse>(`${REPLAY_PREFIX}/recommendations/current`);
    setRecommendations(data);
  }, []);

  const loadProgress = useCallback(async () => {
    const data = await apiGet<ProgressResponse>(`${REPLAY_PREFIX}/profile/progress`);
    setProgress(data);
  }, []);

  const loadMetrics = useCallback(
    async (player: string) => {
      if (!player) return;
      const data = await apiGet<MetricsData>(`${REPLAY_PREFIX}/replay/player_metrics/data?player=${encodeURIComponent(player)}`);
      setMetrics(data);
    },
    []
  );

  const pollStatusUntilReady = useCallback(async () => {
    while (true) {
      const st = await apiGet<ReplayStatus>(`${REPLAY_PREFIX}/replay/status`);
      setStatus(st);
      setLoadingOverlay((prev) => ({
        ...prev,
        open: true,
        title: "Preparing Replay",
        status: st.message || "",
        progress: Number(st.progress || 0),
        checklist: st.checklist || prev.checklist,
        duplicateSessionId: "",
      }));
      if (st.status === "ready") return true;
      if (st.status === "error") return false;
      await new Promise((r) => setTimeout(r, 600));
    }
  }, []);

  const location = useLocation();

  const pickPreferredPlayer = useCallback((players: string[]) => {
    const norm = (v: string) => String(v || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    const candidates = [profile?.username ?? "", ...(profile?.aliases ?? [])]
      .map((p) => p.trim())
      .filter(Boolean)
      .map(norm);
    if (!players?.length) return "";
    for (const p of players) {
      if (candidates.includes(norm(p))) {
        return p;
      }
    }
    return players[0];
  }, [profile]);

  const loadReplaySession = useCallback(async () => {
    const sess = await apiGet<{ ok: boolean; data?: ReplaySession }>(`${REPLAY_PREFIX}/replay/session`);
    const data = sess?.data;
    if (!data) {
      setSession(null);
      return "";
    }
    setSession(data);
    const preferred = data.analysis_player || pickPreferredPlayer(data.players || []);
    setSelectedPlayer(preferred);
    return preferred;
  }, [pickPreferredPlayer]);

  const runAnalysisForPlayer = useCallback(async (player: string) => {
    if (!player) return;
    setLoadingOverlay((prev) => ({
      ...prev,
      open: true,
      title: "Analyzing Replay",
      status: `Running full-game analysis for ${player}...`,
      progress: 0.88,
      checklist: {
        upload_received: true,
        replay_parsed: true,
        timeline_ready: true,
        analysis_ready: false,
        dashboard_ready: false,
      },
      duplicateSessionId: "",
    }));
    await apiPost(`${REPLAY_PREFIX}/replay/analysis/select_player`, { player });
    await apiPost(`${REPLAY_PREFIX}/replay/analysis/run`, {});
    await loadMetrics(player);
    await loadMechanics();
    await loadProgress();
    setLoadingOverlay((prev) => ({
      ...prev,
      title: "Replay Ready",
      status: "Everything is loaded.",
      progress: 1,
      checklist: {
        upload_received: true,
        replay_parsed: true,
        timeline_ready: true,
        analysis_ready: true,
        dashboard_ready: true,
      },
    }));
    setTimeout(() => {
      setLoadingOverlay((prev) => ({ ...prev, open: false }));
    }, 500);
  }, [loadMechanics, loadMetrics, loadProgress]);

  const ensureAnalysisAndMetrics = useCallback(
    async (player: string) => {
      if (!player) return;
      try {
        const st = await apiGet<{ ok: boolean; data?: { analysis_ready?: boolean; analysis_player?: string } }>(
          `${REPLAY_PREFIX}/replay/analysis/status`
        );
        const lockedPlayer = String(st?.data?.analysis_player || "");
        if (lockedPlayer && lockedPlayer !== player) {
          setSelectedPlayer(lockedPlayer);
          return;
        }
        if (!st?.data?.analysis_ready) {
          await runAnalysisForPlayer(player);
          return;
        }
        await loadMetrics(player);
        await loadMechanics();
      } catch {
        await loadMetrics(player).catch(() => {
          // ignore
        });
      }
    },
    [loadMechanics, loadMetrics, runAnalysisForPlayer]
  );

  const refreshAll = useCallback(async () => {
    setError("");
    try {
      await Promise.all([loadReplayData(), loadLibrary(), loadRecommendations(), loadProgress()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [loadReplayData, loadLibrary, loadRecommendations, loadProgress]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    if (!selectedPlayer) return;
    void ensureAnalysisAndMetrics(selectedPlayer).catch(() => {
      // ignore
    });
  }, [selectedPlayer, ensureAnalysisAndMetrics]);

  const uploadReplay = async (file: File) => {
    setError("");
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      setLoadingOverlay((prev) => ({
        ...prev,
        open: true,
        title: "Preparing Replay",
        status: "Uploading replay...",
        progress: 0.05,
        checklist: prev.checklist,
        duplicateSessionId: "",
      }));
      const res = await fetch(`${REPLAY_PREFIX}/replay/upload`, {
        method: "POST",
        body: form,
        credentials: "include",
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || res.statusText);
      }
      const ok = await pollStatusUntilReady();
      if (!ok) {
        setLoadingOverlay((prev) => ({ ...prev, open: false }));
        return;
      }
      const preferred = await loadReplaySession();
      if (preferred) {
        await runAnalysisForPlayer(preferred);
      } else {
        setLoadingOverlay((prev) => ({ ...prev, open: false }));
      }
      await refreshAll();
    } catch (err) {
      setLoadingOverlay((prev) => ({ ...prev, open: false }));
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const openSaved = async (sessionId: string) => {
    try {
      if (!sessionId) {
        setError("Saved replay is missing a session id.");
        return;
      }
      await apiPost(`${REPLAY_PREFIX}/replay/open_saved`, { session_id: sessionId });
      setLoadingOverlay((prev) => ({
        ...prev,
        open: true,
        title: "Preparing Replay",
        status: "Loading replay from library...",
        progress: 0.15,
        duplicateSessionId: "",
      }));
      const ok = await pollStatusUntilReady();
      if (!ok) {
        setLoadingOverlay((prev) => ({ ...prev, open: false }));
        return;
      }
      const preferred = await loadReplaySession();
      if (preferred) {
        await runAnalysisForPlayer(preferred);
      } else {
        setLoadingOverlay((prev) => ({ ...prev, open: false }));
      }
      await refreshAll();
    } catch (err) {
      setLoadingOverlay((prev) => ({ ...prev, open: false }));
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const openReplayFolder = async () => {
    await apiPost(`${REPLAY_PREFIX}/replay/open_default_folder`, {});
  };

  const analyzePlayer = async () => {
    if (!selectedPlayer) return;
    await runAnalysisForPlayer(selectedPlayer);
    await refreshAll();
  };

  const progressSeries = useMemo(() => {
    const points = progress?.data?.points ?? [];
    return points.map((p) => ({ t: Number(p.x_time_unix || 0), v: Number(p.overall_mechanics_score || 0) }));
  }, [progress]);

  const metricSnapshot = useMemo(() => {
    const arr = metrics?.data?.metrics_timeline ?? [];
    return arr.length ? arr[arr.length - 1] : null;
  }, [metrics]);

  const mechanicEvents = mechanics?.data?.mechanic_events ?? [];
  const nextEvent = useMemo(() => {
    if (!mechanicEvents.length) return null;
    const sorted = [...mechanicEvents].sort((a, b) => Number(a.time ?? 0) - Number(b.time ?? 0));
    return sorted.find((e) => Number(e.time ?? 0) >= currentTime) ?? sorted[sorted.length - 1];
  }, [mechanicEvents, currentTime]);

  return (
    <div className="replay-dashboard">
      <header className="top">
        <div>
          <h1>Rocket League Replay Dashboard</h1>
          <div className="status-text">Welcome back, {profile?.username ?? "Pilot"}</div>
        </div>
        <div className="top-actions">
          <button type="button" className="ghost" onClick={() => window.open("/live", "_blank")}>Open Live Analysis</button>
          <button type="button" className="ghost" onClick={() => window.open("/replay", "_blank")}>Open Replay View</button>
          <Link to="/account" state={{ from: location.pathname }} className="ghost">Account</Link>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <section className="profile-pill">
        <span id="profileStatus">Logged in as {profile?.username ?? "Unknown"}</span>
        <div className="profile-actions">
          <button type="button" onClick={() => setShowLibrary(true)}>Open Replay Library</button>
          <button type="button" className="ghost" onClick={() => logout()}>Log Out</button>
        </div>
      </section>

      <section className="controls">
        <input
          id="replayFile"
          type="file"
          accept=".replay"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              void uploadReplay(file).catch((err) => setError(err instanceof Error ? err.message : String(err)));
            }
          }}
        />
        <button type="button" onClick={openReplayFolder}>Open Replay Folder</button>
        <span className="duration-label">Duration: {fmtDuration(session?.duration_s)}</span>
      </section>

      <div className="player-select">
        <div className="pill">Player: {selectedPlayer || "unknown"}</div>
      </div>

      <section className="progress-wrap">
        <div className="progress-bar" style={{ width: `${Math.round((status?.progress ?? 0) * 100)}%` }} />
        <div className="progress-label">{status?.message ?? "No replay loaded."}</div>
      </section>

      <section className="tab-strip">
        <button type="button" className={`tab-btn ${activeTab === "analysis" ? "active" : ""}`} onClick={() => setActiveTab("analysis")}>Analysis</button>
        <button type="button" className={`tab-btn ${activeTab === "improve" ? "active" : ""}`} onClick={() => setActiveTab("improve")}>Improvement</button>
      </section>

      {activeTab === "analysis" && (
        <section className="layout tab-panel">
            <ReplayVisualizer
              timeline={session?.timeline ?? []}
            replayMeta={(session?.replay_meta ?? {}) as unknown as {
              map_name?: string;
              player_teams?: Record<string, number>;
              score_samples?: { time_s: number; blue: number; orange: number }[];
              clock_samples?: { time_s: number; seconds_remaining: number }[];
              ot_start_s?: number | null;
              goal_pause_windows?: { pause_start_s?: number; pause_end_s?: number; blue?: number; orange?: number }[];
              demo_events?: { victim_player?: string; time_s?: number }[];
              boost_samples_by_player?: Record<string, { time_s?: number; boost?: number }[]>;
            }}
            events={mechanicEvents}
            selectedPlayer={selectedPlayer}
            onTimeChange={(t) => setCurrentTime(t)}
            boostPads={session?.boost_pads ?? []}
            seekTime={seekTime}
          />
          <div className="metrics-card">
            <h2>Live Metrics on Replay</h2>
            <div className="metric-grid">
              {metricMeta.map((m) => (
                <div className="metric-card" key={m.key}>
                  <h3>{m.label}</h3>
                  <p>{fmtNumber(Number(metricSnapshot?.[m.key] ?? 0), 2)}</p>
                </div>
              ))}
            </div>
            <div className="bubble-card">
              <button className="bubble-toggle" type="button" onClick={() => loadMechanics()}>Mechanic Grades</button>
              <div className="bubble-body">
                {mechanicEvents.slice(0, 10).map((ev, idx) => (
                  <div key={`${ev.mechanic_id}-${idx}`} className="library-item">
                    <strong>{englishEventName(ev.mechanic_id)}</strong>
                    <div className="library-item-meta">{fmtNumber(ev.score ?? 0, 1)} | {ev.quality_label ?? "neutral"}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="bubble-card">
              <div className="library-item-meta">Next event: {nextEvent ? `${englishEventName(nextEvent.mechanic_id)} @ ${fmtNumber(nextEvent.time ?? 0, 2)}s` : "none"}</div>
              <div className="library-list">
                {mechanicEvents.slice(0, 12).map((ev, idx) => (
                  <div key={`${ev.mechanic_id}-${idx}-list`} className="library-item">
                    <div>
                      <strong>{englishEventName(ev.mechanic_id)}</strong>
                      <div className="library-item-meta">{fmtNumber(ev.time ?? 0, 2)}s | {ev.quality_label ?? "neutral"}</div>
                    </div>
                    <button
                      type="button"
                      onClick={async () => {
                        const t = Number(ev.time ?? 0);
                        setSeekTime(t);
                        setEventExplainLoading(true);
                        try {
                          const res = await apiPost<{ ok: boolean; data?: { event?: { mechanic_id?: string; quality_label?: string; time?: number }; llm?: { text?: string; error?: string } } }>(
                            `${REPLAY_PREFIX}/mechanics/explain`,
                            { time_s: t, mechanic_id: ev.mechanic_id ?? "", include_llm: true }
                          );
                          const llmText = res?.data?.llm?.text || res?.data?.llm?.error || "No LLM explanation.";
                          setEventExplain({
                            title: `${englishEventName(ev.mechanic_id)} @ ${fmtNumber(t, 2)}s`,
                            body: llmText,
                          });
                        } catch (err) {
                          setEventExplain({
                            title: "Event Coach",
                            body: err instanceof Error ? err.message : String(err),
                          });
                        } finally {
                          setEventExplainLoading(false);
                        }
                      }}
                    >
                      Coach
                    </button>
                  </div>
                ))}
              </div>
            </div>
            <div className="bubble-card">
              <div className="library-item-meta">Event Coach</div>
              <div className="coach-panel">
                <strong>{eventExplain?.title ?? "Select an event"}</strong>
                <div className="library-item-meta">
                  {eventExplainLoading ? "Loading coaching advice..." : (eventExplain?.body ?? "Click Coach on an event to see the LLM explanation.")}
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {activeTab === "improve" && (
        <section className="improvement-layout tab-panel">
          <div className="metrics-card">
            <h2>What To Work On</h2>
            <div className="bubble-card">
              <button className="bubble-toggle" type="button" onClick={() => loadRecommendations()}>Refresh</button>
              <div className="bubble-body">
                {(recommendations?.data?.items ?? []).slice(0, 8).map((rec, idx) => (
                  <div key={`${rec.title}-${idx}`} className="library-item">
                    <strong>{rec.title ?? "Recommendation"}</strong>
                    <div className="library-item-meta">{rec.summary ?? ""}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="metrics-card">
            <h2>Improvement Tracking</h2>
            <div className="bubble-card">
              <button className="bubble-toggle" type="button" onClick={() => loadProgress()}>Refresh</button>
              <div className="bubble-body">
                <div className="library-item-meta">Progress Over Replays</div>
                <LineChart series={progressSeries} width={640} height={220} />
              </div>
            </div>
          </div>
        </section>
      )}

      {showLibrary && (
        <div className="drawer">
          <div className="drawer-panel">
            <div className="library-head">
              <strong>Your Replay Library</strong>
              <div className="profile-actions">
                <button type="button" onClick={() => loadLibrary()}>Refresh</button>
                <button type="button" className="ghost" onClick={() => setShowLibrary(false)}>Close</button>
              </div>
            </div>
            <div className="library-list">
              {(library?.data?.sessions ?? []).slice(0, 50).map((s) => {
                const sid = (s as { session_id?: string; id?: string }).session_id || (s as { session_id?: string; id?: string }).id || "";
                return (
                <div key={sid || s.replay_name} className="library-item">
                  <div>
                    <strong>{s.replay_name}</strong>
                    <div className="library-item-meta">{s.created_at ?? ""}</div>
                  </div>
                  <button type="button" onClick={() => openSaved(sid)}>Open</button>
                </div>
              )})}
            </div>
          </div>
        </div>
      )}

      {loadingOverlay.open && (
        <div className="loading-overlay">
          <div className="loading-card">
            <h2>{loadingOverlay.title}</h2>
            <div className="loading-status">{loadingOverlay.status}</div>
            <div className="loading-progress-wrap">
              <div className="loading-progress-bar" style={{ width: `${Math.max(0, Math.min(100, loadingOverlay.progress * 100))}%` }} />
            </div>
            <ul className="loading-checklist">
              {Object.entries(loadingOverlay.checklist).map(([k, v]) => (
                <li key={k} className={v ? "ok" : "pending"}>{k.replace(/_/g, " ")}</li>
              ))}
            </ul>
            <div className="loading-actions">
              <button type="button" className="ghost" onClick={() => setLoadingOverlay((prev) => ({ ...prev, open: false }))}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
