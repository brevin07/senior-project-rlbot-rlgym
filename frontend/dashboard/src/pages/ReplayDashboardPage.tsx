import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiGet, apiPost } from "../api";
import { useAuth } from "../app/AuthContext";
import ReplayVisualizer from "../components/replay/ReplayVisualizer";
import LineChart from "../components/LineChart";

const REPLAY_PREFIX = "/api/replay";
const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

type AppTab = "home" | "replay" | "improvement" | "training" | "installer";
type TabReadyMap = Record<AppTab, boolean>;
type TabReasonMap = Record<AppTab, string>;

type ReplayStatus = {
  status?: string;
  progress?: number;
  message?: string;
  error?: string;
  replay_name?: string;
  phase?: string;
  checklist?: Record<string, boolean>;
  metrics_status?: string;
  analysis_player?: string;
  analysis_player_valid?: boolean;
  session_ready?: boolean;
  mechanics_ready?: boolean;
  explanations_ready?: boolean;
};

type ExplainProgress = {
  running?: boolean;
  complete?: boolean;
  generated_count?: number;
  cached_count?: number;
  pending_count?: number;
  total_count?: number;
  message?: string;
};

type LoadingOverlayState = {
  active: boolean;
  title: string;
  message: string;
  progress: number;
  phase: string;
  checklist: Record<string, boolean>;
  explain: ExplainProgress | null;
  error: string;
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
  analysis_player_valid?: boolean;
  session_ready?: boolean;
  mechanics_ready?: boolean;
  explanations_ready?: boolean;
};

type ProgressPoint = {
  x_time_unix: number;
  overall_mechanics_score: number;
  mechanic_scores?: Record<string, number>;
};

type ProgressResponse = {
  ok: boolean;
  data?: { points?: ProgressPoint[] };
};

type MechanicEvent = {
  time?: number;
  mechanic_id?: string;
  quality_label?: string;
  score?: number;
  reason?: string;
};

type MechanicsResponse = {
  ok: boolean;
  data?: {
    mechanic_events?: MechanicEvent[];
  };
};

type MetricsData = {
  ok: boolean;
  data?: { metrics_timeline?: { t: number; [k: string]: number }[] };
};

type DifficultyProfile = {
  tier?: string;
  label?: string;
  difficulty_value?: number;
  summary?: string;
  bot_profile_id?: string;
  play_style?: string;
};

type TrainingRecommendation = {
  focus_id?: string;
  title?: string;
  priority_rank?: number;
  priority_score?: number;
  confidence?: number;
  evidence?: string[];
  bot_required?: boolean;
  drill_mode_options?: string[];
  drill_mode_summaries?: Record<string, string>;
  difficulty_profiles?: DifficultyProfile[];
  difficulty_default?: DifficultyProfile;
  scenario_ids?: string[];
  bot_profile_ids?: string[];
};

type HomeSummaryResponse = {
  ok: boolean;
  data?: {
    latest_replay?: LibrarySession;
    progress?: { points?: ProgressPoint[] };
    recommendations?: TrainingRecommendation[];
    quick_launch?: {
      focus_id?: string;
      title?: string;
      difficulty_default?: DifficultyProfile;
      scenario_ids?: string[];
      drill_mode_options?: string[];
    };
  };
};

type TrainingPlanResponse = {
  ok: boolean;
  data?: {
    recommendations?: TrainingRecommendation[];
    session_count?: number;
  };
};

type TrainingPreflightResponse = {
  ok: boolean;
  data?: {
    host_checks_available?: boolean;
    launcher_kind?: string;
    launcher_running?: boolean;
    dependency_ready?: boolean;
    shared_dependency_ready?: boolean;
    python_ready?: boolean;
    rlbot_import_ok?: boolean;
    rlbot_gui_detected?: boolean;
    rlbot_gui_path?: string;
    rlbot_gui_detection_source?: string;
    rocket_league_detected?: boolean;
    last_checked_at?: number;
    scenario_count?: number;
    bot_statuses?: {
      bot_profile_id?: string;
      bot_name?: string;
      config_path?: string;
      python_file?: string;
      requirements_file?: string;
      ready?: boolean;
      missing_modules?: string[];
      messages?: string[];
    }[];
    ready_to_launch?: boolean;
    messages?: string[];
  };
};

type TrainingLaunchResponse = {
  ok: boolean;
  data?: {
    queued?: boolean;
    route?: string;
    launcher_kind?: string;
    bot_name?: string;
    playlist_name?: string;
    status_message?: string;
  };
};

type TrainingLaunchFeedback = {
  phase: "sending" | "opening" | "success" | "error";
  message: string;
  detail?: string;
};

type ExplainBatchResponse = {
  ok: boolean;
  data?: {
    items?: { key?: string; title?: string; body?: string }[];
    complete?: boolean;
    all_complete?: boolean;
    generated_count?: number;
    cached_count?: number;
    pending_count?: number;
    background_started?: boolean;
    priority_ready?: boolean;
    priority_limit?: number;
    remaining_count?: number;
  };
};

const metricMeta = [
  { key: "speed", label: "Speed" },
  { key: "hesitation_percent", label: "Hesitation %" },
  { key: "boost_waste_percent", label: "Boost Waste %" },
  { key: "pressure_percent", label: "Pressure %" },
  { key: "whiff_rate_per_min", label: "Whiff Rate / min" },
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
    kickoff: "Kickoff",
    shadow_defense: "Shadow Defense",
    challenge: "Challenge Timing",
    flicking: "Flicks",
    carrying_dribbling: "Carry + Dribble",
    flicking_carry_offense: "Flicks",
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
    if (t === 0) result = blue > orange ? "Win" : blue < orange ? "Loss" : "Draw";
    else if (t === 1) result = orange > blue ? "Win" : orange < blue ? "Loss" : "Draw";
  }

  return {
    line1: `${result} | ${score} | ${player} | ${arena} | Grade ${grade}`,
    line2: `${s.source_type || "replay"} | ${fmtDuration(Number(s.duration_s || 0))} | ${dateIso || "Unknown date"}`,
  };
}

function explanationProgressLabel(progress: ExplainProgress | null) {
  if (!progress) return "Preparing event coaching...";
  const total = Number(progress.total_count || 0);
  const done = Number(progress.generated_count || 0) + Number(progress.cached_count || 0);
  if (!total) return progress.message || "Preparing event coaching...";
  return `${progress.message || "Preparing event coaching..."} (${done}/${total})`;
}

const INITIAL_EXPLAIN_LIMIT = 10;

export default function ReplayDashboardPage() {
  const { profile, logout } = useAuth();
  const location = useLocation();
  const retryReplayActionRef = useRef<(() => Promise<void>) | null>(null);

  const [activeTab, setActiveTab] = useState<AppTab>("home");
  const [status, setStatus] = useState<ReplayStatus | null>(null);
  const [session, setSession] = useState<ReplaySession | null>(null);
  const [library, setLibrary] = useState<LibraryResponse | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [mechanics, setMechanics] = useState<MechanicsResponse | null>(null);
  const [homeSummary, setHomeSummary] = useState<HomeSummaryResponse | null>(null);
  const [trainingPlan, setTrainingPlan] = useState<TrainingPlanResponse | null>(null);
  const [trainingPreflight, setTrainingPreflight] = useState<TrainingPreflightResponse | null>(null);
  const [trainingPreflightFetchedAt, setTrainingPreflightFetchedAt] = useState(0);
  const [trainingPreflightChecking, setTrainingPreflightChecking] = useState(false);
  const [trainingVerificationRunning, setTrainingVerificationRunning] = useState(false);
  const [trainingVerificationMessage, setTrainingVerificationMessage] = useState("");
  const [selectedPlayer, setSelectedPlayer] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const [seekTime, setSeekTime] = useState<number | undefined>(undefined);
  const [eventExplain, setEventExplain] = useState<{ title: string; body: string } | null>(null);
  const [eventExplainLoading, setEventExplainLoading] = useState(false);
  const [explainCache, setExplainCache] = useState<Record<string, { title: string; body: string }>>({});
  const [trainingSelections, setTrainingSelections] = useState<Record<string, { tier: string; drillMode: string }>>({});
  const [launchingFocus, setLaunchingFocus] = useState("");
  const [trainingLaunchFeedback, setTrainingLaunchFeedback] = useState<Record<string, TrainingLaunchFeedback>>({});
  const [error, setError] = useState("");
  const [tabReady, setTabReady] = useState<TabReadyMap>({ home: false, replay: false, improvement: false, training: false, installer: true });
  const [tabReasons, setTabReasons] = useState<TabReasonMap>({
    home: "Loading dashboard summary...",
    replay: "Loading replay library...",
    improvement: "Loading replay trends...",
    training: "Generating training plan...",
    installer: "",
  });
  const [replayStudioReady, setReplayStudioReady] = useState(false);
  const [overlay, setOverlay] = useState<LoadingOverlayState>({
    active: false,
    title: "",
    message: "",
    progress: 0,
    phase: "idle",
    checklist: {},
    explain: null,
    error: "",
  });
  const trainingPreflightFresh = Boolean(trainingPreflight && (Date.now() - trainingPreflightFetchedAt) < 60_000);
  const trainingPreflightLastChecked = Number(trainingPreflight?.data?.last_checked_at || 0);
  const trainingPreflightBotStatuses = trainingPreflight?.data?.bot_statuses ?? [];
  const trainingPreflightBotStatusMap = Object.fromEntries(
    trainingPreflightBotStatuses.map((status) => [String(status.bot_profile_id || ""), status])
  );

  const loadStatus = useCallback(async () => {
    const resp = await apiGet<ReplayStatus>(`${REPLAY_PREFIX}/replay/status`, { suppressErrorWindow: true });
    setStatus(resp);
    return resp;
  }, []);

  const loadExplainProgress = useCallback(async () => {
    const resp = await apiGet<{ ok: boolean; data?: ExplainProgress }>(`${REPLAY_PREFIX}/mechanics/explain_progress`, { suppressErrorWindow: true });
    return resp?.data || null;
  }, []);

  const loadLibrary = useCallback(async () => {
    const resp = await apiGet<LibraryResponse>(`${REPLAY_PREFIX}/replay/library`, { suppressErrorWindow: true });
    setLibrary(resp);
    return resp;
  }, []);

  const loadProgress = useCallback(async () => {
    const resp = await apiGet<ProgressResponse>(`${REPLAY_PREFIX}/profile/progress`, { suppressErrorWindow: true });
    setProgress(resp);
    return resp;
  }, []);

  const loadHomeSummary = useCallback(async () => {
    const resp = await apiGet<HomeSummaryResponse>(`${REPLAY_PREFIX}/home/summary`, { suppressErrorWindow: true });
    setHomeSummary(resp);
    return resp;
  }, []);

  const loadTrainingPlan = useCallback(async () => {
    const resp = await apiGet<TrainingPlanResponse>(`${REPLAY_PREFIX}/training/plan`, { suppressErrorWindow: true });
    setTrainingPlan(resp);
    return resp;
  }, []);

  const loadTrainingPreflight = useCallback(async (options?: { force?: boolean }) => {
    const force = Boolean(options?.force);
    const cacheFresh = trainingPreflight && (Date.now() - trainingPreflightFetchedAt) < 60_000;
    if (!force && cacheFresh) {
      return trainingPreflight;
    }
    setTrainingPreflightChecking(true);
    try {
      const resp = await apiGet<TrainingPreflightResponse>(`${REPLAY_PREFIX}/training/preflight`, { suppressErrorWindow: true });
      setTrainingPreflight(resp);
      setTrainingPreflightFetchedAt(Date.now());
      return resp;
    } finally {
      setTrainingPreflightChecking(false);
    }
  }, [trainingPreflight, trainingPreflightFetchedAt]);

  const wakeTrainingCompanion = useCallback(async () => {
    const iframe = document.createElement("iframe");
    iframe.style.display = "none";
    iframe.setAttribute("aria-hidden", "true");
    iframe.src = "rocketcoach://verify-deps";
    document.body.appendChild(iframe);
    await sleep(1200);
    document.body.removeChild(iframe);
  }, []);

  const verifyDependencies = useCallback(async () => {
    setError("");
    setTrainingVerificationRunning(true);
    try {
      setTrainingVerificationMessage("Checking for an active RocketCoach Companion...");
      const immediate = await loadTrainingPreflight({ force: true });
      if (immediate?.data?.launcher_running) {
        setTrainingVerificationMessage("RocketCoach Companion is running. Refreshing dependency checks...");
        const refreshed = await loadTrainingPreflight({ force: true });
        if (refreshed?.data?.dependency_ready) {
          setTrainingVerificationMessage("Dependencies verified. Bot drills are ready to launch.");
        } else {
          setTrainingVerificationMessage("Dependency scan finished. Review the missing items below.");
        }
        return refreshed;
      }

      setTrainingVerificationMessage("Starting the local RocketCoach Companion...");
      await wakeTrainingCompanion();

      for (let attempt = 0; attempt < 20; attempt += 1) {
        await sleep(1000);
        setTrainingVerificationMessage(`Waiting for the local RocketCoach Companion... (${attempt + 1}/20)`);
        const polled = await loadTrainingPreflight({ force: true });
        if (polled?.data?.launcher_running) {
          if (polled?.data?.dependency_ready) {
            setTrainingVerificationMessage("Dependencies verified. Bot drills are ready to launch.");
          } else {
            setTrainingVerificationMessage("RocketCoach Companion connected. Review the dependency results below.");
          }
          return polled;
        }
      }

      throw new Error(
        "RocketCoach Companion did not respond. Install the RLBot stack installer, then try Verify Dependencies again."
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setTrainingVerificationMessage(message);
      throw err;
    } finally {
      setTrainingVerificationRunning(false);
    }
  }, [loadTrainingPreflight, wakeTrainingCompanion]);

  const loadMechanics = useCallback(async () => {
    const resp = await apiGet<MechanicsResponse>(`${REPLAY_PREFIX}/mechanics/current`, { suppressErrorWindow: true });
    setMechanics(resp);
    return resp;
  }, []);

  const loadMetrics = useCallback(async (player: string) => {
    if (!player) return null;
    const resp = await apiGet<MetricsData>(`${REPLAY_PREFIX}/replay/player_metrics/data?player=${encodeURIComponent(player)}`, {
      suppressErrorWindow: true,
    });
    setMetrics(resp);
    return resp;
  }, []);

  const loadReplaySession = useCallback(async () => {
    const sess = await apiGet<{ ok: boolean; data?: ReplaySession }>(`${REPLAY_PREFIX}/replay/session`, { suppressErrorWindow: true });
    const data = sess?.data ?? null;
    setSession(data);
    const players = data?.players ?? [];
    const preferred = players.includes(String(data?.analysis_player || "")) ? String(data?.analysis_player || "") : String(players[0] || "");
    setSelectedPlayer(preferred);
    return { session: data, preferred };
  }, []);

  const refreshSummaryViews = useCallback(async () => {
    const [, libraryResp, progressResp, , trainingResp] = await Promise.all([
      loadStatus(),
      loadLibrary(),
      loadProgress(),
      loadHomeSummary(),
      loadTrainingPlan(),
    ]);
    void loadTrainingPreflight().catch(() => undefined);
    setTabReady({
      home: true,
      replay: true,
      improvement: true,
      training: true,
      installer: true,
    });
    setTabReasons({
      home: "",
      replay: libraryResp?.data ? "" : "Loading replay library...",
      improvement: progressResp?.data ? "" : "Loading replay trends...",
      training: trainingResp?.data ? "" : "Generating training plan...",
      installer: "",
    });
  }, [loadHomeSummary, loadLibrary, loadProgress, loadStatus, loadTrainingPlan, loadTrainingPreflight]);

  useEffect(() => {
    void refreshSummaryViews().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [refreshSummaryViews]);

  useEffect(() => {
    if (activeTab !== "training") return;
    if (trainingPreflight && trainingPreflightFresh) return;
    void loadTrainingPreflight().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [activeTab, loadTrainingPreflight, trainingPreflight, trainingPreflightFresh]);

  useEffect(() => {
    if (!replayStudioReady) return;
    const isComplete = Boolean(overlay.explain?.complete);
    const isRunning = Boolean(overlay.explain?.running);
    if (!isRunning || isComplete) return;
    const pollId = window.setInterval(() => {
      void loadExplainProgress()
        .then((progressResp) => {
          if (!progressResp) return;
          setOverlay((prev) => ({
            ...prev,
            explain: progressResp,
          }));
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(pollId);
  }, [loadExplainProgress, overlay.explain?.complete, overlay.explain?.running, replayStudioReady]);

  const openReplayFolder = async () => {
    try {
      await apiPost(`${REPLAY_PREFIX}/replay/open_default_folder`, {}, { suppressErrorWindow: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const startOverlay = useCallback((title: string, message: string) => {
    setOverlay({
      active: true,
      title,
      message,
      progress: 0.05,
      phase: "starting",
      checklist: {},
      explain: null,
      error: "",
    });
  }, []);

  const updateOverlayFromStatus = useCallback((snapshot: ReplayStatus | null, messageOverride?: string) => {
    setOverlay((prev) => ({
      ...prev,
      message: messageOverride || snapshot?.message || prev.message,
      progress: Number(snapshot?.progress ?? prev.progress ?? 0),
      phase: String(snapshot?.phase || snapshot?.status || prev.phase || "loading"),
      checklist: snapshot?.checklist || prev.checklist,
    }));
  }, []);

  const pollReplayReady = useCallback(async () => {
    for (let attempt = 0; attempt < 90; attempt += 1) {
      const snapshot = await loadStatus();
      updateOverlayFromStatus(snapshot);
      if (snapshot?.error) {
        throw new Error(String(snapshot.error));
      }
      if (snapshot?.status === "ready" && snapshot?.checklist?.timeline_ready) {
        return snapshot;
      }
      await sleep(800);
    }
    throw new Error("Replay loading timed out before the timeline was ready.");
  }, [loadStatus, updateOverlayFromStatus]);

  const preloadExplanations = useCallback(async () => {
    setOverlay((prev) => ({
      ...prev,
      message: "Preparing priority coaching before opening replay studio...",
      progress: Math.max(prev.progress, 0.72),
      phase: "explaining",
    }));
    const pollId = window.setInterval(() => {
      void loadExplainProgress()
        .then((progressResp) => {
          setOverlay((prev) => ({
            ...prev,
            explain: progressResp,
            message: explanationProgressLabel(progressResp),
          }));
        })
        .catch(() => undefined);
    }, 800);
    try {
      const resp = await apiPost<ExplainBatchResponse>(
        `${REPLAY_PREFIX}/mechanics/explain_batch`,
        { include_llm: true, mode: "initial_fast", time_budget_s: 12, preload_limit: INITIAL_EXPLAIN_LIMIT },
        { suppressErrorWindow: true }
      );
      const items = resp?.data?.items ?? [];
      const nextCache: Record<string, { title: string; body: string }> = {};
      for (const item of items) {
        const key = String(item?.key || "");
        if (!key) continue;
        nextCache[key] = {
          title: String(item?.title || "Event Coach"),
          body: String(item?.body || "No LLM explanation."),
        };
      }
      setExplainCache((prev) => ({ ...prev, ...nextCache }));
      const priorityReady = Boolean(resp?.data?.priority_ready);
      const pendingCount = Number(resp?.data?.pending_count || 0);
      const allComplete = Boolean(resp?.data?.all_complete || resp?.data?.complete);
      setOverlay((prev) => ({
        ...prev,
        explain: {
          running: pendingCount > 0,
          complete: allComplete,
          generated_count: Number(resp?.data?.generated_count || 0),
          cached_count: Number(resp?.data?.cached_count || 0),
          pending_count: pendingCount,
          total_count: items.length,
          message: !priorityReady
            ? "Replay is opening now. Coaching explanations are still generating in the background."
            : allComplete
            ? "Replay coaching is ready."
            : "Priority replay coaching is ready. More explanations are loading in the background.",
        },
        progress: 1,
        message: !priorityReady
          ? "Replay is opening now. Coaching explanations are still generating in the background."
          : allComplete
          ? "Replay coaching is ready."
          : "Priority replay coaching is ready. More explanations are loading in the background.",
      }));
    } finally {
      window.clearInterval(pollId);
    }
  }, [loadExplainProgress]);

  const hydrateReplayStudio = useCallback(async () => {
    setReplayStudioReady(false);
    setMetrics(null);
    setMechanics(null);
    setEventExplain(null);
    setEventExplainLoading(false);
    setSeekTime(undefined);
    setCurrentTime(0);

    const loaded = await loadReplaySession();
    const replaySession = loaded.session;
    const preferred = String(loaded.preferred || "");
    if (!replaySession) {
      throw new Error("Replay session could not be loaded.");
    }
    if (!preferred || !(replaySession.players || []).includes(preferred)) {
      throw new Error("Replay session loaded without a valid analysis player.");
    }

    setOverlay((prev) => ({
      ...prev,
      message: "Loading player metrics and mechanic grades...",
      progress: Math.max(prev.progress, 0.58),
      phase: "analysis",
    }));
    await Promise.all([loadMetrics(preferred), loadMechanics()]);
    await preloadExplanations();
    setReplayStudioReady(true);
  }, [loadMechanics, loadMetrics, loadReplaySession, preloadExplanations]);

  const runReplayPipeline = useCallback(
    async ({ title, startRequest, waitForParser }: { title: string; startRequest: () => Promise<any>; waitForParser?: boolean | null }) => {
      setError("");
      startOverlay(title, "Starting replay load...");
      try {
        const openResp = await startRequest();
        const shouldWaitForParser =
          waitForParser == null ? String(openResp?.open_mode || "") !== "prepared_cache" : Boolean(waitForParser);
        if (shouldWaitForParser) {
          await pollReplayReady();
        } else {
          const snapshot = await loadStatus();
          updateOverlayFromStatus(snapshot, "Loading replay from prepared cache...");
        }
        await hydrateReplayStudio();
        await refreshSummaryViews();
        setOverlay((prev) => ({ ...prev, active: false, error: "" }));
        setActiveTab("replay");
        return openResp;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setOverlay((prev) => ({ ...prev, active: true, error: message, message }));
        setReplayStudioReady(false);
        setError(message);
        throw err;
      }
    },
    [hydrateReplayStudio, loadStatus, pollReplayReady, refreshSummaryViews, startOverlay, updateOverlayFromStatus]
  );

  const uploadReplay = async (file: File) => {
    retryReplayActionRef.current = null;
    try {
      await runReplayPipeline({
        title: "Loading Replay",
        waitForParser: true,
        startRequest: async () => {
          const fd = new FormData();
          fd.append("file", file);
          const res = await fetch(`${REPLAY_PREFIX}/replay/upload`, { method: "POST", body: fd, credentials: "include" });
          const body = await res.json();
          if (!res.ok || !body?.ok) throw new Error(String(body?.error || `${res.status} ${res.statusText}`));
          return body;
        },
      });
    } catch {
      return;
    }
  };

  const openSaved = useCallback(async (sid: string) => {
    retryReplayActionRef.current = () => openSaved(sid);
    try {
      await runReplayPipeline({
        title: "Opening Saved Replay",
        waitForParser: null,
        startRequest: async () =>
          apiPost<{ ok: boolean; session_id?: string; open_mode?: string }>(
            `${REPLAY_PREFIX}/replay/open_saved`,
            { session_id: sid },
            { suppressErrorWindow: true }
          ),
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setOverlay((prev) => ({ ...prev, active: true, error: message, message }));
      setReplayStudioReady(false);
      setError(message);
    }
  }, [runReplayPipeline]);

  const analyzePlayer = async () => {
    if (!selectedPlayer) return;
    retryReplayActionRef.current = () => analyzePlayer();
    try {
      startOverlay("Reanalyzing Replay", "Running analysis for the selected player...");
      await apiPost(`${REPLAY_PREFIX}/replay/analysis/select_player`, { player: selectedPlayer }, { suppressErrorWindow: true });
      await apiPost(`${REPLAY_PREFIX}/replay/analysis/run`, {}, { suppressErrorWindow: true });
      await hydrateReplayStudio();
      await refreshSummaryViews();
      setOverlay((prev) => ({ ...prev, active: false, error: "" }));
      setActiveTab("replay");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setOverlay((prev) => ({ ...prev, active: true, error: message, message }));
      setReplayStudioReady(false);
      setError(message);
    }
  };

  const loadCurrentSession = async () => {
    retryReplayActionRef.current = () => loadCurrentSession();
    try {
      startOverlay("Loading Current Session", "Preparing current replay session...");
      const snapshot = await loadStatus();
      if (!snapshot?.session_ready && !snapshot?.status) {
        throw new Error("No replay session is currently loaded.");
      }
      updateOverlayFromStatus(snapshot, "Preparing current replay session...");
      await hydrateReplayStudio();
      await refreshSummaryViews();
      setOverlay((prev) => ({ ...prev, active: false, error: "" }));
      setActiveTab("replay");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setOverlay((prev) => ({ ...prev, active: true, error: message, message }));
      setReplayStudioReady(false);
      setError(message);
    }
  };

  const openTab = (tab: AppTab) => {
    if (!tabReady[tab]) return;
    setActiveTab(tab);
  };

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

  const progressPoints = progress?.data?.points ?? homeSummary?.data?.progress?.points ?? [];
  const progressSeries = useMemo(
    () => progressPoints.map((p) => ({ t: Number(p.x_time_unix || 0), v: Number(p.overall_mechanics_score || 0) * 100 })),
    [progressPoints]
  );

  const latestScore = progressSeries.length ? Math.round(progressSeries[progressSeries.length - 1].v) : 0;
  const prevScores = progressSeries.slice(-6, -3);
  const recentScores = progressSeries.slice(-3);
  const trendUp = recentScores.length && prevScores.length
    ? recentScores.reduce((s, p) => s + p.v, 0) / recentScores.length >= prevScores.reduce((s, p) => s + p.v, 0) / prevScores.length
    : true;

  const perMechanicSeries = useMemo(() => {
    const out: Record<string, { t: number; v: number }[]> = {};
    for (const point of progressPoints) {
      const t = Number(point.x_time_unix || 0);
      const mechScores = point.mechanic_scores || {};
      Object.entries(mechScores).forEach(([key, value]) => {
        if (!out[key]) out[key] = [];
        out[key].push({ t, v: Number(value || 0) });
      });
    }
    return out;
  }, [progressPoints]);

  const mechanicEvents = mechanics?.data?.mechanic_events ?? [];
  const groupedMechanics = useMemo(() => {
    const groups = new Map<string, { mechanicId: string; label: string; items: MechanicEvent[]; avg: number }>();
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
    return [...groups.values()].sort((a, b) => a.avg - b.avg);
  }, [mechanicEvents]);

  const recommendations = trainingPlan?.data?.recommendations ?? homeSummary?.data?.recommendations ?? [];
  const latestReplay = homeSummary?.data?.latest_replay || (library?.data?.sessions ?? [])[0];
  const botTrainingReady = Boolean(trainingPreflight?.data?.ready_to_launch);
  const trainingPreflightMessages = trainingPreflight?.data?.messages ?? [];
  const hostChecksAvailable = trainingPreflight?.data?.host_checks_available !== false;
  const trainingLauncherRunning = Boolean(trainingPreflight?.data?.launcher_running);
  const dependencyReady = Boolean(trainingPreflight?.data?.dependency_ready);
  const sharedDependencyReady = Boolean(trainingPreflight?.data?.shared_dependency_ready);
  const rlbotGuiPath = String(trainingPreflight?.data?.rlbot_gui_path || "");
  const rlbotGuiSource = String(trainingPreflight?.data?.rlbot_gui_detection_source || "");

  const setTrainingTier = (focusId: string, tier: string) => {
    setTrainingSelections((prev) => ({
      ...prev,
      [focusId]: { tier, drillMode: prev[focusId]?.drillMode || "" },
    }));
  };

  const setTrainingDrillMode = (focusId: string, drillMode: string) => {
    setTrainingSelections((prev) => ({
      ...prev,
      [focusId]: { tier: prev[focusId]?.tier || "beginner", drillMode },
    }));
  };

  const launchTraining = async (rec: TrainingRecommendation) => {
    const focusId = String(rec.focus_id || "");
    const profiles = rec.difficulty_profiles ?? [];
    const selection = trainingSelections[focusId];
    const tier = selection?.tier || String(rec.difficulty_default?.tier || profiles[0]?.tier || "beginner");
    const profileChoice = profiles.find((p) => p.tier === tier) || rec.difficulty_default || profiles[0] || {};
    const drillMode = selection?.drillMode || String(rec.drill_mode_options?.[0] || "");
    let openingTimer: number | null = null;
    try {
      const preflightResp = (!trainingPreflight || !trainingPreflightFresh)
        ? await loadTrainingPreflight({ force: true })
        : trainingPreflight;
      const preflightData = preflightResp?.data ?? {};
      const preflightMessages = preflightData.messages ?? [];
      const preflightReady = Boolean(preflightData.ready_to_launch);
      const sharedReady = Boolean(preflightData.shared_dependency_ready);
      const launcherRunning = Boolean(preflightData.launcher_running);
      const selectedBotStatus = (preflightData.bot_statuses ?? []).find(
        (status) => String(status.bot_profile_id || "") === String(profileChoice.bot_profile_id || "")
      );
        if (rec.bot_required && (!launcherRunning || !sharedReady)) {
          const message = preflightMessages[0] || "RLBot setup is incomplete. Run Verify Dependencies before launching bot drills.";
          setTrainingLaunchFeedback((prev) => ({
            ...prev,
            [focusId]: {
            phase: "error",
            message,
          },
        }));
        return;
      }
      if (rec.bot_required && selectedBotStatus && !selectedBotStatus.ready) {
        const detail = (selectedBotStatus.messages ?? [])[0] || "The mapped bot is not launch-ready yet.";
        setTrainingLaunchFeedback((prev) => ({
          ...prev,
          [focusId]: {
            phase: "error",
            message: `${selectedBotStatus.bot_name || "This bot"} is not ready to launch.`,
            detail,
          },
        }));
        return;
      }
      setError("");
      setLaunchingFocus(focusId);
      setTrainingLaunchFeedback((prev) => ({
        ...prev,
        [focusId]: {
          phase: "sending",
          message: "Sending launch request...",
        },
      }));
      openingTimer = window.setTimeout(() => {
        setTrainingLaunchFeedback((prev) => {
          if (launchingFocus !== focusId && prev[focusId]?.phase !== "sending") return prev;
          return {
            ...prev,
            [focusId]: {
              phase: "opening",
              message: "Opening Rocket League / RLBot...",
            },
          };
        });
      }, 500);
      const resp = await apiPost<TrainingLaunchResponse>(
        `${REPLAY_PREFIX}/training/launch`,
        {
          focus_id: focusId,
          difficulty_tier: tier,
          difficulty_value: Number(profileChoice.difficulty_value || 0.3),
          bot_profile_id: String(profileChoice.bot_profile_id || ""),
          scenario_ids: rec.scenario_ids || [],
          drill_mode: drillMode,
          bot_required: Boolean(rec.bot_required),
        },
        { suppressErrorWindow: true }
      );
      const launchData = resp?.data ?? {};
      const detailParts = [
        launchData.playlist_name ? `Playlist: ${launchData.playlist_name}` : "",
        launchData.bot_name ? `Bot: ${launchData.bot_name}` : "",
        launchData.launcher_kind ? `Launcher: ${launchData.launcher_kind}` : "",
      ].filter(Boolean);
      setTrainingLaunchFeedback((prev) => ({
        ...prev,
        [focusId]: {
          phase: "success",
          message:
            launchData.status_message ||
            "Training match requested. Check Rocket League. If nothing takes focus within a few seconds, check the training bridge console window for the exact error.",
          detail: detailParts.join(" | "),
        },
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setTrainingLaunchFeedback((prev) => ({
        ...prev,
        [focusId]: {
          phase: "error",
          message,
          detail: "Check the training bridge console window for additional RLBot startup details.",
        },
      }));
    } finally {
      if (openingTimer != null) {
        window.clearTimeout(openingTimer);
      }
      setLaunchingFocus("");
    }
  };

  const TAB_ICONS: Record<AppTab, string> = {
    home: "fa-solid fa-house",
    replay: "fa-solid fa-film",
    improvement: "fa-solid fa-chart-line",
    training: "fa-solid fa-dumbbell",
    installer: "fa-solid fa-download",
  };

  const renderTabButton = (tab: AppTab, label: string) => (
    <button
      type="button"
      className={`nav-btn ${activeTab === tab ? "active" : ""}`}
      onClick={() => openTab(tab)}
      disabled={!tabReady[tab]}
      title={tabReady[tab] ? label : tabReasons[tab]}
    >
      <span className="nav-btn-content">
        <i className={TAB_ICONS[tab]} />
        <span>{label}</span>
      </span>
      {!tabReady[tab] && <span className="nav-btn-subtitle">{tabReasons[tab]}</span>}
    </button>
  );

  return (
    <div className="dashboard-shell">
      <aside className="left-nav">
        <div className="nav-brand">
          <span className="nav-brand-icon">RC</span>
          <span className="nav-brand-text">RocketCoach</span>
        </div>
        <nav className="nav-group">
          <div className="nav-group-label">Dashboard</div>
          {renderTabButton("home", "Home")}
          {renderTabButton("replay", "Replay")}
          {renderTabButton("improvement", "Improvement")}
        </nav>
        <nav className="nav-group">
          <div className="nav-group-label">Tools</div>
          {renderTabButton("training", "Training")}
          {renderTabButton("installer", "Installer")}
        </nav>
        <div className="nav-spacer" />
        <div className="nav-footer">
          <div className="nav-user">
            <i className="fa-solid fa-user-astronaut" />
            <span>{profile?.username ?? "Pilot"}</span>
          </div>
          <Link to="/live" className="nav-footer-link"><i className="fa-solid fa-satellite-dish" /><span>Live Trainer</span></Link>
          <Link to="/account" state={{ from: location.pathname }} className="nav-footer-link"><i className="fa-solid fa-gear" /><span>Account</span></Link>
          <button type="button" className="nav-footer-link" onClick={() => logout()}><i className="fa-solid fa-right-from-bracket" /><span>Log Out</span></button>
        </div>
      </aside>

      <main className="main-content">
        <header className="top">
          <div>
            <h1>RocketCoach Dashboard</h1>
            <div className="status-text">{status?.message ?? "Review replays, track progress, and launch training."}</div>
          </div>
          <div className="top-actions">
            <button type="button" onClick={() => void loadCurrentSession()}>Load Current Session</button>
            <button type="button" className="ghost" onClick={() => void openReplayFolder()}>Open Replay Folder</button>
          </div>
        </header>

        {error && <div className="alert">{error}</div>}

        {activeTab === "home" && (
          <section className="panel-stack">
            <div className="metrics-card">
              <h2>Home</h2>
              <p className="status-text">A quick summary of your recent replay data and the next thing to work on.</p>
            </div>

            {latestReplay ? (
              <div className="metrics-card">
                <div className="card-header">
                  <div>
                    <h3>Recent Performance</h3>
                    <strong>{replayCardLines(latestReplay).line1}</strong>
                    <div className="library-item-meta">{replayCardLines(latestReplay).line2}</div>
                  </div>
                  <button type="button" onClick={() => void openSaved(latestReplay.session_id || latestReplay.id || "")}>Open Latest Replay</button>
                </div>
              </div>
            ) : (
              <div className="metrics-card welcome-card">
                <div className="welcome-header">
                  <div className="welcome-icon"><i className="fa-solid fa-rocket" /></div>
                  <div>
                    <h2>Welcome to RocketCoach{profile?.username ? `, ${profile.username}` : ""}</h2>
                    <p className="text-muted">Upload your first replay to unlock coaching feedback, trend tracking, and personalized training.</p>
                  </div>
                </div>
                <div className="welcome-steps">
                  <div className="welcome-step">
                    <div className="welcome-step-number">1</div>
                    <div>
                      <strong>Upload a replay</strong>
                      <p className="text-muted">Drop a .replay file from your Rocket League replays folder.</p>
                    </div>
                  </div>
                  <div className="welcome-step">
                    <div className="welcome-step-number">2</div>
                    <div>
                      <strong>Get graded</strong>
                      <p className="text-muted">RocketCoach analyzes every mechanic and gives you scores.</p>
                    </div>
                  </div>
                  <div className="welcome-step">
                    <div className="welcome-step-number">3</div>
                    <div>
                      <strong>Train smarter</strong>
                      <p className="text-muted">Practice recommendations tailored to your weaknesses.</p>
                    </div>
                  </div>
                </div>
                <button type="button" onClick={() => openTab("replay")}><i className="fa-solid fa-upload" /> Upload Your First Replay</button>
              </div>
            )}

            <div className="metrics-card">
              <h3>Progress Snapshot</h3>
              <div className="chart-container">
                <LineChart series={progressSeries} width={820} height={220} />
              </div>
              {!progressSeries.length && <div className="library-item-meta">No progress data yet. Analyze a replay to start building your trend line.</div>}
            </div>

            <div className="metrics-card">
              <div className="card-header">
                <div>
                  <h3>What To Work On</h3>
                  <p className="library-item-meta">Short prescriptive guidance based on your most recent replay-backed recommendations.</p>
                </div>
                <button type="button" className="ghost" onClick={() => openTab("training")} disabled={!tabReady.training}>Open Training</button>
              </div>
              <div className="improvement-cards">
                {recommendations.slice(0, 3).map((rec) => (
                  <div key={rec.focus_id || rec.title} className="improvement-card">
                    <div className="improvement-card-header">
                      <div className={`improvement-rank improvement-rank--${Math.min(Number(rec.priority_rank || 1), 3)}`}>#{rec.priority_rank || 1}</div>
                      <div style={{ flex: 1 }}>
                        <strong style={{ fontSize: 15 }}>{rec.title || "Focus"}</strong>
                        <div className="library-item-meta">Confidence {Math.round(Number(rec.confidence || 0) * 100)}%</div>
                      </div>
                    </div>
                    <p className="library-item-meta" style={{ lineHeight: 1.6, margin: "10px 0" }}>
                      {(rec.evidence ?? [])[0] || "Analyze more replays to enrich this recommendation."}
                    </p>
                    <button type="button" onClick={() => openTab("training")} disabled={!tabReady.training}>Train This Mechanic</button>
                  </div>
                ))}
                {!recommendations.length && <div className="library-item-meta">Recommendations will appear here once you have replay analysis data.</div>}
              </div>
            </div>
          </section>
        )}

        {activeTab === "replay" && (
          <section className="panel-stack">
            <div className="metrics-card">
              <div className="library-head">
                <h2>Replay Library</h2>
                <button type="button" className="ghost" onClick={() => void refreshSummaryViews()}>Refresh</button>
              </div>
              <div className="controls">
                <input
                  id="replayFile"
                  type="file"
                  accept=".replay"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void uploadReplay(file);
                    e.currentTarget.value = "";
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
                      <button type="button" onClick={() => void openSaved(sid)} disabled={!sid}>Open</button>
                    </div>
                  );
                })}
                {!((library?.data?.sessions ?? []).length) && <div className="library-item-meta">No saved replays yet. Upload a .replay file to get started.</div>}
              </div>
            </div>

            {!session && (
              <div className="metrics-card empty-state">
                <div className="empty-state-icon"><i className="fa-regular fa-circle-play" /></div>
                <h3>No Replay Open</h3>
                <p>Open a replay from your library or upload a new one to unlock the replay studio.</p>
              </div>
            )}

            {session && !replayStudioReady && (
              <div className="metrics-card empty-state">
                <div className="empty-state-icon"><i className="fa-solid fa-spinner fa-spin" /></div>
                <h3>Replay Loading</h3>
                <p>The replay studio will unlock once metrics, mechanic grades, and the priority coaching explanations are ready.</p>
              </div>
            )}

            {session && replayStudioReady && (
              <section className="layout studio-layout">
                <ReplayVisualizer
                  timeline={session.timeline ?? []}
                  replayMeta={(session.replay_meta ?? {}) as {
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
                    setEventExplain(
                      explainCache[k] || {
                        title: `${englishEventName(ev.mechanicId)} @ ${fmtNumber(ev.time, 2)}s`,
                        body: ev.reason ? `Observed: ${ev.reason}` : "No explanation.",
                      }
                    );
                  }}
                  eventPopup={
                    eventExplain ? (
                      <div className="event-explain-popup">
                        <div className="event-explain-header">
                          <strong>{eventExplain.title}</strong>
                          <button
                            type="button"
                            className="event-explain-close"
                            onClick={() => setEventExplain(null)}
                          >✕</button>
                        </div>
                        <p className="event-explain-body">
                          {eventExplainLoading ? "Loading coaching advice…" : eventExplain.body}
                        </p>
                      </div>
                    ) : null
                  }
                  boostPads={session.boost_pads ?? []}
                  seekTime={seekTime}
                />
                <div className="metrics-card studio-sidebar">
                  {overlay.explain && !overlay.explain.complete && (
                    <div className="improvement-tips" style={{ marginTop: 0 }}>
                      <strong style={{ fontSize: 12 }}>Background Coaching</strong>
                      <p className="library-item-meta" style={{ marginTop: 4 }}>
                        {explanationProgressLabel(overlay.explain)}
                      </p>
                    </div>
                  )}
                  <div className="studio-sidebar-section">
                    <div className="controls" style={{ marginTop: 0, marginBottom: 12 }}>
                      <div className="pill">Player: {selectedPlayer || "unknown"}</div>
                      <button type="button" onClick={() => void analyzePlayer()} disabled={!selectedPlayer}>Analyze</button>
                    </div>
                  </div>

                  <div className="studio-sidebar-section">
                    <h3>Live Metrics</h3>
                    <div className="metric-grid">
                      {metricMeta.map((m) => (
                        <div className="metric-card" key={m.key}>
                          <div className="metric-head">
                            <h4>{m.label}</h4>
                          </div>
                          <p className="metric-value">{fmtNumber(Number(metricSnapshot?.[m.key] ?? 0), 2)}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="studio-sidebar-section">
                    <h3>Mechanic Grades</h3>
                    <div className="library-list mechanic-grades-list">
                      {groupedMechanics.map((group) => (
                        <div key={group.mechanicId} className="bubble-card mech-group">
                          <div className="bubble-toggle mech-group-btn active">
                            <span className="mech-label">{group.label}</span>
                            <span className="mech-stats">
                              <span className="mech-score">{Math.round(group.avg)}/100</span>
                              <span className="mech-count">{group.items.length} events</span>
                            </span>
                          </div>
                          <div className="bubble-body mech-events-wrap">
                            {group.items.map((ev, idx) => (
                              <div key={`${group.mechanicId}-${idx}`} className="library-item mech-event-item">
                                <div className="mech-event-info">
                                  <strong>{fmtNumber(ev.time ?? 0, 2)}s</strong>
                                  <div className="library-item-meta">
                                    <span className={`quality-badge quality-${qualityText(ev.quality_label).toLowerCase()}`}>{qualityText(ev.quality_label)}</span>
                                    <span>Score {Math.round(Number(ev.score ?? 0) * 100)}/100</span>
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
                                      if (explainCache[k]) {
                                        setEventExplain(explainCache[k]);
                                        return;
                                      }
                                      const res = await apiPost<{ ok: boolean; data?: { llm?: { text?: string; error?: string } } }>(
                                        `${REPLAY_PREFIX}/mechanics/explain`,
                                        { time_s: t, mechanic_id: ev.mechanic_id ?? "", include_llm: true },
                                        { suppressErrorWindow: true }
                                      );
                                      const payload = {
                                        title: `${englishEventName(ev.mechanic_id)} @ ${fmtNumber(t, 2)}s`,
                                        body: res?.data?.llm?.text || res?.data?.llm?.error || "No LLM explanation.",
                                      };
                                      setExplainCache((prev) => ({ ...prev, [k]: payload }));
                                      setEventExplain(payload);
                                    } catch (err) {
                                      setEventExplain({ title: "Event Coach", body: err instanceof Error ? err.message : String(err) });
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
                      ))}
                      {!groupedMechanics.length && <div className="library-item-meta">Analyze a replay to view mechanic grades.</div>}
                    </div>
                  </div>

                  <div className="studio-sidebar-section coach-panel">
                    <h3>Coaching Feedback</h3>
                    <div className="coach-content">
                      <strong>{eventExplain?.title ?? "Select an event"}</strong>
                      <p className="library-item-meta">
                        {eventExplainLoading ? "Loading coaching advice..." : eventExplain?.body ?? "Click Coach on an event to jump to that moment and read feedback."}
                      </p>
                    </div>
                  </div>
                </div>
              </section>
            )}
          </section>
        )}

        {activeTab === "improvement" && (
          <section className="panel-stack">
            <div className="metrics-card">
              <h2>Improvement</h2>
              <p className="library-item-meta">Descriptive trend analysis built from your replay history.</p>
            </div>
            {progressSeries.length > 0 && (
              <div className="improvement-summary">
                <div className="summary-stat">
                  <div className="summary-stat-label">Replays Analyzed</div>
                  <div className="summary-stat-value">{progressSeries.length}</div>
                </div>
                <div className="summary-stat">
                  <div className="summary-stat-label">Latest Score</div>
                  <div className="summary-stat-value">{latestScore}<span className="text-muted">/100</span></div>
                </div>
                <div className="summary-stat">
                  <div className="summary-stat-label">Trend</div>
                  <div className="summary-stat-value">
                    <i className={`fa-solid ${trendUp ? "fa-arrow-trend-up" : "fa-arrow-trend-down"}`}
                       style={{ color: trendUp ? "var(--success)" : "var(--danger)" }} />
                  </div>
                </div>
              </div>
            )}
            <div className="metrics-card">
              <h3>Overall Mechanics Score Over Time</h3>
              <div className="chart-container">
                <LineChart series={progressSeries} width={820} height={230} />
              </div>
              {!progressSeries.length && <div className="library-item-meta">No replay trend data yet.</div>}
            </div>
            <div className="improvement-layout">
              {Object.entries(perMechanicSeries).slice(0, 4).map(([mechanicId, series]) => (
                <div className="metrics-card" key={mechanicId}>
                  <h3>{englishEventName(mechanicId)}</h3>
                  <div className="chart-container">
                    <LineChart series={series} width={400} height={180} />
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {activeTab === "installer" && (
          <section className="panel-stack">
            <div className="metrics-card">
              <h2>Installer</h2>
              <p className="library-item-meta">Download the RLBot Stack Installer to set up everything you need on a new machine.</p>
            </div>
            <div className="metrics-card">
              <h3>RLBotStackInstaller.exe</h3>
              <p className="library-item-meta" style={{ marginBottom: 16 }}>
                A standalone Windows installer. No Python installation required — it downloads and configures RLBot GUI, RLBotPack, and the full Python environment.
              </p>
              <a
                href={`${REPLAY_PREFIX}/installer/download`}
                download="RLBotStackInstaller.exe"
                className="installer-download-link"
              >
                Download RLBotStackInstaller.exe
              </a>
            </div>
            <div className="metrics-card">
              <h3>What the installer sets up</h3>
              <div className="library-list" style={{ marginTop: 8 }}>
                <div className="library-item"><span>RLBot GUI — the launcher and match manager for Rocket League bots</span></div>
                <div className="library-item"><span>RLBotPack — a collection of community bots to train against</span></div>
                <div className="library-item"><span>Python virtual environment with all required project dependencies</span></div>
                <div className="library-item"><span>Optional extras: stable-baselines3 and pygame for reinforcement learning</span></div>
              </div>
            </div>
          </section>
        )}

        {activeTab === "training" && (
          <section className="panel-stack">
            <div className="metrics-card">
              <h2>Training</h2>
              <p className="library-item-meta">Prescriptive practice planning based on replay-backed weaknesses and evidence.</p>
            </div>
            <div className="metrics-card">
              <h3>RLBot Setup Installer</h3>
              <p className="library-item-meta" style={{ marginBottom: 16 }}>
                If this machine still needs RLBot GUI, RLBotPack, bot dependencies, or the training runtime, install the full stack first.
              </p>
              <a
                href={`${REPLAY_PREFIX}/installer/download`}
                download="RLBotStackInstaller.exe"
                className="installer-download-link"
              >
                Download RLBotStackInstaller.exe
              </a>
            </div>
            <div className={`metrics-card ${botTrainingReady ? "" : "empty-state"}`}>
              <div className="card-header">
                <h3>RLBot Preflight</h3>
                <span className={`status-badge ${botTrainingReady ? "status-badge--ready" : "status-badge--blocked"}`}>
                  <i className={`fa-solid ${botTrainingReady ? "fa-circle-check" : "fa-triangle-exclamation"}`} />
                  {botTrainingReady ? "Ready" : "Setup Required"}
                </span>
              </div>
              <p className="library-item-meta">
                {botTrainingReady
                  ? "Bot drills are ready to launch."
                  : "Bot drills are blocked until the local training launcher and RLBot prerequisites are ready."}
              </p>
              <div className="library-item-meta" style={{ lineHeight: 1.6, marginBottom: 8 }}>
                <div className="preflight-check">
                  <i className={`fa-solid ${dependencyReady ? "fa-circle-check" : "fa-circle-xmark"}`} style={{ color: dependencyReady ? "var(--success)" : "var(--danger)" }} />
                  <span>Dependencies installed</span>
                </div>
                <div className="preflight-check">
                  <i className={`fa-solid ${trainingLauncherRunning ? "fa-circle-check" : "fa-circle-xmark"}`} style={{ color: trainingLauncherRunning ? "var(--success)" : "var(--danger)" }} />
                  <span>Training launcher running</span>
                </div>
                <div>Last checked: {trainingPreflightLastChecked ? new Date(trainingPreflightLastChecked * 1000).toLocaleString() : "Not yet checked"}</div>
              </div>
              <div className="controls" style={{ marginTop: 0, marginBottom: 12 }}>
                <button
                  type="button"
                  onClick={() => void verifyDependencies().catch((err) => setError(err instanceof Error ? err.message : String(err)))}
                  disabled={trainingPreflightChecking || trainingVerificationRunning}
                >
                  {trainingVerificationRunning ? "Starting Companion..." : "Verify Dependencies"}
                </button>
                <button
                  type="button"
                  onClick={() => void loadTrainingPreflight({ force: true }).catch((err) => setError(err instanceof Error ? err.message : String(err)))}
                  disabled={trainingPreflightChecking || trainingVerificationRunning}
                >
                  {trainingPreflightChecking ? "Checking..." : "Re-run Checks"}
                </button>
                {trainingPreflightFresh && !trainingPreflightChecking && <div className="library-item-meta">Cached result is fresh.</div>}
              </div>
              {trainingVerificationMessage && (
                <div className="library-item-meta" style={{ marginBottom: 8, lineHeight: 1.6 }}>
                  {trainingVerificationMessage}
                </div>
              )}
              <div className="library-item-meta" style={{ lineHeight: 1.6, marginBottom: 8 }}>
                {!hostChecksAvailable ? (
                  <div>
                    Host RLBot and Rocket League installs cannot be verified from the Docker app until the local RocketCoach Companion starts on this machine.
                  </div>
                ) : trainingPreflight?.data?.rlbot_gui_detected ? (
                  <div>
                    RLBot GUI path: {rlbotGuiPath || "detected"}{rlbotGuiSource ? ` (${rlbotGuiSource})` : ""}
                  </div>
                ) : (
                  <div>
                    RLBot GUI path: not detected. Set <code>RLBOT_GUI_PATH</code> to your install folder if it is custom.
                  </div>
                )}
              </div>
              {!trainingLauncherRunning && (
                <div className="library-item-meta" style={{ marginBottom: 8 }}>
                  If the RocketCoach Companion is installed, use <strong>Verify Dependencies</strong> to start it automatically. If this is a new machine, install <code>RLBotStackInstaller.exe</code> first.
                </div>
              )}
              {trainingPreflightMessages.length ? (
                <div className="library-item-meta" style={{ lineHeight: 1.6 }}>
                  {trainingPreflightMessages.slice(0, 4).map((message, idx) => (
                    <div key={`${message}-${idx}`}>{message}</div>
                  ))}
                </div>
              ) : (
                <div className="library-item-meta">No preflight details were returned yet.</div>
              )}
              {!!trainingPreflightBotStatuses.length && (
                <div className="library-list" style={{ marginTop: 12 }}>
                  {trainingPreflightBotStatuses.map((status) => (
                    <div key={String(status.bot_profile_id || status.bot_name || "")} className="library-item">
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, width: "100%" }}>
                        <strong>{status.bot_name || status.bot_profile_id || "Bot"}</strong>
                        <span style={{ color: status.ready ? "#94f0b8" : "#ffb3b3" }}>{status.ready ? "Ready" : "Blocked"}</span>
                      </div>
                      {!!(status.messages ?? []).length && (
                        <div className="library-item-meta" style={{ marginTop: 4, lineHeight: 1.5 }}>
                          {(status.messages ?? []).slice(0, 2).map((message, idx) => (
                            <div key={`${status.bot_profile_id}-${idx}`}>{message}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="improvement-cards">
              {recommendations.map((rec) => {
                const focusId = String(rec.focus_id || "");
                const selectedTier = trainingSelections[focusId]?.tier || String(rec.difficulty_default?.tier || rec.difficulty_profiles?.[0]?.tier || "beginner");
                const selectedDrillMode = trainingSelections[focusId]?.drillMode || String(rec.drill_mode_options?.[0] || "");
                const launchFeedback = trainingLaunchFeedback[focusId];
                const selectedProfile = (rec.difficulty_profiles ?? []).find((profile) => profile.tier === selectedTier) || rec.difficulty_default || rec.difficulty_profiles?.[0] || {};
                const selectedBotStatus = trainingPreflightBotStatusMap[String(selectedProfile.bot_profile_id || "")];
                const selectedBotReady = !rec.bot_required || (selectedBotStatus ? Boolean(selectedBotStatus.ready) : true);
                const canLaunchTraining = !launchingFocus && trainingLauncherRunning && sharedDependencyReady && selectedBotReady;
                return (
                  <div key={focusId || rec.title} className="improvement-card">
                    <div className="improvement-card-header">
                      <div className={`improvement-rank improvement-rank--${Math.min(Number(rec.priority_rank || 1), 3)}`}>#{rec.priority_rank || 1}</div>
                      <div style={{ flex: 1 }}>
                        <strong style={{ fontSize: 15 }}>{rec.title || "Focus"}</strong>
                        <div className="library-item-meta">Priority score {fmtNumber(rec.priority_score, 2)} | Confidence {Math.round(Number(rec.confidence || 0) * 100)}%</div>
                      </div>
                    </div>

                    <div className="library-item-meta" style={{ marginBottom: 10 }}>
                      {(rec.evidence ?? []).slice(0, 3).map((e, idx) => (
                        <div key={`${focusId}-evidence-${idx}`}>{e}</div>
                      ))}
                    </div>

                    <label>
                      Difficulty
                      <select value={selectedTier} onChange={(e) => setTrainingTier(focusId, e.target.value)}>
                        {(rec.difficulty_profiles ?? []).map((profile) => (
                          <option key={profile.tier} value={profile.tier}>{profile.label || profile.tier}</option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Drill Mode
                      <select value={selectedDrillMode} onChange={(e) => setTrainingDrillMode(focusId, e.target.value)}>
                        {(rec.drill_mode_options ?? []).map((mode) => (
                          <option key={mode} value={mode}>{mode}</option>
                        ))}
                      </select>
                    </label>

                    <div className="improvement-tips">
                      <strong style={{ fontSize: 12 }}>Training Notes</strong>
                      <p className="library-item-meta" style={{ marginTop: 4 }}>
                        {(rec.difficulty_profiles ?? []).find((profile) => profile.tier === selectedTier)?.summary ||
                          rec.drill_mode_summaries?.[selectedDrillMode] ||
                          "Use replay-backed drills to repeat the mechanic under the right level of pressure."}
                      </p>
                    </div>

                    <button
                      type="button"
                      disabled={launchingFocus === focusId || (Boolean(rec.bot_required) && !canLaunchTraining)}
                      onClick={() => void launchTraining(rec)}
                      title={Boolean(rec.bot_required) && !canLaunchTraining ? "RLBot preflight requirements are not satisfied yet." : ""}
                    >
                      {launchingFocus === focusId ? "Launching..." : rec.bot_required ? "Train Against Bot" : "Start Drill"}
                    </button>
                    {Boolean(rec.bot_required) && (!trainingLauncherRunning || !sharedDependencyReady) && (
                      <div className="library-item-meta" style={{ marginTop: 8 }}>
                        {(trainingPreflightMessages[0] || "RLBot setup is incomplete. Use Verify Dependencies to start the RocketCoach Companion and scan this machine.")}
                      </div>
                    )}
                    {Boolean(rec.bot_required) && selectedBotStatus && !selectedBotStatus.ready && (
                      <div className="library-item-meta" style={{ marginTop: 8, color: "#ffb3b3", lineHeight: 1.6 }}>
                        <div>{selectedBotStatus.bot_name || "This bot"} is not launch-ready.</div>
                        {!!(selectedBotStatus.messages ?? []).length && <div>{selectedBotStatus.messages?.[0]}</div>}
                      </div>
                    )}
                    {launchFeedback && (
                      <div
                        className="library-item-meta"
                        style={{
                          marginTop: 8,
                          lineHeight: 1.6,
                          color: launchFeedback.phase === "error" ? "#ffb3b3" : undefined,
                        }}
                      >
                        <div>{launchFeedback.message}</div>
                        {launchFeedback.detail && <div>{launchFeedback.detail}</div>}
                      </div>
                    )}
                  </div>
                );
              })}
              {!recommendations.length && <div className="library-item-meta">Analyze replays to generate a training plan.</div>}
            </div>
          </section>
        )}
      </main>

      {overlay.active && (
        <div className="loading-overlay">
          <div className="loading-card">
            <h2>{overlay.title || "Loading"}</h2>
            <div className="loading-status">{overlay.message}</div>
            <div className="loading-progress-wrap">
              <div className="loading-progress-bar" style={{ width: `${Math.max(6, Math.min(100, Math.round((overlay.progress || 0) * 100)))}%` }} />
            </div>
            <ul className="loading-checklist">
              <li className={overlay.checklist.upload_received ? "ok" : "pending"}>Upload received</li>
              <li className={overlay.checklist.replay_parsed ? "ok" : "pending"}>Replay parsed</li>
              <li className={overlay.checklist.timeline_ready ? "ok" : "pending"}>Timeline ready</li>
              <li className={overlay.checklist.analysis_ready ? "ok" : "pending"}>Analysis ready</li>
              <li className={overlay.explain?.complete ? "ok" : "pending"}>LLM explanations ready</li>
            </ul>
            {overlay.explain && <div className="loading-status">{explanationProgressLabel(overlay.explain)}</div>}
            {overlay.error && <div className="alert" style={{ marginTop: 10, marginBottom: 0 }}>{overlay.error}</div>}
            <div className="loading-actions">
              {overlay.error && retryReplayActionRef.current && (
                <button type="button" onClick={() => void retryReplayActionRef.current?.()}>Retry</button>
              )}
              {overlay.error && (
                <button type="button" className="ghost" onClick={() => setOverlay((prev) => ({ ...prev, active: false }))}>Close</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
