const statusEl = document.getElementById("status");
const scenarioSelect = document.getElementById("scenarioSelect");
const applyScenarioBtn = document.getElementById("applyScenario");
const activeScenarioEl = document.getElementById("activeScenario");
const activeSourceEl = document.getElementById("activeSource");
const spawnModeEl = document.getElementById("spawnMode");

const speedVal = document.getElementById("speedVal");
const hesitationVal = document.getElementById("hesitationVal");
const hesitationScoreVal = document.getElementById("hesitationScoreVal");
const boostWasteVal = document.getElementById("boostWasteVal");
const supersonicVal = document.getElementById("supersonicVal");
const usefulSupersonicVal = document.getElementById("usefulSupersonicVal");
const pressureVal = document.getElementById("pressureVal");
const whiffRateVal = document.getElementById("whiffRateVal");
const approachEffVal = document.getElementById("approachEffVal");
const recoveryAvgVal = document.getElementById("recoveryAvgVal");
const contestSuppressedVal = document.getElementById("contestSuppressedVal");
const clearMissContestVal = document.getElementById("clearMissContestVal");
const pressureGatedVal = document.getElementById("pressureGatedVal");
const eventsEl = document.getElementById("events");

const tabLiveBtn = document.getElementById("tabLive");
const tabReviewBtn = document.getElementById("tabReview");
const liveTab = document.getElementById("liveTab");
const reviewTab = document.getElementById("reviewTab");

const reviewSessionSelect = document.getElementById("reviewSessionSelect");
const reviewLoadBtn = document.getElementById("reviewLoadBtn");
const reviewLoadLatestBtn = document.getElementById("reviewLoadLatestBtn");
const reviewStatus = document.getElementById("reviewStatus");
const reviewPlayBtn = document.getElementById("reviewPlayBtn");
const reviewPauseBtn = document.getElementById("reviewPauseBtn");
const reviewTimeline = document.getElementById("reviewTimeline");
const reviewTime = document.getElementById("reviewTime");
const reviewClock = document.getElementById("reviewClock");
const reviewBlueScore = document.getElementById("reviewBlueScore");
const reviewOrangeScore = document.getElementById("reviewOrangeScore");
const reviewEventsEl = document.getElementById("reviewEvents");
const labelSummary = document.getElementById("labelSummary");
const markMissedWhiffBtn = document.getElementById("markMissedWhiffBtn");
const markMissedHesBtn = document.getElementById("markMissedHesBtn");
const reviewLabelLayer = document.getElementById("reviewLabelLayer");
const usernameInput = document.getElementById("usernameInput");
const aliasesInput = document.getElementById("aliasesInput");
const rankSelect = document.getElementById("rankSelect");
const platformSelect = document.getElementById("platformSelect");
const loginBtn = document.getElementById("loginBtn");
const profileStatus = document.getElementById("profileStatus");
const refreshRecsBtn = document.getElementById("refreshRecsBtn");
const recommendationsEl = document.getElementById("recommendations");
const refreshMechanicsBtn = document.getElementById("refreshMechanicsBtn");
const mechanicsEl = document.getElementById("mechanics");

let activeTab = "live";
let reviewLoaded = false;
let reviewPlaying = false;
let reviewStartWallMs = 0;
let reviewStartReplayT = 0;
let reviewCurrentT = 0;
let reviewDuration = 0;
let reviewEvents = [];
let reviewLabels = {};
let selectedEventId = "";
let selectedReviewPlayer = "";

let renderer = null;
let scene = null;
let camera = null;
let ballMesh = null;
let arenaMeshGroup = null;
let proceduralArenaGroup = null;
let boostPadGroup = null;
const nameTags = new Map();
let AXIS_RL_TO_SCENE = null;
let AXIS_SCENE_TO_RL = null;
let camAnchorPos = null;
const camAnchorForward = new THREE.Vector3(1, 0, 0);
const carMeshes = new Map();

let reviewData = null;
let currentProfile = null;

function fmtVal(v, digits = 2) {
  if (v === null || v === undefined) return "0";
  if (typeof v === "number") return v.toFixed(digits);
  return `${v}`;
}

function drawSeries(canvasId, series, color) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  if (!series || series.length < 2) return;

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
}

async function fetchJson(url, init = undefined) {
  const res = await fetch(url, init);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function setProfileUi(profile) {
  currentProfile = profile || null;
  if (!currentProfile || !currentProfile.username) {
    profileStatus.textContent = "Not logged in.";
    if (aliasesInput) aliasesInput.value = "";
    return;
  }
  profileStatus.textContent = `Logged in: ${currentProfile.username} | ${currentProfile.rank_tier} | ${currentProfile.platform}`;
  if (!String(usernameInput.value || "").trim()) usernameInput.value = String(currentProfile.username || "");
  if (aliasesInput) aliasesInput.value = Array.isArray(currentProfile.aliases) ? currentProfile.aliases.join(", ") : "";
  if (currentProfile.rank_tier) rankSelect.value = currentProfile.rank_tier;
  if (currentProfile.platform) platformSelect.value = currentProfile.platform;
}

async function loadCurrentProfile() {
  try {
    const res = await fetchJson("/api/profile/current");
    setProfileUi(res.profile || null);
  } catch (_err) {
    setProfileUi(null);
  }
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
    statusEl.textContent = "Enter a username first.";
    return;
  }
  const res = await fetchJson("/api/profile/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, rank_tier, platform, aliases }),
  });
  setProfileUi(res.profile || null);
  statusEl.textContent = `Welcome, ${username}.`;
}

function renderRecommendations(payload) {
  recommendationsEl.innerHTML = "";
  const recs = payload?.recommendations || [];
  if (!recs.length) {
    const li = document.createElement("li");
    li.className = "rec-item";
    li.textContent = "No recommendations yet. Refresh after a saved session.";
    recommendationsEl.appendChild(li);
    return;
  }
  for (const r of recs) {
    const li = document.createElement("li");
    li.className = "rec-item";
    const scenarios = (r.training?.scenarios || []).join(", ");
    const bot = (r.training?.bot_profiles || [])[0] || "";
    li.innerHTML = `<strong>${r.title || r.focus_id}</strong>
      <div class="rec-meta">score=${Number(r.score || 0).toFixed(2)} confidence=${Number(r.confidence || 0).toFixed(2)}</div>
      <div class="rec-meta">Scenarios: ${scenarios || "n/a"}</div>`;
    const btn = document.createElement("button");
    btn.textContent = "Start Drill";
    btn.addEventListener("click", async () => {
      try {
        const scenario_ids = r.training?.scenarios || [];
        await fetchJson("/api/training/queue_focus", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ focus_id: r.focus_id, bot_profile_id: bot, scenario_ids }),
        });
        statusEl.textContent = `Queued training drill for ${r.title || r.focus_id}.`;
      } catch (err) {
        statusEl.textContent = `Queue drill failed: ${err?.message || err}`;
      }
    });
    li.appendChild(btn);
    recommendationsEl.appendChild(li);
  }
}

async function refreshRecommendations() {
  const res = await fetchJson("/api/recommendations/refresh", { method: "POST" });
  renderRecommendations(res.data || {});
}

function renderMechanics(payload) {
  if (!mechanicsEl) return;
  mechanicsEl.innerHTML = "";
  const grades = Array.isArray(payload?.game_mechanics) ? payload.game_mechanics : [];
  if (!grades.length) {
    const li = document.createElement("li");
    li.className = "rec-item";
    li.textContent = "Load a review session to compute mechanic grades.";
    mechanicsEl.appendChild(li);
    return;
  }
  const overall = Number(payload?.overall_mechanics_score || 0).toFixed(1);
  const head = document.createElement("li");
  head.className = "rec-item";
  head.innerHTML = `<strong>Overall</strong><div class="rec-meta">${overall}/100</div>`;
  mechanicsEl.appendChild(head);
  for (const g of grades) {
    const li = document.createElement("li");
    li.className = "rec-item";
    li.innerHTML = `<strong>${g?.title || g?.mechanic_id || "Mechanic"}</strong>
      <div class="rec-meta">score=${Number(g?.score_0_100 || 0).toFixed(1)} conf=${Number(g?.confidence_0_1 || 0).toFixed(2)} events=${Number(g?.event_count || 0)}</div>`;
    mechanicsEl.appendChild(li);
  }
}

async function refreshMechanics() {
  const res = await fetchJson("/api/mechanics/recompute", { method: "POST" });
  renderMechanics(res.data || {});
}

async function loadMechanicsCurrent() {
  try {
    const res = await fetchJson("/api/mechanics/current");
    renderMechanics(res.data || {});
  } catch (_err) {
    renderMechanics(null);
  }
}

async function loadScenarios() {
  const data = await fetchJson("/api/scenarios");
  scenarioSelect.innerHTML = "";
  for (const scenario of data.scenarios || []) {
    const option = document.createElement("option");
    option.value = scenario.name;
    option.textContent = `${scenario.name} (${scenario.source})`;
    scenarioSelect.appendChild(option);
  }
}

async function applyScenario() {
  const name = scenarioSelect.value;
  if (!name) return;
  await fetchJson("/api/scenario/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

async function refreshCurrent() {
  const data = await fetchJson("/api/metrics/current");

  statusEl.textContent = "Connected";
  activeScenarioEl.textContent = `Active: ${data.active_scenario || "none"}`;
  activeSourceEl.textContent = `Source: ${data.active_source || "n/a"}`;
  spawnModeEl.textContent = `Spawn: ${data.spawn_mode || "n/a"}`;

  const m = data.current || {};
  speedVal.textContent = fmtVal(m.speed, 2);
  hesitationVal.textContent = fmtVal(m.hesitation_percent, 2);
  hesitationScoreVal.textContent = fmtVal(m.hesitation_score, 3);
  boostWasteVal.textContent = fmtVal(m.boost_waste_percent, 2);
  supersonicVal.textContent = fmtVal(m.supersonic_percent, 2);
  usefulSupersonicVal.textContent = fmtVal(m.useful_supersonic_percent, 2);
  pressureVal.textContent = fmtVal(m.pressure_percent, 2);
  whiffRateVal.textContent = fmtVal(m.whiff_rate_per_min, 2);
  approachEffVal.textContent = fmtVal(m.approach_efficiency, 2);
  recoveryAvgVal.textContent = fmtVal(m.recovery_time_avg_s, 3);
  contestSuppressedVal.textContent = fmtVal(m.contest_suppressed_whiffs, 0);
  clearMissContestVal.textContent = fmtVal(m.clear_miss_under_contest, 0);
  pressureGatedVal.textContent = fmtVal(m.pressure_gated_frames, 0);

  eventsEl.innerHTML = "";
  for (const evt of data.events || []) {
    const li = document.createElement("li");
    const reason = evt.reason ? `, reason=${evt.reason}` : "";
    const conf = evt.confidence !== undefined ? `, conf=${evt.confidence}` : "";
    li.textContent = `[${evt.time}] ${evt.type} (distance=${evt.distance}${reason}${conf})`;
    eventsEl.appendChild(li);
  }
}

async function refreshHistory() {
  const data = await fetchJson("/api/metrics/history");
  const h = data.history || {};

  drawSeries("speedChart", h.speed, "#4ec1ff");
  drawSeries("hesitationChart", h.hesitation_percent, "#ff7a5c");
  drawSeries("hesitationScoreChart", h.hesitation_score, "#ff5c96");
  drawSeries("boostChart", h.boost_waste_percent, "#f5d76e");
  drawSeries("supersonicChart", h.supersonic_percent, "#7bf1a8");
  drawSeries("pressureChart", h.pressure_percent, "#fcbf49");
  drawSeries("whiffRateChart", h.whiff_rate_per_min, "#f67280");
  drawSeries("approachChart", h.approach_efficiency, "#9d8df1");
  drawSeries("recoveryChart", h.recovery_time_avg_s, "#73d2de");
}

function setTab(tab) {
  activeTab = tab;
  const liveActive = tab === "live";
  liveTab.classList.toggle("hidden", !liveActive);
  reviewTab.classList.toggle("hidden", liveActive);
  tabLiveBtn.classList.toggle("active", liveActive);
  tabReviewBtn.classList.toggle("active", !liveActive);
  if (!liveActive && !reviewLoaded) {
    loadReviewSessions().catch((err) => {
      reviewStatus.textContent = `Review list failed: ${err?.message || err}`;
    });
  }
}

function rlToScene(pos) {
  return new THREE.Vector3(Number(pos.x || 0), Number(pos.z || 0), -Number(pos.y || 0));
}

function rlQuatToSceneQuat(qx, qy, qz, qw) {
  const q = new THREE.Quaternion(Number(qx || 0), Number(qy || 0), Number(qz || 0), Number(qw || 1));
  if (!AXIS_RL_TO_SCENE || !AXIS_SCENE_TO_RL) return q.normalize();
  q.premultiply(AXIS_RL_TO_SCENE);
  q.multiply(AXIS_SCENE_TO_RL);
  return q.normalize();
}

function createCarMesh(color) {
  const group = new THREE.Group();
  group.rotation.order = "YXZ";

  const body = new THREE.Mesh(
    new THREE.BoxGeometry(122, 36, 84),
    new THREE.MeshStandardMaterial({ color, metalness: 0.18, roughness: 0.44 })
  );
  body.position.y = 26;
  group.add(body);

  const cabin = new THREE.Mesh(
    new THREE.BoxGeometry(62, 22, 68),
    new THREE.MeshStandardMaterial({
      color: 0xd9e4f5,
      metalness: 0.05,
      roughness: 0.22,
      transparent: true,
      opacity: 0.85,
    })
  );
  cabin.position.set(-10, 46, 0);
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
    group.add(w);
  }
  return group;
}

function createNameTag(player) {
  const el = document.createElement("div");
  el.className = "name-tag";
  el.textContent = `${player} | boost 0`;
  reviewLabelLayer.appendChild(el);
  return el;
}

function initReviewScene() {
  if (renderer) return;
  const wrap = document.getElementById("reviewScene");
  const w = Math.max(320, wrap.clientWidth || 960);
  const h = Math.max(220, wrap.clientHeight || 500);

  AXIS_RL_TO_SCENE = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);
  AXIS_SCENE_TO_RL = AXIS_RL_TO_SCENE.clone().invert();

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(w, h);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  wrap.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x213349);
  scene.fog = new THREE.Fog(0x182f4a, 8000, 32000);

  camera = new THREE.PerspectiveCamera(60, w / h, 10, 50000);
  camera.position.set(0, 1300, 2200);
  camera.lookAt(0, 100, 0);
  camAnchorPos = camera.position.clone();

  scene.add(new THREE.HemisphereLight(0xcce1ff, 0x18242e, 0.75));
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(-3000, 6000, 2500);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xa5d1ff, 0.33);
  fill.position.set(2800, 1800, -2400);
  scene.add(fill);

  proceduralArenaGroup = new THREE.Group();
  const field = new THREE.Mesh(
    new THREE.PlaneGeometry(8192, 10240),
    new THREE.MeshPhongMaterial({ color: 0x2f6d4f, side: THREE.DoubleSide })
  );
  field.rotation.x = -Math.PI / 2;
  field.position.y = 0;
  proceduralArenaGroup.add(field);

  const midLine = new THREE.Mesh(
    new THREE.PlaneGeometry(8192, 16),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, side: THREE.DoubleSide })
  );
  midLine.rotation.x = -Math.PI / 2;
  midLine.position.y = 3;
  proceduralArenaGroup.add(midLine);
  scene.add(proceduralArenaGroup);

  ballMesh = new THREE.Mesh(
    new THREE.SphereGeometry(92, 18, 18),
    new THREE.MeshPhongMaterial({ color: 0xf5f5f5 })
  );
  scene.add(ballMesh);

  window.addEventListener("resize", () => {
    if (!renderer || !camera) return;
    const nw = Math.max(320, wrap.clientWidth || 960);
    const nh = Math.max(220, wrap.clientHeight || 500);
    renderer.setSize(nw, nh);
    camera.aspect = nw / nh;
    camera.updateProjectionMatrix();
  });
}

function ensureCarMeshes() {
  if (!scene || !reviewData) return;
  const teams = reviewData.replay_meta?.player_teams || {};
  for (const p of reviewData.players || []) {
    if (carMeshes.has(p)) continue;
    const team = Number(teams[p] || 0);
    const color = team === 1 ? 0xff9933 : 0x4d98ff;
    const car = createCarMesh(color);
    scene.add(car);
    carMeshes.set(p, car);
    nameTags.set(p, createNameTag(p));
  }
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
        if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)) verts.push([x, y, z]);
      }
      continue;
    }
    if (!line.startsWith("f ")) continue;
    const idx = [];
    for (const tok of line.split(/\s+/).slice(1)) {
      const vi = Number(tok.split("/")[0]);
      if (Number.isFinite(vi) && vi !== 0) idx.push(vi > 0 ? vi - 1 : verts.length + vi);
    }
    if (idx.length < 3) continue;
    for (let i = 1; i < idx.length - 1; i++) {
      for (const vi of [idx[0], idx[i], idx[i + 1]]) {
        const v = verts[vi];
        if (!v) continue;
        positions.push(v[0], v[2], -v[1]);
      }
    }
  }
  if (!positions.length) return null;
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geo.computeVertexNormals();
  return new THREE.Mesh(geo, material);
}

function addBoostPads(pads) {
  if (!scene) return;
  if (boostPadGroup) {
    scene.remove(boostPadGroup);
    boostPadGroup = null;
  }
  boostPadGroup = new THREE.Group();
  const smallGeo = new THREE.CylinderGeometry(55, 55, 8, 20);
  const bigGeo = new THREE.CylinderGeometry(90, 90, 10, 24);
  const smallMat = new THREE.MeshStandardMaterial({ color: 0x4cc4ff, emissive: 0x103040, roughness: 0.35, metalness: 0.55 });
  const bigMat = new THREE.MeshStandardMaterial({ color: 0xffb347, emissive: 0x402810, roughness: 0.28, metalness: 0.6 });
  for (const pad of pads || []) {
    const mesh = new THREE.Mesh(pad.size === "big" ? bigGeo : smallGeo, pad.size === "big" ? bigMat : smallMat);
    const pos = rlToScene({ x: pad.x, y: pad.y, z: pad.z || 70 });
    mesh.position.copy(pos).add(new THREE.Vector3(0, 4, 0));
    boostPadGroup.add(mesh);
  }
  scene.add(boostPadGroup);
}

function parseCmfToMesh(arrayBuffer, material) {
  const dv = new DataView(arrayBuffer);
  if (dv.byteLength < 8) return null;
  const triCount = dv.getUint32(0, true);
  const vertexCount = dv.getUint32(4, true);
  if (vertexCount <= 0 || triCount <= 0) return null;
  const expectedBytes = 8 + triCount * 3 * 4 + vertexCount * 3 * 4;
  if (expectedBytes > dv.byteLength) return null;

  let off = 8;
  const index = new Uint32Array(triCount * 3);
  for (let i = 0; i < index.length; i++) {
    index[i] = dv.getUint32(off, true);
    off += 4;
  }
  const CMF_TO_RL = 50.0;
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
  return new THREE.Mesh(geo, material);
}

async function tryLoadArenaMeshes() {
  if (!scene) return;
  if (arenaMeshGroup) {
    scene.remove(arenaMeshGroup);
    arenaMeshGroup = null;
  }
  const mapName = encodeURIComponent(reviewData?.replay_meta?.map_name || "");
  let payload;
  try {
    payload = await fetchJson(`/api/arena_meshes?map_name=${mapName}`);
  } catch {
    return;
  }
  if (!payload?.ok || !payload?.data?.available) return;
  const files = payload.data.files || [];
  const cmfFiles = files.filter((f) => String(f).toLowerCase().endsWith(".cmf"));
  const objFiles = files.filter((f) => String(f).toLowerCase().endsWith(".obj"));
  const targets = cmfFiles.length ? cmfFiles : objFiles;
  if (!targets.length) return;

  const mat = new THREE.MeshStandardMaterial({
    color: 0x9dc4e8,
    emissive: 0x163550,
    metalness: 0.08,
    roughness: 0.56,
    transparent: true,
    opacity: 0.4,
    side: THREE.DoubleSide,
  });
  const group = new THREE.Group();
  let loaded = 0;
  for (const rel of targets) {
    try {
      const res = await fetch(`/collision_meshes/${encodeURI(rel)}`);
      if (!res.ok) continue;
      const mesh = rel.toLowerCase().endsWith(".cmf")
        ? parseCmfToMesh(await res.arrayBuffer(), mat)
        : parseObjToMesh(await res.text(), mat);
      if (mesh) {
        group.add(mesh);
        loaded += 1;
      }
    } catch {
      // ignore one bad mesh file and continue
    }
  }
  if (!loaded) return;
  arenaMeshGroup = group;
  if (proceduralArenaGroup) proceduralArenaGroup.visible = false;
  scene.add(group);
}

function formatClock(frame) {
  if (!frame) return "5:00";
  const sec = Math.max(0, Number(frame.clock_s || 0));
  if (frame.is_overtime) return `OT ${sec.toFixed(1)}`;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function nearestFrameIdx(t) {
  if (!reviewData?.timeline?.length) return 0;
  const arr = reviewData.timeline;
  let lo = 0;
  let hi = arr.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (Number(arr[mid].t || 0) <= t) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

function renderReviewFrame(t) {
  if (!reviewData?.timeline?.length || !renderer) return;
  const idx = nearestFrameIdx(t);
  const frame = reviewData.timeline[idx];
  reviewCurrentT = Number(frame.t || 0);
  reviewTimeline.value = String(idx);
  reviewTime.textContent = `t=${reviewCurrentT.toFixed(2)} / ${reviewDuration.toFixed(2)}s`;

  ballMesh.position.copy(rlToScene(frame.ball || {}));
  ballMesh.quaternion.copy(rlQuatToSceneQuat(frame.ball?.qx, frame.ball?.qy, frame.ball?.qz, frame.ball?.qw));

  for (const p of frame.players || []) {
    const m = carMeshes.get(p.name);
    if (!m) continue;
    m.visible = !p.is_demolished;
    if (!m.visible) continue;
    m.position.copy(rlToScene(p));
    m.quaternion.copy(rlQuatToSceneQuat(p.qx, p.qy, p.qz, p.qw));
  }

  const scores = frame.scores || {};
  reviewBlueScore.textContent = String(scores.blue || 0);
  reviewOrangeScore.textContent = String(scores.orange || 0);
  reviewClock.textContent = formatClock(frame);

  const focus = (frame.players || []).find((p) => p.name === selectedReviewPlayer) || frame.players?.[0];
  if (focus) {
    const target = rlToScene(focus);
    const cam = new THREE.Vector3(target.x, target.y + 520, target.z + 1250);
    camera.position.lerp(cam, 0.28);
    camera.lookAt(target.x, target.y + 120, target.z);
  }

  updateNameTags(frame);
  renderer.render(scene, camera);
  highlightEventAtTime(reviewCurrentT);
}

function reviewAnimate() {
  if (reviewPlaying && reviewData?.timeline?.length) {
    const elapsed = (performance.now() - reviewStartWallMs) / 1000;
    let t = reviewStartReplayT + elapsed;
    if (t >= reviewDuration) {
      t = reviewDuration;
      reviewPlaying = false;
    }
    renderReviewFrame(t);
  }
  requestAnimationFrame(reviewAnimate);
}

function updateLabelSummary() {
  const counts = { TP: 0, FP: 0, TN: 0, FN: 0 };
  for (const id of Object.keys(reviewLabels || {})) {
    const lbl = String(reviewLabels[id]?.label || "").toUpperCase();
    if (counts[lbl] !== undefined) counts[lbl] += 1;
  }
  labelSummary.textContent = `TP ${counts.TP} | FP ${counts.FP} | TN ${counts.TN} | FN ${counts.FN}`;
}

function updateNameTags(frame) {
  if (!camera || !reviewLabelLayer) return;
  const rect = reviewLabelLayer.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;
  for (const p of frame.players || []) {
    const mesh = carMeshes.get(p.name);
    const el = nameTags.get(p.name);
    if (!mesh || !el || p.is_demolished || !mesh.visible) {
      if (el) el.style.display = "none";
      continue;
    }
    const screenPos = mesh.position.clone().add(new THREE.Vector3(0, 120, 0));
    screenPos.project(camera);
    const sx = (screenPos.x * 0.5 + 0.5) * w;
    const sy = (-screenPos.y * 0.5 + 0.5) * h;
    const inDepth = screenPos.z < 1 && screenPos.z > -1;
    const inBounds = sx >= 0 && sx <= w && sy >= 0 && sy <= h;
    const visible = inDepth && inBounds;
    el.style.display = visible ? "block" : "none";
    if (!visible) continue;
    el.style.left = `${sx}px`;
    el.style.top = `${sy}px`;
    el.textContent = `${p.name} | boost ${Number(p.boost || 0).toFixed(0)}`;
    el.classList.toggle("selected", p.name === selectedReviewPlayer);
  }
}

function highlightEventAtTime(t) {
  const items = Array.from(reviewEventsEl.querySelectorAll(".evt-item"));
  let best = null;
  let bestDt = Infinity;
  for (const el of items) {
    const et = Number(el.dataset.time || 0);
    const dt = Math.abs(et - t);
    if (dt < bestDt) {
      bestDt = dt;
      best = el;
    }
    el.classList.remove("active");
  }
  if (best && bestDt <= 0.5) best.classList.add("active");
}

async function saveEventLabel(eventId, label, note) {
  await fetchJson("/api/review/labels/upsert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: eventId, label, note, author: "user" }),
  });
  reviewLabels[eventId] = { label, note, author: "user" };
  updateLabelSummary();
}

function buildReviewEventList() {
  reviewEventsEl.innerHTML = "";
  const events = (reviewEvents || []).slice().sort((a, b) => Number(a.time || 0) - Number(b.time || 0));

  for (const evt of events) {
    const li = document.createElement("li");
    li.className = "evt-item";
    li.dataset.time = String(Number(evt.time || 0));
    li.dataset.eventId = evt.event_id || "";

    const line = document.createElement("div");
    const frameTxt = evt.frame_idx !== undefined ? `f=${evt.frame_idx}` : "";
    const src = evt.manual ? "manual" : "model";
    line.textContent = `[${Number(evt.time || 0).toFixed(2)}] ${evt.type} (${evt.reason || "n/a"}, ${frameTxt}, ${src})`;
    li.appendChild(line);

    const actions = document.createElement("div");
    actions.className = "evt-actions";
    const note = document.createElement("input");
    note.className = "evt-note";
    note.placeholder = "Optional note";
    note.value = reviewLabels[evt.event_id]?.note || evt.label_note || "";

    const makeLabelBtn = (lbl) => {
      const b = document.createElement("button");
      b.textContent = lbl;
      if ((reviewLabels[evt.event_id]?.label || "").toUpperCase() === lbl) b.classList.add("active");
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await saveEventLabel(evt.event_id, lbl, note.value || "");
          buildReviewEventList();
          reviewStatus.textContent = `Saved ${lbl} for ${evt.event_id}`;
        } catch (err) {
          reviewStatus.textContent = `Label save failed: ${err?.message || err}`;
        }
      });
      return b;
    };

    ["TP", "FP", "TN", "FN"].forEach((lbl) => actions.appendChild(makeLabelBtn(lbl)));

    const saveNoteBtn = document.createElement("button");
    saveNoteBtn.textContent = "Save Note";
    saveNoteBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const lbl = (reviewLabels[evt.event_id]?.label || "TP").toUpperCase();
      try {
        await saveEventLabel(evt.event_id, lbl, note.value || "");
        reviewStatus.textContent = `Saved note for ${evt.event_id}`;
      } catch (err) {
        reviewStatus.textContent = `Note save failed: ${err?.message || err}`;
      }
    });
    actions.appendChild(saveNoteBtn);

    li.appendChild(actions);
    li.appendChild(note);

    li.addEventListener("click", () => {
      selectedEventId = evt.event_id;
      renderReviewFrame(Number(evt.time || 0));
      reviewPlaying = false;
    });

    reviewEventsEl.appendChild(li);
  }

  updateLabelSummary();
}

async function loadReviewSessions() {
  const payload = await fetchJson("/api/review/sessions");
  const sessions = payload.sessions || [];
  reviewSessionSelect.innerHTML = "";
  for (const s of sessions) {
    const opt = document.createElement("option");
    opt.value = s.session_id;
    opt.textContent = `${s.session_id} (${Number(s.duration_s || 0).toFixed(1)}s, frames=${s.frame_count || 0})`;
    reviewSessionSelect.appendChild(opt);
  }
  reviewLoaded = true;
}

function clearCarMeshes() {
  for (const [, mesh] of carMeshes) {
    scene.remove(mesh);
  }
  carMeshes.clear();
  for (const [, el] of nameTags) {
    el.remove();
  }
  nameTags.clear();
}

async function loadReviewSession(sessionId) {
  await fetchJson("/api/review/session/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId || "latest" }),
  });
  const sd = await fetchJson("/api/review/session/data");
  const ev = await fetchJson("/api/review/events");
  const lbl = await fetchJson("/api/review/labels");
  reviewData = sd.data;
  reviewEvents = ev.events || [];
  reviewLabels = lbl.labels || {};
  selectedReviewPlayer =
    String(reviewData?.replay_meta?.human_player_name || "").trim() ||
    String(reviewData?.tracked_player_name || "").trim() ||
    String(reviewData?.players?.[Math.max(0, Number(reviewData?.tracked_player_index || 0))] || "").trim() ||
    String(reviewData?.players?.[0] || "").trim();

  reviewDuration = Number(reviewData.duration_s || 0);
  reviewTimeline.max = String(Math.max(0, (reviewData.timeline || []).length - 1));
  reviewTimeline.value = "0";
  reviewCurrentT = Number(reviewData.timeline?.[0]?.t || 0);

  initReviewScene();
  clearCarMeshes();
  ensureCarMeshes();
  addBoostPads(reviewData.boost_pads || []);
  await tryLoadArenaMeshes();
  buildReviewEventList();
  renderReviewFrame(reviewCurrentT);
  await loadMechanicsCurrent();

  reviewStatus.textContent = `Loaded ${reviewData.session_id || "session"} with ${(reviewData.timeline || []).length} frames. Focus: ${selectedReviewPlayer || "n/a"}`;
}

async function markMissed(type) {
  if (!reviewData) return;
  const note = prompt(`Note for missed ${type} (optional):`, "") || "";
  const res = await fetchJson("/api/review/events/mark_missed", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, t: reviewCurrentT, note }),
  });
  reviewEvents.push(res.event);
  buildReviewEventList();
}

async function tickLive() {
  if (activeTab !== "live") return;
  try {
    await refreshCurrent();
    await refreshHistory();
  } catch (_err) {
    statusEl.textContent = "Disconnected";
  }
}

applyScenarioBtn.addEventListener("click", () => {
  applyScenario().catch((err) => {
    statusEl.textContent = `Apply failed: ${err?.message || err}`;
  });
});

tabLiveBtn.addEventListener("click", () => setTab("live"));
tabReviewBtn.addEventListener("click", () => setTab("review"));

reviewLoadBtn.addEventListener("click", () => {
  loadReviewSession(reviewSessionSelect.value).catch((err) => {
    reviewStatus.textContent = `Load failed: ${err?.message || err}`;
  });
});

reviewLoadLatestBtn.addEventListener("click", () => {
  loadReviewSession("latest").catch((err) => {
    reviewStatus.textContent = `Load latest failed: ${err?.message || err}`;
  });
});

reviewPlayBtn.addEventListener("click", () => {
  if (!reviewData?.timeline?.length) {
    reviewStatus.textContent = "Load a review session first.";
    return;
  }
  reviewPlaying = true;
  reviewStartWallMs = performance.now();
  reviewStartReplayT = reviewCurrentT;
});

reviewPauseBtn.addEventListener("click", () => {
  reviewPlaying = false;
});

reviewTimeline.addEventListener("input", () => {
  if (!reviewData?.timeline?.length) return;
  reviewPlaying = false;
  const idx = Number(reviewTimeline.value || 0);
  const frame = reviewData.timeline[Math.max(0, Math.min(idx, reviewData.timeline.length - 1))];
  renderReviewFrame(Number(frame?.t || 0));
});

markMissedWhiffBtn.addEventListener("click", () => {
  markMissed("whiff").catch((err) => {
    reviewStatus.textContent = `Missed mark failed: ${err?.message || err}`;
  });
});

markMissedHesBtn.addEventListener("click", () => {
  markMissed("hesitation").catch((err) => {
    reviewStatus.textContent = `Missed mark failed: ${err?.message || err}`;
  });
});

loginBtn.addEventListener("click", () => {
  loginProfile().catch((err) => {
    statusEl.textContent = `Login failed: ${err?.message || err}`;
  });
});

refreshRecsBtn.addEventListener("click", () => {
  refreshRecommendations().catch((err) => {
    statusEl.textContent = `Recommendation refresh failed: ${err?.message || err}`;
  });
});

refreshMechanicsBtn.addEventListener("click", () => {
  refreshMechanics().catch((err) => {
    statusEl.textContent = `Mechanics refresh failed: ${err?.message || err}`;
  });
});

document.addEventListener("keydown", (ev) => {
  if (activeTab !== "review") return;
  const target = ev.target;
  const typingTarget =
    target &&
    (
      target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.isContentEditable
    );
  if (typingTarget) return;
  if (ev.key === " ") {
    ev.preventDefault();
    if (reviewPlaying) reviewPauseBtn.click();
    else reviewPlayBtn.click();
  }
  if (ev.key === "[" || ev.key === "]") {
    if (!reviewData?.timeline?.length) return;
    reviewPlaying = false;
    const idx = nearestFrameIdx(reviewCurrentT);
    const next = ev.key === "]" ? Math.min(reviewData.timeline.length - 1, idx + 1) : Math.max(0, idx - 1);
    renderReviewFrame(Number(reviewData.timeline[next]?.t || 0));
  }
});

loadCurrentProfile()
  .then(() => refreshRecommendations().catch(() => {}))
  .then(() => loadMechanicsCurrent().catch(() => {}))
  .then(() => loadScenarios())
  .then(() => tickLive())
  .catch(() => {
    statusEl.textContent = "Disconnected";
  });

setInterval(tickLive, 250);
setInterval(() => {
  if (activeTab === "live") {
    loadScenarios().catch(() => {});
  }
}, 5000);

requestAnimationFrame(reviewAnimate);
