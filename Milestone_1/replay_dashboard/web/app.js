const statusText = document.getElementById("statusText");
const replayFile = document.getElementById("replayFile");
const uploadBtn = document.getElementById("uploadBtn");
const openReplayFolderBtn = document.getElementById("openReplayFolderBtn");
const playerSelect = document.getElementById("playerSelect");
const analyzePlayerBtn = document.getElementById("analyzePlayerBtn");
const playBtn = document.getElementById("playBtn");
const pauseBtn = document.getElementById("pauseBtn");
const prevEventBtn = document.getElementById("prevEventBtn");
const nextEventBtn = document.getElementById("nextEventBtn");
const speedSelect = document.getElementById("speedSelect");
const zoomRange = document.getElementById("zoomRange");
const timeLabel = document.getElementById("timeLabel");
const nextEventInfo = document.getElementById("nextEventInfo");
const nextEventExplain = document.getElementById("nextEventExplain");
const durationLabel = document.getElementById("durationLabel");
const arenaStatus = document.getElementById("arenaStatus");
const perfStatus = document.getElementById("perfStatus");
const progressBar = document.getElementById("progressBar");
const progressLabel = document.getElementById("progressLabel");
const timelineSlider = document.getElementById("timelineSlider");
const metricCards = document.getElementById("metricCards");
const eventsEl = document.getElementById("events");
const labelLayer = document.getElementById("labelLayer");
const sceneEl = document.getElementById("scene");
const blueScoreEl = document.getElementById("blueScore");
const orangeScoreEl = document.getElementById("orangeScore");
const clockTextEl = document.getElementById("clockText");
const otBadgeEl = document.getElementById("otBadge");
const debugToggleBtn = document.getElementById("debugToggle");
const debugBubbleEl = document.getElementById("debugBubble");
const debugCloseBtn = document.getElementById("debugClose");
const debugBodyEl = document.getElementById("debugBody");
const eventCoachPanel = document.getElementById("eventCoachPanel");
const eventCoachClose = document.getElementById("eventCoachClose");
const eventCoachTitle = document.getElementById("eventCoachTitle");
const eventCoachScore = document.getElementById("eventCoachScore");
const eventCoachBody = document.getElementById("eventCoachBody");
const usernameInput = document.getElementById("usernameInput");
const aliasesInput = document.getElementById("aliasesInput");
const rankSelect = document.getElementById("rankSelect");
const platformSelect = document.getElementById("platformSelect");
const loginBtn = document.getElementById("loginBtn");
const profileStatus = document.getElementById("profileStatus");
const refreshLibraryBtn = document.getElementById("refreshLibraryBtn");
const libraryList = document.getElementById("libraryList");
const openLibraryBtn = document.getElementById("openLibraryBtn");
const closeLibraryBtn = document.getElementById("closeLibraryBtn");
const libraryDrawer = document.getElementById("libraryDrawer");
const loginGate = document.getElementById("loginGate");
const appShell = document.getElementById("appShell");
const logoutBtn = document.getElementById("logoutBtn");
const timelineEvents = document.getElementById("timelineEvents");
const timelineFilterMode = document.getElementById("timelineFilterMode");
const refreshRecsBtn = document.getElementById("refreshRecsBtn");
const recsList = document.getElementById("recsList");
const refreshMechanicsBtn = document.getElementById("refreshMechanicsBtn");
const mechanicsList = document.getElementById("mechanicsList");
const recsBubbleToggle = document.getElementById("recsBubbleToggle");
const recsBubbleBody = document.getElementById("recsBubbleBody");
const mechanicsBubbleToggle = document.getElementById("mechanicsBubbleToggle");
const mechanicsBubbleBody = document.getElementById("mechanicsBubbleBody");
const toastEl = document.getElementById("toast");

const FIELD_X = 8192;
const FIELD_Y = 10240;
const WALL_HEIGHT = 620;
const WALL_THICKNESS = 60;
const GOAL_WIDTH = 1780;
const GOAL_HEIGHT = 640;
const TELEPORT_DIST_THRESHOLD = 900;
const SHOW_REPLAY_CHARTS = false;

const metricMeta = [
  ["speed", "Speed", "Current car speed. Higher speed means more momentum and faster challenge reach."],
  ["hesitation_percent", "Hesitation %", "Percent of pressured moments where movement looks indecisive."],
  ["hesitation_score", "Hesitation Score", "0-1 moment score of indecision. Higher means more hesitation now."],
  ["boost_waste_percent", "Boost Waste %", "Boost spent in low-value situations. Lower is usually better."],
  ["supersonic_percent", "Supersonic %", "Percent of time above supersonic speed."],
  ["useful_supersonic_percent", "Useful Supersonic %", "Supersonic time spent in useful pressure/progress contexts."],
  ["pressure_percent", "Pressure %", "How often the player is actively pressuring play near ball."],
  ["whiff_rate_per_min", "Whiff Rate / min", "Estimated missed challenge/touch attempts per minute."],
  ["approach_efficiency", "Approach Efficiency", "Ball-closing progress per boost used while approaching."],
  ["recovery_time_avg_s", "Recovery Avg (s)", "Average time to become playable after aerial/awkward states."],
];

let replayData = null;
let selectedPlayer = "";
let currentFrame = 0;
let playing = false;
let playbackSpeed = 1.0;
let isTimelineReady = false;
let metricsReady = false;
let currentReplayTimeS = 0;
let replayStartTimeS = 0;
let replayEndTimeS = 0;
let playStartReplayTimeS = 0;
let playStartWallTimeMs = 0;
let metricPollToken = 0;
let metricRequestInFlight = false;
let lastMetricFetchWallMs = 0;
const METRIC_FETCH_INTERVAL_MS = 120;
let liveMetricPoint = null;
let liveSeekSupported = true;
let liveSeekFailureCount = 0;
let fallbackMetricsInFlight = false;
let zoomScale = 1.0;
let analysisLocked = false;
let currentProfile = null;
let currentMechanics = null;
let playToEventTargetS = null;
let nextEventExplainKey = "";
let nextEventExplainToken = 0;
let timelineEventMode = "top10";
let lastLibrarySessions = [];
let lastAutoPausedEventKey = "";
let eventCoachToken = 0;
let goalPauseWindows = [];
let goalHoldUntilWallMs = 0;
let goalHoldReplayT = 0;
let goalHoldResumeReplayT = 0;
let recentBallTouchUntilT = -1;
let lastBallTouchDetectT = -999;
let reviewOrbitEnabled = false;
let reviewOrbitYaw = 0;
let reviewOrbitPitch = 0;
let reviewOrbitDragging = false;
let reviewOrbitLastX = 0;
let reviewOrbitLastY = 0;

const carObjects = new Map();
const nameTags = new Map();
let ballMesh = null;

let scene;
let camera;
let renderer;
let needsRender = true;
let lastChartDrawMs = 0;
const CHART_DRAW_INTERVAL_MS = 220;
let eventItems = [];
let activeEventIndex = -1;
const metricSeriesCache = {};
let boostPadGroup = null;
let lastTagRefreshMs = 0;
let tagRefreshMs = 60;
let AXIS_RL_TO_SCENE = null;
let AXIS_SCENE_TO_RL = null;
let playerIdxMap = new Map();
let scoreTimeline = [];
let lastFrameLookupIdx = 0;
let clockSamples = [];
let zeroClockStartTimeS = null;
let arenaMeshGroup = null;
let proceduralArenaObjects = [];
let overlayGroup = null;
let lastRenderWallTimeMs = 0;
let fpsCounter = 0;
let fpsAccumMs = 0;
let chartDrawIntervalMs = CHART_DRAW_INTERVAL_MS;
let playbackDriftMs = 0;
let lastRafTsMs = 0;
let camAnchorPos = null;
let camAnchorForward = new THREE.Vector3(1, 0, 0);
let camPosVel = new THREE.Vector3();
let camLookVel = new THREE.Vector3();
let camLook = null;
let demoIntervalsByPlayer = new Map();
let boostSamplesByPlayer = new Map();
let debugOpen = false;
let lastDebugUpdateMs = 0;
let currentFps = 0;
let sceneInitialized = false;
let toastTimer = 0;

function normalizePlayerKey(name) {
  return String(name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function dampedSpringStep(statePos, stateVel, targetPos, stiffness, damping, dt) {
  const accel = targetPos.clone().sub(statePos).multiplyScalar(stiffness).add(stateVel.clone().multiplyScalar(-damping));
  stateVel.addScaledVector(accel, dt);
  statePos.addScaledVector(stateVel, dt);
}

function fmt(v, d = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "0";
  return Number(v).toFixed(d);
}

function showToast(text, ms = 3200) {
  if (!toastEl) return;
  toastEl.textContent = String(text || "");
  toastEl.classList.remove("hidden");
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.classList.add("hidden");
  }, Math.max(1000, Number(ms || 0)));
}

function setDrawerOpen(open) {
  const isOpen = !!open;
  if (!libraryDrawer) return;
  libraryDrawer.classList.toggle("hidden", !isOpen);
  libraryDrawer.setAttribute("aria-hidden", isOpen ? "false" : "true");
  try {
    localStorage.setItem("replay_library_drawer_open", isOpen ? "1" : "0");
  } catch (_err) {}
}

function restoreDrawerState() {
  try {
    const raw = localStorage.getItem("replay_library_drawer_open");
    setDrawerOpen(raw === "1");
  } catch (_err) {
    setDrawerOpen(false);
  }
}

function setBubbleOpen(toggleEl, bodyEl, open, key) {
  if (!toggleEl || !bodyEl) return;
  const isOpen = !!open;
  bodyEl.classList.toggle("hidden", !isOpen);
  toggleEl.setAttribute("aria-expanded", isOpen ? "true" : "false");
  try {
    localStorage.setItem(key, isOpen ? "1" : "0");
  } catch (_err) {}
}

function restoreBubbleStates() {
  const recsOpen = (() => {
    try { return localStorage.getItem("bubble_recs_open") === "1"; } catch (_e) { return false; }
  })();
  const mechOpen = (() => {
    try { return localStorage.getItem("bubble_mech_open") === "1"; } catch (_e) { return false; }
  })();
  setBubbleOpen(recsBubbleToggle, recsBubbleBody, recsOpen, "bubble_recs_open");
  setBubbleOpen(mechanicsBubbleToggle, mechanicsBubbleBody, mechOpen, "bubble_mech_open");
}

function restoreTimelineFilterMode() {
  try {
    const m = localStorage.getItem("timeline_event_mode");
    if (m && ["top10", "worst5", "best5", "all"].includes(m)) {
      timelineEventMode = m;
      if (timelineFilterMode) timelineFilterMode.value = m;
      return;
    }
  } catch (_err) {}
  timelineEventMode = String(timelineFilterMode?.value || "top10");
}

function setNextEventExplainText(text) {
  if (!nextEventExplain) return;
  nextEventExplain.textContent = String(text || "Why: --");
}

function setCoachPanelOpen(open) {
  if (!eventCoachPanel) return;
  eventCoachPanel.classList.toggle("hidden", !open);
  reviewOrbitEnabled = !!open;
  if (!open) {
    reviewOrbitDragging = false;
    reviewOrbitYaw = 0;
    reviewOrbitPitch = 0;
  }
}

function englishEventName(mid) {
  const map = {
    shadow_defense: "shadow defense",
    challenge: "challenge",
    early_challenge_timing: "challenge",
    flicking: "flick",
    carrying_dribbling: "carry and dribble",
    flicking_carry_offense: "flick",
    aerial_offense: "aerial offense",
    aerial_defense: "aerial defense",
    fifty_fifty_control: "50/50 control",
  };
  return map[String(mid || "")] || "mechanic";
}

function stableHashString(v) {
  const s = String(v || "");
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0);
}

function pickByHash(arr, seed) {
  if (!Array.isArray(arr) || !arr.length) return "";
  return arr[Math.abs(Number(seed || 0)) % arr.length];
}

function buildFallbackAdviceText({ mechanicId, label, hints, timeS }) {
  const en = englishEventName(mechanicId || "");
  const hint1 = String((hints && hints[0]) || "kept the decision cleaner under pressure");
  const hint2 = String((hints && hints[1]) || "late, reactive movement after committing");
  const seed = stableHashString(`${mechanicId || ""}|${Math.round(Number(timeS || 0) * 10)}|${label || ""}`);
  const good = [
    `Good ${en}. You ${hint1}, and that kept your options open for the next touch.`,
    `Nice ${en}. You ${hint1}, which gave you cleaner control in that sequence.`,
    `Strong ${en}. You ${hint1}, and forced the play in your favor.`,
    `Well played on ${en}. You ${hint1}, creating a safer next action.`,
    `Good read on ${en}. You ${hint1}, reducing the opponent's pressure window.`,
    `Solid ${en}. You ${hint1}, and made the follow-up easier to execute.`,
  ];
  const bad = [
    `To improve ${en}, try ${hint1} next time.`,
    `For better ${en}, focus on ${hint1} on the first commit.`,
    `To clean up ${en}, try ${hint1} before the ball reaches your challenge window.`,
    `For stronger ${en}, aim to ${hint1} and avoid giving up space.`,
    `To raise your ${en} score, try ${hint1} when this pattern appears again.`,
    `Next time on ${en}, prioritize ${hint1} so the play stays controllable.`,
  ];
  const base = String(label || "").toLowerCase() === "good" ? pickByHash(good, seed) : pickByHash(bad, seed);
  if (String(label || "").toLowerCase() === "good") return base;
  return `${base}\nAvoid: ${hint2}.`;
}

function buildGoalPauseWindows() {
  const raw = replayData?.replay_meta?.goal_pause_windows || [];
  goalPauseWindows = [];
  for (const w of raw) {
    const s = Number(w?.pause_start_s);
    const e = Number(w?.pause_end_s);
    if (!Number.isFinite(s) || !Number.isFinite(e)) continue;
    goalPauseWindows.push({
      start: s,
      end: Math.max(s, e),
      blue: Number(w?.blue || 0),
      orange: Number(w?.orange || 0),
    });
  }
  goalPauseWindows.sort((a, b) => a.start - b.start);
}

function goalPauseWindowAtTime(t) {
  for (const w of goalPauseWindows) {
    if (t < w.start) break;
    if (t >= w.start && t < w.end) return w;
  }
  return null;
}

function alignTimeToTimeline(t) {
  if (!replayData?.timeline?.length) return Number(t || 0);
  const arr = replayData.timeline;
  const target = Number(t || 0);
  let lo = 0;
  let hi = arr.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const mt = Number(arr[mid]?.t || 0);
    if (mt < target) lo = mid + 1;
    else hi = mid - 1;
  }
  const i0 = Math.max(0, Math.min(arr.length - 1, lo));
  const i1 = Math.max(0, Math.min(arr.length - 1, lo - 1));
  const t0 = Number(arr[i0]?.t || 0);
  const t1 = Number(arr[i1]?.t || 0);
  return Math.abs(t0 - target) < Math.abs(t1 - target) ? t0 : t1;
}

function mechanicEventsSorted() {
  const events = (currentMechanics?.mechanic_events || []).slice();
  events.sort((a, b) => Number(a?.time || 0) - Number(b?.time || 0));
  return events;
}

function dedupeMechanicEvents(events) {
  const byKey = new Map();
  for (const e of (events || [])) {
    const t = alignTimeToTimeline(Number(e?.time || 0));
    const bucket = Math.round(t * 2) / 2;
    const k = `${String(e?.mechanic_id || "mech")}|${bucket.toFixed(1)}`;
    if (!byKey.has(k)) {
      byKey.set(k, e);
      continue;
    }
    const prev = byKey.get(k);
    const prevAbs = Math.abs(Number(prev?.quality_score || 0) - 0.5);
    const curAbs = Math.abs(Number(e?.quality_score || 0) - 0.5);
    if (curAbs > prevAbs) byKey.set(k, e);
  }
  return Array.from(byKey.values());
}

function filteredMechanicEvents() {
  const raw = dedupeMechanicEvents(mechanicEventsSorted());
  const withAligned = raw.map((e) => ({ ...e, __aligned_t: alignTimeToTimeline(Number(e?.time || 0)) }));
  if (timelineEventMode === "all") return withAligned.sort((a, b) => Number(a?.__aligned_t || 0) - Number(b?.__aligned_t || 0));
  const scored = withAligned.slice();
  if (timelineEventMode === "worst5") {
    return scored
      .sort((a, b) => Number(a?.quality_score || 0) - Number(b?.quality_score || 0))
      .slice(0, 5)
      .sort((a, b) => Number(a?.__aligned_t || 0) - Number(b?.__aligned_t || 0));
  }
  if (timelineEventMode === "best5") {
    return scored
      .sort((a, b) => Number(b?.quality_score || 0) - Number(a?.quality_score || 0))
      .slice(0, 5)
      .sort((a, b) => Number(a?.__aligned_t || 0) - Number(b?.__aligned_t || 0));
  }
  const worst = scored
    .slice()
    .sort((a, b) => Number(a?.quality_score || 0) - Number(b?.quality_score || 0))
    .slice(0, 5);
  const best = scored
    .slice()
    .sort((a, b) => Number(b?.quality_score || 0) - Number(a?.quality_score || 0))
    .slice(0, 5);
  const merged = dedupeMechanicEvents([...worst, ...best]);
  const mergedAligned = merged.map((e) => ({ ...e, __aligned_t: alignTimeToTimeline(Number(e?.time || 0)) }));
  mergedAligned.sort((a, b) => Number(a?.__aligned_t || 0) - Number(b?.__aligned_t || 0));
  return mergedAligned;
}

function eventRatingText(evt) {
  const score01 = Number(evt?.quality_score || 0);
  const score100 = Math.max(0, Math.min(100, score01 * 100));
  const label = String(evt?.quality_label || "neutral");
  const short = String(evt?.short || evt?.mechanic_id || "MECH");
  return `${short} | ${label} | ${fmt(score100, 1)}/100`;
}

function updateNextEventInfoAtTime(t) {
  if (!nextEventInfo) return;
  const events = filteredMechanicEvents();
  if (!events.length) {
    nextEventInfo.textContent = "Next event: none";
    setNextEventExplainText("Why: --");
    nextEventExplainKey = "";
    return;
  }
  let chosen = null;
  for (const e of events) {
    if (Number(e?.__aligned_t || e?.time || 0) > Number(t || 0) + 0.02) {
      chosen = e;
      break;
    }
  }
  if (!chosen) chosen = events[0];
  const et = Number(chosen?.__aligned_t || chosen?.time || 0);
  nextEventInfo.textContent = `Next event: ${eventRatingText(chosen)} @ ${fmt(et, 2)}s`;
  requestNextEventExplanation(chosen);
}

async function requestNextEventExplanation(evt) {
  const key = `${String(evt?.mechanic_id || "")}|${fmt(Number(evt?.time || 0), 3)}`;
  if (key === nextEventExplainKey) return;
  nextEventExplainKey = key;
  const token = ++nextEventExplainToken;
  setNextEventExplainText("Why: loading event explanation...");
  try {
    const res = await fetchJson("/api/mechanics/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        time_s: Number(evt?.time || 0),
        mechanic_id: String(evt?.mechanic_id || ""),
        include_llm: true,
      }),
    });
    if (token !== nextEventExplainToken) return;
    if (!res?.ok) {
      setNextEventExplainText(`Why: ${res?.error || "explanation unavailable"}`);
      return;
    }
    const det = res?.data?.deterministic || {};
    const llm = res?.data?.llm || {};
    const label = String(det?.quality_label || evt?.quality_label || "neutral");
    const hints = Array.isArray(det?.actionable_hints) ? det.actionable_hints : [];
    const llmText = String(llm?.text || "").trim();
    const fallback = buildFallbackAdviceText({
      mechanicId: det?.mechanic_id || evt?.mechanic_id || "",
      label,
      hints,
      timeS: Number(evt?.time || 0),
    });
    const full = llmText ? llmText : fallback;
    setNextEventExplainText(full);
  } catch (err) {
    if (token !== nextEventExplainToken) return;
    setNextEventExplainText(`Why: explanation failed (${err?.message || err})`);
  }
}

function playToNextMechanicEvent() {
  if (!replayData?.timeline?.length) {
    statusText.textContent = "Load replay data first.";
    return;
  }
  const events = filteredMechanicEvents();
  if (!events.length) {
    statusText.textContent = "No mechanic events available yet.";
    return;
  }
  const nowT = Number(currentReplayTimeS || 0);
  let chosen = null;
  for (const e of events) {
    if (Number(e?.__aligned_t || e?.time || 0) > nowT + 0.02) {
      chosen = e;
      break;
    }
  }
  if (!chosen) {
    chosen = events[0];
    currentReplayTimeS = replayStartTimeS;
    renderAtTime(currentReplayTimeS);
  }
  seekPlayToMechanicEvent(chosen, "next");
}

function playToPrevMechanicEvent() {
  if (!replayData?.timeline?.length) {
    statusText.textContent = "Load replay data first.";
    return;
  }
  const events = filteredMechanicEvents();
  if (!events.length) {
    statusText.textContent = "No mechanic events available yet.";
    return;
  }
  const nowT = Number(currentReplayTimeS || 0);
  let chosen = null;
  for (let i = events.length - 1; i >= 0; i--) {
    const et = Number(events[i]?.__aligned_t || events[i]?.time || 0);
    if (et < nowT - 0.02) {
      chosen = events[i];
      break;
    }
  }
  if (!chosen) chosen = events[events.length - 1];

  seekPlayToMechanicEvent(chosen, "previous");
}

function seekPlayToMechanicEvent(evt, directionLabel) {
  const target = Number(evt?.__aligned_t || evt?.time || 0);
  if (!Number.isFinite(target)) return;
  let nowT = Number(currentReplayTimeS || replayStartTimeS || 0);

  // If wrapped or otherwise behind/ahead incorrectly, reset to start before playing forward.
  if (target < nowT - 0.02) {
    nowT = Number(replayStartTimeS || 0);
    currentReplayTimeS = nowT;
    renderAtTime(nowT);
  }

  // If already at the event, snap and stop (prevents "nothing happened" feel).
  if (Math.abs(target - nowT) <= 0.05) {
    currentReplayTimeS = target;
    renderAtTime(target);
    playing = false;
    playToEventTargetS = null;
    lastAutoPausedEventKey = `${String(evt?.mechanic_id || "")}|${fmt(target, 3)}`;
    openEventCoachPanel(evt).catch(() => {});
    statusText.textContent = `At ${directionLabel} event: ${eventRatingText(evt)}`;
    return;
  }

  playToEventTargetS = target;
  playing = true;
  playStartReplayTimeS = currentReplayTimeS;
  playStartWallTimeMs = performance.now();
  playbackDriftMs = 0;
  statusText.textContent = `Playing to ${directionLabel} event: ${eventRatingText(evt)}`;
  updateNextEventInfoAtTime(currentReplayTimeS);
  needsRender = true;
}

async function openEventCoachPanel(evt) {
  if (!evt) return;
  const et = Number(evt?.__aligned_t || evt?.time || 0);
  const label = String(evt?.quality_label || "neutral");
  const score100 = Math.max(0, Math.min(100, Number(evt?.quality_score || 0) * 100));
  const en = englishEventName(evt?.mechanic_id || "");
  if (eventCoachTitle) eventCoachTitle.textContent = `${en.charAt(0).toUpperCase()}${en.slice(1)}`;
  if (eventCoachScore) eventCoachScore.textContent = `Score: ${fmt(score100, 1)}/100 (${label}) at ${fmt(et, 2)}s`;
  if (eventCoachBody) eventCoachBody.textContent = "Loading coaching advice...";
  setCoachPanelOpen(true);

  const token = ++eventCoachToken;
  try {
    const res = await fetchJson("/api/mechanics/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        time_s: et,
        mechanic_id: String(evt?.mechanic_id || ""),
        include_llm: true,
      }),
    });
    if (token !== eventCoachToken) return;
    const llmText = String(res?.data?.llm?.text || "").trim();
    const hints = Array.isArray(res?.data?.deterministic?.actionable_hints) ? res.data.deterministic.actionable_hints : [];
    const out = llmText || buildFallbackAdviceText({
      mechanicId: evt?.mechanic_id || "",
      label,
      hints,
      timeS: et,
    });
    if (eventCoachBody) eventCoachBody.textContent = out;
  } catch (_err) {
    if (token !== eventCoachToken) return;
    if (eventCoachBody) {
      eventCoachBody.textContent = buildFallbackAdviceText({
        mechanicId: evt?.mechanic_id || "",
        label,
        hints: [],
        timeS: et,
      });
    }
  }
}

function formatClock(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const rem = String(s % 60).padStart(2, "0");
  return `${m}:${rem}`;
}

function buildScoreTimeline() {
  const scoreSamples = replayData?.replay_meta?.score_samples || [];
  const out = [];
  for (const s of scoreSamples) {
    const t = Number(s?.time_s);
    const blue = Number(s?.blue);
    const orange = Number(s?.orange);
    if (!Number.isFinite(t) || !Number.isFinite(blue) || !Number.isFinite(orange)) continue;
    out.push({ t, blue: Math.max(0, Math.floor(blue)), orange: Math.max(0, Math.floor(orange)) });
  }
  out.sort((a, b) => a.t - b.t);
  if (!out.length) out.push({ t: replayStartTimeS, blue: 0, orange: 0 });
  scoreTimeline = out;
}

function buildClockSamples() {
  const raw = replayData?.replay_meta?.clock_samples || [];
  const normalized = [];
  for (const s of raw) {
    const t = Number(s?.time_s);
    const rem = Number(s?.seconds_remaining);
    if (!Number.isFinite(t) || !Number.isFinite(rem)) continue;
    normalized.push({ t, rem: Math.max(0, rem) });
  }
  normalized.sort((a, b) => a.t - b.t);

  clockSamples = [];
  for (const s of normalized) {
    if (clockSamples.length && Math.abs(clockSamples[clockSamples.length - 1].t - s.t) < 1e-6) {
      clockSamples[clockSamples.length - 1].rem = s.rem;
    } else {
      clockSamples.push(s);
    }
  }

  if (!clockSamples.length) {
    clockSamples = [
      { t: replayStartTimeS, rem: 300 },
      { t: replayEndTimeS, rem: Math.max(0, 300 - (replayEndTimeS - replayStartTimeS)) },
    ];
  }

  zeroClockStartTimeS = null;
  for (const s of clockSamples) {
    if (s.rem <= 0.001) {
      zeroClockStartTimeS = s.t;
      break;
    }
  }
}

function secondsRemainingAtTime(t) {
  if (!clockSamples.length) return Math.max(0, 300 - (t - replayStartTimeS));
  let rem = clockSamples[0].rem;
  for (let i = 0; i < clockSamples.length; i++) {
    if (clockSamples[i].t <= t) rem = clockSamples[i].rem;
    else break;
  }
  return Math.max(0, rem);
}

function updateHud(t) {
  const pauseWin = goalPauseWindowAtTime(t);
  let blue = scoreTimeline[0]?.blue || 0;
  let orange = scoreTimeline[0]?.orange || 0;
  for (let i = 0; i < scoreTimeline.length; i++) {
    if (scoreTimeline[i].t <= t) {
      blue = scoreTimeline[i].blue;
      orange = scoreTimeline[i].orange;
      continue;
    }
    break;
  }
  if (pauseWin) {
    blue = Math.max(0, Math.floor(Number(pauseWin.blue || blue)));
    orange = Math.max(0, Math.floor(Number(pauseWin.orange || orange)));
  }
  blueScoreEl.textContent = String(blue);
  orangeScoreEl.textContent = String(orange);

  const remain = pauseWin ? secondsRemainingAtTime(pauseWin.start) : secondsRemainingAtTime(t);
  const inOt = remain <= 0.001 && Number.isFinite(zeroClockStartTimeS) && t > (zeroClockStartTimeS + 0.05);
  if (inOt) {
    const otElapsed = Math.max(0, t - zeroClockStartTimeS);
    otBadgeEl.style.display = "block";
    clockTextEl.textContent = `+${formatClock(otElapsed)}`;
  } else {
    otBadgeEl.style.display = "none";
    clockTextEl.textContent = formatClock(remain);
  }
}

function setDebugOpen(open) {
  debugOpen = !!open;
  if (debugBubbleEl) debugBubbleEl.classList.toggle("closed", !debugOpen);
}

function countHiddenPlayersAtTime(t) {
  if (!replayData?.players?.length) return 0;
  let n = 0;
  for (const p of replayData.players) {
    if (isPlayerDemoHidden(p, t)) n += 1;
  }
  return n;
}

function updateDebugBubble() {
  if (!debugOpen || !debugBodyEl) return;
  const boostSource = replayData?.replay_meta?.boost_source || "unknown";
  const metricMode = liveSeekSupported ? "live-seek" : "legacy-cache";
  const replayT = Number.isFinite(currentReplayTimeS) ? currentReplayTimeS : 0;
  const hiddenNow = countHiddenPlayersAtTime(replayT);
  const mp = getMetricAtFrame(currentFrame) || {};
  const contestSuppressed = Number(mp.contest_suppressed_whiffs || 0);
  const clearMissContest = Number(mp.clear_miss_under_contest || 0);
  const pressureGated = Number(mp.pressure_gated_frames || 0);
  const supFlip = Number(mp.suppressed_whiff_flip_commit || 0);
  const supDisengage = Number(mp.suppressed_whiff_disengage || 0);
  const supBump = Number(mp.suppressed_whiff_bump_intent || 0);
  const supOppFirst = Number(mp.suppressed_whiff_opponent_first_touch || 0);
  const supReposition = Number(mp.suppressed_hesitation_reposition || 0);
  const supSetup = Number(mp.suppressed_hesitation_setup || 0);
  const supSpacing = Number(mp.suppressed_hesitation_spacing || 0);
  const lines = [
    `Player: ${selectedPlayer || "-"}`,
    `Metrics: ${metricMode}`,
    `Live seek failures: ${liveSeekFailureCount}`,
    `Boost source: ${boostSource}`,
    `Boost sample players: ${boostSamplesByPlayer.size}`,
    `Demo events: ${(replayData?.replay_meta?.demo_events || []).length}`,
    `Players demo-hidden now: ${hiddenNow}`,
    `Contest-suppressed whiffs: ${contestSuppressed.toFixed(0)}`,
    `Clear misses under contest: ${clearMissContest.toFixed(0)}`,
    `Pressure gated frames: ${pressureGated.toFixed(0)}`,
    `Whiff suppr (flip): ${supFlip.toFixed(0)}`,
    `Whiff suppr (disengage): ${supDisengage.toFixed(0)}`,
    `Whiff suppr (bump intent): ${supBump.toFixed(0)}`,
    `Whiff suppr (opp first touch): ${supOppFirst.toFixed(0)}`,
    `Hes suppr (reposition): ${supReposition.toFixed(0)}`,
    `Hes suppr (setup): ${supSetup.toFixed(0)}`,
    `Hes suppr (spacing): ${supSpacing.toFixed(0)}`,
    `FPS: ${currentFps.toFixed(1)}`,
    `Drift ms: ${playbackDriftMs.toFixed(1)}`,
    `Frame: ${currentFrame}`,
    `Replay t: ${fmt(replayT, 3)}`,
  ];
  debugBodyEl.textContent = lines.join("\n");
}

function buildDemoIntervals() {
  demoIntervalsByPlayer = new Map();
  const events = replayData?.replay_meta?.demo_events || [];
  for (const ev of events) {
    const player = normalizePlayerKey(ev?.victim_player || "");
    const t = Number(ev?.time_s);
    if (!player || !Number.isFinite(t)) continue;
    const arr = demoIntervalsByPlayer.get(player) || [];
    arr.push({ start: t, end: t + 3.0 });
    demoIntervalsByPlayer.set(player, arr);
  }
  for (const arr of demoIntervalsByPlayer.values()) {
    arr.sort((a, b) => a.start - b.start);
  }
}

function isPlayerDemoHidden(player, t) {
  const arr = demoIntervalsByPlayer.get(normalizePlayerKey(player));
  if (!arr || !arr.length) return false;
  for (const iv of arr) {
    if (t < iv.start) break;
    if (t >= iv.start && t <= iv.end) return true;
  }
  return false;
}

function buildBoostSampleLookup() {
  boostSamplesByPlayer = new Map();
  const raw = replayData?.replay_meta?.boost_samples_by_player || {};
  for (const [player, samples] of Object.entries(raw)) {
    if (!Array.isArray(samples) || !samples.length) continue;
    const normalized = samples
      .map((s) => ({ t: Number(s?.time_s), boost: Number(s?.boost) }))
      .filter((s) => Number.isFinite(s.t) && Number.isFinite(s.boost))
      .sort((a, b) => a.t - b.t);
    if (normalized.length) boostSamplesByPlayer.set(normalizePlayerKey(player), normalized);
  }
}

function boostAtTime(player, t) {
  const arr = boostSamplesByPlayer.get(normalizePlayerKey(player));
  if (!arr || !arr.length) return null;
  let lo = 0;
  let hi = arr.length - 1;
  let best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid].t <= t) {
      best = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  if (best < 0) return null;
  return arr[best].boost;
}

function setProgress(progress, label) {
  progressBar.style.width = `${Math.max(0, Math.min(100, progress * 100))}%`;
  progressLabel.textContent = label || "";
}

function setControlsEnabled(enabled) {
  isTimelineReady = !!enabled;
  playBtn.disabled = !enabled;
  pauseBtn.disabled = !enabled;
  speedSelect.disabled = !enabled;
  timelineSlider.disabled = !enabled;
  zoomRange.disabled = !enabled;
  needsRender = true;
}

function setArenaStatus(text) {
  if (arenaStatus) arenaStatus.textContent = text;
}

function setProceduralArenaVisible(visible) {
  if (!scene || !proceduralArenaObjects.length) return;
  if (visible) {
    for (const obj of proceduralArenaObjects) {
      if (obj && !obj.parent) scene.add(obj);
    }
  } else {
    for (const obj of proceduralArenaObjects) {
      if (obj && obj.parent === scene) scene.remove(obj);
    }
  }
}

function clearMetricDisplay() {
  metricMeta.forEach(([key]) => {
    const el = document.getElementById(`val_${key}`);
    if (el) el.textContent = "--";
  });
  if (eventsEl) eventsEl.innerHTML = "";
  eventItems = [];
  activeEventIndex = -1;
  playToEventTargetS = null;
  if (nextEventInfo) nextEventInfo.textContent = "Next event: none";
  setNextEventExplainText("Why: --");
  nextEventExplainKey = "";
  nextEventExplainToken += 1;
  for (const key of Object.keys(metricSeriesCache)) delete metricSeriesCache[key];
}

function initMetricCards() {
  metricCards.innerHTML = "";
  for (const [key, title, help] of metricMeta) {
    const card = document.createElement("div");
    card.className = "metric";
    card.innerHTML = `
      <div class="metric-head">
        <strong>${title}</strong>
        <button class="info-btn" data-key="${key}">?</button>
      </div>
      <div id="val_${key}" class="metric-value">0.00</div>
      <div id="help_${key}" class="metric-help">${help}</div>
    `;
    metricCards.appendChild(card);
  }
  for (const btn of document.querySelectorAll(".info-btn")) {
    btn.addEventListener("click", () => {
      const key = btn.dataset.key;
      document.getElementById(`help_${key}`)?.classList.toggle("open");
    });
  }
}

function drawSeries(canvasId, series, color, currentT) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !series || series.length < 2) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const tMin = series[0].t;
  const tMax = series[series.length - 1].t;
  const vMin = Math.min(...series.map((p) => p.v));
  const vMax = Math.max(...series.map((p) => p.v));
  const tSpan = Math.max(1e-6, tMax - tMin);
  const vSpan = Math.max(1e-6, vMax - vMin);

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  series.forEach((p, i) => {
    const x = ((p.t - tMin) / tSpan) * (w - 20) + 10;
    const y = h - (((p.v - vMin) / vSpan) * (h - 20) + 10);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  if (currentT !== undefined) {
    const cx = ((currentT - tMin) / tSpan) * (w - 20) + 10;
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, 0);
    ctx.lineTo(cx, h);
    ctx.stroke();
  }
}

function rlToScene(pos) {
  return new THREE.Vector3(pos.x, pos.z, -pos.y);
}

function rlQuatToSceneQuat(qx, qy, qz, qw) {
  const q = new THREE.Quaternion(qx, qy, qz, qw);
  q.premultiply(AXIS_RL_TO_SCENE);
  q.multiply(AXIS_SCENE_TO_RL);
  return q.normalize();
}

function addBoostPads(pads) {
  if (boostPadGroup) {
    scene.remove(boostPadGroup);
    boostPadGroup.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose?.();
      if (obj.material) obj.material.dispose?.();
    });
  }
  boostPadGroup = new THREE.Group();

  const smallGeo = new THREE.CylinderGeometry(55, 55, 8, 20);
  const bigGeo = new THREE.CylinderGeometry(90, 90, 10, 24);
  const smallMat = new THREE.MeshStandardMaterial({ color: 0x4cc4ff, emissive: 0x103040, roughness: 0.35, metalness: 0.55 });
  const bigMat = new THREE.MeshStandardMaterial({ color: 0xffb347, emissive: 0x402810, roughness: 0.28, metalness: 0.6 });

  for (const pad of pads || []) {
    const mesh = new THREE.Mesh(pad.size === "big" ? bigGeo : smallGeo, pad.size === "big" ? bigMat : smallMat);
    const pos = rlToScene({ x: pad.x, y: pad.y, z: pad.z });
    mesh.position.copy(pos).add(new THREE.Vector3(0, 4, 0));
    boostPadGroup.add(mesh);
  }
  scene.add(boostPadGroup);
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function lerpAngle(a, b, t) {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

function createArena() {
  const turf = new THREE.Mesh(
    new THREE.PlaneGeometry(FIELD_X, FIELD_Y),
    new THREE.MeshStandardMaterial({ color: 0x2f6d4f, roughness: 0.9, metalness: 0.05 })
  );
  turf.rotation.x = -Math.PI / 2;
  turf.receiveShadow = true;
  scene.add(turf);

  const lineMat = new THREE.LineBasicMaterial({ color: 0xf8fbff });

  const makeRect = (w, h) => {
    const pts = [
      new THREE.Vector3(-w / 2, 1, -h / 2),
      new THREE.Vector3(w / 2, 1, -h / 2),
      new THREE.Vector3(w / 2, 1, h / 2),
      new THREE.Vector3(-w / 2, 1, h / 2),
      new THREE.Vector3(-w / 2, 1, -h / 2),
    ];
    return new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat);
  };

  scene.add(makeRect(FIELD_X * 0.95, FIELD_Y * 0.95));

  const midLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-FIELD_X * 0.475, 1, 0),
      new THREE.Vector3(FIELD_X * 0.475, 1, 0),
    ]),
    lineMat
  );
  scene.add(midLine);

  const circlePts = [];
  const r = 920;
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * Math.PI * 2;
    circlePts.push(new THREE.Vector3(Math.cos(a) * r, 1, Math.sin(a) * r));
  }
  scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(circlePts), lineMat));

  const wallBlueMat = new THREE.MeshStandardMaterial({ color: 0x3f7fbb, metalness: 0.08, roughness: 0.72, transparent: true, opacity: 0.36 });
  const wallOrangeMat = new THREE.MeshStandardMaterial({ color: 0xbe7d44, metalness: 0.08, roughness: 0.72, transparent: true, opacity: 0.36 });
  const borderMat = new THREE.MeshStandardMaterial({ color: 0x5d7688, metalness: 0.2, roughness: 0.5 });
  const goalFrameBlue = new THREE.MeshStandardMaterial({ color: 0x4aa8ff, metalness: 0.28, roughness: 0.35 });
  const goalFrameOrange = new THREE.MeshStandardMaterial({ color: 0xff914d, metalness: 0.28, roughness: 0.35 });
  const curveMat = new THREE.MeshStandardMaterial({ color: 0x6a8398, metalness: 0.15, roughness: 0.55, transparent: true, opacity: 0.28 });

  // Side walls split by half so each side is team-colored.
  const leftBlue = new THREE.Mesh(new THREE.BoxGeometry(WALL_THICKNESS, WALL_HEIGHT, FIELD_Y / 2), wallBlueMat);
  leftBlue.position.set(-FIELD_X / 2, WALL_HEIGHT / 2, FIELD_Y / 4);
  const leftOrange = new THREE.Mesh(new THREE.BoxGeometry(WALL_THICKNESS, WALL_HEIGHT, FIELD_Y / 2), wallOrangeMat);
  leftOrange.position.set(-FIELD_X / 2, WALL_HEIGHT / 2, -FIELD_Y / 4);
  const rightBlue = new THREE.Mesh(new THREE.BoxGeometry(WALL_THICKNESS, WALL_HEIGHT, FIELD_Y / 2), wallBlueMat);
  rightBlue.position.set(FIELD_X / 2, WALL_HEIGHT / 2, FIELD_Y / 4);
  const rightOrange = new THREE.Mesh(new THREE.BoxGeometry(WALL_THICKNESS, WALL_HEIGHT, FIELD_Y / 2), wallOrangeMat);
  rightOrange.position.set(FIELD_X / 2, WALL_HEIGHT / 2, -FIELD_Y / 4);
  scene.add(leftBlue, leftOrange, rightBlue, rightOrange);

  const rimFrontL = new THREE.Mesh(
    new THREE.BoxGeometry((FIELD_X - GOAL_WIDTH) / 2, WALL_HEIGHT, WALL_THICKNESS),
    wallBlueMat
  );
  rimFrontL.position.set(-(GOAL_WIDTH + FIELD_X) / 4, WALL_HEIGHT / 2, FIELD_Y / 2);
  scene.add(rimFrontL);
  const rimFrontR = rimFrontL.clone();
  rimFrontR.position.x = -rimFrontL.position.x;
  scene.add(rimFrontR);
  const rimBackL = rimFrontL.clone();
  rimBackL.position.z = -FIELD_Y / 2;
  rimBackL.material = wallOrangeMat;
  scene.add(rimBackL);
  const rimBackR = rimFrontR.clone();
  rimBackR.position.z = -FIELD_Y / 2;
  rimBackR.material = wallOrangeMat;
  scene.add(rimBackR);

  const topFront = new THREE.Mesh(new THREE.BoxGeometry(GOAL_WIDTH, WALL_HEIGHT - GOAL_HEIGHT, WALL_THICKNESS), wallBlueMat);
  topFront.position.set(0, GOAL_HEIGHT + (WALL_HEIGHT - GOAL_HEIGHT) / 2, FIELD_Y / 2);
  scene.add(topFront);
  const topBack = topFront.clone();
  topBack.position.z = -FIELD_Y / 2;
  topBack.material = wallOrangeMat;
  scene.add(topBack);

  const border = new THREE.Mesh(
    new THREE.BoxGeometry(FIELD_X + 260, 26, FIELD_Y + 260),
    borderMat
  );
  border.position.set(0, 12, 0);
  scene.add(border);

  function addGoal(z, frameMat, wallMat) {
    const postL = new THREE.Mesh(new THREE.BoxGeometry(18, GOAL_HEIGHT, 18), frameMat);
    postL.position.set(-GOAL_WIDTH / 2, GOAL_HEIGHT / 2, z);
    const postR = postL.clone();
    postR.position.x = GOAL_WIDTH / 2;
    const cross = new THREE.Mesh(new THREE.BoxGeometry(GOAL_WIDTH, 18, 18), frameMat);
    cross.position.set(0, GOAL_HEIGHT, z);
    const floor = new THREE.Mesh(new THREE.BoxGeometry(GOAL_WIDTH, 10, 840), wallMat);
    floor.position.set(0, 5, z + (z > 0 ? -420 : 420));
    scene.add(postL, postR, cross, floor);
  }
  addGoal(FIELD_Y / 2 - 2, goalFrameBlue, wallBlueMat);
  addGoal(-FIELD_Y / 2 + 2, goalFrameOrange, wallOrangeMat);

  // Corner curves and wall-to-ceiling curvature (approximate RL arena transitions).
  const cornerR = 800;
  const cornerH = 460;
  const cornerGeo = new THREE.CylinderGeometry(cornerR, cornerR, cornerH, 20, 1, true, 0, Math.PI / 2);
  const corners = [
    [FIELD_X / 2 - cornerR, cornerH / 2, FIELD_Y / 2 - cornerR, 0],
    [-FIELD_X / 2 + cornerR, cornerH / 2, FIELD_Y / 2 - cornerR, Math.PI / 2],
    [-FIELD_X / 2 + cornerR, cornerH / 2, -FIELD_Y / 2 + cornerR, Math.PI],
    [FIELD_X / 2 - cornerR, cornerH / 2, -FIELD_Y / 2 + cornerR, -Math.PI / 2],
  ];
  for (const [x, y, z, ry] of corners) {
    const m = z > 0 ? wallBlueMat : wallOrangeMat;
    const curve = new THREE.Mesh(cornerGeo, m);
    curve.rotation.y = ry;
    curve.position.set(x, y, z);
    scene.add(curve);
  }

  const ceilingR = 500;
  const ceilingGeo = new THREE.TorusGeometry(ceilingR, 26, 8, 24, Math.PI / 2);
  const ceilLeftBlue = new THREE.Mesh(ceilingGeo, curveMat);
  ceilLeftBlue.position.set(-FIELD_X / 2 + ceilingR, WALL_HEIGHT + 120, FIELD_Y / 4);
  ceilLeftBlue.rotation.set(Math.PI / 2, 0, 0);
  const ceilLeftOrange = ceilLeftBlue.clone();
  ceilLeftOrange.position.z = -FIELD_Y / 4;
  const ceilRightBlue = ceilLeftBlue.clone();
  ceilRightBlue.position.x = FIELD_X / 2 - ceilingR;
  const ceilRightOrange = ceilLeftOrange.clone();
  ceilRightOrange.position.x = FIELD_X / 2 - ceilingR;
  scene.add(ceilLeftBlue, ceilLeftOrange, ceilRightBlue, ceilRightOrange);
}

function createMapOverlay() {
  if (overlayGroup) {
    scene.remove(overlayGroup);
  }
  overlayGroup = new THREE.Group();

  const lineMat = new THREE.MeshBasicMaterial({ color: 0xf7fbff, transparent: true, opacity: 0.98 });
  const brightBlue = new THREE.MeshBasicMaterial({ color: 0x31a8ff, transparent: true, opacity: 0.18 });
  const brightOrange = new THREE.MeshBasicMaterial({ color: 0xffa041, transparent: true, opacity: 0.18 });
  const wallBlueMat = new THREE.MeshBasicMaterial({ color: 0x4ab4ff, transparent: true, opacity: 0.6, side: THREE.DoubleSide });
  const wallOrangeMat = new THREE.MeshBasicMaterial({ color: 0xff9f4f, transparent: true, opacity: 0.6, side: THREE.DoubleSide });

  const playW = FIELD_X * 0.92;
  const playH = FIELD_Y * 0.92;

  const midLine = new THREE.Mesh(new THREE.PlaneGeometry(playW, 16), lineMat);
  midLine.rotation.x = -Math.PI / 2;
  midLine.position.set(0, 2, 0);
  overlayGroup.add(midLine);

  const halfBlue = new THREE.Mesh(new THREE.PlaneGeometry(playW, playH * 0.5), brightBlue);
  halfBlue.rotation.x = -Math.PI / 2;
  halfBlue.position.set(0, 1, playH * 0.25);
  overlayGroup.add(halfBlue);

  const halfOrange = new THREE.Mesh(new THREE.PlaneGeometry(playW, playH * 0.5), brightOrange);
  halfOrange.rotation.x = -Math.PI / 2;
  halfOrange.position.set(0, 1, -playH * 0.25);
  overlayGroup.add(halfOrange);

  const wallH = WALL_HEIGHT + 140;

  const makeWall = (x, z, len, rotY, mat) => {
    const wall = new THREE.Mesh(new THREE.PlaneGeometry(len, wallH), mat);
    wall.position.set(x, wallH * 0.5, z);
    wall.rotation.y = rotY;
    return wall;
  };

  overlayGroup.add(makeWall(-FIELD_X * 0.5 + 20, FIELD_Y * 0.25, FIELD_Y * 0.5, Math.PI / 2, wallBlueMat));
  overlayGroup.add(makeWall(FIELD_X * 0.5 - 20, FIELD_Y * 0.25, FIELD_Y * 0.5, -Math.PI / 2, wallBlueMat));
  overlayGroup.add(makeWall(-FIELD_X * 0.5 + 20, -FIELD_Y * 0.25, FIELD_Y * 0.5, Math.PI / 2, wallOrangeMat));
  overlayGroup.add(makeWall(FIELD_X * 0.5 - 20, -FIELD_Y * 0.25, FIELD_Y * 0.5, -Math.PI / 2, wallOrangeMat));

  const borderPts = [
    new THREE.Vector3(-playW * 0.5, 3, -playH * 0.5),
    new THREE.Vector3(playW * 0.5, 3, -playH * 0.5),
    new THREE.Vector3(playW * 0.5, 3, playH * 0.5),
    new THREE.Vector3(-playW * 0.5, 3, playH * 0.5),
    new THREE.Vector3(-playW * 0.5, 3, -playH * 0.5),
  ];
  overlayGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(borderPts), new THREE.LineBasicMaterial({ color: 0xffffff })));

  const centerCirclePts = [];
  const r = 900;
  for (let i = 0; i <= 72; i++) {
    const a = (i / 72) * Math.PI * 2;
    centerCirclePts.push(new THREE.Vector3(Math.cos(a) * r, 3, Math.sin(a) * r));
  }
  overlayGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(centerCirclePts), new THREE.LineBasicMaterial({ color: 0xffffff })));

  scene.add(overlayGroup);
}

function parseObjToMesh(objText, material) {
  const verts = [];
  const positions = [];
  const lines = objText.split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("v ")) {
      const p = line.split(/\s+/);
      if (p.length >= 4) {
        const x = Number(p[1]);
        const y = Number(p[2]);
        const z = Number(p[3]);
        if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) {
          verts.push([x, y, z]);
        }
      }
      continue;
    }
    if (line.startsWith("f ")) {
      const p = line.split(/\s+/).slice(1);
      const idx = [];
      for (const tok of p) {
        const head = tok.split("/")[0];
        const vi = Number(head);
        if (Number.isFinite(vi) && vi !== 0) idx.push(vi > 0 ? vi - 1 : verts.length + vi);
      }
      if (idx.length < 3) continue;
      for (let i = 1; i < idx.length - 1; i++) {
        const tri = [idx[0], idx[i], idx[i + 1]];
        for (const vi of tri) {
          const v = verts[vi];
          if (!v) continue;
          positions.push(v[0], v[2], -v[1]);
        }
      }
    }
  }
  if (!positions.length) return null;
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geo.computeVertexNormals();
  const mesh = new THREE.Mesh(geo, material);
  mesh.frustumCulled = true;
  return mesh;
}

function parseCmfToMesh(arrayBuffer, material) {
  const dv = new DataView(arrayBuffer);
  if (dv.byteLength < 8) return null;
  // CMF format from RLArenaCollisionDumper:
  // int numTris, int numVertices, then tris, then vertices.
  const triCount = dv.getUint32(0, true);
  const vertexCount = dv.getUint32(4, true);
  if (vertexCount <= 0 || triCount <= 0) return null;
  // DUMPER/Bullet units to Rocket League UU.
  const CMF_TO_RL = 50.0;

  const expectedBytes = 8 + triCount * 3 * 4 + vertexCount * 3 * 4;
  if (expectedBytes > dv.byteLength) return null;

  let off = 8;
  const index = new Uint32Array(triCount * 3);
  let indexInvalid = false;
  for (let i = 0; i < index.length; i++) {
    index[i] = dv.getUint32(off, true);
    if (index[i] >= vertexCount) indexInvalid = true;
    off += 4;
  }
  if (indexInvalid) return null;

  const pos = new Float32Array(vertexCount * 3);
  for (let i = 0; i < vertexCount; i++) {
    const x = dv.getFloat32(off, true); off += 4;
    const y = dv.getFloat32(off, true); off += 4;
    const z = dv.getFloat32(off, true); off += 4;
    pos[i * 3 + 0] = x * CMF_TO_RL;
    pos[i * 3 + 1] = z * CMF_TO_RL;
    pos[i * 3 + 2] = -y * CMF_TO_RL;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setIndex(new THREE.BufferAttribute(index, 1));
  geo.computeVertexNormals();
  const mesh = new THREE.Mesh(geo, material);
  mesh.frustumCulled = true;
  return mesh;
}

async function tryLoadArenaCollisionMeshes() {
  if (!scene) return;
  if (arenaMeshGroup) {
    scene.remove(arenaMeshGroup);
    arenaMeshGroup.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose?.();
      if (obj.material) obj.material.dispose?.();
    });
    arenaMeshGroup = null;
  }

  let payload;
  try {
    const mapName = encodeURIComponent(replayData?.replay_meta?.map_name || "");
    payload = await fetchJson(`/api/arena_meshes?map_name=${mapName}`);
  } catch {
    setProceduralArenaVisible(true);
    setArenaStatus("Arena: procedural fallback (mesh API failed)");
    return;
  }
  if (!payload?.ok || !payload?.data?.available) {
    setProceduralArenaVisible(true);
    setArenaStatus("Arena: procedural fallback (no mesh files)");
    return;
  }

  const files = payload.data.files || [];
  const cmfFiles = files
    .filter((f) => String(f).toLowerCase().endsWith(".cmf"))
    .sort((a, b) => {
      const ai = Number((String(a).match(/mesh_(\d+)\.cmf$/i) || [])[1] || 999999);
      const bi = Number((String(b).match(/mesh_(\d+)\.cmf$/i) || [])[1] || 999999);
      return ai - bi;
    });
  const objFiles = files.filter((f) => String(f).toLowerCase().endsWith(".obj"));
  const targets = cmfFiles.length ? cmfFiles : objFiles;
  if (!targets.length) {
    setProceduralArenaVisible(true);
    setArenaStatus("Arena: procedural fallback (unsupported mesh format)");
    return;
  }

  const group = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({
    color: 0x9dc4e8,
    emissive: 0x163550,
    metalness: 0.08,
    roughness: 0.56,
    transparent: true,
    opacity: 0.4,
    side: THREE.DoubleSide,
  });

  let parsedOk = 0;
  let parsedFail = 0;
  for (const rel of targets) {
    try {
      const res = await fetch(`/collision_meshes/${encodeURI(rel)}`);
      if (!res.ok) continue;
      let mesh = null;
      if (String(rel).toLowerCase().endsWith(".cmf")) {
        const buf = await res.arrayBuffer();
        mesh = parseCmfToMesh(buf, mat);
      } else {
        const txt = await res.text();
        mesh = parseObjToMesh(txt, mat);
      }
      if (mesh) {
        group.add(mesh);
        parsedOk += 1;
      } else {
        parsedFail += 1;
      }
    } catch {
      // Continue loading other meshes.
      parsedFail += 1;
    }
  }

  if (!group.children.length) {
    mat.dispose();
    setProceduralArenaVisible(true);
    setArenaStatus("Arena: procedural fallback (mesh parse failed)");
    return;
  }
  arenaMeshGroup = group;
  setProceduralArenaVisible(false);
  scene.add(arenaMeshGroup);
  const folder = payload?.data?.folder || "unknown";
  setArenaStatus(`Arena: CMF (${folder}, ${parsedOk}/${targets.length} meshes)`);
  console.log(`[arena] using folder=${folder} files=${targets.length} loaded=${parsedOk} failed=${parsedFail}`);
}

function createCarMesh(color) {
  const group = new THREE.Group();
  group.rotation.order = "YXZ";

  const body = new THREE.Mesh(
    new THREE.BoxGeometry(122, 36, 84),
    new THREE.MeshStandardMaterial({ color, metalness: 0.18, roughness: 0.44 })
  );
  body.position.y = 26;
  body.castShadow = true;
  group.add(body);

  const cabin = new THREE.Mesh(
    new THREE.BoxGeometry(62, 22, 68),
    new THREE.MeshStandardMaterial({ color: 0xd9e4f5, metalness: 0.05, roughness: 0.22, transparent: true, opacity: 0.85 })
  );
  cabin.position.set(-10, 46, 0);
  cabin.castShadow = true;
  group.add(cabin);

  const nose = new THREE.Mesh(
    new THREE.ConeGeometry(16, 18, 16),
    new THREE.MeshStandardMaterial({ color, metalness: 0.18, roughness: 0.45 })
  );
  nose.rotation.z = -Math.PI / 2;
  nose.position.set(64, 26, 0);
  group.add(nose);

  const wheelGeo = new THREE.CylinderGeometry(13, 13, 10, 14);
  const wheelMat = new THREE.MeshStandardMaterial({ color: 0x171717, roughness: 0.95 });
  const wheelOffsets = [
    [44, 13, 34],
    [44, 13, -34],
    [-38, 13, 34],
    [-38, 13, -34],
  ];
  for (const [x, y, z] of wheelOffsets) {
    const w = new THREE.Mesh(wheelGeo, wheelMat);
    w.rotation.z = Math.PI / 2;
    w.position.set(x, y, z);
    w.castShadow = true;
    group.add(w);
  }

  group.userData.yaw = 0;
  group.userData.pitch = 0;
  group.userData.roll = 0;
  group.userData.vel = new THREE.Vector3();
  group.userData.spinPitchVel = 0;
  group.userData.spinRollVel = 0;
  group.userData.prevJump = 0;
  group.userData.prevDoubleJump = 0;
  return group;
}

function createNameTag(player) {
  const el = document.createElement("div");
  el.className = "name-tag";
  el.textContent = `${player} | boost 0`;
  labelLayer.appendChild(el);
  return el;
}

function initScene() {
  AXIS_RL_TO_SCENE = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);
  AXIS_SCENE_TO_RL = AXIS_RL_TO_SCENE.clone().invert();

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x182f4a);
  scene.fog = new THREE.Fog(0x182f4a, 8000, 32000);

  camera = new THREE.PerspectiveCamera(55, sceneEl.clientWidth / sceneEl.clientHeight, 10, 100000);
  camera.position.set(-2600, 2200, 4600);
  camera.lookAt(0, 0, 0);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(sceneEl.clientWidth, sceneEl.clientHeight);
  renderer.setPixelRatio(1.0);
  renderer.shadowMap.enabled = false;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;

  sceneEl.innerHTML = "";
  sceneEl.appendChild(renderer.domElement);
  renderer.domElement.style.touchAction = "none";

  renderer.domElement.addEventListener("pointerdown", (ev) => {
    const inReview = reviewOrbitEnabled && !playing;
    if (!inReview) return;
    reviewOrbitDragging = true;
    reviewOrbitLastX = Number(ev.clientX || 0);
    reviewOrbitLastY = Number(ev.clientY || 0);
    renderer.domElement.setPointerCapture?.(ev.pointerId);
    ev.preventDefault();
  });

  renderer.domElement.addEventListener("pointermove", (ev) => {
    if (!reviewOrbitDragging) return;
    const x = Number(ev.clientX || 0);
    const y = Number(ev.clientY || 0);
    const dx = x - reviewOrbitLastX;
    const dy = y - reviewOrbitLastY;
    reviewOrbitLastX = x;
    reviewOrbitLastY = y;
    reviewOrbitYaw -= dx * 0.0055;
    reviewOrbitPitch = clamp(reviewOrbitPitch - dy * 0.0045, -0.7, 0.75);
    needsRender = true;
    ev.preventDefault();
  });

  const stopOrbitDrag = (ev) => {
    if (!reviewOrbitDragging) return;
    reviewOrbitDragging = false;
    renderer.domElement.releasePointerCapture?.(ev.pointerId);
  };
  renderer.domElement.addEventListener("pointerup", stopOrbitDrag);
  renderer.domElement.addEventListener("pointercancel", stopOrbitDrag);

  scene.add(new THREE.HemisphereLight(0xcce1ff, 0x18242e, 0.75));

  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(-3000, 6000, 2500);
  key.castShadow = false;
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xa5d1ff, 0.33);
  fill.position.set(2800, 1800, -2400);
  scene.add(fill);

  const beforeArena = new Set(scene.children);
  createArena();
  proceduralArenaObjects = scene.children.filter((obj) => !beforeArena.has(obj));
  createMapOverlay();
  setArenaStatus("Arena: procedural fallback");

  ballMesh = new THREE.Mesh(
    new THREE.SphereGeometry(95, 28, 28),
    new THREE.MeshStandardMaterial({ color: 0xf7b500, metalness: 0.32, roughness: 0.3 })
  );
  ballMesh.castShadow = true;
  scene.add(ballMesh);

  window.addEventListener("resize", () => {
    const w = sceneEl.clientWidth;
    const h = sceneEl.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    needsRender = true;
  });
}

function clearScenePlayers() {
  for (const obj of carObjects.values()) {
    scene.remove(obj.mesh);
  }
  carObjects.clear();
  for (const el of nameTags.values()) {
    el.remove();
  }
  nameTags.clear();
}

function buildScenePlayers(players) {
  clearScenePlayers();
  const teamMap = replayData?.replay_meta?.player_teams || {};
  const teamByNorm = new Map();
  for (const [name, team] of Object.entries(teamMap)) {
    teamByNorm.set(normalizePlayerKey(name), Number(team));
  }
  players.forEach((player, idx) => {
    const team = teamByNorm.has(normalizePlayerKey(player))
      ? teamByNorm.get(normalizePlayerKey(player))
      : Number(teamMap[player]);
    let color = 0xc9d6e6;
    if (team === 0) color = 0x49a8ff;
    else if (team === 1) color = 0xff8a5b;
    const mesh = createCarMesh(color);
    scene.add(mesh);
    carObjects.set(player, { mesh, lastPos: null, lastRawPos: null, lastReplayT: null, renderPos: null });
    nameTags.set(player, createNameTag(player));
  });
}

function updateTagStyles() {
  for (const [name, el] of nameTags.entries()) {
    el.classList.toggle("selected", name === selectedPlayer);
  }
}

function getMetricAtFrame(frameIdx) {
  if (liveMetricPoint) return liveMetricPoint;
  if (!replayData || !replayData.metrics_timeline || !replayData.metrics_timeline.length) return null;
  return replayData.metrics_timeline[Math.max(0, Math.min(frameIdx, replayData.metrics_timeline.length - 1))];
}

function findFrameIndexAtOrBeforeTime(targetT) {
  if (!replayData || !replayData.timeline || replayData.timeline.length === 0) return 0;
  const arr = replayData.timeline;
  if (targetT <= arr[0].t) return 0;
  if (targetT >= arr[arr.length - 1].t) return arr.length - 1;

  // Fast path: local scan from previous index during normal playback.
  let idx = Math.max(0, Math.min(lastFrameLookupIdx, arr.length - 1));
  if (arr[idx].t <= targetT) {
    while (idx + 1 < arr.length && arr[idx + 1].t <= targetT) idx += 1;
    lastFrameLookupIdx = idx;
    return idx;
  }
  while (idx > 0 && arr[idx].t > targetT) idx -= 1;
  if (arr[idx].t <= targetT) {
    lastFrameLookupIdx = idx;
    return idx;
  }

  let lo = 0;
  let hi = arr.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const mt = arr[mid].t;
    if (mt === targetT) return mid;
    if (mt < targetT) lo = mid + 1;
    else hi = mid - 1;
  }
  lastFrameLookupIdx = Math.max(0, hi);
  return lastFrameLookupIdx;
}

function interpolate(a, b, t) {
  return a + (b - a) * t;
}

function hermite(p0, v0, p1, v1, t, dt) {
  const tt = t * t;
  const ttt = tt * t;
  const h00 = 2 * ttt - 3 * tt + 1;
  const h10 = ttt - 2 * tt + t;
  const h01 = -2 * ttt + 3 * tt;
  const h11 = ttt - tt;
  return h00 * p0 + h10 * v0 * dt + h01 * p1 + h11 * v1 * dt;
}

function interpPosWithVelocity(p0, p1, v0, v1, alpha, dt) {
  return hermite(p0, v0, p1, v1, alpha, dt);
}

function interpCarPosition(p0, p1, alpha) {
  const dx = Number(p1.x || 0) - Number(p0.x || 0);
  const dy = Number(p1.y || 0) - Number(p0.y || 0);
  const dz = Number(p1.z || 0) - Number(p0.z || 0);
  const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
  if (dist > TELEPORT_DIST_THRESHOLD) {
    return {
      x: Number(p1.x || 0),
      y: Number(p1.y || 0),
      z: Number(p1.z || 0),
    };
  }
  return {
    x: interpolate(Number(p0.x || 0), Number(p1.x || 0), alpha),
    y: interpolate(Number(p0.y || 0), Number(p1.y || 0), alpha),
    z: interpolate(Number(p0.z || 0), Number(p1.z || 0), alpha),
  };
}

function getInterpolatedFrame(t) {
  const idx = findFrameIndexAtOrBeforeTime(t);
  const f0 = replayData.timeline[idx];
  const nidx = Math.min(idx + 1, replayData.timeline.length - 1);
  const f1 = replayData.timeline[nidx];
  const dt = Math.max(1e-6, f1.t - f0.t);
  const alpha = clamp((t - f0.t) / dt, 0, 1);

  const players = replayData.players.map((name) => {
    const idxByName = playerIdxMap.get(name) ?? 0;
    const p0 = (f0.players && f0.players[idxByName]) ? f0.players[idxByName] : (f0.players || []).find((p) => p.name === name) || { name };
    const p1 = (f1.players && f1.players[idxByName]) ? f1.players[idxByName] : (f1.players || []).find((p) => p.name === name) || p0;
    const vx0 = Number.isFinite(p0.vx) ? p0.vx : 0;
    const vy0 = Number.isFinite(p0.vy) ? p0.vy : 0;
    const vz0 = Number.isFinite(p0.vz) ? p0.vz : 0;
    const vx1 = Number.isFinite(p1.vx) ? p1.vx : vx0;
    const vy1 = Number.isFinite(p1.vy) ? p1.vy : vy0;
    const vz1 = Number.isFinite(p1.vz) ? p1.vz : vz0;
    const pos = interpCarPosition(p0, p1, alpha);
    return {
      name,
      x: pos.x,
      y: pos.y,
      z: pos.z,
      boost: interpolate(p0.boost ?? 0, p1.boost ?? 0, alpha),
      steer: interpolate(p0.steer ?? 0, p1.steer ?? 0, alpha),
      throttle: interpolate(p0.throttle ?? 0, p1.throttle ?? 0, alpha),
      handbrake: Math.round(interpolate(p0.handbrake ?? 0, p1.handbrake ?? 0, alpha)),
      jump: Math.round(interpolate(p0.jump ?? 0, p1.jump ?? 0, alpha)),
      double_jump: Math.round(interpolate(p0.double_jump ?? 0, p1.double_jump ?? 0, alpha)),
      qx0: Number.isFinite(p0.qx) ? p0.qx : 0,
      qy0: Number.isFinite(p0.qy) ? p0.qy : 0,
      qz0: Number.isFinite(p0.qz) ? p0.qz : 0,
      qw0: Number.isFinite(p0.qw) ? p0.qw : 1,
      qx1: Number.isFinite(p1.qx) ? p1.qx : (Number.isFinite(p0.qx) ? p0.qx : 0),
      qy1: Number.isFinite(p1.qy) ? p1.qy : (Number.isFinite(p0.qy) ? p0.qy : 0),
      qz1: Number.isFinite(p1.qz) ? p1.qz : (Number.isFinite(p0.qz) ? p0.qz : 0),
      qw1: Number.isFinite(p1.qw) ? p1.qw : (Number.isFinite(p0.qw) ? p0.qw : 1),
      yaw: lerpAngle(Number(p0.yaw || 0), Number(p1.yaw || p0.yaw || 0), alpha),
      vx: interpolate(vx0, vx1, alpha),
      vy: interpolate(vy0, vy1, alpha),
      vz: interpolate(vz0, vz1, alpha),
    };
  });

  const bvx0 = Number.isFinite(f0.ball.vx) ? f0.ball.vx : 0;
  const bvy0 = Number.isFinite(f0.ball.vy) ? f0.ball.vy : 0;
  const bvz0 = Number.isFinite(f0.ball.vz) ? f0.ball.vz : 0;
  const bvx1 = Number.isFinite(f1.ball.vx) ? f1.ball.vx : bvx0;
  const bvy1 = Number.isFinite(f1.ball.vy) ? f1.ball.vy : bvy0;
  const bvz1 = Number.isFinite(f1.ball.vz) ? f1.ball.vz : bvz0;
  return {
    idx,
    t,
    ball: {
      x: interpPosWithVelocity(f0.ball.x, f1.ball.x, bvx0, bvx1, alpha, dt),
      y: interpPosWithVelocity(f0.ball.y, f1.ball.y, bvy0, bvy1, alpha, dt),
      z: interpPosWithVelocity(f0.ball.z, f1.ball.z, bvz0, bvz1, alpha, dt),
      qx0: Number.isFinite(f0.ball.qx) ? f0.ball.qx : 0,
      qy0: Number.isFinite(f0.ball.qy) ? f0.ball.qy : 0,
      qz0: Number.isFinite(f0.ball.qz) ? f0.ball.qz : 0,
      qw0: Number.isFinite(f0.ball.qw) ? f0.ball.qw : 1,
      qx1: Number.isFinite(f1.ball.qx) ? f1.ball.qx : (Number.isFinite(f0.ball.qx) ? f0.ball.qx : 0),
      qy1: Number.isFinite(f1.ball.qy) ? f1.ball.qy : (Number.isFinite(f0.ball.qy) ? f0.ball.qy : 0),
      qz1: Number.isFinite(f1.ball.qz) ? f1.ball.qz : (Number.isFinite(f0.ball.qz) ? f0.ball.qz : 0),
      qw1: Number.isFinite(f1.ball.qw) ? f1.ball.qw : (Number.isFinite(f0.ball.qw) ? f0.ball.qw : 1),
      vx: interpolate(bvx0, bvx1, alpha),
      vy: interpolate(bvy0, bvy1, alpha),
      vz: interpolate(bvz0, bvz1, alpha),
    },
    players,
    alpha,
  };
}

function updateCamera(interpFrame, dtS) {
  const zoom = 1 / zoomScale;
  const fallback = interpFrame.players[0];
  const fp = interpFrame.players.find((p) => p.name === selectedPlayer) || fallback;
  if (!fp) return;

  const carPos = rlToScene(fp);
  const q = slerpedSceneQuat(fp.qx0, fp.qy0, fp.qz0, fp.qw0, fp.qx1, fp.qy1, fp.qz1, fp.qw1, interpFrame.alpha);
  const forward = new THREE.Vector3(1, 0, 0).applyQuaternion(q);
  forward.y = 0;
  if (forward.lengthSq() < 1e-6) {
    forward.set(1, 0, 0);
  } else {
    forward.normalize();
  }
  const speed = Math.sqrt((fp.vx || 0) * (fp.vx || 0) + (fp.vy || 0) * (fp.vy || 0));
  const ballPos = rlToScene(interpFrame.ball);
  const dirTarget = speed < 120 ? camAnchorForward.clone() : forward;
  const dirSmooth = 1 - Math.exp(-10.0 * Math.max(0.0, dtS || (1 / 60)));
  camAnchorForward.lerp(dirTarget, dirSmooth).normalize();
  const up = new THREE.Vector3(0, 1, 0);

  const chaseDistance = 1050 * zoom;
  const chaseHeight = 460 * zoom;
  const desiredPos = carPos
    .clone()
    .addScaledVector(camAnchorForward, -chaseDistance)
    .addScaledVector(up, chaseHeight);

  desiredPos.y = clamp(desiredPos.y, 320, 1800);

  const playerFocus = carPos
    .clone()
    .addScaledVector(camAnchorForward, 340)
    .addScaledVector(up, 140);
  const ballFocus = ballPos.clone().addScaledVector(up, 130);

  const carBallDist = carPos.distanceTo(ballPos);
  const nowT = Number(currentReplayTimeS || 0);
  if (carBallDist <= 260 && (nowT - lastBallTouchDetectT) >= 0.24) {
    lastBallTouchDetectT = nowT;
    recentBallTouchUntilT = nowT + 1.6;
  }

  let lookTarget = playerFocus.clone();
  const keepBallInFrame = nowT <= recentBallTouchUntilT;
  if (keepBallInFrame) {
    lookTarget.lerp(ballFocus, 0.58);
  }

  const dt = Math.min(0.05, Math.max(1 / 240, dtS || (1 / 60)));
  const stiff = 70.0;
  const damp = 16.0;
  let cameraPosTarget = desiredPos.clone();
  if (reviewOrbitEnabled && !playing) {
    const offset = desiredPos.clone().sub(carPos);
    const yawQ = new THREE.Quaternion().setFromAxisAngle(up, reviewOrbitYaw);
    offset.applyQuaternion(yawQ);
    const offNorm = offset.clone().normalize();
    const rightAxis = new THREE.Vector3().crossVectors(up, offNorm).normalize();
    if (rightAxis.lengthSq() > 1e-6) {
      const pitchQ = new THREE.Quaternion().setFromAxisAngle(rightAxis, reviewOrbitPitch);
      offset.applyQuaternion(pitchQ);
    }
    cameraPosTarget = carPos.clone().add(offset);
    lookTarget = keepBallInFrame
      ? carPos.clone().addScaledVector(up, 130).lerp(ballFocus, 0.52)
      : carPos.clone().addScaledVector(up, 125);
  }

  if (!camAnchorPos) camAnchorPos = cameraPosTarget.clone();
  dampedSpringStep(camAnchorPos, camPosVel, cameraPosTarget, stiff, damp, dt);
  camera.position.copy(camAnchorPos);
  camera.up.set(0, 1, 0);
  if (!camLook) camLook = lookTarget.clone();
  dampedSpringStep(camLook, camLookVel, lookTarget, 90.0, 18.0, dt);
  if (Math.abs(camera.fov - 55) > 0.05) {
    camera.fov += (55 - camera.fov) * (1 - Math.exp(-8.0 * dt));
    camera.updateProjectionMatrix();
  }
  camera.lookAt(camLook);
  if (keepBallInFrame) {
    camera.updateMatrixWorld();
    const ballNdc = ballPos.clone().project(camera);
    if (Math.abs(ballNdc.x) > 0.84 || Math.abs(ballNdc.y) > 0.82) {
      const corrected = camLook.clone().lerp(ballFocus, 0.7);
      dampedSpringStep(camLook, camLookVel, corrected, 98.0, 20.0, dt);
      camera.lookAt(camLook);
    }
  }
}

function updateNameTags(interpFrame) {
  const now = performance.now();
  if (now - lastTagRefreshMs < tagRefreshMs) return;
  lastTagRefreshMs = now;

  const rect = sceneEl.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;

  for (const p of interpFrame.players) {
    const el = nameTags.get(p.name);
    const entry = carObjects.get(p.name);
    if (!el || !entry) continue;
    if (isPlayerDemoHidden(p.name, currentReplayTimeS)) {
      el.style.display = "none";
      continue;
    }

    const screenPos = entry.mesh.position.clone().add(new THREE.Vector3(0, 120, 0));
    screenPos.project(camera);

    const sx = (screenPos.x * 0.5 + 0.5) * w;
    const sy = (-screenPos.y * 0.5 + 0.5) * h;
    const inDepth = screenPos.z < 1 && screenPos.z > -1;
    const inBounds = sx >= 0 && sx <= w && sy >= 0 && sy <= h;
    const visible = inDepth && inBounds;

    el.style.display = visible ? "block" : "none";
    if (!visible) continue;

    const dist = camera.position.distanceTo(entry.mesh.position);
    const scale = clamp(1.45 - dist / 8500, 0.82, 1.25);
    const opacity = clamp(1.3 - dist / 13000, 0.35, 1);
    const pad = 8;
    const sxClamped = clamp(sx, pad, Math.max(pad, w - pad));
    const syClamped = clamp(sy, pad, Math.max(pad, h - pad));

    el.style.left = `${sxClamped}px`;
    el.style.top = `${syClamped}px`;
    el.style.transform = `translate(-50%, -50%) scale(${scale})`;
    el.style.opacity = `${opacity}`;
    let boostVal = Number(p.boost || 0);
    if (!Number.isFinite(boostVal) || boostVal <= 0) {
      const metaBoost = boostAtTime(p.name, currentReplayTimeS);
      if (Number.isFinite(metaBoost)) boostVal = Number(metaBoost);
    }
    if (!Number.isFinite(boostVal) || boostVal <= 0) {
      const f = replayData?.timeline?.[currentFrame];
      if (f?.players) {
        const fp = f.players.find((x) => x.name === p.name);
        if (fp && Number.isFinite(Number(fp.boost))) boostVal = Number(fp.boost);
      }
    }
    el.textContent = `${p.name} | boost ${fmt(boostVal, 0)}`;
  }
}

function slerpedSceneQuat(qx0, qy0, qz0, qw0, qx1, qy1, qz1, qw1, alpha) {
  const q0 = rlQuatToSceneQuat(qx0, qy0, qz0, qw0);
  const q1 = rlQuatToSceneQuat(qx1, qy1, qz1, qw1);
  return q0.slerp(q1, alpha);
}

function buildEventList() {
  if (!eventsEl) {
    eventItems = [];
    activeEventIndex = -1;
    return;
  }
  eventsEl.innerHTML = "";
  eventItems = [];
  activeEventIndex = -1;
  if (!replayData || !replayData.events) return;
  for (const evt of replayData.events.slice(0, 60)) {
    const li = document.createElement("li");
    li.textContent = `[${fmt(evt.time, 2)}] ${evt.type || "event"} (${evt.reason || "n/a"})`;
    eventsEl.appendChild(li);
    eventItems.push({ t: Number(evt.time || 0), el: li });
  }
}

function updateEventsAtTime(t) {
  if (!eventItems.length) return;
  let bestIdx = -1;
  let bestDt = Infinity;
  for (let i = 0; i < eventItems.length; i++) {
    const dt = Math.abs(eventItems[i].t - t);
    if (dt < bestDt) {
      bestDt = dt;
      bestIdx = i;
    }
  }

  const idx = bestDt <= 0.45 ? bestIdx : -1;
  if (idx === activeEventIndex) return;
  if (activeEventIndex >= 0) eventItems[activeEventIndex]?.el.classList.remove("active");
  activeEventIndex = idx;
  if (activeEventIndex >= 0) eventItems[activeEventIndex]?.el.classList.add("active");
}

function renderAtTime(t) {
  if (!replayData || !replayData.timeline?.length) return;
  const interpFrame = getInterpolatedFrame(t);
  currentFrame = interpFrame.idx;
  currentReplayTimeS = interpFrame.t;

  const ballPos = rlToScene(interpFrame.ball);
  ballMesh.position.copy(ballPos);
  const ballQ = slerpedSceneQuat(
    interpFrame.ball.qx0, interpFrame.ball.qy0, interpFrame.ball.qz0, interpFrame.ball.qw0,
    interpFrame.ball.qx1, interpFrame.ball.qy1, interpFrame.ball.qz1, interpFrame.ball.qw1,
    interpFrame.alpha
  );
  ballMesh.quaternion.copy(ballQ);

  for (const p of interpFrame.players) {
    const entry = carObjects.get(p.name);
    if (!entry) continue;
    const hidden = isPlayerDemoHidden(p.name, currentReplayTimeS);
    entry.mesh.visible = !hidden;
    if (hidden) continue;
    const rawPos = rlToScene(p);
    entry.mesh.position.copy(rawPos).add(new THREE.Vector3(0, 18, 0));
    const q = slerpedSceneQuat(p.qx0, p.qy0, p.qz0, p.qw0, p.qx1, p.qy1, p.qz1, p.qw1, interpFrame.alpha);
    entry.mesh.quaternion.copy(q);
  }

  const nowMs = performance.now();
  const dtS = lastRenderWallTimeMs > 0 ? Math.max(0.0, (nowMs - lastRenderWallTimeMs) / 1000.0) : (1 / 60);
  lastRenderWallTimeMs = nowMs;
  updateCamera(interpFrame, dtS);
  updateNameTags(interpFrame);

  const m = metricsReady ? getMetricAtFrame(currentFrame) : null;
  if (m) {
    metricMeta.forEach(([key]) => {
      const el = document.getElementById(`val_${key}`);
      if (el) el.textContent = fmt(m[key], key === "hesitation_score" ? 3 : 2);
    });
    updateEventsAtTime(m.t);
    timeLabel.textContent = `t=${fmt(m.t, 2)} / ${fmt(replayEndTimeS, 2)}s`;
  } else {
    timeLabel.textContent = `t=${fmt(currentReplayTimeS, 2)} / ${fmt(replayEndTimeS, 2)}s`;
  }
  updateHud(currentReplayTimeS);
  updateNextEventInfoAtTime(currentReplayTimeS);

  timelineSlider.value = String(currentFrame);
  renderer.render(scene, camera);
  needsRender = false;
}

function rebuildCharts() {
  if (!SHOW_REPLAY_CHARTS) return;
  if (!metricsReady || !replayData || !replayData.metrics_timeline?.length) return;
  const current = getMetricAtFrame(currentFrame);
  const tNow = current ? current.t : undefined;
  const toSeries = (key) => {
    if (!metricSeriesCache[key]) {
      metricSeriesCache[key] = replayData.metrics_timeline.map((p) => ({ t: p.t, v: p[key] }));
    }
    return metricSeriesCache[key];
  };

  drawSeries("speedChart", toSeries("speed"), "#44d2ff", tNow);
  drawSeries("hesitationChart", toSeries("hesitation_percent"), "#ff7a5c", tNow);
  drawSeries("hesitationScoreChart", toSeries("hesitation_score"), "#ff5c96", tNow);
  drawSeries("boostChart", toSeries("boost_waste_percent"), "#f5d76e", tNow);
  drawSeries("supersonicChart", toSeries("supersonic_percent"), "#7bf1a8", tNow);
  drawSeries("pressureChart", toSeries("pressure_percent"), "#fcbf49", tNow);
  drawSeries("whiffRateChart", toSeries("whiff_rate_per_min"), "#f67280", tNow);
  drawSeries("approachChart", toSeries("approach_efficiency"), "#9d8df1", tNow);
  drawSeries("recoveryChart", toSeries("recovery_time_avg_s"), "#73d2de", tNow);
}

function animate(tsMs) {
  if (!Number.isFinite(tsMs)) tsMs = performance.now();
  if (!lastRafTsMs) lastRafTsMs = tsMs;
  const rafDtMs = Math.max(0.0, tsMs - lastRafTsMs);
  lastRafTsMs = tsMs;

  if (playing && isTimelineReady && replayData?.timeline?.length) {
    const nowMs = performance.now();
    const elapsedWallS = Math.max(0, (nowMs - playStartWallTimeMs) / 1000);
    const prevReplayT = Number(currentReplayTimeS || 0);
    let targetReplayT = playStartReplayTimeS + elapsedWallS * playbackSpeed;
    if (goalHoldUntilWallMs > nowMs) {
      targetReplayT = goalHoldReplayT;
    } else if (goalHoldUntilWallMs > 0) {
      goalHoldUntilWallMs = 0;
      targetReplayT = goalHoldResumeReplayT;
      playStartReplayTimeS = targetReplayT;
      playStartWallTimeMs = nowMs;
      playbackDriftMs = 0;
      statusText.textContent = "Kickoff reset.";
    }
    const targetFromJump = playToEventTargetS;
    if (playToEventTargetS !== null && Number.isFinite(playToEventTargetS) && targetReplayT >= playToEventTargetS) {
      targetReplayT = playToEventTargetS;
      playing = false;
      playToEventTargetS = null;
      const events = filteredMechanicEvents();
      const hit = events.find((ev) => Math.abs(Number(ev?.__aligned_t || ev?.time || 0) - Number(targetFromJump || 0)) <= 0.08);
      if (hit) {
        const key = `${String(hit?.mechanic_id || "")}|${fmt(Number(hit?.__aligned_t || hit?.time || 0), 3)}`;
        lastAutoPausedEventKey = key;
        openEventCoachPanel(hit).catch(() => {});
      }
    }
    if (targetReplayT >= replayEndTimeS) {
      targetReplayT = replayEndTimeS;
      playing = false;
      playToEventTargetS = null;
    }
    if (playing && playToEventTargetS === null && goalHoldUntilWallMs <= 0) {
      for (const w of goalPauseWindows) {
        if (w.start > (prevReplayT + 0.01) && w.start <= (targetReplayT + 0.01)) {
          targetReplayT = w.start;
          goalHoldReplayT = w.start;
          goalHoldResumeReplayT = Math.max(w.end, w.start);
          goalHoldUntilWallMs = nowMs + 3000.0;
          statusText.textContent = "Goal scored. Holding restart for 3s...";
          break;
        }
      }
    }
    if (playing && playToEventTargetS === null && goalHoldUntilWallMs <= 0) {
      const events = filteredMechanicEvents();
      let hit = null;
      for (const ev of events) {
        const et = Number(ev?.__aligned_t || ev?.time || 0);
        if (!Number.isFinite(et)) continue;
        if (et > (prevReplayT + 0.01) && et <= (targetReplayT + 0.01)) {
          hit = ev;
          break;
        }
      }
      if (hit) {
        const key = `${String(hit?.mechanic_id || "")}|${fmt(Number(hit?.__aligned_t || hit?.time || 0), 3)}`;
        if (key !== lastAutoPausedEventKey) {
          targetReplayT = Number(hit?.__aligned_t || hit?.time || targetReplayT);
          playing = false;
          playToEventTargetS = null;
          lastAutoPausedEventKey = key;
          openEventCoachPanel(hit).catch(() => {});
          statusText.textContent = `Paused at event: ${eventRatingText(hit)}`;
        }
      }
    }
    renderAtTime(targetReplayT);
    const replayElapsedS = currentReplayTimeS - playStartReplayTimeS;
    playbackDriftMs = (replayElapsedS - elapsedWallS * playbackSpeed) * 1000;

    const now = performance.now();
    if (metricsReady && now - lastChartDrawMs >= chartDrawIntervalMs) {
      rebuildCharts();
      lastChartDrawMs = now;
    }
  } else if (needsRender && isTimelineReady && replayData?.timeline?.length) {
    renderAtTime(currentReplayTimeS);
  }

  if (metricsReady && selectedPlayer && isTimelineReady) {
    const now = performance.now();
    if (now - lastMetricFetchWallMs >= METRIC_FETCH_INTERVAL_MS) {
      lastMetricFetchWallMs = now;
      fetchLiveMetricAtTime(currentReplayTimeS);
    }
  }

  fpsCounter += 1;
  fpsAccumMs += rafDtMs;
  if (fpsCounter >= 30) {
    const fps = fpsCounter / Math.max(1e-6, fpsAccumMs / 1000);
    currentFps = fps;
    if (perfStatus) perfStatus.textContent = `FPS: ${fps.toFixed(1)} | drift ${playbackDriftMs.toFixed(1)}ms`;
    // Keep >=30 FPS by reducing non-critical UI update cadence.
    if (fps < 30) {
      tagRefreshMs = 110;
      chartDrawIntervalMs = 340;
    } else if (fps < 40) {
      tagRefreshMs = 85;
      chartDrawIntervalMs = 260;
    } else {
      tagRefreshMs = 60;
      chartDrawIntervalMs = CHART_DRAW_INTERVAL_MS;
    }
    fpsCounter = 0;
    fpsAccumMs = 0;
  }

  if (debugOpen) {
    const now = performance.now();
    if (now - lastDebugUpdateMs >= 220) {
      lastDebugUpdateMs = now;
      updateDebugBubble();
    }
  }

  if (playing && camAnchorPos && replayData?.timeline?.length) {
    const fp = replayData.timeline[Math.max(0, Math.min(currentFrame, replayData.timeline.length - 1))]?.players?.find((p) => p.name === selectedPlayer);
    if (fp) {
      const cpos = rlToScene(fp);
      const dist = camera.position.distanceTo(cpos);
      if (dist > 8000) {
        camAnchorPos = null;
        camPosVel.set(0, 0, 0);
        camLook = null;
        camLookVel.set(0, 0, 0);
      }
    }
  }

  requestAnimationFrame(animate);
}

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  return res.json();
}

function ensureSceneInitialized() {
  if (sceneInitialized) return;
  if (typeof THREE === "undefined") {
    statusText.textContent = "3D renderer failed to load (THREE missing). Hard refresh and retry.";
    return;
  }
  initScene();
  setControlsEnabled(false);
  animate();
  sceneInitialized = true;
}

function setProfileUi(profile) {
  currentProfile = profile || null;
  if (!currentProfile || !currentProfile.username) {
    profileStatus.textContent = "Not logged in.";
    if (aliasesInput) aliasesInput.value = "";
    if (loginGate) loginGate.classList.remove("hidden");
    if (appShell) appShell.classList.add("hidden");
    setDrawerOpen(false);
    return;
  }
  profileStatus.textContent = `Logged in: ${currentProfile.username} | ${currentProfile.rank_tier} | ${currentProfile.platform}`;
  if (!String(usernameInput.value || "").trim()) usernameInput.value = String(currentProfile.username || "");
  if (aliasesInput) aliasesInput.value = Array.isArray(currentProfile.aliases) ? currentProfile.aliases.join(", ") : "";
  if (currentProfile.rank_tier) rankSelect.value = currentProfile.rank_tier;
  if (currentProfile.platform) platformSelect.value = currentProfile.platform;
  if (loginGate) loginGate.classList.add("hidden");
  if (appShell) appShell.classList.remove("hidden");
  setDrawerOpen(false);
  restoreBubbleStates();
  ensureSceneInitialized();
}

async function logoutProfile() {
  const res = await fetchJson("/api/profile/logout", { method: "POST" });
  if (!res?.ok) {
    statusText.textContent = `Logout failed: ${res?.error || "unknown error"}`;
    return;
  }
  setProfileUi(null);
  renderLibrary([]);
  renderRecommendations([]);
  renderMechanics(null);
  replayData = null;
  selectedPlayer = "";
  metricsReady = false;
  currentMechanics = null;
  clearMetricDisplay();
  if (timelineEvents) timelineEvents.innerHTML = "";
  setControlsEnabled(false);
  setDrawerOpen(false);
  statusText.textContent = "Logged out.";
}

function renderRecommendations(recs) {
  if (!recsList) return;
  recsList.innerHTML = "";
  const arr = Array.isArray(recs) ? recs : [];
  if (!arr.length) {
    const empty = document.createElement("div");
    empty.className = "library-item-meta";
    empty.textContent = "No recommendations yet. Label a few events and refresh.";
    recsList.appendChild(empty);
    return;
  }
  for (const r of arr) {
    const row = document.createElement("div");
    row.className = "library-item";
    const info = document.createElement("div");
    const score = Number(r?.score || 0).toFixed(2);
    const conf = Number(r?.confidence || 0).toFixed(2);
    const ev = (r?.evidence || []).slice(0, 2).join(" | ");
    info.innerHTML = `<div class="rec-item-title">${r?.title || r?.focus_id || "Focus"}</div>
      <div class="library-item-meta">Score ${score} | Confidence ${conf}</div>
      <div class="rec-item-evidence">${ev || "No evidence text yet."}</div>`;
    row.appendChild(info);
    recsList.appendChild(row);
  }
}

async function loadCurrentRecommendations() {
  if (!currentProfile || !currentProfile.id) {
    renderRecommendations([]);
    return;
  }
  const res = await fetchJson("/api/recommendations/current");
  if (!res?.ok) {
    renderRecommendations([]);
    return;
  }
  renderRecommendations(res?.data?.recommendations || []);
}

async function refreshRecommendations() {
  if (!currentProfile || !currentProfile.id) {
    renderRecommendations([]);
    return;
  }
  const res = await fetchJson("/api/recommendations/refresh", { method: "POST" });
  if (!res?.ok) {
    statusText.textContent = `Recommendation refresh failed: ${res?.error || "unknown error"}`;
    return;
  }
  renderRecommendations(res?.data?.recommendations || []);
}

function renderMechanics(payload) {
  if (!mechanicsList) return;
  mechanicsList.innerHTML = "";
  const data = payload || {};
  const grades = Array.isArray(data?.game_mechanics) ? data.game_mechanics : [];
  if (!grades.length) {
    const empty = document.createElement("div");
    empty.className = "library-item-meta";
    empty.textContent = "Run replay analysis to generate mechanic grades.";
    mechanicsList.appendChild(empty);
    return;
  }
  const overall = Number(data?.overall_mechanics_score || 0).toFixed(1);
  const head = document.createElement("div");
  head.className = "library-item-meta";
  head.textContent = `Overall mechanics score: ${overall}/100`;
  mechanicsList.appendChild(head);
  for (const g of grades) {
    const row = document.createElement("div");
    row.className = "library-item mech-grade-row";
    const score = Number(g?.score_0_100 || 0).toFixed(1);
    const conf = Number(g?.confidence_0_1 || 0).toFixed(2);
    row.innerHTML = `<div class="rec-item-title">${g?.title || g?.mechanic_id || "Mechanic"}</div>
      <div class="mech-grade-score">Score ${score}/100 | Confidence ${conf} | Events ${Number(g?.event_count || 0)}</div>`;
    mechanicsList.appendChild(row);
  }
}

async function loadCurrentMechanics() {
  const res = await fetchJson("/api/mechanics/current");
  if (!res?.ok) {
    renderMechanics(null);
    renderTimelineEventMarkers();
    return;
  }
  currentMechanics = res?.data || null;
  renderMechanics(currentMechanics);
  renderTimelineEventMarkers();
}

async function recomputeMechanics() {
  const res = await fetchJson("/api/mechanics/recompute", { method: "POST" });
  if (!res?.ok) {
    statusText.textContent = `Mechanic recompute failed: ${res?.error || "unknown error"}`;
    return;
  }
  currentMechanics = res?.data || null;
  renderMechanics(currentMechanics);
  renderTimelineEventMarkers();
}

function renderTimelineEventMarkers() {
  if (!timelineEvents) return;
  timelineEvents.innerHTML = "";
  const mechEvents = filteredMechanicEvents();
  if (!mechEvents.length) return;
  const t0 = Number(replayStartTimeS || 0);
  const t1 = Number(replayEndTimeS || 0);
  const span = Math.max(1e-6, t1 - t0);
  for (const e of mechEvents) {
    const t = Number(e?.__aligned_t || e?.time);
    if (!Number.isFinite(t)) continue;
    const leftPct = clamp(((t - t0) / span) * 100, 0, 100);
    const marker = document.createElement("div");
    const q = String(e?.quality_label || "neutral").toLowerCase();
    marker.className = `timeline-event-marker ${q === "good" || q === "bad" ? q : "neutral"}`;
    marker.style.left = `${leftPct}%`;
    const shortLabel = String(e?.short || "MECH").slice(0, 6);
    const mid = String(e?.mechanic_id || "mechanic");
    const reason = String(e?.reason || "");
    marker.title = `${mid} @ ${fmt(t, 2)}s${reason ? ` | ${reason}` : ""}`;
    marker.innerHTML = `<div class="timeline-event-line"></div><div class="timeline-event-label">${shortLabel}</div>`;
    timelineEvents.appendChild(marker);
  }
  updateNextEventInfoAtTime(currentReplayTimeS);
}

async function loadCurrentProfile() {
  const res = await fetchJson("/api/profile/current");
  if (!res?.ok) {
    setProfileUi(null);
    return;
  }
  setProfileUi(res.profile || null);
}

async function loginProfile() {
  const username = String(usernameInput?.value || "").trim();
  const aliasesRaw = String(aliasesInput?.value || "");
  const aliases = aliasesRaw
    .split(",")
    .map((s) => String(s || "").trim())
    .filter((s) => s.length > 0);
  const rank_tier = String(rankSelect?.value || "bronze_1");
  const platform = String(platformSelect?.value || "epic");
  if (!username) {
    statusText.textContent = "Enter a username first.";
    return;
  }
  const res = await fetchJson("/api/profile/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, rank_tier, platform, aliases }),
  });
  if (!res?.ok) {
    statusText.textContent = `Login failed: ${res?.error || "unknown error"}`;
    return;
  }
  setProfileUi(res.profile || null);
  statusText.textContent = `Welcome, ${username}.`;
  await loadCurrentRecommendations();
}

function renderLibrary(sessions) {
  if (!libraryList) return;
  libraryList.innerHTML = "";
  if (!sessions?.length) {
    const empty = document.createElement("div");
    empty.className = "library-item-meta";
    empty.textContent = "No saved replays yet.";
    libraryList.appendChild(empty);
    return;
  }
  for (const s of sessions) {
    const row = document.createElement("div");
    row.className = "library-item";
    const info = document.createElement("div");
    info.innerHTML = `<div>${s.replay_name || s.session_id}</div><div class="library-item-meta">${s.source_type || "replay"} | ${s.map_name || "soccar"} | ${(Number(s.duration_s || 0)).toFixed(1)}s</div>`;
    const btn = document.createElement("button");
    btn.textContent = "Open";
    btn.addEventListener("click", async () => {
      const res = await fetchJson("/api/replay/open_saved", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: s.session_id }),
      });
      if (!res?.ok) {
        statusText.textContent = `Open saved replay failed: ${res?.error || "unknown error"}`;
        return;
      }
      const ok = await pollStatusUntilReady();
      if (!ok) return;
      await loadReplaySession();
      statusText.textContent = "Saved replay opened.";
    });
    row.appendChild(info);
    row.appendChild(btn);
    libraryList.appendChild(row);
  }
}

async function loadLibrary() {
  if (!currentProfile || !currentProfile.id) {
    renderLibrary([]);
    return;
  }
  const res = await fetchJson("/api/replay/library");
  if (!res?.ok) {
    statusText.textContent = `Library load failed: ${res?.error || "unknown error"}`;
    return;
  }
  const data = res?.data || {};
  const cleanup = Number(data?.cleanup?.duplicate_names_removed || 0);
  if (cleanup > 0) {
    showToast(`Removed ${cleanup} duplicate replay name${cleanup === 1 ? "" : "s"} from your library.`);
  }
  lastLibrarySessions = data?.sessions || [];
  renderLibrary(lastLibrarySessions);
}

async function ensureLegacyMetricsForPlayer(player) {
  if (!player || fallbackMetricsInFlight) return;
  fallbackMetricsInFlight = true;
  try {
    await fetchJson("/api/replay/player_metrics/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player }),
    });
    const deadline = performance.now() + 30000;
    while (performance.now() < deadline) {
      const st = await fetchJson(`/api/replay/player_metrics/status?player=${encodeURIComponent(player)}`);
      if (!st?.ok) throw new Error(st?.error || "metric status failed");
      const s = st?.data?.status;
      if (s === "ready") break;
      if (s === "error") throw new Error(st?.data?.error || "metric computation failed");
      await new Promise((r) => setTimeout(r, 250));
    }
    const dataRes = await fetchJson(`/api/replay/player_metrics/data?player=${encodeURIComponent(player)}`);
    if (!dataRes?.ok) throw new Error(dataRes?.error || "metric data failed");
    replayData.metrics_timeline = dataRes.data?.metrics_timeline || [];
    replayData.events = dataRes.data?.events || [];
    liveMetricPoint = null;
    metricsReady = true;
    buildEventList();
    rebuildCharts();
  } finally {
    fallbackMetricsInFlight = false;
  }
}

async function fetchLiveMetricAtTime(t) {
  if (!selectedPlayer || metricRequestInFlight || !liveSeekSupported) return;
  if (!replayData || !replayData.timeline?.length) return;
  metricRequestInFlight = true;
  const token = metricPollToken;
  try {
    const payload = await fetchJson("/api/replay/metrics/seek", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player: selectedPlayer, t }),
    });
    if (token !== metricPollToken) return;
    if (!payload.ok) {
      liveSeekFailureCount += 1;
      if (liveSeekFailureCount >= 3) {
        liveSeekSupported = false;
        statusText.textContent = `Live metric seek unavailable, falling back to cached metrics for ${selectedPlayer}...`;
        ensureLegacyMetricsForPlayer(selectedPlayer).catch((err) => {
          statusText.textContent = `Metric load failed: ${err?.message || err}`;
        });
      } else {
        statusText.textContent = `Live metric seek failed: ${payload.error || "unknown error"}`;
      }
      return;
    }
    liveSeekFailureCount = 0;
    const data = payload.data || {};
    const point = data.metric_point || null;
    liveMetricPoint = point;
    replayData.events = data.events || replayData.events || [];
    if (point && Number.isFinite(Number(point.t))) {
      const arr = replayData.metrics_timeline || [];
      const last = arr.length ? arr[arr.length - 1] : null;
      if (!last || Number(point.t) > Number(last.t) + 1e-6) {
        arr.push(point);
      }
      replayData.metrics_timeline = arr;
    }
    buildEventList();
  } catch (err) {
    liveSeekFailureCount += 1;
    if (liveSeekFailureCount >= 3) {
      liveSeekSupported = false;
      statusText.textContent = `Live metric seek unavailable, falling back to cached metrics for ${selectedPlayer}...`;
      ensureLegacyMetricsForPlayer(selectedPlayer).catch((e) => {
        statusText.textContent = `Metric load failed: ${e?.message || e}`;
      });
    } else {
      statusText.textContent = `Live metric seek failed: ${err?.message || err}`;
    }
  } finally {
    metricRequestInFlight = false;
  }
}

async function runAnalysisForSelectedPlayer(player) {
  if (!player) throw new Error("Choose a player first.");
  await fetchJson("/api/replay/analysis/select_player", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player }),
  });
  const run = await fetchJson("/api/replay/analysis/run", { method: "POST" });
  if (!run?.ok) throw new Error(run?.error || "Analysis failed.");
  analysisLocked = true;
  playerSelect.disabled = true;
}

async function pollStatusUntilReady() {
  while (true) {
    const status = await fetchJson("/api/replay/status");
    setProgress(status.progress || 0, status.message || "");
    statusText.textContent = status.error ? `Error: ${status.error}` : status.message;
    if (status.status === "ready") return true;
    if (status.status === "error") return false;
    await new Promise((r) => setTimeout(r, 600));
  }
}

async function loadPlayers() {
  // Kept for compatibility; player list is built from replay session metadata.
  return;
}

function populatePlayerSelect() {
  if (!replayData) return;
  const prev = playerSelect.value;
  const players = replayData.players || [];
  const teams = replayData?.replay_meta?.player_teams || {};
  const blue = [];
  const orange = [];
  const other = [];

  for (const p of players) {
    const t = Number(teams[p]);
    if (t === 0) blue.push(p);
    else if (t === 1) orange.push(p);
    else other.push(p);
  }

  const addGroup = (label, list) => {
    if (!list.length) return;
    const g = document.createElement("optgroup");
    g.label = label;
    for (const p of list) {
      const option = document.createElement("option");
      option.value = p;
      option.textContent = p;
      g.appendChild(option);
    }
    playerSelect.appendChild(g);
  };

  playerSelect.innerHTML = "";
  addGroup("Blue Team", blue);
  addGroup("Orange Team", orange);
  addGroup("Other", other);

  const all = [...blue, ...orange, ...other];
  if (all.length) {
    const preferred = replayData?.analysis_player || prev;
    playerSelect.value = all.includes(preferred) ? preferred : (all.includes(prev) ? prev : all[0]);
  }
}

async function loadReplaySession() {
  const payload = await fetchJson("/api/replay/session");
  if (!payload.ok) throw new Error(payload.error || "Failed to fetch replay session.");
  liveSeekSupported = false;
  liveSeekFailureCount = 0;

  const session = payload.data;
  replayData = {
    session_id: session.session_id,
    replay_name: session.replay_name,
    players: session.players || [],
    duration_s: session.duration_s || 0,
    timeline: session.timeline || [],
    boost_pads: session.boost_pads || [],
    replay_meta: session.replay_meta || {},
    metrics_timeline: [],
    events: [],
    analysis_player: session.analysis_player || "",
    analysis_ready: !!session.analysis_ready,
    analysis_locked: !!session.analysis_locked,
  };
  currentMechanics = null;
  analysisLocked = !!session.analysis_locked;

  replayStartTimeS = Number(replayData.timeline?.[0]?.t || 0);
  replayEndTimeS = Number(replayData.timeline?.[replayData.timeline.length - 1]?.t || 0);
  currentReplayTimeS = replayStartTimeS;
  lastAutoPausedEventKey = "";
  setCoachPanelOpen(false);
  lastFrameLookupIdx = 0;
  playerIdxMap = new Map();
  replayData.players.forEach((p, i) => playerIdxMap.set(p, i));
  buildScoreTimeline();
  buildClockSamples();
  buildGoalPauseWindows();
  buildDemoIntervals();
  buildBoostSampleLookup();
  populatePlayerSelect();
  selectedPlayer = replayData.analysis_player || "";
  if (selectedPlayer) playerSelect.value = selectedPlayer;
  playerSelect.disabled = analysisLocked;
  camAnchorPos = null;
  camAnchorForward.set(1, 0, 0);
  camPosVel.set(0, 0, 0);
  camLookVel.set(0, 0, 0);
  camLook = null;
  recentBallTouchUntilT = -1;
  lastBallTouchDetectT = -999;
  reviewOrbitEnabled = false;
  reviewOrbitYaw = 0;
  reviewOrbitPitch = 0;
  reviewOrbitDragging = false;
  goalHoldUntilWallMs = 0;
  goalHoldReplayT = 0;
  goalHoldResumeReplayT = 0;

  durationLabel.textContent = `Duration: ${fmt(replayEndTimeS - replayStartTimeS, 2)}s`;
  timelineSlider.max = String(Math.max(0, replayData.timeline.length - 1));

  buildScenePlayers(replayData.players);
  addBoostPads(replayData.boost_pads);
  await tryLoadArenaCollisionMeshes();
  updateTagStyles();
  setControlsEnabled(true);
  renderAtTime(currentReplayTimeS);
  lastChartDrawMs = 0;

  if (selectedPlayer) {
    statusText.textContent = `Running analysis for ${selectedPlayer}...`;
    await loadReplayDataForPlayer(selectedPlayer);
    statusText.textContent = `Replay ready for ${selectedPlayer}.`;
  } else {
    statusText.textContent = "Replay loaded, but your logged-in username was not found in this replay.";
  }
}

async function loadReplayDataForPlayer(player) {
  selectedPlayer = player;
  updateTagStyles();
  metricsReady = false;
  lastAutoPausedEventKey = "";
  setCoachPanelOpen(false);
  recentBallTouchUntilT = -1;
  lastBallTouchDetectT = -999;
  reviewOrbitEnabled = false;
  reviewOrbitYaw = 0;
  reviewOrbitPitch = 0;
  reviewOrbitDragging = false;
  goalHoldUntilWallMs = 0;
  goalHoldReplayT = 0;
  goalHoldResumeReplayT = 0;
  clearMetricDisplay();
  liveMetricPoint = null;
  replayData.metrics_timeline = [];
  replayData.events = [];
  currentMechanics = null;
  for (const key of Object.keys(metricSeriesCache)) delete metricSeriesCache[key];
  metricPollToken += 1;
  liveSeekFailureCount = 0;
  statusText.textContent = `Running future-aware analysis for ${player}...`;
  await runAnalysisForSelectedPlayer(player);
  const dataRes = await fetchJson(`/api/replay/player_metrics/data?player=${encodeURIComponent(player)}`);
  if (!dataRes?.ok) throw new Error(dataRes?.error || "metric data failed");
  replayData.metrics_timeline = dataRes.data?.metrics_timeline || [];
  replayData.events = dataRes.data?.events || [];
  metricsReady = true;
  liveMetricPoint = null;
  buildEventList();
  renderTimelineEventMarkers();
  rebuildCharts();
  await loadCurrentMechanics();
  needsRender = true;
}

async function uploadReplay() {
  if (!currentProfile || !currentProfile.id) {
    statusText.textContent = "Log in first to save and analyze replays.";
    return;
  }
  const file = replayFile.files?.[0];
  if (!file) {
    statusText.textContent = "Choose a .replay file first.";
    return;
  }

  playing = false;
  setControlsEnabled(false);
  metricsReady = false;
  clearMetricDisplay();

  const form = new FormData();
  form.append("file", file);

  setProgress(0.05, "Uploading replay...");
  statusText.textContent = "Uploading replay...";

  try {
    const res = await fetchJson("/api/replay/upload", { method: "POST", body: form });
    if (!res.ok) {
      statusText.textContent = `Upload failed: ${res.error || "unknown error"}`;
      showToast(res.error || "Upload failed.");
      return;
    }

    const ok = await pollStatusUntilReady();
    if (!ok) return;

    await loadReplaySession();
    if (replayData?.replay_meta?.boost_unresolved) {
      statusText.textContent = `${statusText.textContent} (boost unresolved in extracted CSV)`;
    }
  } catch (err) {
    statusText.textContent = `Replay load failed: ${err?.message || err}`;
    setControlsEnabled(false);
  }
}

uploadBtn.addEventListener("click", uploadReplay);

openReplayFolderBtn?.addEventListener("click", async () => {
  try {
    const res = await fetchJson("/api/replay/open_default_folder", { method: "POST" });
    if (!res?.ok) {
      statusText.textContent = `Open replay folder failed: ${res?.error || "unknown error"}`;
      return;
    }
    const p = String(res?.path || "");
    statusText.textContent = p ? `Opened replay folder: ${p}` : "Opened replay folder.";
  } catch (err) {
    statusText.textContent = `Open replay folder failed: ${err?.message || err}`;
  }
});

playBtn.addEventListener("click", () => {
  if (!replayData || !replayData.timeline?.length) {
    statusText.textContent = "Load replay data first.";
    return;
  }
  if (currentReplayTimeS >= replayEndTimeS - 1e-6) {
    currentReplayTimeS = replayStartTimeS;
    renderAtTime(currentReplayTimeS);
    rebuildCharts();
  }
  playing = true;
  playToEventTargetS = null;
  setCoachPanelOpen(false);
  recentBallTouchUntilT = -1;
  lastBallTouchDetectT = -999;
  reviewOrbitEnabled = false;
  reviewOrbitYaw = 0;
  reviewOrbitPitch = 0;
  reviewOrbitDragging = false;
  goalHoldUntilWallMs = 0;
  goalHoldReplayT = 0;
  goalHoldResumeReplayT = 0;
  playStartReplayTimeS = currentReplayTimeS;
  playStartWallTimeMs = performance.now();
  playbackDriftMs = 0;
  needsRender = true;
});

pauseBtn.addEventListener("click", () => {
  playing = false;
  playToEventTargetS = null;
  reviewOrbitDragging = false;
  goalHoldUntilWallMs = 0;
  goalHoldReplayT = 0;
  goalHoldResumeReplayT = 0;
  playbackDriftMs = 0;
  needsRender = true;
});

eventCoachClose?.addEventListener("click", () => {
  setCoachPanelOpen(false);
});

nextEventBtn?.addEventListener("click", () => {
  playToNextMechanicEvent();
});

prevEventBtn?.addEventListener("click", () => {
  playToPrevMechanicEvent();
});

speedSelect.addEventListener("change", () => {
  playbackSpeed = Number(speedSelect.value || 1);
  if (playing) {
    playStartReplayTimeS = currentReplayTimeS;
    playStartWallTimeMs = performance.now();
  }
  needsRender = true;
});

zoomRange.addEventListener("input", () => {
  zoomScale = Number(zoomRange.value || 1);
  needsRender = true;
});

timelineSlider.addEventListener("input", () => {
  currentFrame = Number(timelineSlider.value || 0);
  playing = false;
  playToEventTargetS = null;
  lastAutoPausedEventKey = "";
  reviewOrbitDragging = false;
  goalHoldUntilWallMs = 0;
  goalHoldReplayT = 0;
  goalHoldResumeReplayT = 0;
  if (replayData?.timeline?.length) {
    const frame = replayData.timeline[Math.max(0, Math.min(currentFrame, replayData.timeline.length - 1))];
    currentReplayTimeS = Number(frame?.t || replayStartTimeS);
    lastFrameLookupIdx = currentFrame;
    renderAtTime(currentReplayTimeS);
    rebuildCharts();
    needsRender = true;
  }
});

playerSelect.addEventListener("change", async () => {
  if (!playerSelect.value) return;
  if (analysisLocked) {
    statusText.textContent = `Analysis locked to ${selectedPlayer}. Upload replay again to analyze another player.`;
    playerSelect.value = selectedPlayer;
    return;
  }
  camAnchorPos = null;
  camAnchorForward.set(1, 0, 0);
  camPosVel.set(0, 0, 0);
  camLookVel.set(0, 0, 0);
  camLook = null;
  needsRender = true;
});

analyzePlayerBtn?.addEventListener("click", () => {});

loginBtn?.addEventListener("click", () => {
  loginProfile().catch((err) => {
    statusText.textContent = `Login failed: ${err?.message || err}`;
  });
});

logoutBtn?.addEventListener("click", () => {
  logoutProfile().catch((err) => {
    statusText.textContent = `Logout failed: ${err?.message || err}`;
  });
});

usernameInput?.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") {
    ev.preventDefault();
    loginBtn?.click();
  }
});

refreshLibraryBtn?.addEventListener("click", () => {
  loadLibrary().catch((err) => {
    statusText.textContent = `Library refresh failed: ${err?.message || err}`;
  });
});

openLibraryBtn?.addEventListener("click", () => {
  setDrawerOpen(true);
  loadLibrary().catch((err) => {
    statusText.textContent = `Library load failed: ${err?.message || err}`;
  });
});

closeLibraryBtn?.addEventListener("click", () => {
  setDrawerOpen(false);
});

libraryDrawer?.addEventListener("click", (ev) => {
  if (ev.target === libraryDrawer) setDrawerOpen(false);
});

recsBubbleToggle?.addEventListener("click", () => {
  const open = recsBubbleToggle.getAttribute("aria-expanded") !== "true";
  setBubbleOpen(recsBubbleToggle, recsBubbleBody, open, "bubble_recs_open");
});

mechanicsBubbleToggle?.addEventListener("click", () => {
  const open = mechanicsBubbleToggle.getAttribute("aria-expanded") !== "true";
  setBubbleOpen(mechanicsBubbleToggle, mechanicsBubbleBody, open, "bubble_mech_open");
});

timelineFilterMode?.addEventListener("change", () => {
  timelineEventMode = String(timelineFilterMode.value || "top10");
  try { localStorage.setItem("timeline_event_mode", timelineEventMode); } catch (_err) {}
  renderTimelineEventMarkers();
});

refreshRecsBtn?.addEventListener("click", () => {
  refreshRecommendations().catch((err) => {
    statusText.textContent = `Recommendation refresh failed: ${err?.message || err}`;
  });
});

refreshMechanicsBtn?.addEventListener("click", () => {
  recomputeMechanics().catch((err) => {
    statusText.textContent = `Mechanic recompute failed: ${err?.message || err}`;
  });
});

if (debugToggleBtn) {
  debugToggleBtn.addEventListener("click", () => {
    setDebugOpen(!debugOpen);
    updateDebugBubble();
  });
}
if (debugCloseBtn) {
  debugCloseBtn.addEventListener("click", () => setDebugOpen(false));
}
setDebugOpen(false);
restoreTimelineFilterMode();

document.addEventListener("keydown", (ev) => {
  const target = ev.target;
  const typingTarget =
    target &&
    (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
  if (typingTarget) return;
  if (ev.key === "Escape" && libraryDrawer && !libraryDrawer.classList.contains("hidden")) {
    setDrawerOpen(false);
    return;
  }
  if (ev.key === "]") {
    ev.preventDefault();
    playToNextMechanicEvent();
  } else if (ev.key === "[") {
    ev.preventDefault();
    playToPrevMechanicEvent();
  }
});

initMetricCards();

loadCurrentProfile()
  .then(() => loadCurrentRecommendations())
  .then(() => loadCurrentMechanics())
  .catch(() => {
    setProfileUi(null);
    renderLibrary([]);
    renderRecommendations([]);
    renderMechanics(null);
  });
