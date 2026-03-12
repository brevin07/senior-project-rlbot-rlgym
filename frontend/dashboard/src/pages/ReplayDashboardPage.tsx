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
  error?: string;
  checklist?: Record<string, boolean>;
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
};

type LibrarySession = {
  session_id?: string;
  id?: string;
  replay_name?: string;
  created_at?: string;
  source_type?: string;
  duration_s?: number;
  map_name?: string;
  tracked_player_name?: string;
  player_teams?: Record<string, number>;
  summary?: {
    overall_mechanics_score?: number;
    replay_date_iso?: string;
    analysis_player?: string;
    team_scores_final?: { blue?: number; orange?: number };
  };
};

type LibraryResponse = {
  ok: boolean;
  data?: {
    sessions?: LibrarySession[];
    cleanup?: { duplicate_names_removed?: number };
  };
};

type ProgressResponse = {
  ok: boolean;
  data?: { points?: { x_time_unix: number; overall_mechanics_score: number }[] };
};

type MechanicsResponse = {
  ok: boolean;
  data?: { mechanic_events?: { time?: number; mechanic_id?: string; quality_label?: string; score?: number; reason?: string }[] };
};

type MetricsData = {
  ok: boolean;
  data?: { metrics_timeline?: { t: number; [k: string]: number }[] };
};

const metricMeta = [
  { key: "speed", label: "Speed", hint: "Current car speed in replay context." },
  { key: "hesitation_percent", label: "Hesitation %", hint: "Percent of moments with delayed or unclear intent." },
  { key: "boost_waste_percent", label: "Boost Waste %", hint: "Boost spent in low-value situations. Lower is better." },
  { key: "supersonic_percent", label: "Supersonic %", hint: "Time spent at supersonic speed." },
  { key: "useful_supersonic_percent", label: "Useful Supersonic %", hint: "Supersonic time in pressure or useful lanes." },
  { key: "pressure_percent", label: "Pressure %", hint: "How often you are actively pressuring the play." },
  { key: "whiff_rate_per_min", label: "Whiff Rate / min", hint: "Estimated misses per minute." },
  { key: "recovery_time_avg_s", label: "Recovery Avg (s)", hint: "Average time to become playable after awkward states." },
];

type AppTab = "home" | "replays" | "studio" | "improvement";

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
    kickoff: "Kickoff",
    shadow_defense: "Shadow Defense",
    challenge: "Challenge",
    flicking: "Flick",
    carrying_dribbling: "Carry + Dribble",
    flicking_carry_offense: "Flick",
    aerial_offense: "Aerial Offense",
    aerial_defense: "Aerial Defense",
    fifty_fifty_control: "50/50 Control",
  };
  const key = String(mid || "");
  return map[key] || key || "Mechanic";
}

function qualityText(value?: string) {
  const q = String(value || "").toLowerCase();
  if (q.startsWith("good")) return "Good";
  if (q.startsWith("bad")) return "Bad";
  return "Neutral";
}

function eventKey(ev: { time?: number; mechanic_id?: string }) {
  return `${String(ev.mechanic_id || "")}|${Number(ev.time ?? 0).toFixed(3)}`;
}

function replayCardLines(s: LibrarySession) {
  const summary = s?.summary || {};
  const player = String(s?.tracked_player_name || summary?.analysis_player || "Unknown");
  const arena = String(s?.map_name || "Arena");
  const gradeRaw = Number(summary?.overall_mechanics_score || 0);
  const grade = Number.isFinite(gradeRaw) ? Math.round(gradeRaw * 100) : 0;
  const dateIso = String(summary?.replay_date_iso || s?.created_at || "").slice(0, 10);

  let result = "Result";
  let score = "--";
  const teamScores = summary?.team_scores_final || {};
  const blue = Number(teamScores?.blue);
  const orange = Number(teamScores?.orange);
  const playerTeams = s?.player_teams || {};
  const t = Number(playerTeams?.[player]);
  if (Number.isFinite(blue) && Number.isFinite(orange)) {
    score = `${blue}-${orange}`;
    if (t === 0) result = blue > orange ? "Win" : (blue < orange ? "Loss" : "Draw");
    else if (t === 1) result = orange > blue ? "Win" : (orange < blue ? "Loss" : "Draw");
  }

  const line1 = `${result} | ${score} | ${player} | ${arena} | Grade ${grade}`;
  const line2 = `${s.source_type || "replay"} | ${fmtDuration(Number(s.duration_s || 0))} | ${dateIso || "Unknown date"}`;
  return { line1, line2 };
}

const TUTORIAL_SEEN_KEY = "rlcoach_tutorial_seen";

const TUTORIAL_STEPS = [
  {
    icon: "⬆️",
    title: "Step 1: Upload a Replay",
    description:
      "Go to the Replays tab and upload a .replay file from your Rocket League replay folder. Click 'Open Replay Folder' in the header to find your files quickly.",
  },
  {
    icon: "🎬",
    title: "Step 2: Open in Studio",
    description:
      "Once uploaded, click 'Open' on any replay card. RocketCoach will process it and take you to Replay Studio where you can watch the 3D playback of your game.",
  },
  {
    icon: "🔍",
    title: "Step 3: Analyze Your Play",
    description:
      "In Studio, click 'Analyze' to run the full mechanics analysis. Live metrics and mechanic grades will populate in the sidebar. Click 'Coach' on any event for personalized feedback.",
  },
  {
    icon: "📈",
    title: "Step 4: Check Improvement",
    description:
      "Visit the Improvement tab to see your top 3 mechanics to practice based on your replay data. Track your progress over time in the Home tab chart.",
  },
];

const IMPROVEMENT_PLACEHOLDER = [
  {
    rank: 1,
    mechanic: "Aerial Control",
    priority: "High" as const,
    description:
      "Your aerial mechanics show inconsistent ball contact angles. Focus on controlling your car rotation in the air before making contact.",
  },
  {
    rank: 2,
    mechanic: "Boost Management",
    priority: "Medium" as const,
    description:
      "Boost is being spent in low-value situations. Practice collecting small pads and throttle-feathering to conserve boost for pressure moments.",
  },
  {
    rank: 3,
    mechanic: "Defending",
    priority: "Low" as const,
    description:
      "Shadow defense positioning could be improved. Work on maintaining goal-side positioning and reading opponent dribbles.",
  },
];

function TutorialModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const current = TUTORIAL_STEPS[step];
  const isFirst = step === 0;
  const isLast = step === TUTORIAL_STEPS.length - 1;

  return (
    <div className="drawer">
      <div className="drawer-panel tutorial-modal">
        <div className="tutorial-header">
          <h2>How to Use RocketCoach</h2>
          <button type="button" className="ghost" onClick={onClose}>Close</button>
        </div>
        <div className="tutorial-step-indicator">
          {TUTORIAL_STEPS.map((_, i) => (
            <div key={i} className={`tutorial-dot ${i === step ? "active" : i < step ? "done" : ""}`} />
          ))}
        </div>
        <div className="tutorial-body">
          <div className="tutorial-icon">{current.icon}</div>
          <h3>{current.title}</h3>
          <p className="library-item-meta" style={{ fontSize: 14, lineHeight: 1.6 }}>{current.description}</p>
        </div>
        <div className="tutorial-footer">
          <button type="button" className="ghost" disabled={isFirst} onClick={() => setStep((s) => s - 1)}>Back</button>
          <span className="status-text" style={{ fontSize: 12 }}>{step + 1} / {TUTORIAL_STEPS.length}</span>
          {isLast ? (
            <button type="button" onClick={onClose}>Done</button>
          ) : (
            <button type="button" onClick={() => setStep((s) => s + 1)}>Next</button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ReplayDashboardPage() {
  const { profile, logout } = useAuth();
  const location = useLocation();

  const [activeTab, setActiveTab] = useState<AppTab>("home");
  const [status, setStatus] = useState<ReplayStatus | null>(null);
  const [session, setSession] = useState<ReplaySession | null>(null);
  const [library, setLibrary] = useState<LibraryResponse | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [mechanics, setMechanics] = useState<MechanicsResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);

  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const [seekTime, setSeekTime] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [eventExplain, setEventExplain] = useState<{ title: string; body: string } | null>(null);
  const [eventExplainLoading, setEventExplainLoading] = useState(false);
  const [explainCache, setExplainCache] = useState<Record<string, { title: string; body: string }>>({});
  const [eventPopup, setEventPopup] = useState<{ title: string; body: string } | null>(null);
  const [loadingLibraryOpen, setLoadingLibraryOpen] = useState(false);
  const [showLiveMetrics, setShowLiveMetrics] = useState(true);
  const [openMetricHelp, setOpenMetricHelp] = useState("");
  const [openMechanicId, setOpenMechanicId] = useState("");
  const [noPlayerPopup, setNoPlayerPopup] = useState("");
  const [showTutorial, setShowTutorial] = useState(false);
  const [improvementScope, setImprovementScope] = useState<"all" | "latest">("all");

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
  });

  const pickPreferredPlayer = useCallback((players: string[]) => {
    const norm = (v: string) => String(v || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    const candidates = [profile?.username ?? "", ...(profile?.aliases ?? [])].map(norm);
    if (!players?.length) return "";
    for (const p of players) {
      if (candidates.includes(norm(p))) return p;
    }
    return "";
  }, [profile]);

  const loadStatus = useCallback(async () => {
    const st = await apiGet<ReplayStatus>(`${REPLAY_PREFIX}/replay/status`, { suppressErrorWindow: true });
    setStatus(st);
  }, []);

  const loadLibrary = useCallback(async () => {
    const lib = await apiGet<LibraryResponse>(`${REPLAY_PREFIX}/replay/library`);
    setLibrary(lib);
  }, []);

  const loadProgress = useCallback(async () => {
    const data = await apiGet<ProgressResponse>(`${REPLAY_PREFIX}/profile/progress`, { suppressErrorWindow: true });
    setProgress(data);
  }, []);

  const loadMetrics = useCallback(async (player: string) => {
    if (!player) return;
    const data = await apiGet<MetricsData>(`${REPLAY_PREFIX}/replay/player_metrics/data?player=${encodeURIComponent(player)}`);
    setMetrics(data);
  }, []);

  const loadMechanics = useCallback(async () => {
    const data = await apiGet<MechanicsResponse>(`${REPLAY_PREFIX}/mechanics/current`);
    setMechanics(data);
  }, []);

  const lookupCachedExplanation = useCallback((mechanicId: string, time: number) => {
    const exact = explainCache[`${mechanicId}|${Number(time ?? 0).toFixed(3)}`];
    if (exact) return exact;
    for (const [k, payload] of Object.entries(explainCache)) {
      if (k.startsWith(`${mechanicId}|`)) return payload;
    }
    return null;
  }, [explainCache]);

  const precomputeEventExplanations = useCallback(async (events: { time?: number; mechanic_id?: string; reason?: string }[]) => {
    if (!events.length) return;
    try {
      const batch = await apiPost<{
        ok: boolean;
        data?: { items?: { key: string; title?: string; body?: string; mechanic_id?: string; time?: number }[] };
      }>(
        `${REPLAY_PREFIX}/mechanics/explain_batch`,
        { include_llm: true, mode: "hybrid", time_budget_s: 20, preload_limit: 20 },
        { suppressErrorWindow: true }
      );
      const nextCache: Record<string, { title: string; body: string }> = {};
      const items = batch?.data?.items ?? [];
      for (const it of items) {
        const k = String(it.key || `${String(it.mechanic_id || "")}|${Number(it.time ?? 0).toFixed(3)}`);
        if (!k) continue;
        nextCache[k] = {
          title: String(it.title || `${englishEventName(it.mechanic_id)} @ ${fmtNumber(Number(it.time ?? 0), 2)}s`),
          body: String(it.body || "No explanation."),
        };
      }
      setExplainCache((prev) => ({ ...prev, ...nextCache }));
    } catch {
      const nextCache: Record<string, { title: string; body: string }> = {};
      for (const ev of events) {
        const k = eventKey(ev);
        nextCache[k] = {
          title: `${englishEventName(ev.mechanic_id)} @ ${fmtNumber(Number(ev.time ?? 0), 2)}s`,
          body: String(ev.reason || "No explanation."),
        };
      }
      setExplainCache((prev) => ({ ...prev, ...nextCache }));
    }
  }, []);

  const runAnalysisForPlayer = useCallback(async (player: string) => {
    if (!player) return;
    setLoadingOverlay((prev) => ({
      ...prev,
      open: true,
      title: "Analyzing Replay",
      status: `Running full-game analysis for ${player}...`,
      progress: 0.88,
    }));
    await apiPost(`${REPLAY_PREFIX}/replay/analysis/select_player`, { player });
    await apiPost(`${REPLAY_PREFIX}/replay/analysis/run`, {});
    await Promise.all([loadMetrics(player), loadMechanics(), loadProgress()]);
    const evs = (await apiGet<MechanicsResponse>(`${REPLAY_PREFIX}/mechanics/current`))?.data?.mechanic_events ?? [];
    await precomputeEventExplanations(evs);
    setLoadingOverlay((prev) => ({ ...prev, open: false, progress: 1 }));
  }, [loadMechanics, loadMetrics, loadProgress, precomputeEventExplanations]);

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

  const pollStatusUntilReady = useCallback(async () => {
    while (true) {
      const st = await apiGet<ReplayStatus>(`${REPLAY_PREFIX}/replay/status`, { suppressErrorWindow: true });
      setStatus(st);
      setLoadingOverlay((prev) => ({
        ...prev,
        open: true,
        title: "Preparing Replay",
        status: st.message || "",
        progress: Number(st.progress || 0),
        checklist: st.checklist || prev.checklist,
      }));
      if (st.status === "ready") return true;
      if (st.status === "error") {
        const detail = String(st.error || st.message || "Replay processing failed.").trim();
        if (detail.toLowerCase().includes("no player with name")) setNoPlayerPopup(detail);
        else setError(detail);
        return false;
      }
      await new Promise((r) => setTimeout(r, 600));
    }
  }, []);

  const openSaved = async (sessionId: string) => {
    try {
      if (!sessionId) return;
      setLoadingLibraryOpen(true);
      setError("");
      setNoPlayerPopup("");
      await apiPost(`${REPLAY_PREFIX}/replay/open_saved`, { session_id: sessionId });
      setLoadingOverlay((prev) => ({ ...prev, open: true, status: "Loading replay from library...", progress: 0.15 }));
      const ok = await pollStatusUntilReady();
      if (!ok) {
        setLoadingOverlay((prev) => ({ ...prev, open: false }));
        return;
      }
      const preferred = await loadReplaySession();
      if (preferred) await runAnalysisForPlayer(preferred);
      else setLoadingOverlay((prev) => ({ ...prev, open: false }));
      await Promise.all([loadLibrary(), loadProgress(), loadStatus()]);
      setActiveTab("studio");
    } catch (err) {
      setLoadingOverlay((prev) => ({ ...prev, open: false }));
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingLibraryOpen(false);
    }
  };

  const uploadReplay = async (file: File) => {
    setError("");
    setNoPlayerPopup("");
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      setLoadingOverlay((prev) => ({ ...prev, open: true, status: "Uploading replay...", progress: 0.05 }));
      const res = await fetch(`${REPLAY_PREFIX}/replay/upload`, {
        method: "POST",
        body: form,
        credentials: "include",
      });
      if (!res.ok) throw new Error((await res.text()) || res.statusText);
      const ok = await pollStatusUntilReady();
      if (!ok) {
        setLoadingOverlay((prev) => ({ ...prev, open: false }));
        return;
      }
      const preferred = await loadReplaySession();
      if (preferred) await runAnalysisForPlayer(preferred);
      else setLoadingOverlay((prev) => ({ ...prev, open: false }));
      await Promise.all([loadLibrary(), loadProgress(), loadStatus()]);
      setActiveTab("studio");
    } catch (err) {
      setLoadingOverlay((prev) => ({ ...prev, open: false }));
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const openReplayFolder = async () => {
    try {
      await apiPost(`${REPLAY_PREFIX}/replay/open_default_folder`, {});
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const loadCurrentSession = async () => {
    try {
      setError("");
      const preferred = await loadReplaySession();
      if (preferred) await Promise.all([loadMetrics(preferred), loadMechanics()]);
      setActiveTab("studio");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const analyzePlayer = async () => {
    if (!selectedPlayer) return;
    try {
      await runAnalysisForPlayer(selectedPlayer);
      await Promise.all([loadLibrary(), loadProgress(), loadStatus()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void Promise.all([loadLibrary(), loadProgress(), loadStatus()]).catch((err) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [loadLibrary, loadProgress, loadStatus]);

  const progressSeries = useMemo(() => {
    const points = progress?.data?.points ?? [];
    return points.map((p) => ({ t: Number(p.x_time_unix || 0), v: Number(p.overall_mechanics_score || 0) * 100 }));
  }, [progress]);

  const metricSnapshot = useMemo(() => {
    const arr = [...(metrics?.data?.metrics_timeline ?? [])].sort((a, b) => Number(a.t ?? 0) - Number(b.t ?? 0));
    if (!arr.length) return null;
    let out = arr[0];
    for (const point of arr) {
      if (Number(point.t ?? 0) <= currentTime) out = point;
      else break;
    }
    return out;
  }, [metrics, currentTime]);

  const mechanicEvents = mechanics?.data?.mechanic_events ?? [];
  const groupedMechanics = useMemo(() => {
    const groups = new Map<string, { mechanicId: string; label: string; items: typeof mechanicEvents; avg: number }>();
    const sorted = [...mechanicEvents].sort((a, b) => Number(a.time ?? 0) - Number(b.time ?? 0));
    for (const ev of sorted) {
      const id = String(ev.mechanic_id || "unknown");
      if (!groups.has(id)) groups.set(id, { mechanicId: id, label: englishEventName(id), items: [], avg: 0 });
      groups.get(id)!.items.push(ev);
    }
    for (const g of groups.values()) {
      const sum = g.items.reduce((acc, it) => acc + Number(it.score ?? 0), 0);
      g.avg = g.items.length ? (sum / g.items.length) * 100 : 0;
    }
    return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label));
  }, [mechanicEvents]);

  const latestReplay = (library?.data?.sessions ?? [])[0];

  const closeTutorial = useCallback(() => {
    localStorage.setItem(TUTORIAL_SEEN_KEY, "1");
    setShowTutorial(false);
  }, []);

  useEffect(() => {
    if (library === null) return;
    const seen = localStorage.getItem(TUTORIAL_SEEN_KEY);
    const hasReplays = (library?.data?.sessions ?? []).length > 0;
    if (!seen && !hasReplays) {
      setShowTutorial(true);
    }
  }, [library]);

  return (
    <div className="dashboard-shell">
      <aside className="left-nav">
        <div className="nav-brand">RocketCoach</div>
        <button type="button" className={`nav-btn ${activeTab === "home" ? "active" : ""}`} onClick={() => setActiveTab("home")}>Home</button>
        <button type="button" className={`nav-btn ${activeTab === "replays" ? "active" : ""}`} onClick={() => setActiveTab("replays")}>Replays</button>
        <button type="button" className={`nav-btn ${activeTab === "studio" ? "active" : ""}`} onClick={() => setActiveTab("studio")}>Replay Studio</button>
        <button type="button" className={`nav-btn ${activeTab === "improvement" ? "active" : ""}`} onClick={() => setActiveTab("improvement")}>Improvement</button>
        <div className="nav-spacer" />
        <span className="status-text">{profile?.username ?? "Pilot"}</span>
        <Link to="/account" state={{ from: location.pathname }} className="ghost nav-link">Account</Link>
        <button type="button" className="ghost" onClick={() => logout()}>Log Out</button>
      </aside>

      <main className="main-content">
        <header className="top">
          <div>
            <h1>RocketCoach Dashboard</h1>
            <div className="status-text">{status?.message ?? "Ready. Select a tab to start."}</div>
          </div>
          <div className="top-actions">
            <button type="button" onClick={loadCurrentSession}>Load Current Session</button>
            <button type="button" className="ghost" onClick={openReplayFolder}>Open Replay Folder</button>
          </div>
        </header>

        {error && <div className="alert">{error}</div>}

        {activeTab === "home" && (
          <section className="panel-stack">
            <div className="metrics-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                <div>
                  <h2>Dashboard Overview</h2>
                  <p className="status-text">Track your progress and recent performance</p>
                </div>
                <button type="button" className="ghost" onClick={() => setShowTutorial(true)}>How to Use</button>
              </div>
            </div>

            {latestReplay && (
              <div className="metrics-card">
                <h3>Latest Replay</h3>
                <div className="replay-card-highlight">
                  <div className="replay-card-main">
                    <div className="replay-result-badge">{replayCardLines(latestReplay).line1.split(" | ")[0]}</div>
                    <div className="replay-card-details">
                      <strong>{replayCardLines(latestReplay).line1}</strong>
                      <div className="library-item-meta">{replayCardLines(latestReplay).line2}</div>
                    </div>
                  </div>
                  <button type="button" onClick={() => void openSaved(latestReplay.session_id || latestReplay.id || "")}>Open Replay</button>
                </div>
              </div>
            )}

            <div className="metrics-card">
              <h3>Mechanic Performance Over Time</h3>
              <div className="chart-container">
                <LineChart series={progressSeries} width={820} height={230} />
              </div>
              {progressSeries.length === 0 && (
                <div className="library-item-meta">No data yet. Upload and analyze a replay to start tracking your progress.</div>
              )}
            </div>

            {latestReplay && groupedMechanics.length > 0 && (
              <div className="metrics-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h3 style={{ margin: 0 }}>Recent Mechanic Grades</h3>
                  <button type="button" style={{ fontSize: 13 }} onClick={() => setActiveTab("improvement")}>View Improvement Tips</button>
                </div>
                <div className="mechanic-summary-grid">
                  {groupedMechanics.slice(0, 6).map((group) => (
                    <div key={group.mechanicId} className="mechanic-summary-card">
                      <div className="mechanic-summary-label">{group.label}</div>
                      <div className="mechanic-summary-score">{Math.round(group.avg)}/100</div>
                      <div className="mechanic-summary-count">{group.items.length} events</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!latestReplay && (
              <div className="metrics-card empty-state">
                <h3>Get Started</h3>
                <p>Upload a replay file to begin analyzing your gameplay and receive personalized coaching.</p>
                <button type="button" onClick={() => setActiveTab("replays")}>Go to Replays</button>
              </div>
            )}
          </section>
        )}

        {activeTab === "replays" && (
          <section className="metrics-card">
            <div className="library-head">
              <h2>Replay Library</h2>
              <button type="button" className="ghost" onClick={() => void loadLibrary()} disabled={loadingLibraryOpen}>Refresh</button>
            </div>
            <div className="controls">
              <input
                id="replayFile"
                type="file"
                accept=".replay"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void uploadReplay(file);
                }}
              />
            </div>
            <div className="library-list replay-library-list">
              {(library?.data?.sessions ?? []).map((s) => {
                const sid = s.session_id || s.id || "";
                const lines = replayCardLines(s);
                const resultLabel = lines.line1.split(" | ")[0];
                return (
                  <div key={sid || s.replay_name} className="library-item replay-library-card">
                    <div className="replay-card-content">
                      <div className={`replay-badge replay-badge-${resultLabel.toLowerCase()}`}>{resultLabel}</div>
                      <div className="replay-card-info">
                        <strong>{lines.line1}</strong>
                        <div className="library-item-meta">{lines.line2}</div>
                      </div>
                    </div>
                    <button type="button" onClick={() => void openSaved(sid)} disabled={!sid || loadingLibraryOpen}>Open</button>
                  </div>
                );
              })}
              {!((library?.data?.sessions ?? []).length) && <div className="library-item-meta">No saved replays yet. Upload a .replay file to get started.</div>}
            </div>
          </section>
        )}

        {activeTab === "studio" && (
          <section className="layout studio-layout">
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
              onAutoEventPause={(ev) => {
                const k = `${String(ev.mechanicId || "")}|${Number(ev.time ?? 0).toFixed(3)}`;
                const fromCache = explainCache[k] || lookupCachedExplanation(String(ev.mechanicId || ""), Number(ev.time ?? 0));
                const fallback = {
                  title: `${englishEventName(ev.mechanicId)} @ ${fmtNumber(ev.time, 2)}s`,
                  body: ev.reason ? `Observed: ${ev.reason}` : "No explanation.",
                };
                setEventPopup(fromCache || fallback);
              }}
              eventPopup={
                eventPopup ? (
                  <div className="event-popup">
                    <div className="event-popup__head">
                      <strong>{eventPopup.title}</strong>
                      <button type="button" className="ghost" onClick={() => setEventPopup(null)}>Close</button>
                    </div>
                    <p>{eventPopup.body}</p>
                  </div>
                ) : null
              }
              boostPads={session?.boost_pads ?? []}
              seekTime={seekTime}
            />
            <div className="metrics-card studio-sidebar">
              <div className="studio-sidebar-section">
                <div className="controls" style={{ marginTop: 0, marginBottom: 12 }}>
                  <div className="pill">Player: {selectedPlayer || "unknown"}</div>
                  <button type="button" onClick={() => void analyzePlayer()} disabled={!selectedPlayer}>Analyze</button>
                </div>
              </div>

              <div className="studio-sidebar-section">
                <div className="section-header">
                  <h3>Live Metrics</h3>
                  <button type="button" className="ghost icon-btn" onClick={() => setShowLiveMetrics((v) => !v)}>
                    {showLiveMetrics ? "−" : "+"}
                  </button>
                </div>
                {showLiveMetrics && (
                  <div className="metric-grid">
                    {metricMeta.map((m) => (
                      <div className="metric-card" key={m.key}>
                        <div className="metric-head">
                          <h4>{m.label}</h4>
                          <button type="button" className="info-btn" onClick={() => setOpenMetricHelp((prev) => (prev === m.key ? "" : m.key))}>?</button>
                        </div>
                        <p className="metric-value">{fmtNumber(Number(metricSnapshot?.[m.key] ?? 0), 2)}</p>
                        {openMetricHelp === m.key && <div className="metric-help open">{m.hint}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="studio-sidebar-section">
                <h3>Mechanic Grades</h3>

                <div className="library-list mechanic-grades-list">
                  {groupedMechanics.map((group) => (
                    <div key={group.mechanicId} className="bubble-card mech-group">
                      <button
                        type="button"
                        className={`bubble-toggle mech-group-btn ${openMechanicId === group.mechanicId ? "active" : ""}`}
                        onClick={() => setOpenMechanicId((prev) => (prev === group.mechanicId ? "" : group.mechanicId))}
                      >
                        <span className="mech-label">{group.label}</span>
                        <span className="mech-stats">
                          <span className="mech-score">{Math.round(group.avg)}/100</span>
                          <span className="mech-count">{group.items.length} events</span>
                        </span>
                      </button>
                      {openMechanicId === group.mechanicId && (
                        <div className="bubble-body mech-events-wrap">
                          {group.items.map((ev, idx) => {
                            const score100 = Math.round(Number(ev.score ?? 0) * 100);
                            const quality = qualityText(ev.quality_label);
                            return (
                              <div key={`${group.mechanicId}-${idx}-${Number(ev.time ?? 0).toFixed(3)}`} className="library-item mech-event-item">
                                <div className="mech-event-info">
                                  <strong>{fmtNumber(ev.time ?? 0, 2)}s</strong>
                                  <div className="library-item-meta">
                                    <span className={`quality-badge quality-${quality.toLowerCase()}`}>{quality}</span>
                                    <span>Score {score100}/100</span>
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  className="coach-btn"
                                  onClick={async () => {
                                    const t = Number(ev.time ?? 0);
                                    setSeekTime(t);
                                    setEventExplainLoading(true);
                                    try {
                                      const k = eventKey(ev);
                                      const cached = explainCache[k] || lookupCachedExplanation(String(ev.mechanic_id || ""), Number(ev.time ?? 0));
                                      if (cached) {
                                        setEventExplain(cached);
                                        return;
                                      }
                                      const res = await apiPost<{ ok: boolean; data?: { llm?: { text?: string; error?: string } } }>(
                                        `${REPLAY_PREFIX}/mechanics/explain`,
                                        { time_s: t, mechanic_id: ev.mechanic_id ?? "", include_llm: true },
                                        { suppressErrorWindow: true }
                                      );
                                      const llmText = res?.data?.llm?.text || res?.data?.llm?.error || "No LLM explanation.";
                                      const payload = { title: `${englishEventName(ev.mechanic_id)} @ ${fmtNumber(t, 2)}s`, body: llmText };
                                      setExplainCache((prev) => ({ ...prev, [k]: payload }));
                                      setEventExplain(payload);
                                    } catch (err) {
                                      setEventExplain({ title: "Event Coach", body: err instanceof Error ? err.message : String(err) });
                                    } finally {
                                      setEventExplainLoading(false);
                                    }
                                  }}
                                >
                                  🎯 Coach
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  ))}
                  {!groupedMechanics.length && <div className="library-item-meta">No mechanic events loaded yet. Analyze a replay to see mechanic grades.</div>}
                </div>
              </div>

              <div className="studio-sidebar-section coach-panel">
                <h3>Coaching Feedback</h3>
                <div className="coach-content">
                  <strong>{eventExplain?.title ?? "Select an event"}</strong>
                  <p className="library-item-meta">
                    {eventExplainLoading ? "Loading coaching advice..." : (eventExplain?.body ?? "Click Coach on an event to jump to that moment and view personalized advice.")}
                  </p>
                </div>
              </div>

              {!!mechanicEvents.length && (
                <div className="studio-sidebar-section" style={{ borderBottom: "none", paddingBottom: 0 }}>
                  <button type="button" style={{ width: "100%" }} onClick={() => setActiveTab("improvement")}>
                    View Improvement Tips
                  </button>
                </div>
              )}
            </div>
          </section>
        )}
        {activeTab === "improvement" && (
          <section className="panel-stack">
            <div className="metrics-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
                <div>
                  <h2>Improvement Recommendations</h2>
                  <p className="library-item-meta">Recommendations are based on your replay analysis data</p>
                </div>
                <button type="button" className="ghost" onClick={() => setActiveTab("replays")}>Back to Replays</button>
              </div>

              <div className="improvement-toggle" style={{ marginTop: 16, marginBottom: 20 }}>
                <button
                  type="button"
                  className={improvementScope === "all" ? "" : "ghost"}
                  onClick={() => setImprovementScope("all")}
                >
                  All Replays
                </button>
                <button
                  type="button"
                  className={improvementScope === "latest" ? "" : "ghost"}
                  onClick={() => setImprovementScope("latest")}
                >
                  Latest Replay
                </button>
              </div>

              <h3 style={{ marginBottom: 14 }}>Top 3 Mechanics to Practice</h3>

              <div className="improvement-cards">
                {IMPROVEMENT_PLACEHOLDER.map((item) => (
                  <div key={item.rank} className="improvement-card">
                    <div className="improvement-card-header">
                      <div className={`improvement-rank improvement-rank--${item.rank}`}>#{item.rank}</div>
                      <div style={{ flex: 1 }}>
                        <strong style={{ fontSize: 15 }}>{item.mechanic}</strong>
                        <div style={{ marginTop: 4 }}>
                          <span className={`quality-badge improvement-priority--${item.priority.toLowerCase()}`}>{item.priority} Priority</span>
                        </div>
                      </div>
                    </div>
                    <p className="library-item-meta" style={{ lineHeight: 1.6, margin: "10px 0" }}>{item.description}</p>
                    <div className="improvement-tips">
                      <strong style={{ fontSize: 12 }}>Practice Tips</strong>
                      <p className="library-item-meta" style={{ marginTop: 4, fontStyle: "italic" }}>Coming soon — algorithm in development</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}
      </main>

      {noPlayerPopup && (
        <div className="drawer">
          <div className="drawer-panel">
            <h2>Replay Not Compatible</h2>
            <div className="alert">{noPlayerPopup}</div>
            <div className="loading-actions">
              <button type="button" onClick={() => setNoPlayerPopup("")}>Close</button>
            </div>
          </div>
        </div>
      )}

      {showTutorial && <TutorialModal onClose={closeTutorial} />}

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
              <button type="button" className="ghost" onClick={() => setLoadingOverlay((prev) => ({ ...prev, open: false }))}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
