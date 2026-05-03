import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiGet, apiPost } from "../api";
import { useAuth } from "../app/AuthContext";
import ReplayVisualizer from "../components/replay/ReplayVisualizer";
import LineChart from "../components/LineChart";

const REPLAY_PREFIX = "/api/replay";
const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
const REPLAY_PICKER_ID = "rc-replay";
const REPLAY_PICKER_ID_EPIC = "rc-replay-epic";
const REPLAY_PICKER_ID_STANDARD = "rc-replay-std";
const REPLAY_LIBRARY_PAGE_SIZE = 6;

type ReplayPickerFileHandle = {
  getFile(): Promise<File>;
};

type ReplayPickerWindow = Window & typeof globalThis & {
  showOpenFilePicker?: (options: {
    id?: string;
    startIn?: "documents";
    multiple?: boolean;
    excludeAcceptAllOption?: boolean;
    types?: { description?: string; accept: Record<string, string[]> }[];
  }) => Promise<ReplayPickerFileHandle[]>;
};

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
};

type LoadingOverlayState = {
  active: boolean;
  title: string;
  message: string;
  progress: number;
  phase: string;
  checklist: Record<string, boolean>;
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
    gamemode?: string;
    player_count?: number;
  };
};

type LibraryResponse = {
  ok: boolean;
  data?: {
    sessions?: LibrarySession[];
    cleanup?: { duplicate_names_removed?: number };
  };
};

type LibraryRecomputeResponse = {
  ok: boolean;
  data?: {
    total_sessions?: number;
    updated_sessions?: number;
    failed_sessions?: number;
    skipped_sessions?: number;
    errors?: string[];
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
  session_id?: string;
  replay_name?: string;
  replay_date_iso?: string;
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
  quality_score?: number;
  quality_score_0_100?: number;
  reason?: string;
  title?: string;          // backend key (preferred)
  template_title?: string; // legacy alias
  template_body?: string;
  event_type?: string;
  mechanic_tags?: string[];
  mechanic_tag_labels?: string[];
  issue_tags?: string[];
  improvement_tags?: string[];
  mechanic_description?: string;
  why_it_matters?: string;
  common_mistake?: string;
  training_cue?: string;
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

type BridgeSessionStartResponse = {
  ok: boolean;
  data?: {
    token?: string;
    action?: string;
    callback_url?: string;
  };
};

type BridgeSessionStatusResponse = {
  ok: boolean;
  data?: {
    token?: string;
    status?: string;
    action?: string;
    result?: {
      preflight?: TrainingPreflightResponse["data"];
      launch?: TrainingLaunchResponse["data"];
    };
    error?: string;
  };
};

function unavailableTrainingPreflight(): TrainingPreflightResponse {
  return {
    ok: true,
    data: {
      host_checks_available: false,
      launcher_kind: "training_bridge",
      launcher_running: false,
      dependency_ready: false,
      shared_dependency_ready: false,
      python_ready: false,
      rlbot_import_ok: false,
      rlbot_gui_detected: false,
      rlbot_gui_path: "",
      rlbot_gui_detection_source: "launcher_unavailable",
      rocket_league_detected: false,
      last_checked_at: 0,
      scenario_count: 0,
      bot_statuses: [],
      ready_to_launch: false,
      messages: [
        "The local RocketCoach Companion is not running on this machine yet.",
        "Use Verify Dependencies to start it, then rerun the checks.",
      ],
    },
  };
}

const metricMeta = [
  { key: "speed", label: "Speed" },
  { key: "hesitation_percent", label: "Hesitation %" },
  { key: "boost_waste_percent", label: "Boost Waste %" },
  { key: "pressure_percent", label: "Pressure %" },
  { key: "whiff_rate_per_min", label: "Whiff Rate / min" },
  { key: "recovery_time_avg_s", label: "Recovery Avg (s)" },
];

type MechanicMeta = {
  label: string;
  description: string;
  why: string;
  mistake: string;
  cue: string;
};

const mechanicMeta: Record<string, MechanicMeta> = {
  kickoff: {
    label: "Kickoff",
    description: "Kickoff measures how well you win or neutralize the first touch and protect your team from an instant counter.",
    why: "Kickoffs decide early possession, boost control, and whether your team starts on offense or under pressure.",
    mistake: "Arriving late, hitting off-center, or losing the recovery after the first touch.",
    cue: "Arrive square, hit through the middle, and land ready for the next bounce.",
  },
  shadow_defense: {
    label: "Shadow Defense",
    description: "Shadow Defense measures how well you stay goal-side, control space, and delay the attacker without committing too early.",
    why: "Good shadow defense buys time and forces the attacker into a weaker touch.",
    mistake: "Backing off too far or challenging before you can actually win the ball.",
    cue: "Match the attacker earlier and hold a tighter line so you can pressure safely.",
  },
  challenge: {
    label: "Challenge",
    description: "Challenge tracks how safely and effectively you contest the ball when another player can meet it.",
    why: "Good challenges stop counters and turn contested balls into touches your team can read.",
    mistake: "Turning in late, challenging from the side, or losing the 50 into danger.",
    cue: "Turn in earlier and hit with the nose through the center of the contest.",
  },
  fifty_fifty_control: {
    label: "50/50 Control",
    description: "50/50 Control measures how well you absorb and direct contested contact into a playable outcome.",
    why: "Winning the exit of a 50 converts chaos into possession instead of another emergency touch.",
    mistake: "Flipping through the ball too hard or landing with no plan for the next bounce.",
    cue: "Stay grounded when possible, center your car, and deaden the touch into followable space.",
  },
  aerial_offense: {
    label: "Aerial Offense",
    description: "Aerial Offense measures how much threat your airborne touches create once you leave the ground in attack.",
    why: "Strong attacking aerials create shots, passes, and second touches before the defense can reset.",
    mistake: "Meeting the ball late or getting contact without enough pace or direction.",
    cue: "Read the takeoff earlier, attack forward, and recover into the next play.",
  },
  aerial_defense: {
    label: "Aerial Defense",
    description: "Aerial Defense tracks how well your airborne touches remove danger from your half.",
    why: "A good defensive aerial stops the shot and breaks pressure instead of recycling it.",
    mistake: "Saving the ball but leaving it centered or too playable for the opponent.",
    cue: "Beat the ball to the dangerous lane and clear wider when you need safety first.",
  },
  flicking: {
    label: "Flicks",
    description: "Flicks measure how well you convert dribble control into lift, pace, and a threatening release.",
    why: "A clean flick punishes defenders who wait too long and turns control into a real scoring chance.",
    mistake: "Flicking late or from an unstable dribble with too little upward pop.",
    cue: "Balance the dribble first, then pop the ball earlier and more cleanly.",
  },
  carrying_dribbling: {
    label: "Carries / Dribbles",
    description: "Carries and Dribbles measure how well you hold close ball control under pressure and turn it into a productive next action.",
    why: "Stable dribbles create options before the defender gets to choose the play for you.",
    mistake: "Letting the ball drift too far or waiting too long to turn the dribble into a threat.",
    cue: "Keep the ball close to your hood and choose the next move before pressure closes space.",
  },
  flip_reset: {
    label: "Flip Reset",
    description: "Flip Reset tracks how reliably you recollect your flip mid-air by touching all four wheels to the ball.",
    why: "A flip reset gives you an extra aerial dodge, enabling shots that defenders cannot predict.",
    mistake: "Only grazing the ball with one side of the car, wasting the aerial without gaining the reset.",
    cue: "Flatten your car underneath the ball and drive up into it so all wheels make contact.",
  },
  ceiling_shot: {
    label: "Ceiling Shot",
    description: "Ceiling Shot measures how well you drive off the ceiling and convert the diagonal drop into an on-target attempt.",
    why: "Ceiling shots arrive from unexpected angles and timings that force goalkeepers into difficult reads.",
    mistake: "Losing the ball off the ceiling or jumping too early and thinning the contact.",
    cue: "Ride the ceiling longer before jumping, then boost into the ball from above.",
  },
  double_tap: {
    label: "Double Tap",
    description: "Double Tap tracks how cleanly you hit a backboard rebound back into goal before the keeper can adjust.",
    why: "A double tap is one of the hardest shots to save — the ball reverses direction before anyone can react.",
    mistake: "Making the first touch too soft or too hard so the rebound bounces unpredictably.",
    cue: "Hit the backboard at mid-height with pace, then position quickly for the rebound angle.",
  },
};

function fmtNumber(v: number | undefined, digits = 2) {
  if (v == null || Number.isNaN(v)) return "--";
  return Number(v).toFixed(digits);
}

function fmtClockLabel(seconds: number, isOvertime = false): string {
  const total = Math.floor(Math.max(0, seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${isOvertime ? "+" : ""}${m}:${s.toString().padStart(2, "0")}`;
}

function fmtGameTime(
  secs: number | undefined,
  timeline?: { t: number; seconds_remaining?: number; is_overtime?: boolean }[],
  otStartS?: number | null
): string {
  if (secs == null || Number.isNaN(secs)) return "0:00";
  const arr = timeline ?? [];
  if (!arr.length) return fmtClockLabel(Number(secs));
  const aligned = alignEventTimeToTimeline(arr, Number(secs));
  const frame = arr.find((item) => Math.abs(Number(item?.t ?? 0) - aligned) < 1e-4) ?? null;
  const isOvertime = Boolean(frame?.is_overtime) || (otStartS != null && aligned >= Number(otStartS));
  if (isOvertime) {
    return fmtClockLabel(Math.max(0, aligned - Number(otStartS ?? aligned)), true);
  }
  return fmtClockLabel(Number(frame?.seconds_remaining ?? 0));
}

function fmtDuration(seconds?: number) {
  if (!seconds || Number.isNaN(seconds)) return "0:00";
  const s = Math.round(seconds);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function normalizeScore100(value?: number) {
  let score = Number(value ?? 0);
  if (!Number.isFinite(score)) return 0;
  score = Math.abs(score);
  if (score <= 1) return score * 100;
  while (score > 100) {
    score /= score >= 1000 ? 100 : 10;
  }
  return score;
}

function normalizeConfidencePercent(value?: number) {
  let confidence = Number(value ?? 0);
  if (!Number.isFinite(confidence)) return 0;
  confidence = Math.abs(confidence);
  if (confidence <= 1) return confidence * 100;
  while (confidence > 100) {
    confidence /= confidence >= 1000 ? 100 : 10;
  }
  return confidence;
}

function mechanicEventScore(ev?: MechanicEvent) {
  return normalizeScore100(Number(ev?.score ?? ev?.quality_score_0_100 ?? ev?.quality_score ?? 0));
}

function mechanicMetaFor(mid?: string, ev?: MechanicEvent): MechanicMeta {
  const key = String(mid || ev?.mechanic_id || "");
  const fallbackLabel = englishEventName(key);
  const base = mechanicMeta[key];
  return {
    label: fallbackLabel,
    description: String(ev?.mechanic_description || base?.description || `${fallbackLabel} tracks how cleanly you handled this type of touch in this moment.`),
    why: String(ev?.why_it_matters || base?.why || `Improving your ${fallbackLabel.toLowerCase()} makes the next play easier to control and sets up better opportunities.`),
    mistake: String(ev?.common_mistake || base?.mistake || "The touch did not create a controllable next outcome."),
    cue: String(ev?.training_cue || base?.cue || "Slow the play down mentally, improve your approach angle, and recover into the next touch."),
  };
}

function explainMechanicGroup(group: { mechanicId: string; label: string; items: MechanicEvent[]; avg: number }) {
  const meta = mechanicMetaFor(group.mechanicId, group.items[0]);
  const badCount = group.items.filter((ev) => qualityText(ev.quality_label) === "Bad").length;
  const goodCount = group.items.filter((ev) => qualityText(ev.quality_label) === "Good").length;
  const bodyParts = [
    `${meta.label} is averaging ${fmtNumber(group.avg, 2)}/100 across ${group.items.length} tracked event${group.items.length === 1 ? "" : "s"}.`,
    meta.description,
    `Why it matters: ${meta.why}`,
    `Most common miss: ${meta.mistake}`,
    `Best next cue: ${meta.cue}`,
    `Replay trend: ${goodCount} strong event${goodCount === 1 ? "" : "s"} and ${badCount} event${badCount === 1 ? "" : "s"} that clearly need work.`,
  ];
  return {
    title: `${meta.label} Score Guide`,
    body: bodyParts.filter(Boolean).join(" "),
  };
}

function mechanicEventBody(ev?: MechanicEvent) {
  if (!ev) return "No event details were recorded for this moment.";
  const base = String(ev.template_body || "").trim();
  if (base) return base;
  const meta = mechanicMetaFor(ev.mechanic_id, ev);
  const fallbackReason = String(ev.reason || "").trim();
  if (fallbackReason) {
    return `${fallbackReason.charAt(0).toUpperCase()}${fallbackReason.slice(1)}. ${meta.cue}`;
  }
  return `${meta.mistake} ${meta.cue}`;
}

function mechanicEventExplainTitle(ev?: MechanicEvent) {
  if (!ev) return "Select an event";
  return englishEventName(ev.mechanic_id);
}

function buildMechanicEventExplain(ev?: MechanicEvent) {
  return {
    title: mechanicEventExplainTitle(ev),
    body: mechanicEventBody(ev),
    grade: qualityText(ev?.quality_label),
    tags: mechanicEventTags(ev),
  };
}

function mechanicEventKey(ev?: MechanicEvent, fallback = "") {
  const mid = String(ev?.mechanic_id || "event");
  const t = Number(ev?.time ?? 0);
  const rounded = Number.isFinite(t) ? t.toFixed(2) : "0.00";
  return `${mid}:${rounded}:${fallback}`;
}

function alignEventTimeToTimeline(timeline: { t: number }[] | undefined, targetTime: number) {
  const arr = timeline ?? [];
  if (!arr.length) return Number(targetTime || 0);
  const target = Number(targetTime || 0);
  let lo = 0;
  let hi = arr.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const midTime = Number(arr[mid]?.t ?? 0);
    if (midTime < target) lo = mid + 1;
    else if (midTime > target) hi = mid - 1;
    else return midTime;
  }
  const lowerIdx = Math.max(0, Math.min(arr.length - 1, hi));
  const upperIdx = Math.max(0, Math.min(arr.length - 1, lo));
  const lowerTime = Number(arr[lowerIdx]?.t ?? target);
  const upperTime = Number(arr[upperIdx]?.t ?? target);
  return Math.abs(upperTime - target) < Math.abs(target - lowerTime) ? upperTime : lowerTime;
}

function replayDisplayName(s: LibrarySession) {
  const summary = s?.summary || {};
  const rawDate = String(summary?.replay_date_iso || s?.created_at || "").trim();
  if (rawDate) {
    const parsed = new Date(rawDate);
    if (!Number.isNaN(parsed.getTime())) {
      const month = parsed.getMonth() + 1;
      const day = parsed.getDate();
      const year = String(parsed.getFullYear()).slice(-2);
      return `${month}-${day}-${year}.replay`;
    }
  }
  return "Replay.replay";
}

function replaySessionDisplayName(session?: ReplaySession | null) {
  const rawDate = String((session?.replay_meta?.replay_date_iso as string) || "").trim();
  if (rawDate) {
    const parsed = new Date(rawDate);
    if (!Number.isNaN(parsed.getTime())) {
      const month = parsed.getMonth() + 1;
      const day = parsed.getDate();
      const year = String(parsed.getFullYear()).slice(-2);
      return `${month}-${day}-${year}.replay`;
    }
  }
  const rawName = String(session?.replay_name || "").trim();
  if (rawName) {
    return /\.replay$/i.test(rawName) ? rawName : `${rawName}.replay`;
  }
  return "Replay.replay";
}

function pointReplayDisplayName(point?: ProgressPoint): string {
  const rawDate = String(point?.replay_date_iso || "").trim();
  if (rawDate) {
    const d = new Date(rawDate);
    if (!Number.isNaN(d.getTime())) {
      const m = d.getMonth() + 1;
      const day = d.getDate();
      const yr = String(d.getFullYear()).slice(-2);
      return `${m}-${day}-${yr}.replay`;
    }
  }
  const rawName = String(point?.replay_name || "").trim();
  if (rawName) {
    return /\.replay$/i.test(rawName) ? rawName : `${rawName}.replay`;
  }
  const xTimeUnix = Number(point?.x_time_unix || 0);
  if (xTimeUnix > 0) {
    const d = new Date(xTimeUnix * 1000);
    const m = d.getMonth() + 1;
    const day = d.getDate();
    const yr = String(d.getFullYear()).slice(-2);
    return `${m}-${day}-${yr}.replay`;
  }
  return "Replay.replay";
}

function mechanicEventTags(ev?: MechanicEvent): string[] {
  const labels = (ev?.mechanic_tag_labels || []).map((tag) => String(tag || "").trim()).filter(Boolean);
  if (labels.length) return labels.slice(0, 3);
  return (ev?.mechanic_tags || [])
    .map((tag) => String(tag || "").trim())
    .filter(Boolean)
    .map((tag) => tag.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()))
    .slice(0, 3);
}

function qualityClassName(value?: string) {
  return qualityText(value).toLowerCase();
}

function englishEventName(mid?: string) {
  const map: Record<string, string> = {
    kickoff: "Kickoff",
    shadow_defense: "Shadow Defense",
    challenge: "Challenge",
    flicking: "Flicks",
    carrying_dribbling: "Carry + Dribble",
    flicking_carry_offense: "Flicks",
    aerial_offense: "Aerial Offense",
    aerial_defense: "Aerial Defense",
    fifty_fifty_control: "50/50 Control",
  };
  const key = String(mid || "").trim();
  if (map[key]) return map[key];
  if (key) return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return "Event";
}

function normalizePlayerKey(value?: string) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "");
}

function resolvePlayerTeamValue(
  playerTeams: Record<string, number>,
  candidates: string[]
): number | null {
  for (const candidate of candidates) {
    const raw = String(candidate || "").trim();
    if (!raw) continue;
    const direct = Number(playerTeams?.[raw]);
    if (Number.isFinite(direct)) return direct;
  }
  const normalizedEntries = Object.entries(playerTeams || {}).map(([name, team]) => [normalizePlayerKey(name), Number(team)] as const);
  for (const candidate of candidates) {
    const normalized = normalizePlayerKey(candidate);
    if (!normalized) continue;
    const match = normalizedEntries.find(([name]) => name === normalized);
    if (match && Number.isFinite(match[1])) return match[1];
  }
  return null;
}

function qualityText(value?: string) {
  const q = String(value || "").toLowerCase();
  if (q.startsWith("good")) return "Good";
  if (q.startsWith("bad")) return "Bad";
  return "Neutral";
}

function replayCardLines(
  s: LibrarySession,
  profile?: { username?: string; aliases?: string[] } | null
) {
  const summary = s?.summary || {};
  const player = String(s?.tracked_player_name || summary?.analysis_player || "Unknown");
  const arena = String(s?.map_name || "Arena");
  const grade = normalizeScore100(Number(summary?.overall_mechanics_score || 0));
  const label = replayDisplayName(s);

  let result = "Result";
  let score = "--";
  const teamScores = summary?.team_scores_final || {};
  const blue = Number(teamScores?.blue);
  const orange = Number(teamScores?.orange);
  const playerTeams = (s?.player_teams || (summary as any)?.player_teams || {}) as Record<string, number>;
  const teamCandidates = [
    player,
    String(summary?.analysis_player || ""),
    String(s?.tracked_player_name || ""),
    String(profile?.username || ""),
    ...((profile?.aliases || []) as string[]),
  ];
  const resolvedTeam = resolvePlayerTeamValue(playerTeams, teamCandidates);
  const t = resolvedTeam == null ? Number.NaN : Number(resolvedTeam);
  if (Number.isFinite(blue) && Number.isFinite(orange)) {
    score = t === 1 ? `${orange}-${blue}` : `${blue}-${orange}`;
    if (t === 0) result = blue > orange ? "Win" : blue < orange ? "Loss" : "Draw";
    else if (t === 1) result = orange > blue ? "Win" : orange < blue ? "Loss" : "Draw";
  }
  const outcomeLabel = result !== "Result"
    ? (score !== "--" ? `${result} (${score})` : result)
    : score;

  return {
    line1: label,
    line2: `${outcomeLabel} | ${player} | ${arena} | Grade ${fmtNumber(grade, 2)} | ${fmtDuration(Number(s.duration_s || 0))}`,
    result,
  };
}

function sessionGamemode(s: LibrarySession) {
  const summary = (s?.summary || {}) as Record<string, unknown>;
  const explicit = String(summary.gamemode || "").trim().toLowerCase();
  if (explicit === "1v1" || explicit === "2v2" || explicit === "3v3") return explicit;
  const count = Number(summary.player_count || 0);
  if (count === 2) return "1v1";
  if (count === 4) return "2v2";
  if (count === 6) return "3v3";
  const teams = (s?.player_teams || (summary.player_teams as Record<string, number> | undefined) || {}) as Record<string, number>;
  const playerCount = Object.keys(teams).length;
  if (playerCount === 2) return "1v1";
  if (playerCount === 4) return "2v2";
  if (playerCount === 6) return "3v3";
  return "unknown";
}

type TrendSeriesPoint = { t: number; v: number; sessionId?: string; replayName?: string };
type TrendSummary = {
  label: string;
  className: "up" | "down" | "flat" | "new";
  title: string;
  delta: number;
  relativePct: number | null;
};

function trendSummary(series: TrendSeriesPoint[]): TrendSummary {
  const usable = [...series]
    .filter((p) => Number.isFinite(Number(p.v)))
    .sort((a, b) => Number(a.t || 0) - Number(b.t || 0));
  if (usable.length < 2) {
    return {
      label: "New trend",
      className: "new",
      title: "Analyze more replays to calculate a trend.",
      delta: 0,
      relativePct: null,
    };
  }
  const first = Number(usable[0].v || 0);
  const latest = Number(usable[usable.length - 1].v || 0);
  const delta = latest - first;
  const className = Math.abs(delta) < 0.05 ? "flat" : delta > 0 ? "up" : "down";
  if (Math.abs(first) < 0.01) {
    return {
      label: `${delta >= 0 ? "+" : ""}${fmtNumber(delta, 1)} pts`,
      className,
      title: `Changed from ${fmtNumber(first, 1)} to ${fmtNumber(latest, 1)}.`,
      delta,
      relativePct: null,
    };
  }
  const relativePct = (delta / first) * 100;
  const pctLabel = `${relativePct >= 0 ? "+" : ""}${fmtNumber(relativePct, 1)}%`;
  return {
    label: pctLabel,
    className,
    title: `Changed from ${fmtNumber(first, 1)} to ${fmtNumber(latest, 1)} (${delta >= 0 ? "+" : ""}${fmtNumber(delta, 1)} points).`,
    delta,
    relativePct,
  };
}

function hasRealReplayData(s?: LibrarySession | null) {
  if (!s) return false;
  const summary = s.summary || {};
  const replayName = String(s.replay_name || "").trim();
  const replayDate = String(summary.replay_date_iso || "").trim();
  const replaySha = String((summary as any).replay_sha1 || "").trim();
  const player = String(s.tracked_player_name || summary.analysis_player || "").trim();
  const mapName = String(s.map_name || "").trim();
  const duration = Number(s.duration_s || 0);
  const eventCount = Number((summary as any).mechanic_event_count || 0);
  const grade = Number(summary.overall_mechanics_score || 0);
  const id = String(s.session_id || s.id || "").trim();
  const hasIdentity = Boolean(replayName || replayDate || replaySha || id);
  const hasReplayShape =
    duration > 0 ||
    eventCount > 0 ||
    grade > 0 ||
    Boolean(replayDate || replaySha) ||
    (Boolean(replayName) && replayName.toLowerCase() !== "replay.replay") ||
    (Boolean(player) && player.toLowerCase() !== "unknown") ||
    (Boolean(mapName) && mapName.toLowerCase() !== "arena");
  return hasIdentity && hasReplayShape;
}

function platformUsesEpicReplayFolder(platform?: string) {
  const normalized = String(platform || "").trim().toLowerCase();
  return normalized === "epic" || normalized === "epic games";
}

function replayFolderPathLabel(platform?: string) {
  if (platformUsesEpicReplayFolder(platform)) {
    return String.raw`Replay folder: Documents\My Games\Rocket League\TAGame\DemosEpic (falls back to Documents\My Games\Rocket League\TAGame\Demos if DemosEpic is missing)`;
  }
  return String.raw`Replay folder: Documents\My Games\Rocket League\TAGame\Demos`;
}

export default function ReplayDashboardPage() {
  const { profile, logout } = useAuth();
  const location = useLocation();
  const retryReplayActionRef = useRef<(() => Promise<void>) | null>(null);
  const replayFileInputRef = useRef<HTMLInputElement | null>(null);
  const [replayFolderStatus, setReplayFolderStatus] = useState<string>("");
  const [showReplayPathModal, setShowReplayPathModal] = useState(false);
  const [replayPathModalPendingOpen, setReplayPathModalPendingOpen] = useState(false);

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
  const [reviewRequest, setReviewRequest] = useState<{ id: number; time: number; event: MechanicEvent } | null>(null);
  const [eventExplain, setEventExplain] = useState<{ title: string; body: string; grade: string; tags: string[] } | null>(null);
  const [scoreExplain, setScoreExplain] = useState<{ title: string; body: string } | null>(null);
  const [librarySearch, setLibrarySearch] = useState("");
  const [libraryResultFilter, setLibraryResultFilter] = useState("all");
  const [libraryGamemodeFilter, setLibraryGamemodeFilter] = useState("all");
  const [librarySort, setLibrarySort] = useState("newest");
  const [libraryPage, setLibraryPage] = useState(0);
  const [showLibraryDrawer, setShowLibraryDrawer] = useState(false);
  const [mechanicView, setMechanicView] = useState<"grouped" | "timeline">("timeline");
  const [focusedMechanicIds, setFocusedMechanicIds] = useState<Set<string>>(new Set());
  const [activeMechanicEventKey, setActiveMechanicEventKey] = useState("");
  const [trainingSelections, setTrainingSelections] = useState<Record<string, { tier: string; drillMode: string }>>({});
  const [launchingFocus, setLaunchingFocus] = useState("");
  const lastProtocolLaunchRef = useRef<{ url: string; at: number }>({ url: "", at: 0 });
  const [trainingLaunchFeedback, setTrainingLaunchFeedback] = useState<Record<string, TrainingLaunchFeedback>>({});
  const [error, setError] = useState("");
  const [feedbackKey, setFeedbackKey] = useState<string | null>(null);
  const [feedbackDraft, setFeedbackDraft] = useState("");
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const [feedbackSavedKeys, setFeedbackSavedKeys] = useState<Set<string>>(new Set());
  const [mechInfoOpen, setMechInfoOpen] = useState<string | null>(null);
  const tutorialStorageKey = useMemo(
    () => `rocketcoach-tutorial-dismissed:${String((profile as { id?: string | number } | null)?.id || profile?.username || "guest")}`,
    [profile]
  );
  const replayPathHelpStorageKey = useMemo(
    () => `rocketcoach-replay-path-help-dismissed:${String((profile as { id?: string | number } | null)?.id || profile?.username || "guest")}`,
    [profile]
  );
  const [showTutorial, setShowTutorial] = useState(true);
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
    error: "",
  });
  const trainingPreflightFresh = Boolean(trainingPreflight && (Date.now() - trainingPreflightFetchedAt) < 60_000);
  const trainingPreflightLastChecked = Number(trainingPreflight?.data?.last_checked_at || 0);
  const trainingPreflightBotStatuses = trainingPreflight?.data?.bot_statuses ?? [];
  const trainingPreflightBotStatusMap = Object.fromEntries(
    trainingPreflightBotStatuses.map((status) => [String(status.bot_profile_id || ""), status])
  );
  const replayFolderGuide = useMemo(
    () =>
      platformUsesEpicReplayFolder(String(profile?.platform || ""))
        ? "Documents > My Games > Rocket League > TAGame > DemosEpic"
        : "Documents > My Games > Rocket League > TAGame > Demos",
    [profile?.platform]
  );

  const loadStatus = useCallback(async () => {
    const resp = await apiGet<ReplayStatus>(`${REPLAY_PREFIX}/replay/status`, { suppressErrorWindow: true });
    setStatus(resp);
    return resp;
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
      const resp = await apiGet<TrainingPreflightResponse>(`${REPLAY_PREFIX}/training/preflight`, { suppressErrorWindow: true })
        .catch(() => unavailableTrainingPreflight());
      setTrainingPreflight(resp);
      setTrainingPreflightFetchedAt(Date.now());
      return resp;
    } finally {
      setTrainingPreflightChecking(false);
    }
  }, [trainingPreflight, trainingPreflightFetchedAt]);

  const wakeTrainingCompanion = useCallback(async (launchUrl = "rocketcoach://verify-deps") => {
    const now = Date.now();
    const lastLaunch = lastProtocolLaunchRef.current;
    if (lastLaunch.url === launchUrl && (now - lastLaunch.at) < 4000) {
      return;
    }
    lastProtocolLaunchRef.current = { url: launchUrl, at: now };
    const anchor = document.createElement("a");
    anchor.href = launchUrl;
    anchor.style.display = "none";
    anchor.setAttribute("aria-hidden", "true");
    document.body.appendChild(anchor);
    anchor.click();
    await sleep(250);
    if (document.body.contains(anchor)) {
      document.body.removeChild(anchor);
    }
  }, []);

  const createBridgeSession = useCallback(async (action: "verify" | "launch", payload?: Record<string, unknown>) => {
    return apiPost<BridgeSessionStartResponse>(
      `${REPLAY_PREFIX}/training/bridge_session/start`,
      { action, payload: payload || {} },
      { suppressErrorWindow: true }
    );
  }, []);

  const pollBridgeSession = useCallback(async (token: string) => {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await sleep(1000);
      const status = await apiGet<BridgeSessionStatusResponse>(
        `${REPLAY_PREFIX}/training/bridge_session/status?token=${encodeURIComponent(token)}`,
        { suppressErrorWindow: true }
      );
      const state = String(status?.data?.status || "");
      if (state === "completed" || state === "error") {
        return status;
      }
    }
    throw new Error("RocketCoach Companion did not report back in time. Check the local RocketCoach callback log and try again.");
  }, []);

  const verifyDependencies = useCallback(async () => {
    setError("");
    setTrainingVerificationRunning(true);
    try {
      setTrainingVerificationMessage("Starting the local RocketCoach Companion...");
      const session = await createBridgeSession("verify");
      const token = String(session?.data?.token || "");
      const callbackUrl = String(session?.data?.callback_url || "");
      if (!token || !callbackUrl) {
        throw new Error("RocketCoach could not prepare a verification session.");
      }
      const protocolUrl = `rocketcoach://verify-deps?action=verify-deps&callback=${encodeURIComponent(callbackUrl)}`;
      await wakeTrainingCompanion(protocolUrl);
      setTrainingVerificationMessage("Waiting for RocketCoach Companion to verify this machine...");
      const completed = await pollBridgeSession(token);
      if (String(completed?.data?.status || "") === "error") {
        throw new Error(String(completed?.data?.error || "RocketCoach Companion verification failed."));
      }
      const preflight = completed?.data?.result?.preflight;
      const wrapped: TrainingPreflightResponse = { ok: true, data: preflight };
      setTrainingPreflight(wrapped);
      setTrainingPreflightFetchedAt(Date.now());
      if (preflight?.dependency_ready) {
        setTrainingVerificationMessage("Dependencies verified. Bot drills are ready to launch.");
      } else {
        setTrainingVerificationMessage("Dependency scan finished. Review the missing items below.");
      }
      return wrapped;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setTrainingVerificationMessage(message);
      throw err;
    } finally {
      setTrainingVerificationRunning(false);
    }
  }, [createBridgeSession, pollBridgeSession, wakeTrainingCompanion]);

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
    const preferred = Boolean(data?.analysis_player_valid) && players.includes(String(data?.analysis_player || ""))
      ? String(data?.analysis_player || "")
      : "";
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
    try {
      const dismissed = window.localStorage.getItem(tutorialStorageKey);
      setShowTutorial(dismissed !== "1");
    } catch {
      setShowTutorial(true);
    }
  }, [tutorialStorageKey]);

  // Close mechanic info popup when clicking outside any .mechanic-ring-item
  useEffect(() => {
    if (!mechInfoOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Element | null;
      if (!target?.closest(".mechanic-ring-item")) {
        setMechInfoOpen(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [mechInfoOpen]);

  const dismissTutorial = useCallback(() => {
    setShowTutorial(false);
    try {
      window.localStorage.setItem(tutorialStorageKey, "1");
    } catch {
      // Ignore storage failures.
    }
  }, [tutorialStorageKey]);

  const reopenTutorial = useCallback(() => {
    setShowTutorial(true);
    try {
      window.localStorage.removeItem(tutorialStorageKey);
    } catch {
      // Ignore storage failures.
    }
    // Don't switch tabs — modal content adapts to whichever tab is active.
  }, [tutorialStorageKey]);

  const startOverlay = useCallback((title: string, message: string) => {
    setOverlay({
      active: true,
      title,
      message,
      progress: 0.05,
      phase: "starting",
      checklist: {},
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

  const hydrateReplayStudio = useCallback(async () => {
    setReplayStudioReady(false);
    setMetrics(null);
    setMechanics(null);
    setEventExplain(null);
    setScoreExplain(null);
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
    setReplayStudioReady(true);
  }, [loadMechanics, loadMetrics, loadReplaySession]);

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
        setOverlay((prev) => ({ ...prev, active: false, error: "" }));
        setActiveTab("replay");
        void refreshSummaryViews().catch((refreshErr) => {
          setError(refreshErr instanceof Error ? refreshErr.message : String(refreshErr));
        });
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

  const openNativeReplayPicker = useCallback(async () => {
    const pickerWindow = window as ReplayPickerWindow;
    const pickerId = platformUsesEpicReplayFolder(String(profile?.platform || ""))
      ? REPLAY_PICKER_ID_EPIC
      : REPLAY_PICKER_ID_STANDARD;
    if (typeof pickerWindow.showOpenFilePicker === "function") {
      try {
        const [handle] = await pickerWindow.showOpenFilePicker({
          id: pickerId || REPLAY_PICKER_ID,
          startIn: "documents",
          multiple: false,
          excludeAcceptAllOption: true,
          types: [
            {
              description: "Rocket League Replay",
              accept: {
                "application/octet-stream": [".replay"],
              },
            },
          ],
        });
        const file = await handle?.getFile();
        if (file) {
          setReplayFolderStatus("");
          await uploadReplay(file);
          return;
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (!/abort|cancel/i.test(message)) {
          setReplayFolderStatus(
            `Your browser fell back to the standard file picker. Browse to ${replayFolderGuide}.`
          );
          replayFileInputRef.current?.click();
        }
        return;
      }
    }
    setReplayFolderStatus(
      `This browser uses the standard file picker. Browse to ${replayFolderGuide}.`
    );
    replayFileInputRef.current?.click();
  }, [profile?.platform, replayFolderGuide, uploadReplay]);

  const openReplayPicker = useCallback(async () => {
    let dismissed = false;
    try {
      dismissed = window.localStorage.getItem(replayPathHelpStorageKey) === "1";
    } catch {
      dismissed = false;
    }
    if (!dismissed) {
      setReplayPathModalPendingOpen(true);
      setShowReplayPathModal(true);
      return;
    }
    await openNativeReplayPicker();
  }, [openNativeReplayPicker, replayPathHelpStorageKey]);

  const closeReplayPathModal = useCallback(() => {
    setShowReplayPathModal(false);
    setReplayPathModalPendingOpen(false);
  }, []);

  const continueReplayPathModal = useCallback(async () => {
    try {
      window.localStorage.setItem(replayPathHelpStorageKey, "1");
    } catch {
      // Ignore storage failures.
    }
    setShowReplayPathModal(false);
    const shouldOpen = replayPathModalPendingOpen;
    setReplayPathModalPendingOpen(false);
    if (shouldOpen) {
      await openNativeReplayPicker();
    }
  }, [openNativeReplayPicker, replayPathHelpStorageKey, replayPathModalPendingOpen]);

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

  const deleteSavedReplay = useCallback(async (sid: string) => {
    if (!sid) return;
    const target = (library?.data?.sessions ?? []).find((item) => String(item.session_id || item.id || "") === sid);
    const label = target ? replayDisplayName(target) : "this replay";
    if (!window.confirm(`Delete ${label} from your replay library?`)) return;
    try {
      setError("");
      await apiPost(`${REPLAY_PREFIX}/replay/delete`, { session_id: sid }, { suppressErrorWindow: true });
      if (String(session?.session_id || "") === sid) {
        setSession(null);
        setReplayStudioReady(false);
        setMetrics(null);
        setMechanics(null);
        setSelectedPlayer("");
        setEventExplain(null);
        setScoreExplain(null);
      }
      await refreshSummaryViews();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [library?.data?.sessions, refreshSummaryViews, session?.session_id]);

  const recomputeReplayLibrary = useCallback(async () => {
    retryReplayActionRef.current = () => void recomputeReplayLibrary();
    try {
      setError("");
      startOverlay("Regrading Replay Library", "Recomputing mechanic grades for every saved replay...");
      const resp = await apiPost<LibraryRecomputeResponse>(
        `${REPLAY_PREFIX}/replay/library/recompute`,
        {},
        { suppressErrorWindow: true }
      );
      if (session?.session_id) {
        await hydrateReplayStudio();
      }
      await refreshSummaryViews();
      const total = Number(resp?.data?.total_sessions ?? 0);
      const updated = Number(resp?.data?.updated_sessions ?? 0);
      const failed = Number(resp?.data?.failed_sessions ?? 0);
      setOverlay((prev) => ({ ...prev, active: false, error: "" }));
      if (failed > 0) {
        setError(`Replay library updated: ${updated}/${total} replays recomputed, ${failed} failed.`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setOverlay((prev) => ({ ...prev, active: true, error: message, message }));
      setError(message);
    }
  }, [hydrateReplayStudio, refreshSummaryViews, session?.session_id, startOverlay]);

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
    () =>
      progressPoints.map((p) => {
        const t = Number(p.x_time_unix || 0);
        return {
          t,
          v: normalizeScore100(Number(p.overall_mechanics_score || 0)),
          sessionId: String(p.session_id || ""),
          replayName: pointReplayDisplayName(p),
        };
      }),
    [progressPoints]
  );

  const latestScore = progressSeries.length ? Math.round(progressSeries[progressSeries.length - 1].v) : 0;
  const overallTrendSummary = useMemo(() => trendSummary(progressSeries), [progressSeries]);

  const perMechanicSeries = useMemo(() => {
    const out: Record<string, { t: number; v: number; sessionId: string; replayName: string }[]> = {};
    for (const point of progressPoints) {
      const t = Number(point.x_time_unix || 0);
      const mechScores = point.mechanic_scores || {};
      Object.entries(mechScores).forEach(([key, value]) => {
        const normalized = normalizeScore100(Number(value));
        if (!Number.isFinite(normalized)) return;
        if (!out[key]) out[key] = [];
        out[key].push({
          t,
          v: normalized,
          sessionId: String(point.session_id || ""),
          replayName: pointReplayDisplayName(point),
        });
      });
    }
    return out;
  }, [progressPoints]);
  const mechanicTrendEntries = useMemo(
    () =>
      Object.entries(perMechanicSeries).sort((a, b) =>
        englishEventName(a[0]).localeCompare(englishEventName(b[0]))
      ),
    [perMechanicSeries]
  );
  const mechanicTrendSummaries = useMemo(() => {
    const out: Record<string, TrendSummary> = {};
    for (const [mechanicId, series] of Object.entries(perMechanicSeries)) {
      out[mechanicId] = trendSummary(series);
    }
    return out;
  }, [perMechanicSeries]);

  useEffect(() => {
    if (!activeMechanicEventKey) return;
    const selector = `[data-event-key="${CSS.escape(activeMechanicEventKey)}"]`;
    const id = window.setTimeout(() => {
      const el = document.querySelector(selector);
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }, 60);
    return () => window.clearTimeout(id);
  }, [activeMechanicEventKey, mechanicView, focusedMechanicIds]);

  const openReplayFromTrend = useCallback(
    async (sessionId?: string, focusMechanicId?: string) => {
      const sid = String(sessionId || "");
      if (!sid) return;
      if (focusMechanicId) {
        setFocusedMechanicIds(new Set([focusMechanicId]));
      } else {
        setFocusedMechanicIds(new Set());
      }
      await openSaved(sid);
    },
    [openSaved, perMechanicSeries]
  );

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
      const sum = g.items.reduce((acc, it) => acc + mechanicEventScore(it), 0);
      g.avg = g.items.length ? normalizeScore100(sum / g.items.length) : 0;
    }
    return [...groups.values()].sort((a, b) => a.avg - b.avg);
  }, [mechanicEvents]);

  const currentReplayOverallScore = useMemo(() => {
    const fromPayload = Number(mechanics?.data?.overall_mechanics_score);
    if (Number.isFinite(fromPayload) && fromPayload > 0) return normalizeScore100(fromPayload);
    if (!groupedMechanics.length) return 0;
    const sum = groupedMechanics.reduce((acc, group) => acc + Number(group.avg || 0), 0);
    return normalizeScore100(sum / groupedMechanics.length);
  }, [groupedMechanics, mechanics]);

  const librarySessions = library?.data?.sessions ?? [];
  const filteredLibrarySessions = useMemo(() => {
    const query = librarySearch.trim().toLowerCase();
    const matchesQuery = (sessionItem: LibrarySession) => {
      if (!query) return true;
      const lines = replayCardLines(sessionItem, profile);
      const haystack = [
        lines.line1,
        lines.line2,
        sessionItem.map_name,
        sessionItem.tracked_player_name,
        sessionItem.summary?.analysis_player,
        sessionItem.summary?.replay_date_iso,
      ]
        .map((value) => String(value || "").toLowerCase())
        .join(" ");
      return haystack.includes(query);
    };
    const matchesResult = (sessionItem: LibrarySession) => {
      if (libraryResultFilter === "all") return true;
      return replayCardLines(sessionItem, profile).result.toLowerCase() === libraryResultFilter;
    };
    const matchesGamemode = (sessionItem: LibrarySession) => {
      if (libraryGamemodeFilter === "all") return true;
      return sessionGamemode(sessionItem) === libraryGamemodeFilter;
    };
    const items = librarySessions.filter((sessionItem) => matchesQuery(sessionItem) && matchesResult(sessionItem) && matchesGamemode(sessionItem));
    const scoreOf = (sessionItem: LibrarySession) => normalizeScore100(Number(sessionItem.summary?.overall_mechanics_score || 0));
    const timeOf = (sessionItem: LibrarySession) => {
      const raw = String(sessionItem.summary?.replay_date_iso || sessionItem.created_at || "");
      const parsed = new Date(raw);
      return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
    };
    items.sort((a, b) => {
      if (librarySort === "oldest") return timeOf(a) - timeOf(b);
      if (librarySort === "best") return scoreOf(b) - scoreOf(a);
      if (librarySort === "worst") return scoreOf(a) - scoreOf(b);
      return timeOf(b) - timeOf(a);
    });
    return items;
  }, [librarySessions, librarySearch, libraryResultFilter, libraryGamemodeFilter, librarySort, profile]);

  const realLibrarySessions = useMemo(
    () => librarySessions.filter((item) => hasRealReplayData(item)),
    [librarySessions]
  );
  const latestReplayRaw = homeSummary?.data?.latest_replay || realLibrarySessions[0];
  const latestReplay = hasRealReplayData(latestReplayRaw) ? latestReplayRaw : null;
  const hasReplayHistory = Boolean(latestReplay) || realLibrarySessions.length > 0 || progressPoints.length > 0;
  const recommendations = hasReplayHistory
    ? (trainingPlan?.data?.recommendations ?? homeSummary?.data?.recommendations ?? [])
    : [];
  const trackedPlayerLabel = selectedPlayer || session?.analysis_player || latestReplay?.tracked_player_name || latestReplay?.summary?.analysis_player || "";
  const headerReplayStudioActive = activeTab === "replay" && Boolean(session && replayStudioReady);
  const trainingPreflightKnown = trainingPreflightFetchedAt > 0;
  const botTrainingReady = trainingPreflightKnown && Boolean(trainingPreflight?.data?.ready_to_launch);
  const trainingPreflightMessages = trainingPreflight?.data?.messages ?? [];
  const hostChecksAvailable = trainingPreflight?.data?.host_checks_available !== false;
  const trainingLauncherRunning = trainingPreflightKnown ? Boolean(trainingPreflight?.data?.launcher_running) : false;
  const dependencyReady = trainingPreflightKnown ? Boolean(trainingPreflight?.data?.dependency_ready) : false;
  const sharedDependencyReady = trainingPreflightKnown ? Boolean(trainingPreflight?.data?.shared_dependency_ready) : false;
  const rlbotGuiPath = String(trainingPreflight?.data?.rlbot_gui_path || "");
  const rlbotGuiSource = String(trainingPreflight?.data?.rlbot_gui_detection_source || "");
  const showTrainingInstallerCard = trainingPreflightKnown && !trainingLauncherRunning && !dependencyReady;
  const replayLibraryPageCount = Math.max(1, Math.ceil(filteredLibrarySessions.length / REPLAY_LIBRARY_PAGE_SIZE));
  const replayLibraryPageIndex = Math.min(libraryPage, replayLibraryPageCount - 1);
  const pagedLibrarySessions = filteredLibrarySessions.slice(
    replayLibraryPageIndex * REPLAY_LIBRARY_PAGE_SIZE,
    (replayLibraryPageIndex + 1) * REPLAY_LIBRARY_PAGE_SIZE
  );

  useEffect(() => {
    setLibraryPage(0);
  }, [librarySearch, libraryResultFilter, libraryGamemodeFilter, librarySort]);

  useEffect(() => {
    if (libraryPage > replayLibraryPageCount - 1) {
      setLibraryPage(Math.max(0, replayLibraryPageCount - 1));
    }
  }, [libraryPage, replayLibraryPageCount]);

  const setTrainingTier = (focusId: string, tier: string) => {
    setTrainingSelections((prev) => ({
      ...prev,
      [focusId]: { tier, drillMode: prev[focusId]?.drillMode || "" },
    }));
  };

  const launchTraining = async (rec: TrainingRecommendation) => {
    const focusId = String(rec.focus_id || "");
    if (launchingFocus) {
      return;
    }
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
        const bridgeSession = await createBridgeSession("launch", {
            focus_id: focusId,
            difficulty_tier: tier,
            difficulty_value: Number(profileChoice.difficulty_value || 0.3),
            bot_profile_id: String(profileChoice.bot_profile_id || ""),
            scenario_ids: rec.scenario_ids || [],
            drill_mode: drillMode,
            bot_required: Boolean(rec.bot_required),
            platform: String(profile?.platform || "epic"),
        });
      const token = String(bridgeSession?.data?.token || "");
      const callbackUrl = String(bridgeSession?.data?.callback_url || "");
      if (!token || !callbackUrl) {
        throw new Error("RocketCoach could not prepare a training launch session.");
      }
      const launchPayload = encodeURIComponent(JSON.stringify({
        focus_id: focusId,
        difficulty_tier: tier,
        difficulty_value: Number(profileChoice.difficulty_value || 0.3),
        bot_profile_id: String(profileChoice.bot_profile_id || ""),
        scenario_ids: rec.scenario_ids || [],
        drill_mode: drillMode,
        bot_required: Boolean(rec.bot_required),
        platform: String(profile?.platform || "epic"),
      }));
      const protocolUrl = `rocketcoach://train?action=train&callback=${encodeURIComponent(callbackUrl)}&payload=${launchPayload}`;
      await wakeTrainingCompanion(protocolUrl);
      const resp = await pollBridgeSession(token);
      if (String(resp?.data?.status || "") === "error") {
        throw new Error(String(resp?.data?.error || "RocketCoach training launch failed."));
      }
      const launchData = resp?.data?.result?.launch ?? {};
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

  const TAB_META: Record<AppTab, { title: string; description: string }> = {
    home: {
      title: "Overview",
      description: "A quick summary of your recent replay data and the next thing to work on.",
    },
    replay: {
      title: "Replay Library",
      description: "Upload replays, explore the 3D viewer, and dig into per-mechanic grades.",
    },
    improvement: {
      title: "Improvement",
      description: "Descriptive trend analysis built from your replay history.",
    },
    training: {
      title: "Training",
      description: "Prescriptive practice planning based on replay-backed weaknesses and evidence.",
    },
    installer: {
      title: "Installer",
      description: "Download the RLBot Stack Installer to set up everything you need on a new machine.",
    },
  };
  const activeTabMeta = TAB_META[activeTab] ?? TAB_META.home;

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
          {renderTabButton("home", "Overview")}
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
          <Link to="/account" state={{ from: location.pathname }} className="nav-footer-link"><i className="fa-solid fa-gear" /><span>Account</span></Link>
          <button type="button" className="nav-footer-link" onClick={() => logout()}><i className="fa-solid fa-right-from-bracket" /><span>Log Out</span></button>
        </div>
      </aside>

      {showTutorial && (
        <div className="tutorial-overlay" onClick={dismissTutorial}>
          <div className="tutorial-modal" onClick={(e) => e.stopPropagation()}>
            <div className="tutorial-modal-header">
              {activeTab === "home" && <><i className="fa-solid fa-rocket" /><span>RocketCoach</span></>}
              {activeTab === "replay" && <><i className="fa-solid fa-film" /><span>Replay Tab</span></>}
              {activeTab === "improvement" && <><i className="fa-solid fa-chart-line" /><span>Improvement Tab</span></>}
              {activeTab === "training" && <><i className="fa-solid fa-dumbbell" /><span>Training Tab</span></>}
              {activeTab === "installer" && <><i className="fa-solid fa-wrench" /><span>Installer Tab</span></>}
            </div>
            {activeTab === "home" && (
              <div className="tutorial-modal-body">
                <p>RocketCoach analyzes your Rocket League replays and turns your weaknesses into a personalized training plan.</p>
                <ol className="tutorial-steps">
                  <li><strong>Upload a replay</strong> — go to the Replay tab and pick a <code>.replay</code> file from your RL replays folder.</li>
                  <li><strong>Review mechanic grades</strong> — each mechanic (challenge, shadow, aerial…) gets a score out of 100 with event-specific coaching advice.</li>
                  <li><strong>Check your trends</strong> — the Improvement tab shows how your scores change over time across all replays.</li>
                  <li><strong>Train the weak spot</strong> — the Training tab builds a bot session targeting your lowest-scoring mechanic.</li>
                </ol>
              </div>
            )}
            {activeTab === "replay" && (
              <div className="tutorial-modal-body">
                <p>The Replay tab is your coaching hub for a single game.</p>
                <ol className="tutorial-steps">
                  <li><strong>Choose Replay File</strong> — pick a <code>.replay</code> file saved by Rocket League. The file is uploaded and analyzed automatically.</li>
                  <li><strong>3D viewer</strong> — the playback pauses automatically at key mechanic moments and shows a coaching card.</li>
                  <li><strong>Mechanic Grades panel</strong> — switch between Grouped view (averages per mechanic) and Timeline view (every event in order). Click any event to jump to that moment.</li>
                  <li><strong>Coach Feedback</strong> — select any event for a full breakdown including issue tags, thresholds, and improvement cues.</li>
                </ol>
              </div>
            )}
            {activeTab === "improvement" && (
              <div className="tutorial-modal-body">
                <p>The Improvement tab tracks your progress across every replay you have uploaded.</p>
                <ol className="tutorial-steps">
                  <li><strong>Overall score trend</strong> — the top chart shows your average mechanic score over time.</li>
                  <li><strong>Per-mechanic graphs</strong> — each mechanic has its own 0–100 chart. Hover a dot to see which replay it came from and the score for that session.</li>
                  <li><strong>Click a dot</strong> — jumps directly into that replay and filters to that mechanic, so you can review the exact sessions behind any dip or spike.</li>
                </ol>
              </div>
            )}
            {activeTab === "training" && (
              <div className="tutorial-modal-body">
                <p>The Training tab turns your replay analysis into actionable bot practice.</p>
                <ol className="tutorial-steps">
                  <li><strong>Recommendations</strong> — RocketCoach picks the 3 mechanics you need most based on your recent replay scores.</li>
                  <li><strong>Personalized advice</strong> — each card shows coaching advice pulled from your actual replay data.</li>
                  <li><strong>Launch session</strong> — opens a bot training session in Rocket League targeting that mechanic at your skill tier.</li>
                </ol>
              </div>
            )}
            {activeTab === "installer" && (
              <div className="tutorial-modal-body">
                <p>The Installer tab verifies and sets up the tools RocketCoach needs to run bot training on your machine.</p>
                <ol className="tutorial-steps">
                  <li><strong>Verify Dependencies</strong> — checks that Python, RLBot, and required packages are installed correctly.</li>
                  <li><strong>Fix any issues</strong> — follow the on-screen steps for any check that fails.</li>
                  <li><strong>Run once</strong> — you only need to do this on a new machine or after a major update.</li>
                </ol>
              </div>
            )}
            <div className="tutorial-modal-footer">
              <button type="button" onClick={dismissTutorial}>Got it</button>
            </div>
          </div>
        </div>
      )}

      {showReplayPathModal && (
        <div className="tutorial-overlay" onClick={closeReplayPathModal}>
          <div className="tutorial-modal replay-path-modal" onClick={(e) => e.stopPropagation()}>
            <div className="tutorial-modal-header">
              <i className="fa-solid fa-folder-open" />
              <span>Find Your Replay Folder</span>
            </div>
            <div className="tutorial-modal-body">
              <p>Rocket League saves replay files in this folder on your computer:</p>
              <div className="replay-path-callout">
                <code>{replayFolderGuide.replaceAll(" > ", "\\")}</code>
              </div>
              <p>
                Browsers can start a picker in <strong>Documents</strong>, but they cannot automatically open the deeper{" "}
                <strong>{platformUsesEpicReplayFolder(String(profile?.platform || "")) ? "DemosEpic" : "Demos"}</strong> folder unless you browse there yourself.
              </p>
            </div>
            <div className="tutorial-modal-footer">
              <button type="button" className="ghost" onClick={closeReplayPathModal}>Close</button>
              <button type="button" onClick={() => void continueReplayPathModal()}>Continue to picker</button>
            </div>
          </div>
        </div>
      )}

      <main className="main-content">
        <header className="top top--themed">
          <div className="top-heading">
            <div className="top-eyebrow">
              <i className={TAB_ICONS[activeTab]} />
              <span>RocketCoach</span>
            </div>
            <h1>{activeTabMeta.title}</h1>
            <div className="status-text">{activeTab === "home" && !latestReplay ? "Upload your first replay in the Replay tab to get started." : activeTabMeta.description}</div>
          </div>
          <div className="top-actions">
            <button type="button" className="ghost" onClick={reopenTutorial}>
              <i className="fa-solid fa-circle-question" /> Help
            </button>
            {headerReplayStudioActive && (
              <button
                type="button"
                className="ghost replay-library-header-btn"
                onClick={() => setShowLibraryDrawer(true)}
              >
                <i className="fa-solid fa-folder-open" />
                <span>Replay Library</span>
                {librarySessions.length ? <span className="badge-count">{librarySessions.length}</span> : null}
              </button>
            )}
          </div>
        </header>

        {error && <div className="alert">{error}</div>}

        {activeTab === "home" && (
          <section className="panel-stack home-layout">
            {showTutorial && latestReplay && (
              <div className="metrics-card welcome-card">
                <div className="welcome-header">
                  <div className="welcome-icon"><i className="fa-solid fa-rocket" /></div>
                  <div>
                    <h2>Welcome to RocketCoach{profile?.username ? `, ${profile.username}` : ""}</h2>
                    <p className="text-muted">Here’s the shortest path from login to bot training.</p>
                  </div>
                </div>
                <div className="welcome-steps">
                  <div className="welcome-step">
                    <div className="welcome-step-number">1</div>
                    <div>
                      <strong>Verify your setup</strong>
                      <p className="text-muted">Open Training and run <strong>Verify Dependencies</strong> once on this machine.</p>
                    </div>
                  </div>
                  <div className="welcome-step">
                    <div className="welcome-step-number">2</div>
                    <div>
                      <strong>Upload a replay</strong>
                      <p className="text-muted">Use the Replay tab to choose a `.replay` file from your Rocket League replay folder.</p>
                    </div>
                  </div>
                  <div className="welcome-step">
                    <div className="welcome-step-number">3</div>
                    <div>
                      <strong>Train the weak mechanic</strong>
                      <p className="text-muted">Open Training and launch the top recommendation to practice what the replay exposed.</p>
                    </div>
                  </div>
                </div>
                <div className="controls">
                  <button type="button" onClick={() => openTab("replay")}><i className="fa-solid fa-upload" /> Upload Replay</button>
                  <button type="button" className="ghost" onClick={dismissTutorial}>Got It</button>
                </div>
              </div>
            )}

            {!latestReplay ? (
              <div className="metrics-card home-empty-card">
                <div className="home-empty-icon"><i className="fa-solid fa-upload" /></div>
                <h2>Upload your first replay</h2>
                <p className="home-empty-sub">
                  RocketCoach starts once you add a match. Upload a `.replay` file to unlock the replay viewer, mechanic grades, coaching notes, progress tracking, and training recommendations{profile?.username ? `, ${profile.username}` : ""}.
                </p>
                <div className="home-empty-points">
                  <div className="home-empty-point"><i className="fa-solid fa-film" /><span>3D replay playback with coaching cues</span></div>
                  <div className="home-empty-point"><i className="fa-solid fa-chart-line" /><span>Per-mechanic scores and progress trends</span></div>
                  <div className="home-empty-point"><i className="fa-solid fa-dumbbell" /><span>Training ideas based on your replay</span></div>
                </div>
                <button type="button" className="home-empty-cta" onClick={() => openTab("replay")}>
                  <i className="fa-solid fa-upload" /> Upload a Replay
                </button>
              </div>
            ) : null}

            {latestReplay && (
            <div className="home-grid">
              <div className="home-grid-cell home-grid-cell--left">
                <div className="metrics-card">
                  {latestReplay ? (
                    <div className="card-header">
                      <div>
                        <h3>Recent Performance</h3>
                        <strong>{replayCardLines(latestReplay, profile).line1}</strong>
                        <div className="library-item-meta">{replayCardLines(latestReplay, profile).line2}</div>
                        {trackedPlayerLabel ? <div className="library-item-meta">Tracked player: {trackedPlayerLabel}</div> : null}
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setFocusedMechanicIds(new Set());
                          void openSaved(latestReplay.session_id || latestReplay.id || "");
                        }}
                      >
                        Open Latest Replay
                      </button>
                    </div>
                  ) : (
                    <div className="empty-state" style={{ padding: "var(--space-4) 0" }}>
                      <div className="empty-state-icon"><i className="fa-regular fa-circle-play" /></div>
                      <h3>Recent Performance</h3>
                      <p className="library-item-meta">Open a replay to see your recent performance here.</p>
                      <button type="button" onClick={() => openTab("replay")} style={{ marginTop: 10 }}><i className="fa-solid fa-upload" /> Open a Replay</button>
                    </div>
                  )}
                </div>

                <div className="metrics-card home-progress-mini">
                  <div className="chart-card-heading">
                    <div>
                      <h3>Progress Snapshot</h3>
                      <p className="library-item-meta">All-mechanic grade trend</p>
                    </div>
                    {progressSeries.length > 0 && (
                      <span
                        className={`trend-badge trend-badge--${overallTrendSummary.className}`}
                        title={overallTrendSummary.title}
                      >
                        {overallTrendSummary.label}
                      </span>
                    )}
                  </div>
                  <div className="chart-container" style={{ width: "100%" }}>
                    <LineChart series={progressSeries} width={800} height={180} yMin={0} yMax={100} />
                  </div>
                  {!progressSeries.length && <div className="library-item-meta">No data yet. Analyze a replay to start tracking.</div>}
                </div>
              </div>

              <div className="metrics-card home-grid-cell home-grid-cell--work">
                <div className="card-header">
                  <div>
                    <h3>What To Work On</h3>
                    <p className="library-item-meta">Your top replay-backed weaknesses, ranked.</p>
                  </div>
                  <button type="button" className="ghost" onClick={() => openTab("training")} disabled={!tabReady.training}>Open Training</button>
                </div>
                <div className="improvement-cards improvement-cards--compact">
                  {recommendations.slice(0, 3).map((rec) => {
                    const meta = mechanicMetaFor(String(rec.focus_id || ""));
                    return (
                      <div key={rec.focus_id || rec.title} className="improvement-card">
                        <div className="improvement-card-header">
                          <div className={`improvement-rank improvement-rank--${Math.min(Number(rec.priority_rank || 1), 3)}`}>#{rec.priority_rank || 1}</div>
                          <div style={{ flex: 1 }}>
                            <strong style={{ fontSize: 15 }}>{rec.title || "Focus"}</strong>
                            <div className="library-item-meta">Confidence {Math.round(normalizeConfidencePercent(Number(rec.confidence || 0)))}%</div>
                          </div>
                        </div>
                        <p className="library-item-meta" style={{ lineHeight: 1.6, margin: "8px 0 0" }}>
                          {meta.description}
                        </p>
                        <p className="library-item-meta" style={{ lineHeight: 1.6, margin: "10px 0" }}>
                          {(rec.evidence ?? [])[0] || "Analyze more replays to enrich this recommendation."}
                        </p>
                        <button type="button" onClick={() => openTab("training")} disabled={!tabReady.training}>Train This Mechanic</button>
                      </div>
                    );
                  })}
                  {!recommendations.length && <div className="library-item-meta">Recommendations will appear here once you have replay analysis data.</div>}
                </div>
              </div>
            </div>
            )}
          </section>
        )}

        {activeTab === "replay" && (() => {
          const studioActive = Boolean(session && replayStudioReady);
          const libraryDrawerOpen = studioActive && showLibraryDrawer;
          const libraryInline = !studioActive;
          const libraryCardJsx = (
            <div className="metrics-card replay-library-panel">
              <div className="library-head">
                <h2>Replay Library</h2>
                <div className="controls" style={{ marginTop: 0 }}>
                  <button type="button" className="ghost" onClick={() => void refreshSummaryViews()}>Refresh</button>
                  <button type="button" className="ghost" onClick={() => void recomputeReplayLibrary()}>Recompute All</button>
                  {studioActive && (
                    <button type="button" className="ghost" onClick={() => setShowLibraryDrawer(false)} aria-label="Close library">
                      <i className="fa-solid fa-xmark" />
                    </button>
                  )}
                </div>
              </div>
              <div className="controls replay-action-bar">
                <input
                  id="replayFile"
                  ref={replayFileInputRef}
                  type="file"
                  accept=".replay"
                  className="sr-only-file-input"
                  tabIndex={-1}
                  aria-hidden="true"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void uploadReplay(file);
                    e.currentTarget.value = "";
                  }}
                />
                <button type="button" onClick={() => void openReplayPicker()}>
                  <i className="fa-solid fa-folder-open" /> Choose Replay File
                </button>
              </div>
              <div className="library-item-meta replay-picker-help">
                {replayFolderStatus || (
                  <>
                    If the picker opens in the wrong place, browse to <strong>{replayFolderGuide}</strong>.
                  </>
                )}
              </div>
              <div className="controls" style={{ marginTop: 14 }}>
                <input
                  type="search"
                  value={librarySearch}
                  onChange={(e) => setLibrarySearch(e.target.value)}
                  placeholder="Search by date, player, map, or result"
                  style={{ minWidth: 220, flex: 1 }}
                />
                <select value={libraryResultFilter} onChange={(e) => setLibraryResultFilter(e.target.value)}>
                  <option value="all">All Results</option>
                  <option value="win">Wins</option>
                  <option value="loss">Losses</option>
                  <option value="draw">Draws</option>
                  <option value="result">Unknown Result</option>
                </select>
                <select value={libraryGamemodeFilter} onChange={(e) => setLibraryGamemodeFilter(e.target.value)}>
                  <option value="all">All Modes</option>
                  <option value="1v1">1v1</option>
                  <option value="2v2">2v2</option>
                  <option value="3v3">3v3</option>
                  <option value="unknown">Unknown Mode</option>
                </select>
                <select value={librarySort} onChange={(e) => setLibrarySort(e.target.value)}>
                  <option value="newest">Newest First</option>
                  <option value="oldest">Oldest First</option>
                  <option value="best">Best Score</option>
                  <option value="worst">Needs Work</option>
                </select>
              </div>
              <div className="library-list replay-library-list">
                {pagedLibrarySessions.map((s) => {
                  const sid = s.session_id || s.id || "";
                  const lines = replayCardLines(s, profile);
                  const resultLabel = String(lines.result || "Result");
                  return (
                    <div key={sid || s.replay_name} className="library-item replay-library-card">
                      <div className="replay-card-content">
                        <div className={`replay-badge replay-badge-${resultLabel.toLowerCase()}`}>{resultLabel}</div>
                        <div className="replay-card-info">
                          <strong>{lines.line1}</strong>
                          <div className="library-item-meta">{lines.line2}</div>
                        </div>
                      </div>
                      <div className="controls" style={{ marginTop: 0 }}>
                        <button
                          type="button"
                          onClick={() => {
                            setFocusedMechanicIds(new Set());
                            void openSaved(sid);
                            if (studioActive) setShowLibraryDrawer(false);
                          }}
                          disabled={!sid}
                        >
                          Open
                        </button>
                        <button type="button" className="ghost" onClick={() => void deleteSavedReplay(sid)} disabled={!sid}>Delete</button>
                      </div>
                    </div>
                  );
                })}
                {!filteredLibrarySessions.length && (
                  <div className="library-item-meta">
                    {librarySessions.length
                      ? "No replays match the current search or filters."
                      : "No saved replays yet. Upload a .replay file to get started."}
                  </div>
                )}
              </div>
              {filteredLibrarySessions.length > REPLAY_LIBRARY_PAGE_SIZE && (
                <div className="replay-library-pagination">
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => setLibraryPage((page) => Math.max(0, page - 1))}
                    disabled={replayLibraryPageIndex <= 0}
                  >
                    <i className="fa-solid fa-arrow-left" /> Previous
                  </button>
                  <div className="library-item-meta replay-library-page-status">
                    Page {replayLibraryPageIndex + 1} of {replayLibraryPageCount}
                  </div>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => setLibraryPage((page) => Math.min(replayLibraryPageCount - 1, page + 1))}
                    disabled={replayLibraryPageIndex >= replayLibraryPageCount - 1}
                  >
                    Next <i className="fa-solid fa-arrow-right" />
                  </button>
                </div>
              )}
            </div>
          );

          // Build flat timeline list (sorted by time)
          const mechanicFocusActive = focusedMechanicIds.size > 0;
          const timelineEvents = mechanicEvents
            .filter((ev) => !mechanicFocusActive || focusedMechanicIds.has(String(ev.mechanic_id || "")))
            .slice()
            .sort((a, b) => Number(a.time ?? 0) - Number(b.time ?? 0));

          const visibleGroups = groupedMechanics.filter((g) => !mechanicFocusActive || focusedMechanicIds.has(g.mechanicId));

          const toggleMechanicFocus = (mid: string) => {
            setFocusedMechanicIds((prev) => {
              const next = new Set(prev);
              if (next.has(mid)) next.delete(mid);
              else next.add(mid);
              return next;
            });
          };

          const clearMechanicFocus = () => setFocusedMechanicIds(new Set());

          const jumpToEvent = (ev: MechanicEvent) => {
            const alignedTime = alignEventTimeToTimeline(session?.timeline, Number(ev.time ?? 0));
            setCurrentTime(Math.max(0, alignedTime - 1.5));
            setSeekTime(undefined);
            setEventExplain(null);
            setActiveMechanicEventKey(mechanicEventKey({ ...ev, time: alignedTime }));
            setReviewRequest({
              id: Date.now(),
              time: alignedTime,
              event: { ...ev, time: alignedTime },
            });
          };

          const makeFbKey = (ev: MechanicEvent, prefix: string) =>
            `${prefix}:${ev.mechanic_id ?? ""}:${ev.time ?? 0}`;

          const toggleFeedback = (key: string) => {
            setFeedbackKey(prev => (prev === key ? null : key));
            setFeedbackDraft("");
          };

          const submitFeedback = async (ev: MechanicEvent, key: string) => {
            const note = feedbackDraft.trim();
            if (!note || feedbackSaving) return;
            setFeedbackSaving(true);

            const entry = {
              session_id: session?.session_id ?? null,
              replay_name: session?.replay_name ?? "unknown",
              event_time: ev.time ?? 0,
              mechanic_id: ev.mechanic_id ?? "",
              quality_label: ev.quality_label ?? "",
              quality_score: ev.quality_score ?? 0,
              reason: ev.reason ?? "",
              verdict: "wrong",
              note,
            };

            try {
              await apiPost(`${REPLAY_PREFIX}/mechanic-feedback`, entry);
              setFeedbackSavedKeys(prev => new Set([...prev, key]));
              setFeedbackKey(null);
              setFeedbackDraft("");
            } catch (err) {
              console.warn("[mechanic-feedback] save failed", err);
            } finally {
              setFeedbackSaving(false);
            }
          };

          const renderFeedbackBox = (ev: MechanicEvent, key: string) => (
            <div className="mech-feedback-box" onClick={e => e.stopPropagation()}>
              <textarea
                className="mech-feedback-input"
                placeholder="What's wrong? e.g. 'this is a kickoff, not a challenge'"
                value={feedbackDraft}
                rows={2}
                onChange={e => setFeedbackDraft(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void submitFeedback(ev, key); }}
                autoFocus
              />
              <div className="mech-feedback-actions">
                <button
                  type="button"
                  className="mech-feedback-submit"
                  disabled={!feedbackDraft.trim() || feedbackSaving}
                  onClick={() => void submitFeedback(ev, key)}
                >
                  {feedbackSaving ? "Saving…" : "Submit"}
                </button>
                <button
                  type="button"
                  className="mech-feedback-cancel"
                  onClick={() => setFeedbackKey(null)}
                >
                  Cancel
                </button>
              </div>
            </div>
          );

          return (
            <section className="panel-stack replay-layout">
              {libraryInline && libraryCardJsx}

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
                  <p>The replay studio will unlock once metrics and mechanic grades are ready.</p>
                </div>
              )}

              {studioActive && (
                <>
                  {groupedMechanics.length === 0 && (
                    <div className="replay-studio-toolbar">
                      {trackedPlayerLabel && (
                        <div className="library-item-meta">
                          Tracking <strong>{trackedPlayerLabel}</strong>
                        </div>
                      )}
                    </div>
                  )}

                  {groupedMechanics.length > 0 && (
                    <div className="metrics-card mechanic-rings-bar">
                      <div className="mechanic-rings-header">
                        <div className="mechanic-rings-title-row">
                          <h3>Mechanic Grades</h3>
                          <span className="mechanic-overall-score">
                            Overall {fmtNumber(currentReplayOverallScore, 1)}
                          </span>
                        </div>
                        {trackedPlayerLabel && (
                          <div className="library-item-meta">
                            Tracking <strong>{trackedPlayerLabel}</strong>
                          </div>
                        )}
                      </div>
                      <div className="mechanic-rings-grid">
                        {groupedMechanics.map((g, idx) => {
                          const score = Math.round(g.avg);
                          const quality = score >= 72 ? "good" : score >= 45 ? "neutral" : "bad";
                          const color = quality === "good" ? "var(--success)" : quality === "neutral" ? "var(--warning)" : "var(--danger)";
                          const clamp = Math.max(0, Math.min(100, score));
                          const infoOpen = mechInfoOpen === g.mechanicId;
                          const meta = mechanicMetaFor(g.mechanicId, g.items[0]);
                          return (
                            <div
                              key={g.mechanicId}
                              className={`mechanic-ring-item ${idx === groupedMechanics.length - 1 ? "align-end" : idx === 0 ? "align-start" : "align-center"}`}
                            >
                              <div className="mechanic-ring-svg-wrap">
                                <svg viewBox="0 0 36 36" width="82" height="82">
                                  <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--surface-3)" strokeWidth="2.6" />
                                  <circle
                                    cx="18" cy="18" r="15.9"
                                    fill="none"
                                    stroke={color}
                                    strokeWidth="2.6"
                                    strokeLinecap="round"
                                    strokeDasharray={`${clamp} ${100 - clamp}`}
                                    transform="rotate(-90 18 18)"
                                  />
                                  <text x="18" y="18" textAnchor="middle" dominantBaseline="central" fontSize="7.5" fontWeight="700" fill="var(--text-primary)">{score}</text>
                                </svg>
                                <button
                                  type="button"
                                  className="mechanic-ring-info-btn"
                                  title={`About ${g.label}`}
                                  aria-label={`Info about ${g.label}`}
                                  onClick={() => setMechInfoOpen(infoOpen ? null : g.mechanicId)}
                                >i</button>
                              </div>
                              <span className="mechanic-ring-label">{g.label}</span>
                              <span className={`mechanic-ring-grade-pill mechanic-ring-grade-pill--${quality}`}>
                                {quality === "good" ? "Good" : quality === "neutral" ? "Mixed" : "Needs Work"}
                              </span>
                              {infoOpen && (
                                <div className="mechanic-ring-info-card">
                                  <div className="mechanic-ring-info-card-header">
                                    <strong>{meta.label}</strong>
                                    <button
                                      type="button"
                                      className="mechanic-ring-info-close"
                                      aria-label="Close"
                                      onClick={() => setMechInfoOpen(null)}
                                    >✕</button>
                                  </div>
                                  <p className="mechanic-ring-info-desc">{meta.description}</p>
                                  <div className="mechanic-ring-info-rows">
                                    <div className="mechanic-ring-info-row"><span className="mechanic-ring-info-lbl">Why it matters</span><span>{meta.why}</span></div>
                                    <div className="mechanic-ring-info-row"><span className="mechanic-ring-info-lbl">Common miss</span><span>{meta.mistake}</span></div>
                                    <div className="mechanic-ring-info-row"><span className="mechanic-ring-info-lbl">Training cue</span><span>{meta.cue}</span></div>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <section className="layout studio-layout">
                    <ReplayVisualizer
                      timeline={session.timeline ?? []}
                      replayName={replaySessionDisplayName(session)}
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
                        setEventExplain(buildMechanicEventExplain(ev));
                        setActiveMechanicEventKey(mechanicEventKey(ev));
                        const mid = String(ev?.mechanic_id || "");
                        if (mid) {
                          setFocusedMechanicIds((prev) => {
                            if (!prev.size || prev.has(mid)) return prev;
                            const next = new Set(prev);
                            next.add(mid);
                            return next;
                          });
                        }
                      }}
                      onAutoEventClear={() => setEventExplain(null)}
                      eventPopup={
                        eventExplain ? (
                          <div className="event-explain-popup">
                            <div className="event-explain-header">
                              <div className="event-explain-title-row">
                                <strong>{eventExplain.title}</strong>
                                <span className={`quality-badge quality-${eventExplain.grade.toLowerCase()}`}>{eventExplain.grade}</span>
                              </div>
                              <button
                                type="button"
                                className="event-explain-close"
                                onClick={() => setEventExplain(null)}
                              >✕</button>
                            </div>
                            {eventExplain.tags.length ? (
                              <div className="mech-tag-row">
                                {eventExplain.tags.map((tag) => (
                                  <span key={tag} className="mech-tag">{tag}</span>
                                ))}
                              </div>
                            ) : null}
                            <p className="event-explain-body">
                              {eventExplain.body}
                            </p>
                          </div>
                        ) : null
                      }
                      boostPads={session.boost_pads ?? []}
                      seekTime={seekTime}
                      reviewRequest={reviewRequest}
                    />
                    <div className="metrics-card studio-sidebar">
                      <div className="studio-sidebar-section">
                        <div className="mech-view-header">
                          <h3>Mechanic Grades</h3>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <div className="mech-view-toggle" role="tablist" aria-label="Mechanic view mode">
                            <button
                              type="button"
                              className={mechanicView === "timeline" ? "active" : ""}
                              onClick={() => setMechanicView("timeline")}
                              role="tab"
                              aria-selected={mechanicView === "timeline"}
                            >
                              <i className="fa-solid fa-timeline" /> Timeline
                            </button>
                            <button
                              type="button"
                              className={mechanicView === "grouped" ? "active" : ""}
                              onClick={() => setMechanicView("grouped")}
                              role="tab"
                              aria-selected={mechanicView === "grouped"}
                            >
                              <i className="fa-solid fa-layer-group" /> Grouped
                            </button>
                          </div>
                          </div>
                        </div>

                        {groupedMechanics.length > 0 && (
                          <div className="mech-filter-chips">
                            <button
                              type="button"
                              className={`mech-chip ${mechanicFocusActive ? "off" : "on"}`}
                              onClick={clearMechanicFocus}
                              title="Show every mechanic"
                            >
                              All
                            </button>
                            {groupedMechanics.map((g) => {
                              const focused = focusedMechanicIds.has(g.mechanicId);
                              return (
                                <button
                                  type="button"
                                  key={`chip-${g.mechanicId}`}
                                  className={`mech-chip ${focused ? "on" : mechanicFocusActive ? "off" : ""}`}
                                  onClick={() => toggleMechanicFocus(g.mechanicId)}
                                  title={focused ? `Remove ${g.label} from focus` : `Focus ${g.label}`}
                                >
                                  {g.label}
                                </button>
                              );
                            })}
                          </div>
                        )}

                        {mechanicView === "grouped" ? (
                          <div className="library-list mechanic-grades-list">
                            {visibleGroups.map((group) => (
                              <div
                                key={group.mechanicId}
                                className="bubble-card mech-group"
                                data-quality={group.avg >= 72 ? "good" : group.avg >= 45 ? "neutral" : "bad"}
                              >
                                <div className="bubble-toggle mech-group-btn active">
                                  <span className="mech-label">{group.label}</span>
                                  <span className="mech-stats">
                                    <span className="mech-score">{fmtNumber(group.avg, 2)}</span>
                                    <span className="mech-count">{group.items.length} events</span>
                                  </span>
                                </div>
                                <div className="bubble-body mech-events-wrap">
                                  <div className="library-item-meta" style={{ lineHeight: 1.7, marginBottom: 10 }}>
                                    {mechanicMetaFor(group.mechanicId, group.items[0]).description}
                                  </div>
                                  <div className="library-item-meta" style={{ marginBottom: 10 }}>
                                    Cue: {mechanicMetaFor(group.mechanicId, group.items[0]).cue}
                                  </div>
                                  {group.items.map((ev, idx) => {
                                    const fbKey = makeFbKey(ev, `g:${group.mechanicId}:${idx}`);
                                    const isSaved = feedbackSavedKeys.has(fbKey);
                                    const isOpen = feedbackKey === fbKey;
                                    const eventKey = mechanicEventKey({
                                      ...ev,
                                      time: alignEventTimeToTimeline(session?.timeline, Number(ev.time ?? 0)),
                                    });
                                    const isActiveEvent = activeMechanicEventKey === eventKey;
                                    return (
                                      <div
                                        key={`${group.mechanicId}-${idx}`}
                                        className={`library-item mech-event-item${isActiveEvent ? " mech-event-item--active" : ""}`}
                                        data-quality={qualityClassName(ev.quality_label)}
                                        data-event-key={eventKey}
                                      >
                                        <button
                                          type="button"
                                          className="mech-event-clickable"
                                          onClick={() => jumpToEvent(ev)}
                                          title="Jump to this moment"
                                        >
                                          <div className="mech-event-info">
                                            <strong>{fmtGameTime(ev.time ?? 0, session?.timeline ?? [], session?.replay_meta?.ot_start_s ?? null)}</strong>
                                            <div className="library-item-meta">
                                              <span className={`quality-badge quality-${qualityClassName(ev.quality_label)}`}>{qualityText(ev.quality_label)}</span>
                                              <span>Score {fmtNumber(mechanicEventScore(ev), 2)}</span>
                                            </div>
                                            {mechanicEventTags(ev).length ? (
                                              <div className="mech-tag-row">
                                                {mechanicEventTags(ev).map((tag) => (
                                                  <span key={tag} className="mech-tag">{tag}</span>
                                                ))}
                                              </div>
                                            ) : null}
                                            {(ev.template_body || ev.reason) ? <div className="library-item-meta">{mechanicEventBody(ev)}</div> : null}
                                          </div>
                                        </button>
                                        <button
                                          type="button"
                                          className={`mech-flag-btn${isSaved ? " mech-flag-btn--saved" : ""}`}
                                          title={isSaved ? "Feedback saved ✓" : "Flag this detection as wrong"}
                                          onClick={() => toggleFeedback(fbKey)}
                                        >
                                          <i className={`fa-solid ${isSaved ? "fa-check" : "fa-flag"}`} />
                                        </button>
                                        {isOpen && renderFeedbackBox(ev, fbKey)}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            ))}
                            {!visibleGroups.length && <div className="library-item-meta">{groupedMechanics.length ? "No focused mechanics selected." : "Analyze a replay to view mechanic grades."}</div>}
                          </div>
                        ) : (
                          <div className="library-list mechanic-timeline-list">
                            {timelineEvents.map((ev, idx) => {
                              const fbKey = makeFbKey(ev, `tl:${idx}`);
                              const isSaved = feedbackSavedKeys.has(fbKey);
                              const isOpen = feedbackKey === fbKey;
                              const eventKey = mechanicEventKey({
                                ...ev,
                                time: alignEventTimeToTimeline(session?.timeline, Number(ev.time ?? 0)),
                              });
                              const isActiveEvent = activeMechanicEventKey === eventKey;
                              return (
                                <div
                                  key={`tl-${idx}`}
                                  className={`library-item mech-event-item${isActiveEvent ? " mech-event-item--active" : ""}`}
                                  data-quality={qualityClassName(ev.quality_label)}
                                  data-event-key={eventKey}
                                >
                                  <button
                                    type="button"
                                    className="mech-event-clickable"
                                    onClick={() => jumpToEvent(ev)}
                                    title="Jump to this moment"
                                  >
                                    <div className="mech-event-info">
                                      <strong>{fmtGameTime(ev.time ?? 0, session?.timeline ?? [], session?.replay_meta?.ot_start_s ?? null)}</strong>
                                      <div className="library-item-meta">
                                        <span className="mech-timeline-label">{englishEventName(String(ev.mechanic_id || ""))}</span>
                                        <span className={`quality-badge quality-${qualityClassName(ev.quality_label)}`}>{qualityText(ev.quality_label)}</span>
                                        <span>Score {fmtNumber(mechanicEventScore(ev), 2)}</span>
                                      </div>
                                      {mechanicEventTags(ev).length ? (
                                        <div className="mech-tag-row">
                                          {mechanicEventTags(ev).map((tag) => (
                                            <span key={tag} className="mech-tag">{tag}</span>
                                          ))}
                                        </div>
                                      ) : null}
                                      {(ev.template_body || ev.reason) ? <div className="library-item-meta">{mechanicEventBody(ev)}</div> : null}
                                    </div>
                                  </button>
                                  <button
                                    type="button"
                                    className={`mech-flag-btn${isSaved ? " mech-flag-btn--saved" : ""}`}
                                    title={isSaved ? "Feedback saved ✓" : "Flag this detection as wrong"}
                                    onClick={() => toggleFeedback(fbKey)}
                                  >
                                    <i className={`fa-solid ${isSaved ? "fa-check" : "fa-flag"}`} />
                                  </button>
                                  {isOpen && renderFeedbackBox(ev, fbKey)}
                                </div>
                              );
                            })}
                            {!timelineEvents.length && <div className="library-item-meta">{mechanicEvents.length ? "No events match the focused mechanics." : "Analyze a replay to view mechanic events."}</div>}
                          </div>
                        )}
                      </div>
                    </div>
                  </section>
                </>
              )}

              {libraryDrawerOpen && (
                <div
                  className="library-drawer-backdrop"
                  onClick={() => setShowLibraryDrawer(false)}
                  role="presentation"
                >
                  <div
                    className="library-drawer"
                    onClick={(e) => e.stopPropagation()}
                    role="dialog"
                    aria-label="Replay Library"
                  >
                    {libraryCardJsx}
                  </div>
                </div>
              )}
            </section>
          );
        })()}

        {activeTab === "improvement" && (
          <section className="panel-stack">
            {progressSeries.length > 0 && (
              <div className="improvement-summary">
                <div className="summary-stat">
                  <div className="summary-stat-label">Replays Analyzed</div>
                  <div className="summary-stat-value">{progressSeries.length}</div>
                </div>
                <div className="summary-stat">
                  <div className="summary-stat-label">Latest Score</div>
                  <div className="summary-stat-value">{latestScore}</div>
                </div>
                <div className="summary-stat">
                  <div className="summary-stat-label">Trend</div>
                  <div className={`summary-stat-value trend-summary-value trend-summary-value--${overallTrendSummary.className}`}>
                    <i
                      className={`fa-solid ${
                        overallTrendSummary.className === "up"
                          ? "fa-arrow-trend-up"
                          : overallTrendSummary.className === "down"
                            ? "fa-arrow-trend-down"
                            : "fa-minus"
                      }`}
                    />
                    <span title={overallTrendSummary.title}>{overallTrendSummary.label}</span>
                  </div>
                </div>
              </div>
            )}
            <div className="metrics-card">
              <div className="chart-card-heading">
                <div>
                  <h3>Overall Mechanics Score Over Time</h3>
                  <p className="library-item-meta">Latest replay compared to your first replay in this graph.</p>
                </div>
                {progressSeries.length > 0 && (
                  <span
                    className={`trend-badge trend-badge--${overallTrendSummary.className}`}
                    title={overallTrendSummary.title}
                  >
                    {overallTrendSummary.label}
                  </span>
                )}
              </div>
              <div className="chart-container">
                <LineChart
                  series={progressSeries}
                  width={820}
                  height={230}
                  yMin={0}
                  yMax={100}
                  onPointClick={(point) => void openReplayFromTrend((point as { sessionId?: string }).sessionId)}
                  pointTitle={(point) => {
                    const replayName = String((point as { replayName?: string }).replayName || "").trim();
                    return replayName ? `Open ${replayName}` : "Open replay";
                  }}
                />
              </div>
              {!progressSeries.length && <div className="library-item-meta">No replay trend data yet.</div>}
            </div>
            <div className="improvement-layout">
              {mechanicTrendEntries.map(([mechanicId, series]) => {
                const mechanicTrend = mechanicTrendSummaries[mechanicId] || trendSummary(series);
                return (
                <div className="metrics-card" key={mechanicId}>
                  <div className="chart-card-heading chart-card-heading--compact">
                    <h3>{englishEventName(mechanicId)}</h3>
                    <span
                      className={`trend-badge trend-badge--${mechanicTrend.className}`}
                      title={mechanicTrend.title}
                    >
                      {mechanicTrend.label}
                    </span>
                  </div>
                  <div className="chart-container">
                    <LineChart
                      series={series}
                      width={400}
                      height={180}
                      yMin={0}
                      yMax={100}
                      tooltipLabel={englishEventName(mechanicId)}
                      onPointClick={(point) =>
                        void openReplayFromTrend((point as { sessionId?: string }).sessionId, mechanicId)
                      }
                      pointTitle={(point) => {
                        const replayName = String((point as { replayName?: string }).replayName || "").trim();
                        return replayName ? `Open ${replayName} and focus ${englishEventName(mechanicId)}` : `Open replay for ${englishEventName(mechanicId)}`;
                      }}
                    />
                  </div>
                  <div className="library-item-meta" style={{ marginTop: 8 }}>
                    Click a point to open that replay and jump into a {englishEventName(mechanicId).toLowerCase()} review.
                  </div>
                </div>
                );
              })}
            </div>
          </section>
        )}

        {activeTab === "installer" && (
          <section className="panel-stack">
            <div className="metrics-card">
              <h3>RLBotStackInstaller.exe</h3>
              <p className="library-item-meta" style={{ marginBottom: 16 }}>
                A standalone Windows installer. No Python installation required — it downloads and configures RLBot GUI, RLBotPack, and the full Python environment.
              </p>
              <a
                href={`${REPLAY_PREFIX}/installer/download?v=${encodeURIComponent(String(import.meta.env.VITE_APP_VERSION || "latest"))}`}
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
            {showTrainingInstallerCard && (
              <div className="metrics-card">
                <h3>RLBot Setup Installer</h3>
                <p className="library-item-meta" style={{ marginBottom: 16 }}>
                  RocketCoach could not start the local companion and the training dependencies are not ready on this machine yet.
                </p>
                <a
                  href={`${REPLAY_PREFIX}/installer/download?v=${encodeURIComponent(String(import.meta.env.VITE_APP_VERSION || "latest"))}`}
                  download="RLBotStackInstaller.exe"
                  className="installer-download-link"
                >
                  Download RLBotStackInstaller.exe
                </a>
              </div>
            )}
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
                  <i
                    className={`fa-solid ${!trainingPreflightKnown ? "fa-circle-question" : dependencyReady ? "fa-circle-check" : "fa-circle-xmark"}`}
                    style={{ color: !trainingPreflightKnown ? "var(--text-muted)" : dependencyReady ? "var(--success)" : "var(--danger)" }}
                  />
                  <span>Dependencies installed</span>
                </div>
                <div className="preflight-check">
                  <i
                    className={`fa-solid ${!trainingPreflightKnown ? "fa-circle-question" : trainingLauncherRunning ? "fa-circle-check" : "fa-circle-xmark"}`}
                    style={{ color: !trainingPreflightKnown ? "var(--text-muted)" : trainingLauncherRunning ? "var(--success)" : "var(--danger)" }}
                  />
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
                {trainingPreflightKnown && trainingPreflightFresh && !trainingPreflightChecking && <div className="library-item-meta">Cached result is fresh.</div>}
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
                <div className="library-item-meta">
                  {trainingPreflightKnown ? "No preflight details were returned yet." : "RocketCoach is still checking this machine."}
                </div>
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
                const meta = mechanicMetaFor(focusId);
                const selectedTier = trainingSelections[focusId]?.tier || String(rec.difficulty_default?.tier || rec.difficulty_profiles?.[0]?.tier || "beginner");
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
                        <div className="library-item-meta">Priority score {fmtNumber(normalizeScore100(Number(rec.priority_score || 0)), 2)} | Confidence {Math.round(normalizeConfidencePercent(Number(rec.confidence || 0)))}%</div>
                      </div>
                    </div>

                    <div className="library-item-meta" style={{ marginBottom: 10 }}>
                      {(rec.evidence ?? []).slice(0, 3).map((e, idx) => (
                        <div key={`${focusId}-evidence-${idx}`}>{e}</div>
                      ))}
                    </div>

                    <p className="library-item-meta" style={{ lineHeight: 1.6, margin: "6px 0 10px" }}>
                      {meta.description}
                    </p>

                    <div className="training-advice-box">
                      <strong style={{ fontSize: 12 }}>What to focus on in practice</strong>
                      <p className="library-item-meta" style={{ marginTop: 4, lineHeight: 1.6 }}>
                        {(rec.evidence ?? []).length
                          ? `Based on your replays: ${(rec.evidence ?? []).slice(0, 2).map((e) => {
                              const m = e.match(/mechanic score ([\d.]+)/);
                              return m ? `scored ${m[1]}` : "";
                            }).filter(Boolean).join(", ") || "room for improvement"}. ${
                              (rec.difficulty_profiles ?? []).find((profile) => profile.tier === selectedTier)?.summary ||
                              "Work on consistency and decision-making under pressure at this mechanic."
                            }`
                          : "Analyze more replays so RocketCoach can build personalized training advice for this mechanic."}
                      </p>
                    </div>

                    <label>
                      Difficulty
                      <select value={selectedTier} onChange={(e) => setTrainingTier(focusId, e.target.value)}>
                        {(rec.difficulty_profiles ?? []).map((profile) => (
                          <option key={profile.tier} value={profile.tier}>{profile.label || profile.tier}</option>
                        ))}
                      </select>
                    </label>

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
            </ul>
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
