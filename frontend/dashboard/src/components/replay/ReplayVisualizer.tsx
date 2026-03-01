import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

type ReplayFrame = {
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
};

type ReplayMeta = {
  map_name?: string;
  player_teams?: Record<string, number>;
  score_samples?: { time_s: number; blue: number; orange: number }[];
  clock_samples?: { time_s: number; seconds_remaining: number }[];
  ot_start_s?: number | null;
  goal_pause_windows?: { pause_start_s?: number; pause_end_s?: number; blue?: number; orange?: number }[];
  demo_events?: { victim_player?: string; time_s?: number }[];
  boost_samples_by_player?: Record<string, { time_s?: number; boost?: number }[]>;
};

type MechanicEvent = {
  time?: number;
  mechanic_id?: string;
  quality_label?: string;
  score?: number;
  short?: string;
  quality_score?: number;
  reason?: string;
};

type BoostPad = { x: number; y: number; z: number; size: string };

type ReplayVisualizerProps = {
  timeline: ReplayFrame[];
  replayMeta: ReplayMeta;
  events: MechanicEvent[];
  selectedPlayer: string;
  boostPads: BoostPad[];
  onTimeChange?: (timeS: number, frameIdx: number) => void;
  seekTime?: number | null;
};

const FIELD_X = 8192;
const FIELD_Y = 10240;
const WALL_HEIGHT = 620;
const WALL_THICKNESS = 60;
const GOAL_WIDTH = 1780;
const GOAL_HEIGHT = 640;
const TELEPORT_DIST_THRESHOLD = 900;

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

function lerpAngle(a: number, b: number, t: number) {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

function interpolate(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function hermite(p0: number, v0: number, p1: number, v1: number, t: number, dt: number) {
  const tt = t * t;
  const ttt = tt * t;
  const h00 = 2 * ttt - 3 * tt + 1;
  const h10 = ttt - 2 * tt + t;
  const h01 = -2 * ttt + 3 * tt;
  const h11 = ttt - tt;
  return h00 * p0 + h10 * v0 * dt + h01 * p1 + h11 * v1 * dt;
}

function interpPosWithVelocity(p0: number, p1: number, v0: number, v1: number, alpha: number, dt: number) {
  return hermite(p0, v0, p1, v1, alpha, dt);
}

function fmtTime(seconds: number) {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function scoreAtTime(samples: ReplayMeta["score_samples"], t: number) {
  if (!samples || !samples.length) return { blue: 0, orange: 0 };
  let blue = samples[0].blue ?? 0;
  let orange = samples[0].orange ?? 0;
  for (const s of samples) {
    if (Number(s.time_s) <= t) {
      blue = Number(s.blue ?? blue);
      orange = Number(s.orange ?? orange);
    } else {
      break;
    }
  }
  return { blue, orange };
}

function clockAtTime(samples: ReplayMeta["clock_samples"], t: number) {
  if (!samples || !samples.length) return 300;
  let cur = samples[0].seconds_remaining ?? 300;
  for (const s of samples) {
    if (Number(s.time_s) <= t) {
      cur = Number(s.seconds_remaining ?? cur);
    } else {
      break;
    }
  }
  return cur;
}

function normalizePlayerKey(name: string) {
  return String(name || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function toSceneVec(x: number, y: number, z: number) {
  return new THREE.Vector3(x, z, -y);
}

function rlQuatToSceneQuat(qx: number, qy: number, qz: number, qw: number, axis: THREE.Quaternion) {
  const q = new THREE.Quaternion(qx, qy, qz, qw);
  q.premultiply(axis);
  q.multiply(axis.clone().invert());
  return q.normalize();
}

function createArena(scene: THREE.Scene) {
  const turf = new THREE.Mesh(
    new THREE.PlaneGeometry(FIELD_X, FIELD_Y),
    new THREE.MeshStandardMaterial({ color: 0x2f6d4f, roughness: 0.9, metalness: 0.05 })
  );
  turf.rotation.x = -Math.PI / 2;
  turf.receiveShadow = true;
  scene.add(turf);

  const lineMat = new THREE.LineBasicMaterial({ color: 0xf8fbff });
  const makeRect = (w: number, h: number) => {
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

  const circlePts = [] as THREE.Vector3[];
  const r = 920;
  for (let i = 0; i <= 64; i += 1) {
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

  function addGoal(z: number, frameMat: THREE.Material, wallMat: THREE.Material) {
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

  const cornerR = 800;
  const cornerH = 460;
  const cornerGeo = new THREE.CylinderGeometry(cornerR, cornerR, cornerH, 20, 1, true, 0, Math.PI / 2);
  const corners: [number, number, number, number][] = [
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

function createMapOverlay(scene: THREE.Scene) {
  const overlayGroup = new THREE.Group();

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

  const makeWall = (x: number, z: number, len: number, rotY: number, mat: THREE.Material) => {
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

  const centerCirclePts = [] as THREE.Vector3[];
  const r = 900;
  for (let i = 0; i <= 72; i += 1) {
    const a = (i / 72) * Math.PI * 2;
    centerCirclePts.push(new THREE.Vector3(Math.cos(a) * r, 3, Math.sin(a) * r));
  }
  overlayGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(centerCirclePts), new THREE.LineBasicMaterial({ color: 0xffffff })));

  scene.add(overlayGroup);
  return overlayGroup;
}

function parseObjToMesh(objText: string, material: THREE.Material) {
  const verts: number[][] = [];
  const positions: number[] = [];
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
      const idx: number[] = [];
      for (const tok of p) {
        const head = tok.split("/")[0];
        const vi = Number(head);
        if (Number.isFinite(vi) && vi !== 0) idx.push(vi > 0 ? vi - 1 : verts.length + vi);
      }
      if (idx.length < 3) continue;
      for (let i = 1; i < idx.length - 1; i += 1) {
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

function parseCmfToMesh(arrayBuffer: ArrayBuffer, material: THREE.Material) {
  const dv = new DataView(arrayBuffer);
  if (dv.byteLength < 8) return null;
  const triCount = dv.getUint32(0, true);
  const vertexCount = dv.getUint32(4, true);
  if (vertexCount <= 0 || triCount <= 0) return null;
  const CMF_TO_RL = 50.0;
  const expectedBytes = 8 + triCount * 3 * 4 + vertexCount * 3 * 4;
  if (expectedBytes > dv.byteLength) return null;

  let off = 8;
  const index = new Uint32Array(triCount * 3);
  let indexInvalid = false;
  for (let i = 0; i < index.length; i += 1) {
    index[i] = dv.getUint32(off, true);
    if (index[i] >= vertexCount) indexInvalid = true;
    off += 4;
  }
  if (indexInvalid) return null;

  const pos = new Float32Array(vertexCount * 3);
  for (let i = 0; i < vertexCount; i += 1) {
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

function createCarMesh(color: number) {
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

function dampedSpringStep(pos: THREE.Vector3, vel: THREE.Vector3, target: THREE.Vector3, stiff: number, damp: number, dt: number) {
  const toTarget = target.clone().sub(pos);
  const accel = toTarget.multiplyScalar(stiff).add(vel.clone().multiplyScalar(-damp));
  vel.add(accel.multiplyScalar(dt));
  pos.add(vel.clone().multiplyScalar(dt));
}

export default function ReplayVisualizer({ timeline, replayMeta, events, selectedPlayer, boostPads, onTimeChange, seekTime }: ReplayVisualizerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const labelLayerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const ballRef = useRef<THREE.Mesh | null>(null);
  const arenaMeshGroupRef = useRef<THREE.Group | null>(null);
  const overlayGroupRef = useRef<THREE.Group | null>(null);
  const proceduralArenaObjectsRef = useRef<THREE.Object3D[]>([]);
  const carObjectsRef = useRef<Map<string, { mesh: THREE.Object3D }>>(new Map());
  const nameTagsRef = useRef<Map<string, HTMLDivElement>>(new Map());
  const boostPadGroupRef = useRef<THREE.Group | null>(null);
  const axisRef = useRef<THREE.Quaternion | null>(null);

  const rafRef = useRef<number | null>(null);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const zoomRef = useRef(1);
  const currentFrameRef = useRef(0);
  const currentReplayTimeRef = useRef(0);
  const playStartReplayRef = useRef(0);
  const playStartWallRef = useRef(0);
  const lastFrameLookupIdxRef = useRef(0);
  const lastRenderWallMsRef = useRef(0);
  const camAnchorForwardRef = useRef(new THREE.Vector3(1, 0, 0));
  const camAnchorPosRef = useRef<THREE.Vector3 | null>(null);
  const camPosVelRef = useRef(new THREE.Vector3());
  const camLookRef = useRef<THREE.Vector3 | null>(null);
  const camLookVelRef = useRef(new THREE.Vector3());

  const reviewOrbitEnabledRef = useRef(false);
  const reviewOrbitYawRef = useRef(0);
  const reviewOrbitPitchRef = useRef(0);
  const reviewOrbitDraggingRef = useRef(false);
  const reviewOrbitLastXRef = useRef(0);
  const reviewOrbitLastYRef = useRef(0);
  const lastUiUpdateRef = useRef(0);

  const boostSamplesByPlayerRef = useRef<Map<string, { t: number; boost: number }[]>>(new Map());
  const demoIntervalsByPlayerRef = useRef<Map<string, { start: number; end: number }[]>>(new Map());

  const goalPauseWindowsRef = useRef<{ start: number; end: number; blue: number; orange: number }[]>([]);
  const goalHoldUntilWallMsRef = useRef(0);
  const goalHoldReplayTRef = useRef(0);
  const goalHoldResumeReplayTRef = useRef(0);
  const playToEventTargetRef = useRef<number | null>(null);
  const lastAutoPausedEventKeyRef = useRef("");
  const lastBallTouchDetectTRef = useRef(0);
  const recentBallTouchUntilTRef = useRef(0);

  const [currentFrame, setCurrentFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [debugOpen, setDebugOpen] = useState(false);
  const [arenaStatus, setArenaStatus] = useState("Arena: procedural fallback");
  const [timelineEventMode, setTimelineEventMode] = useState<"top10" | "worst5" | "best5" | "all">("top10");

  const maxFrame = Math.max(0, (timeline?.length ?? 1) - 1);
  const currentTimeS = timeline?.[currentFrame]?.t ?? 0;

  useEffect(() => {
    playingRef.current = playing;
  }, [playing]);

  useEffect(() => {
    speedRef.current = speed;
  }, [speed]);

  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);

  useEffect(() => {
    currentFrameRef.current = currentFrame;
  }, [currentFrame]);

  useEffect(() => {
    if (playing) {
      playStartReplayRef.current = timeline?.[currentFrameRef.current]?.t ?? 0;
      playStartWallRef.current = performance.now();
    }
  }, [playing, timeline]);

  useEffect(() => {
    camAnchorForwardRef.current.set(1, 0, 0);
    camAnchorPosRef.current = null;
    camPosVelRef.current.set(0, 0, 0);
    camLookRef.current = null;
    camLookVelRef.current.set(0, 0, 0);
    reviewOrbitEnabledRef.current = false;
    reviewOrbitYawRef.current = 0;
    reviewOrbitPitchRef.current = 0;
    reviewOrbitDraggingRef.current = false;
    lastBallTouchDetectTRef.current = 0;
    recentBallTouchUntilTRef.current = 0;
  }, [timeline]);

  useEffect(() => {
    if (!timeline?.length || seekTime == null) return;
    const start = timeline[0]?.t ?? 0;
    const end = timeline[timeline.length - 1]?.t ?? 0;
    const t = clamp(seekTime, start, end);
    const idx = Math.round(((t - start) / Math.max(1e-6, end - start)) * (timeline.length - 1));
    setCurrentFrame(clamp(idx, 0, timeline.length - 1));
  }, [seekTime, timeline]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !labelLayerRef.current) return;
    for (const [name, el] of nameTagsRef.current.entries()) {
      el.classList.toggle("selected", name === selectedPlayer);
    }
  }, [selectedPlayer]);

  useEffect(() => {
    const boostLookup = new Map<string, { t: number; boost: number }[]>();
    for (const [player, samples] of Object.entries(replayMeta?.boost_samples_by_player ?? {})) {
      if (!Array.isArray(samples) || !samples.length) continue;
      const normalized = samples
        .map((s) => ({ t: Number(s?.time_s), boost: Number(s?.boost) }))
        .filter((s) => Number.isFinite(s.t) && Number.isFinite(s.boost))
        .sort((a, b) => a.t - b.t);
      if (normalized.length) boostLookup.set(normalizePlayerKey(player), normalized);
    }
    boostSamplesByPlayerRef.current = boostLookup;

    const demoMap = new Map<string, { start: number; end: number }[]>();
    for (const ev of replayMeta?.demo_events ?? []) {
      const player = normalizePlayerKey(String(ev?.victim_player || ""));
      const t = Number(ev?.time_s);
      if (!player || !Number.isFinite(t)) continue;
      const arr = demoMap.get(player) || [];
      arr.push({ start: t, end: t + 3.0 });
      demoMap.set(player, arr);
    }
    for (const arr of demoMap.values()) {
      arr.sort((a, b) => a.start - b.start);
    }
    demoIntervalsByPlayerRef.current = demoMap;

    const goalWindows = [] as { start: number; end: number; blue: number; orange: number }[];
    for (const w of replayMeta?.goal_pause_windows ?? []) {
      const s = Number(w?.pause_start_s);
      const e = Number(w?.pause_end_s);
      if (!Number.isFinite(s) || !Number.isFinite(e)) continue;
      goalWindows.push({
        start: s,
        end: Math.max(s, e),
        blue: Number(w?.blue ?? 0),
        orange: Number(w?.orange ?? 0),
      });
    }
    goalWindows.sort((a, b) => a.start - b.start);
    goalPauseWindowsRef.current = goalWindows;
  }, [replayMeta]);

  useEffect(() => {
    if (!containerRef.current) return;
    const width = containerRef.current.clientWidth || 800;
    const height = containerRef.current.clientHeight || 520;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x182f4a);
    scene.fog = new THREE.Fog(0x182f4a, 8000, 32000);

    const camera = new THREE.PerspectiveCamera(55, width / height, 10, 100000);
    camera.position.set(-2600, 2200, 4600);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    renderer.setSize(width, height);
    renderer.shadowMap.enabled = false;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;

    axisRef.current = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);

    scene.add(new THREE.HemisphereLight(0xcce1ff, 0x18242e, 0.75));
    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(-3000, 6000, 2500);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xa5d1ff, 0.33);
    fill.position.set(2800, 1800, -2400);
    scene.add(fill);

    const beforeArena = new Set(scene.children);
    createArena(scene);
    proceduralArenaObjectsRef.current = scene.children.filter((obj) => !beforeArena.has(obj));
    overlayGroupRef.current = createMapOverlay(scene);

    const ball = new THREE.Mesh(
      new THREE.SphereGeometry(95, 28, 28),
      new THREE.MeshStandardMaterial({ color: 0xf7b500, metalness: 0.32, roughness: 0.3 })
    );
    ball.castShadow = true;
    scene.add(ball);

    sceneRef.current = scene;
    cameraRef.current = camera;
    rendererRef.current = renderer;
    ballRef.current = ball;

    containerRef.current.innerHTML = "";
    containerRef.current.appendChild(renderer.domElement);
    renderer.domElement.style.touchAction = "none";

    const onResize = () => {
      if (!containerRef.current || !rendererRef.current || !cameraRef.current) return;
      const w = containerRef.current.clientWidth || 800;
      const h = containerRef.current.clientHeight || 520;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
    };
    onResize();

    const ro = new ResizeObserver(() => onResize());
    ro.observe(containerRef.current);
    window.addEventListener("resize", onResize);

    const onPointerDown = (ev: PointerEvent) => {
      if (!reviewOrbitEnabledRef.current || playingRef.current) return;
      reviewOrbitDraggingRef.current = true;
      reviewOrbitLastXRef.current = Number(ev.clientX || 0);
      reviewOrbitLastYRef.current = Number(ev.clientY || 0);
      renderer.domElement.setPointerCapture?.(ev.pointerId);
      ev.preventDefault();
    };
    const onPointerMove = (ev: PointerEvent) => {
      if (!reviewOrbitDraggingRef.current) return;
      const x = Number(ev.clientX || 0);
      const y = Number(ev.clientY || 0);
      const dx = x - reviewOrbitLastXRef.current;
      const dy = y - reviewOrbitLastYRef.current;
      reviewOrbitLastXRef.current = x;
      reviewOrbitLastYRef.current = y;
      reviewOrbitYawRef.current -= dx * 0.0055;
      reviewOrbitPitchRef.current = clamp(reviewOrbitPitchRef.current - dy * 0.0045, -0.7, 0.75);
      ev.preventDefault();
    };
    const stopOrbitDrag = (ev: PointerEvent) => {
      if (!reviewOrbitDraggingRef.current) return;
      reviewOrbitDraggingRef.current = false;
      renderer.domElement.releasePointerCapture?.(ev.pointerId);
    };

    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerup", stopOrbitDrag);
    renderer.domElement.addEventListener("pointercancel", stopOrbitDrag);

    return () => {
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerup", stopOrbitDrag);
      renderer.domElement.removeEventListener("pointercancel", stopOrbitDrag);
      window.removeEventListener("resize", onResize);
      ro.disconnect();
      renderer.dispose();
    };
  }, []);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    if (boostPadGroupRef.current) {
      scene.remove(boostPadGroupRef.current);
      boostPadGroupRef.current.traverse((obj) => {
        if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose?.();
        if ((obj as THREE.Mesh).material) {
          const mat = (obj as THREE.Mesh).material as THREE.Material | THREE.Material[];
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose?.());
          else mat.dispose?.();
        }
      });
    }

    const group = new THREE.Group();
    const smallGeo = new THREE.CylinderGeometry(55, 55, 8, 20);
    const bigGeo = new THREE.CylinderGeometry(90, 90, 10, 24);
    const smallMat = new THREE.MeshStandardMaterial({ color: 0x4cc4ff, emissive: 0x103040, roughness: 0.35, metalness: 0.55 });
    const bigMat = new THREE.MeshStandardMaterial({ color: 0xffb347, emissive: 0x402810, roughness: 0.28, metalness: 0.6 });
    for (const pad of boostPads || []) {
      const mesh = new THREE.Mesh(pad.size === "big" ? bigGeo : smallGeo, pad.size === "big" ? bigMat : smallMat);
      mesh.position.copy(toSceneVec(pad.x, pad.y, pad.z)).add(new THREE.Vector3(0, 4, 0));
      group.add(mesh);
    }
    boostPadGroupRef.current = group;
    scene.add(group);
  }, [boostPads]);

  useEffect(() => {
    const arenaGroup = arenaMeshGroupRef.current;
    const scene = sceneRef.current;
    if (!scene) return;

    if (arenaGroup) {
      scene.remove(arenaGroup);
      arenaGroup.traverse((obj) => {
        if ((obj as THREE.Mesh).geometry) (obj as THREE.Mesh).geometry.dispose?.();
        if ((obj as THREE.Mesh).material) {
          const mat = (obj as THREE.Mesh).material as THREE.Material | THREE.Material[];
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose?.());
          else mat.dispose?.();
        }
      });
      arenaMeshGroupRef.current = null;
    }

    let cancelled = false;
    const mapName = String(replayMeta?.map_name || "");
    const setProceduralVisible = (visible: boolean) => {
      for (const obj of proceduralArenaObjectsRef.current) {
        if (visible) {
          if (!obj.parent) scene.add(obj);
        } else if (obj.parent === scene) {
          scene.remove(obj);
        }
      }
    };

    const load = async () => {
      let payload: any;
      try {
        payload = await fetch(`/api/replay/arena_meshes?map_name=${encodeURIComponent(mapName)}`, { credentials: "include" }).then((r) => r.json());
      } catch {
        if (!cancelled) {
          setProceduralVisible(true);
          setArenaStatus("Arena: procedural fallback (mesh API failed)");
        }
        return;
      }
      if (cancelled) return;
      if (!payload?.ok || !payload?.data?.available) {
        setProceduralVisible(true);
        setArenaStatus("Arena: procedural fallback (no mesh files)");
        return;
      }

      const files = payload.data.files || [];
      const cmfFiles = files
        .filter((f: string) => String(f).toLowerCase().endsWith(".cmf"))
        .sort((a: string, b: string) => {
          const ai = Number((String(a).match(/mesh_(\d+)\.cmf$/i) || [])[1] || 999999);
          const bi = Number((String(b).match(/mesh_(\d+)\.cmf$/i) || [])[1] || 999999);
          return ai - bi;
        });
      const objFiles = files.filter((f: string) => String(f).toLowerCase().endsWith(".obj"));
      const targets = cmfFiles.length ? cmfFiles : objFiles;
      if (!targets.length) {
        setProceduralVisible(true);
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
          let mesh: THREE.Mesh | null = null;
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
          parsedFail += 1;
        }
      }

      if (cancelled) {
        mat.dispose();
        return;
      }

      if (!group.children.length) {
        mat.dispose();
        setProceduralVisible(true);
        setArenaStatus("Arena: procedural fallback (mesh parse failed)");
        return;
      }
      arenaMeshGroupRef.current = group;
      setProceduralVisible(false);
      scene.add(group);
      const folder = payload?.data?.folder || "unknown";
      setArenaStatus(`Arena: CMF (${folder}, ${parsedOk}/${targets.length} meshes)`);
      if (parsedFail > 0) {
        console.log(`[arena] using folder=${folder} files=${targets.length} loaded=${parsedOk} failed=${parsedFail}`);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [replayMeta]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    const players = timeline?.[0]?.players?.map((p) => p.name) ?? [];
    const existing = carObjectsRef.current;

    for (const [name, entry] of existing.entries()) {
      if (!players.includes(name)) {
        scene.remove(entry.mesh);
        existing.delete(name);
        const tag = nameTagsRef.current.get(name);
        if (tag) tag.remove();
        nameTagsRef.current.delete(name);
      }
    }

    const teamMap = replayMeta?.player_teams ?? {};
    for (const name of players) {
      if (existing.has(name)) continue;
      const team = Number(teamMap?.[name] ?? 0);
      const mesh = createCarMesh(team === 1 ? 0xff8a5b : 0x49a8ff);
      scene.add(mesh);
      existing.set(name, { mesh });

      if (labelLayerRef.current) {
        const el = document.createElement("div");
        el.className = "name-tag";
        el.textContent = `${name} | boost 0`;
        labelLayerRef.current.appendChild(el);
        nameTagsRef.current.set(name, el);
      }
    }
  }, [timeline, replayMeta]);

  const eventMarkers = useMemo(() => {
    if (!timeline?.length) return [] as { t: number; label: string; score: number; mechanicId: string; reason: string }[];
    return (events || [])
      .map((e) => ({
        t: Number(e.time ?? 0),
        label: String(e.quality_label ?? "neutral"),
        score: Number(e.quality_score ?? e.score ?? 0),
        mechanicId: String(e.mechanic_id ?? "event"),
        reason: String(e.reason ?? ""),
      }))
      .filter((e) => !Number.isNaN(e.t));
  }, [events, timeline]);

  const displayMarkers = useMemo(() => {
    if (!eventMarkers.length) return [];
    if (timelineEventMode === "all") return [...eventMarkers].sort((a, b) => a.t - b.t);
    if (timelineEventMode === "worst5") {
      return [...eventMarkers]
        .sort((a, b) => a.score - b.score)
        .slice(0, 5)
        .sort((a, b) => a.t - b.t);
    }
    if (timelineEventMode === "best5") {
      return [...eventMarkers]
        .sort((a, b) => b.score - a.score)
        .slice(0, 5)
        .sort((a, b) => a.t - b.t);
    }
    const worst = [...eventMarkers].sort((a, b) => a.score - b.score).slice(0, 5);
    const best = [...eventMarkers].sort((a, b) => b.score - a.score).slice(0, 5);
    const merged = [...worst, ...best];
    const seen = new Set<string>();
    const deduped = merged.filter((e) => {
      const k = `${e.mechanicId}|${e.t.toFixed(3)}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    return deduped.sort((a, b) => a.t - b.t);
  }, [eventMarkers, timelineEventMode]);

  useEffect(() => {
    if (!timeline?.length) return;
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const renderer = rendererRef.current;
    const ball = ballRef.current;
    if (!scene || !camera || !renderer || !ball) return;

    const findFrameIndexAtOrBeforeTime = (targetT: number) => {
      const arr = timeline;
      if (targetT <= arr[0].t) return 0;
      if (targetT >= arr[arr.length - 1].t) return arr.length - 1;

      let idx = clamp(lastFrameLookupIdxRef.current, 0, arr.length - 1);
      if (arr[idx].t <= targetT) {
        while (idx + 1 < arr.length && arr[idx + 1].t <= targetT) idx += 1;
        lastFrameLookupIdxRef.current = idx;
        return idx;
      }
      while (idx > 0 && arr[idx].t > targetT) idx -= 1;
      if (arr[idx].t <= targetT) {
        lastFrameLookupIdxRef.current = idx;
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
      lastFrameLookupIdxRef.current = Math.max(0, hi);
      return lastFrameLookupIdxRef.current;
    };

    const interpCarPosition = (p0: ReplayFrame["players"][number], p1: ReplayFrame["players"][number], alpha: number) => {
      const dx = Number(p1.x || 0) - Number(p0.x || 0);
      const dy = Number(p1.y || 0) - Number(p0.y || 0);
      const dz = Number(p1.z || 0) - Number(p0.z || 0);
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (dist > TELEPORT_DIST_THRESHOLD) {
        return { x: Number(p1.x || 0), y: Number(p1.y || 0), z: Number(p1.z || 0) };
      }
      return {
        x: interpolate(Number(p0.x || 0), Number(p1.x || 0), alpha),
        y: interpolate(Number(p0.y || 0), Number(p1.y || 0), alpha),
        z: interpolate(Number(p0.z || 0), Number(p1.z || 0), alpha),
      };
    };

    const getInterpolatedFrame = (t: number) => {
      const idx = findFrameIndexAtOrBeforeTime(t);
      const f0 = timeline[idx];
      const nidx = Math.min(idx + 1, timeline.length - 1);
      const f1 = timeline[nidx];
      const dt = Math.max(1e-6, f1.t - f0.t);
      const alpha = clamp((t - f0.t) / dt, 0, 1);

      const players = (timeline[0]?.players ?? []).map((p0) => p0.name).map((name) => {
        const p0 = (f0.players || []).find((p) => p.name === name) || { name, x: 0, y: 0, z: 0 };
        const p1 = (f1.players || []).find((p) => p.name === name) || p0;
        const vx0 = Number.isFinite(p0.vx) ? Number(p0.vx) : 0;
        const vy0 = Number.isFinite(p0.vy) ? Number(p0.vy) : 0;
        const vz0 = Number.isFinite(p0.vz) ? Number(p0.vz) : 0;
        const vx1 = Number.isFinite(p1.vx) ? Number(p1.vx) : vx0;
        const vy1 = Number.isFinite(p1.vy) ? Number(p1.vy) : vy0;
        const vz1 = Number.isFinite(p1.vz) ? Number(p1.vz) : vz0;
        const pos = interpCarPosition(p0, p1, alpha);
        return {
          name,
          x: pos.x,
          y: pos.y,
          z: pos.z,
          boost: interpolate(Number(p0.boost ?? 0), Number(p1.boost ?? 0), alpha),
          steer: interpolate(Number(p0.steer ?? 0), Number(p1.steer ?? 0), alpha),
          throttle: interpolate(Number(p0.throttle ?? 0), Number(p1.throttle ?? 0), alpha),
          handbrake: Math.round(interpolate(Number(p0.handbrake ?? 0), Number(p1.handbrake ?? 0), alpha)),
          jump: Math.round(interpolate(Number(p0.jump ?? 0), Number(p1.jump ?? 0), alpha)),
          double_jump: Math.round(interpolate(Number(p0.double_jump ?? 0), Number(p1.double_jump ?? 0), alpha)),
          qx0: Number.isFinite(p0.qx) ? Number(p0.qx) : 0,
          qy0: Number.isFinite(p0.qy) ? Number(p0.qy) : 0,
          qz0: Number.isFinite(p0.qz) ? Number(p0.qz) : 0,
          qw0: Number.isFinite(p0.qw) ? Number(p0.qw) : 1,
          qx1: Number.isFinite(p1.qx) ? Number(p1.qx) : (Number.isFinite(p0.qx) ? Number(p0.qx) : 0),
          qy1: Number.isFinite(p1.qy) ? Number(p1.qy) : (Number.isFinite(p0.qy) ? Number(p0.qy) : 0),
          qz1: Number.isFinite(p1.qz) ? Number(p1.qz) : (Number.isFinite(p0.qz) ? Number(p0.qz) : 0),
          qw1: Number.isFinite(p1.qw) ? Number(p1.qw) : (Number.isFinite(p0.qw) ? Number(p0.qw) : 1),
          yaw: lerpAngle(Number(p0.yaw || 0), Number(p1.yaw || p0.yaw || 0), alpha),
          vx: interpolate(vx0, vx1, alpha),
          vy: interpolate(vy0, vy1, alpha),
          vz: interpolate(vz0, vz1, alpha),
        };
      });

      const bvx0 = Number.isFinite(f0.ball.vx) ? Number(f0.ball.vx) : 0;
      const bvy0 = Number.isFinite(f0.ball.vy) ? Number(f0.ball.vy) : 0;
      const bvz0 = Number.isFinite(f0.ball.vz) ? Number(f0.ball.vz) : 0;
      const bvx1 = Number.isFinite(f1.ball.vx) ? Number(f1.ball.vx) : bvx0;
      const bvy1 = Number.isFinite(f1.ball.vy) ? Number(f1.ball.vy) : bvy0;
      const bvz1 = Number.isFinite(f1.ball.vz) ? Number(f1.ball.vz) : bvz0;

      return {
        idx,
        t,
        ball: {
          x: interpPosWithVelocity(f0.ball.x, f1.ball.x, bvx0, bvx1, alpha, dt),
          y: interpPosWithVelocity(f0.ball.y, f1.ball.y, bvy0, bvy1, alpha, dt),
          z: interpPosWithVelocity(f0.ball.z, f1.ball.z, bvz0, bvz1, alpha, dt),
          qx0: Number.isFinite(f0.ball.qx) ? Number(f0.ball.qx) : 0,
          qy0: Number.isFinite(f0.ball.qy) ? Number(f0.ball.qy) : 0,
          qz0: Number.isFinite(f0.ball.qz) ? Number(f0.ball.qz) : 0,
          qw0: Number.isFinite(f0.ball.qw) ? Number(f0.ball.qw) : 1,
          qx1: Number.isFinite(f1.ball.qx) ? Number(f1.ball.qx) : (Number.isFinite(f0.ball.qx) ? Number(f0.ball.qx) : 0),
          qy1: Number.isFinite(f1.ball.qy) ? Number(f1.ball.qy) : (Number.isFinite(f0.ball.qy) ? Number(f0.ball.qy) : 0),
          qz1: Number.isFinite(f1.ball.qz) ? Number(f1.ball.qz) : (Number.isFinite(f0.ball.qz) ? Number(f0.ball.qz) : 0),
          qw1: Number.isFinite(f1.ball.qw) ? Number(f1.ball.qw) : (Number.isFinite(f0.ball.qw) ? Number(f0.ball.qw) : 1),
          vx: interpolate(bvx0, bvx1, alpha),
          vy: interpolate(bvy0, bvy1, alpha),
          vz: interpolate(bvz0, bvz1, alpha),
        },
        players,
        alpha,
      };
    };

    const slerpedSceneQuat = (qx0: number, qy0: number, qz0: number, qw0: number, qx1: number, qy1: number, qz1: number, qw1: number, alpha: number) => {
      if (!axisRef.current) return new THREE.Quaternion();
      const q0 = rlQuatToSceneQuat(qx0, qy0, qz0, qw0, axisRef.current);
      const q1 = rlQuatToSceneQuat(qx1, qy1, qz1, qw1, axisRef.current);
      return q0.slerp(q1, alpha);
    };

    const boostAtTime = (player: string, t: number) => {
      const arr = boostSamplesByPlayerRef.current.get(normalizePlayerKey(player));
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
    };

    const isPlayerDemoHidden = (player: string, t: number) => {
      const arr = demoIntervalsByPlayerRef.current.get(normalizePlayerKey(player));
      if (!arr || !arr.length) return false;
      for (const iv of arr) {
        if (t < iv.start) break;
        if (t >= iv.start && t <= iv.end) return true;
      }
      return false;
    };

    const alignEventToTimeline = (e: MechanicEvent) => {
      const arr = timeline;
      if (!arr.length) return { __aligned_t: Number(e?.time || 0), __aligned_idx: 0 };
      const target = Number(e?.time || 0);
      let lo = 0;
      let hi = arr.length - 1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        const mt = Number(arr[mid]?.t || 0);
        if (mt < target) lo = mid + 1;
        else if (mt > target) hi = mid - 1;
        else return { __aligned_t: mt, __aligned_idx: mid };
      }
      const idx = clamp(Math.max(0, hi), 0, arr.length - 1);
      return { __aligned_t: Number(arr[idx]?.t || target), __aligned_idx: idx };
    };

    const dedupeMechanicEvents = (arr: MechanicEvent[]) => {
      const byKey = new Map<string, MechanicEvent>();
      for (const e of arr) {
        const aligned = alignEventToTimeline(e);
        const idx = Number((aligned as any).__aligned_idx || 0);
        const k = `${String(e?.mechanic_id || "mech")}|${idx}`;
        if (!byKey.has(k)) byKey.set(k, { ...e, ...(aligned as any) });
      }
      return Array.from(byKey.values());
    };

    const filteredMechanicEvents = () => {
      const raw = dedupeMechanicEvents(events);
      if (!raw.length) return [] as (MechanicEvent & { __aligned_t?: number; __aligned_idx?: number })[];
      const withAligned = raw.map((e) => ({ ...e, ...alignEventToTimeline(e) }));
      if (timelineEventMode === "all") {
        return withAligned.sort((a, b) => Number((a as any).__aligned_t || 0) - Number((b as any).__aligned_t || 0));
      }
      const scored = withAligned.slice();
      if (timelineEventMode === "worst5") {
        return scored
          .sort((a, b) => Number(a?.score ?? a?.quality_score ?? 0) - Number(b?.score ?? b?.quality_score ?? 0))
          .slice(0, 5)
          .sort((a, b) => Number((a as any).__aligned_t || 0) - Number((b as any).__aligned_t || 0));
      }
      if (timelineEventMode === "best5") {
        return scored
          .sort((a, b) => Number(b?.score ?? b?.quality_score ?? 0) - Number(a?.score ?? a?.quality_score ?? 0))
          .slice(0, 5)
          .sort((a, b) => Number((a as any).__aligned_t || 0) - Number((b as any).__aligned_t || 0));
      }
      const worst = scored
        .sort((a, b) => Number(a?.score ?? a?.quality_score ?? 0) - Number(b?.score ?? b?.quality_score ?? 0))
        .slice(0, 5);
      const best = scored
        .sort((a, b) => Number(b?.score ?? b?.quality_score ?? 0) - Number(a?.score ?? a?.quality_score ?? 0))
        .slice(0, 5);
      const merged = dedupeMechanicEvents([...worst, ...best]);
      return merged
        .map((e) => ({ ...e, ...alignEventToTimeline(e) }))
        .sort((a, b) => Number((a as any).__aligned_t || 0) - Number((b as any).__aligned_t || 0));
    };

    const updateNameTags = (interpFrame: ReturnType<typeof getInterpolatedFrame>) => {
      if (!labelLayerRef.current || !sceneRef.current || !cameraRef.current) return;
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;

      for (const p of interpFrame.players) {
        const el = nameTagsRef.current.get(p.name);
        const entry = carObjectsRef.current.get(p.name);
        if (!el || !entry) continue;
        if (isPlayerDemoHidden(p.name, currentReplayTimeRef.current)) {
          el.style.display = "none";
          continue;
        }
        const screenPos = entry.mesh.position.clone().add(new THREE.Vector3(0, 120, 0));
        screenPos.project(camera);
        const sx = (screenPos.x * 0.5 + 0.5) * rect.width;
        const sy = (-screenPos.y * 0.5 + 0.5) * rect.height;
        const inDepth = screenPos.z < 1 && screenPos.z > -1;
        const inBounds = sx >= 0 && sx <= rect.width && sy >= 0 && sy <= rect.height;
        const visible = inDepth && inBounds;
        el.style.display = visible ? "block" : "none";
        if (!visible) continue;

        const dist = camera.position.distanceTo(entry.mesh.position);
        const scale = clamp(1.45 - dist / 8500, 0.82, 1.25);
        const opacity = clamp(1.3 - dist / 13000, 0.35, 1);
        const pad = 8;
        const sxClamped = clamp(sx, pad, Math.max(pad, rect.width - pad));
        const syClamped = clamp(sy, pad, Math.max(pad, rect.height - pad));

        el.style.left = `${sxClamped}px`;
        el.style.top = `${syClamped}px`;
        el.style.transform = `translate(-50%, -50%) scale(${scale})`;
        el.style.opacity = `${opacity}`;

        let boostVal = Number(p.boost || 0);
        if (!Number.isFinite(boostVal) || boostVal <= 0) {
          const metaBoost = boostAtTime(p.name, currentReplayTimeRef.current);
          if (Number.isFinite(metaBoost)) boostVal = Number(metaBoost);
        }
        el.textContent = `${p.name} | boost ${Number.isFinite(boostVal) ? Math.round(boostVal) : 0}`;
      }
    };

    const updateCamera = (interpFrame: ReturnType<typeof getInterpolatedFrame>, dtS: number) => {
      const zoomScale = zoomRef.current;
      const zoomFactor = 1 / zoomScale;
      const fallback = interpFrame.players[0];
      const fp = interpFrame.players.find((p) => p.name === selectedPlayer) || fallback;
      if (!fp) return;

      const carPos = toSceneVec(fp.x, fp.y, fp.z);
      const q = slerpedSceneQuat(fp.qx0, fp.qy0, fp.qz0, fp.qw0, fp.qx1, fp.qy1, fp.qz1, fp.qw1, interpFrame.alpha);
      const forward = new THREE.Vector3(1, 0, 0).applyQuaternion(q);
      forward.y = 0;
      if (forward.lengthSq() < 1e-6) {
        forward.set(1, 0, 0);
      } else {
        forward.normalize();
      }
      const speedMag = Math.sqrt((fp.vx || 0) * (fp.vx || 0) + (fp.vy || 0) * (fp.vy || 0));
      const ballPos = toSceneVec(interpFrame.ball.x, interpFrame.ball.y, interpFrame.ball.z);
      const dirTarget = speedMag < 120 ? camAnchorForwardRef.current.clone() : forward;
      const dirSmooth = 1 - Math.exp(-10.0 * Math.max(0.0, dtS || 1 / 60));
      camAnchorForwardRef.current.lerp(dirTarget, dirSmooth).normalize();
      const up = new THREE.Vector3(0, 1, 0);

      const chaseDistance = 1050 * zoomFactor;
      const chaseHeight = 460 * zoomFactor;
      const desiredPos = carPos
        .clone()
        .addScaledVector(camAnchorForwardRef.current, -chaseDistance)
        .addScaledVector(up, chaseHeight);

      desiredPos.y = clamp(desiredPos.y, 320, 1800);

      const playerFocus = carPos
        .clone()
        .addScaledVector(camAnchorForwardRef.current, 340)
        .addScaledVector(up, 140);
      const ballFocus = ballPos.clone().addScaledVector(up, 130);

      const carBallDist = carPos.distanceTo(ballPos);
      const nowT = Number(currentReplayTimeRef.current || 0);
      if (carBallDist <= 260 && (nowT - lastBallTouchDetectTRef.current) >= 0.24) {
        lastBallTouchDetectTRef.current = nowT;
        recentBallTouchUntilTRef.current = nowT + 1.6;
      }

      let lookTarget = playerFocus.clone();
      const keepBallInFrame = nowT <= recentBallTouchUntilTRef.current;
      if (keepBallInFrame) {
        lookTarget.lerp(ballFocus, 0.58);
      }

      const dt = Math.min(0.05, Math.max(1 / 240, dtS || 1 / 60));
      const stiff = 70.0;
      const damp = 16.0;
      let cameraPosTarget = desiredPos.clone();

      if (reviewOrbitEnabledRef.current && !playingRef.current) {
        const offset = desiredPos.clone().sub(carPos);
        const yawQ = new THREE.Quaternion().setFromAxisAngle(up, reviewOrbitYawRef.current);
        offset.applyQuaternion(yawQ);
        const offNorm = offset.clone().normalize();
        const rightAxis = new THREE.Vector3().crossVectors(up, offNorm).normalize();
        if (rightAxis.lengthSq() > 1e-6) {
          const pitchQ = new THREE.Quaternion().setFromAxisAngle(rightAxis, reviewOrbitPitchRef.current);
          offset.applyQuaternion(pitchQ);
        }
        cameraPosTarget = carPos.clone().add(offset);
        lookTarget = keepBallInFrame
          ? carPos.clone().addScaledVector(up, 130).lerp(ballFocus, 0.52)
          : carPos.clone().addScaledVector(up, 125);
      }

      if (!camAnchorPosRef.current) camAnchorPosRef.current = cameraPosTarget.clone();
      dampedSpringStep(camAnchorPosRef.current, camPosVelRef.current, cameraPosTarget, stiff, damp, dt);
      camera.position.copy(camAnchorPosRef.current);
      camera.up.set(0, 1, 0);
      if (!camLookRef.current) camLookRef.current = lookTarget.clone();
      dampedSpringStep(camLookRef.current, camLookVelRef.current, lookTarget, 90.0, 18.0, dt);
      if (Math.abs(camera.fov - 55) > 0.05) {
        camera.fov += (55 - camera.fov) * (1 - Math.exp(-8.0 * dt));
        camera.updateProjectionMatrix();
      }
      camera.lookAt(camLookRef.current);
      if (keepBallInFrame) {
        camera.updateMatrixWorld();
        const ballNdc = ballPos.clone().project(camera);
        if (Math.abs(ballNdc.x) > 0.84 || Math.abs(ballNdc.y) > 0.82) {
          const corrected = camLookRef.current.clone().lerp(ballFocus, 0.7);
          dampedSpringStep(camLookRef.current, camLookVelRef.current, corrected, 98.0, 20.0, dt);
          camera.lookAt(camLookRef.current);
        }
      }
    };

    const renderAtTime = (t: number) => {
      if (!timeline.length) return;
      const interpFrame = getInterpolatedFrame(t);
      currentFrameRef.current = interpFrame.idx;
      currentReplayTimeRef.current = interpFrame.t;

      const ballPos = toSceneVec(interpFrame.ball.x, interpFrame.ball.y, interpFrame.ball.z);
      ball.position.copy(ballPos);
      const ballQ = slerpedSceneQuat(
        interpFrame.ball.qx0,
        interpFrame.ball.qy0,
        interpFrame.ball.qz0,
        interpFrame.ball.qw0,
        interpFrame.ball.qx1,
        interpFrame.ball.qy1,
        interpFrame.ball.qz1,
        interpFrame.ball.qw1,
        interpFrame.alpha
      );
      ball.quaternion.copy(ballQ);

      for (const p of interpFrame.players) {
        const entry = carObjectsRef.current.get(p.name);
        if (!entry) continue;
        const hidden = isPlayerDemoHidden(p.name, currentReplayTimeRef.current);
        entry.mesh.visible = !hidden;
        if (hidden) continue;
        const rawPos = toSceneVec(p.x, p.y, p.z);
        entry.mesh.position.copy(rawPos).add(new THREE.Vector3(0, 18, 0));
        const q = slerpedSceneQuat(p.qx0, p.qy0, p.qz0, p.qw0, p.qx1, p.qy1, p.qz1, p.qw1, interpFrame.alpha);
        entry.mesh.quaternion.copy(q);
      }

      const nowMs = performance.now();
      const dtS = lastRenderWallMsRef.current > 0 ? Math.max(0.0, (nowMs - lastRenderWallMsRef.current) / 1000.0) : 1 / 60;
      lastRenderWallMsRef.current = nowMs;
      updateCamera(interpFrame, dtS);
      updateNameTags(interpFrame);

      renderer.render(scene, camera);
    };

    const updatePlaybackState = (now: number) => {
      if (!playingRef.current || !timeline.length) return;
      const start = timeline[0]?.t ?? 0;
      const end = timeline[timeline.length - 1]?.t ?? 0;
      const elapsed = (now - playStartWallRef.current) / 1000;
      let targetReplayT = playStartReplayRef.current + elapsed * speedRef.current;

      if (goalHoldUntilWallMsRef.current > now) {
        targetReplayT = goalHoldReplayTRef.current;
      } else if (goalHoldUntilWallMsRef.current > 0) {
        goalHoldUntilWallMsRef.current = 0;
        targetReplayT = goalHoldResumeReplayTRef.current;
        playStartReplayRef.current = targetReplayT;
        playStartWallRef.current = now;
      }

      if (playToEventTargetRef.current !== null && Number.isFinite(playToEventTargetRef.current) && targetReplayT >= playToEventTargetRef.current) {
        targetReplayT = playToEventTargetRef.current;
        playToEventTargetRef.current = null;
        setPlaying(false);
        playingRef.current = false;
      }

      if (targetReplayT >= end) {
        targetReplayT = end;
        playToEventTargetRef.current = null;
        setPlaying(false);
        playingRef.current = false;
      }

      if (playingRef.current && playToEventTargetRef.current === null && goalHoldUntilWallMsRef.current <= 0) {
        const prevReplayT = currentReplayTimeRef.current;
        for (const w of goalPauseWindowsRef.current) {
          if (w.start > (prevReplayT + 0.01) && w.start <= (targetReplayT + 0.01)) {
            targetReplayT = w.start;
            goalHoldReplayTRef.current = w.start;
            goalHoldResumeReplayTRef.current = Math.max(w.end, w.start);
            goalHoldUntilWallMsRef.current = now + 3000.0;
            break;
          }
        }
      }

      if (playingRef.current && playToEventTargetRef.current === null && goalHoldUntilWallMsRef.current <= 0) {
        const evs = filteredMechanicEvents();
        let hit: (MechanicEvent & { __aligned_t?: number }) | null = null;
        const prevReplayT = currentReplayTimeRef.current;
        for (const ev of evs) {
          const et = Number((ev as any).__aligned_t || ev.time || 0);
          if (!Number.isFinite(et)) continue;
          if (et > (prevReplayT + 0.01) && et <= (targetReplayT + 0.01)) {
            hit = ev as any;
            break;
          }
        }
        if (hit) {
          const key = `${String(hit?.mechanic_id || "")}|${Number((hit as any).__aligned_t || hit?.time || 0).toFixed(3)}`;
          if (key !== lastAutoPausedEventKeyRef.current) {
            targetReplayT = Number((hit as any).__aligned_t || hit?.time || targetReplayT);
            playToEventTargetRef.current = null;
            lastAutoPausedEventKeyRef.current = key;
            setPlaying(false);
            playingRef.current = false;
          }
        }
      }

      renderAtTime(clamp(targetReplayT, start, end));
    };

    const tick = (now: number) => {
      if (playingRef.current) {
        updatePlaybackState(now);
      } else {
        const t = timeline[currentFrameRef.current]?.t ?? timeline[0]?.t ?? 0;
        renderAtTime(t);
      }
      onTimeChange?.(currentReplayTimeRef.current, currentFrameRef.current);
      if (now - lastUiUpdateRef.current > 80) {
        setCurrentFrame(currentFrameRef.current);
        lastUiUpdateRef.current = now;
      }
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [timeline, selectedPlayer, onTimeChange, events, timelineEventMode]);

  const nextEvent = useMemo(() => {
    if (!displayMarkers.length) return null;
    const sorted = [...displayMarkers].sort((a, b) => a.t - b.t);
    return sorted.find((e) => e.t >= currentTimeS) ?? sorted[sorted.length - 1];
  }, [displayMarkers, currentTimeS]);

  const score = scoreAtTime(replayMeta?.score_samples, currentTimeS);
  const clock = clockAtTime(replayMeta?.clock_samples, currentTimeS);
  const isOvertime = replayMeta?.ot_start_s != null && currentTimeS >= Number(replayMeta.ot_start_s);

  const handlePlay = () => {
    setPlaying(true);
  };

  const handlePause = () => {
    setPlaying(false);
  };

  const playToNextEvent = () => {
    if (!displayMarkers.length) return;
    const sorted = [...displayMarkers].sort((a, b) => a.t - b.t);
    const next = sorted.find((e) => e.t > currentTimeS + 1e-4);
    if (!next) return;
    playToEventTargetRef.current = next.t;
    setPlaying(true);
  };

  const playToPrevEvent = () => {
    if (!displayMarkers.length) return;
    const sorted = [...displayMarkers].sort((a, b) => a.t - b.t);
    const prev = [...sorted].reverse().find((e) => e.t < currentTimeS - 1e-4);
    if (!prev) return;
    playToEventTargetRef.current = prev.t;
    setPlaying(true);
  };

  const toggleOrbit = () => {
    const next = !reviewOrbitEnabledRef.current;
    reviewOrbitEnabledRef.current = next;
    if (!next) {
      reviewOrbitYawRef.current = 0;
      reviewOrbitPitchRef.current = 0;
      reviewOrbitDraggingRef.current = false;
    }
  };

  return (
    <div className="scene-card">
      <h2>3D Replay View</h2>
      <div className="scene-wrap">
        <div className="scene-canvas" ref={containerRef} />
        <div className="hud-bar">
          <div className="team-score blue">{score.blue}</div>
          <div className="clock-wrap">
            <div className="clock-text">{fmtTime(clock)}</div>
            <div className={`ot-badge${isOvertime ? " show" : ""}`}>OT</div>
          </div>
          <div className="team-score orange">{score.orange}</div>
        </div>
        <div className="arena-status">{arenaStatus}</div>
        <button className="debug-toggle" type="button" onClick={() => setDebugOpen((v) => !v)}>Debug</button>
        <div className={`debug-bubble${debugOpen ? "" : " closed"}`}>
          <div className="debug-head">
            <strong>Visualizer Debug</strong>
            <button type="button" onClick={() => setDebugOpen(false)}>x</button>
          </div>
          <div className="debug-body">
            <div>Frames: {timeline.length}</div>
            <div>Time: {currentTimeS.toFixed(2)}s</div>
            <div>Zoom: {zoom.toFixed(2)}x</div>
            <div>Orbit: {reviewOrbitEnabledRef.current ? "on" : "off"}</div>
          </div>
        </div>
        <div className="label-layer" ref={labelLayerRef} />
      </div>

      <input
        className="timeline-slider"
        type="range"
        min={0}
        max={maxFrame}
        value={currentFrame}
        onChange={(e) => {
          setCurrentFrame(Number(e.target.value));
          setPlaying(false);
        }}
      />

      <div className="timeline-filter">
        <label htmlFor="timelineFilterMode">Event Markers</label>
        <select
          id="timelineFilterMode"
          value={timelineEventMode}
          onChange={(e) => setTimelineEventMode(e.target.value as "top10" | "worst5" | "best5" | "all")}
        >
          <option value="top10">Top 5 Worst + 5 Best</option>
          <option value="worst5">Worst 5</option>
          <option value="best5">Best 5</option>
          <option value="all">All</option>
        </select>
      </div>

      <div className="timeline-events">
        {displayMarkers.map((e, idx) => (
          <div
            key={`${e.t}-${idx}`}
            className={`timeline-event-marker ${e.label}`}
            style={{ left: `${(e.t / Math.max(1e-6, timeline[timeline.length - 1]?.t || 1)) * 100}%` }}
            title={`${e.mechanicId} @ ${e.t.toFixed(2)}s${e.reason ? ` | ${e.reason}` : ""}`}
          >
            <div className="timeline-event-line" />
            <div className="timeline-event-label">{e.mechanicId.slice(0, 6)}</div>
          </div>
        ))}
      </div>

      <div className="playback-tools">
        <button type="button" onClick={playToPrevEvent} disabled={!timeline.length}>Prev Event</button>
        <button type="button" onClick={handlePlay} disabled={!timeline.length}>Play</button>
        <button type="button" onClick={handlePause} disabled={!timeline.length}>Pause</button>
        <button type="button" onClick={playToNextEvent} disabled={!timeline.length}>Next Event</button>
        <button type="button" className="ghost" onClick={toggleOrbit}>Orbit</button>
        <label htmlFor="speedSelect">Speed</label>
        <select id="speedSelect" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
          <option value={0.5}>0.5x</option>
          <option value={1}>1x</option>
          <option value={2}>2x</option>
        </select>
        <label htmlFor="zoomRange">Zoom</label>
        <input
          id="zoomRange"
          type="range"
          min={0.6}
          max={2.0}
          step={0.05}
          value={zoom}
          onChange={(e) => setZoom(Number(e.target.value))}
        />
        <span className="time-label">t={currentTimeS.toFixed(2)}</span>
        <span className="next-event-label">Next event: {nextEvent ? `${nextEvent.mechanicId} @ ${nextEvent.t.toFixed(2)}s` : "none"}</span>
      </div>
    </div>
  );
}
