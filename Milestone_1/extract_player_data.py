import json
import pandas as pd
import argparse
import os
import builtins
import math

CSV_DIR = os.path.join(os.path.dirname(__file__), "heuristic_analysis", "csv_files")


def _safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        cleaned = []
        for a in args:
            s = str(a).encode("ascii", "replace").decode("ascii")
            cleaned.append(s)
        builtins.print(*cleaned, **kwargs)


print = _safe_print


def _normalize_output_csv(output_csv: str) -> str:
    base = os.path.basename(output_csv)
    os.makedirs(CSV_DIR, exist_ok=True)
    return os.path.join(CSV_DIR, base)


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _boost_to_percent(value):
    v = _to_float(value, 0.0)
    if v <= 1.0:
        return int(max(0.0, min(100.0, v * 100.0)))
    if v <= 255.0:
        return int(max(0.0, min(100.0, (v / 255.0) * 100.0)))
    if v <= 100.0:
        return int(max(0.0, min(100.0, v)))
    return int(max(0.0, min(100.0, v / 1000.0)))


def _extract_numeric(attr_dict, preferred_keys=None):
    if preferred_keys is None:
        preferred_keys = ()
    if isinstance(attr_dict, (int, float)):
        return float(attr_dict)
    if not isinstance(attr_dict, dict):
        return None
    for k in preferred_keys:
        if k in attr_dict and isinstance(attr_dict[k], (int, float)):
            return float(attr_dict[k])
    for v in attr_dict.values():
        if isinstance(v, (int, float)):
            return float(v)
    for v in attr_dict.values():
        if isinstance(v, dict):
            nested = _extract_numeric(v, preferred_keys=preferred_keys)
            if nested is not None:
                return float(nested)
    return None


def _quat_to_euler_zyx(qx, qy, qz, qw):
    # Returns yaw(Z), pitch(Y), roll(X) in radians.
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    sinp = 2.0 * (qw * qy - qz * qx)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    return yaw, pitch, roll


def extract_final(input_json: str, output_csv: str) -> None:
    """
    Convert a rrrocket JSON (from `rrrocket -n -j <replay> > <base>.json`) into a wide CSV.

    - input_json: Path to the JSON file produced by rrrocket.
    - output_csv: Path to write the aggregated gameplay CSV.
    """
    print(f"📂 Reading {input_json}...")
    try:
        with open(input_json, 'r', encoding='utf-8', errors='replace') as f:
            line = f.readline()
            if not line:
                print("❌ Error: JSON file is empty.")
                return
            data = json.loads(line)
    except FileNotFoundError:
        print(f"❌ File not found: {input_json}")
        print("   Tip: Run rrrocket to produce it, e.g.\n"
              "   ./rrrocket -n -j \"/path/to/your.replay\" > <BASE>.json")
        return
    except Exception as e:
        print(f"❌ Error reading JSON: {e}")
        return

    # 1. Build Decoder Ring
    objects_list = data.get('objects', [])
    object_id_to_name = {i: name for i, name in enumerate(objects_list)}

    frames = data.get('network_frames', {}).get('frames', [])
    print(f"✅ Found {len(frames)} frames. Extracting COMPLETE data (Players + Ball)...")

    # --- MAPPINGS ---
    pri_map = {}  # PRI_ID -> Player Name
    car_pri_map = {}  # Car_ID -> PRI_ID
    comp_to_car_map = {}
    actor_class_map = {}
    boost_component_candidates = set()
    unresolved_boost_by_component = {}
    ball_actor_ids = set()  # Track multiple ball IDs if they change
    boost_component_ids = set()
    car_boost_state = {}

    extracted_rows = []
    seen_players = set()
    boost_seen = 0
    boost_mapped = 0
    boost_rows_written = 0

    for i, frame in enumerate(frames):
        row = {'frame': i, 'time': frame.get('time', 0)}

        # --- TRACK NEW ACTORS ---
        for new_actor in frame.get('new_actors', []):
            actor_id = new_actor.get('actor_id')
            name_id = new_actor.get('object_id')
            name = object_id_to_name.get(name_id, "")
            actor_class_map[actor_id] = name
            if "CarComponent_Boost" in name:
                boost_component_candidates.add(actor_id)

            # --- BROADER BALL DETECTION ---
            if "Ball" in name and "Archetypes" in name:
                ball_actor_ids.add(actor_id)
            elif "Ball_TA" in name:  # Fallback for older replays
                ball_actor_ids.add(actor_id)

        # --- CLEANUP ---
        for deleted_id in frame.get('deleted_actors', []):
            if deleted_id in car_pri_map:
                del car_pri_map[deleted_id]
            if deleted_id in comp_to_car_map:
                del comp_to_car_map[deleted_id]
            if deleted_id in boost_component_ids:
                boost_component_ids.discard(deleted_id)
            if deleted_id in unresolved_boost_by_component:
                del unresolved_boost_by_component[deleted_id]
            if deleted_id in boost_component_candidates:
                boost_component_candidates.discard(deleted_id)
            if deleted_id in ball_actor_ids:
                ball_actor_ids.discard(deleted_id)

        # --- PROCESS UPDATES ---
        for actor in frame.get('updated_actors', []):
            actor_id = actor.get('actor_id')
            obj_id = actor.get('object_id')
            prop_name = object_id_to_name.get(obj_id, "")
            attrs = actor.get('attribute', {})
            val = next(iter(attrs.values())) if attrs else None
            actor_class = actor_class_map.get(actor_id, "")

            # A. PLAYER MAPPING
            if "PlayerName" in prop_name and isinstance(val, str):
                pri_map[actor_id] = val
                seen_players.add(val)

            # B. CAR LINKING
            if "Pawn:PlayerReplicationInfo" in prop_name:
                if "Car" not in actor_class:
                    continue
                pri_id = None
                if isinstance(val, dict) and "ActiveActor" in attrs:
                    aa = attrs["ActiveActor"]
                    if aa.get("active"):
                        pri_id = aa.get("actor")
                elif isinstance(val, int):
                    pri_id = val
                if isinstance(pri_id, int) and pri_id >= 0:
                    car_pri_map[actor_id] = pri_id

            # C. BOOST LINKING
            if "CarComponent_TA:Vehicle" in prop_name:
                car_id = None
                if isinstance(val, dict) and "ActiveActor" in attrs:
                    aa = attrs["ActiveActor"]
                    if aa.get("active"):
                        car_id = aa.get("actor")
                elif isinstance(val, int):
                    car_id = val
                if isinstance(car_id, int) and car_id >= 0 and (
                    actor_id in boost_component_candidates
                    or "CarComponent_Boost" in actor_class
                ):
                    comp_to_car_map[actor_id] = car_id
                    if actor_id in unresolved_boost_by_component:
                        car_boost_state[car_id] = unresolved_boost_by_component.pop(actor_id)

            # --- D. DATA EXTRACTION ---
            # 1. BOOST AMOUNT
            if (
                "ReplicatedBoost" in prop_name
                or "ReplicatedBoostAmount" in prop_name
                or "CurrentBoostAmount" in prop_name
                or "ServerConfirmBoostAmount" in prop_name
                or "ClientFixBoostAmount" in prop_name
            ):
                boost_component_ids.add(actor_id)
                boost_component_candidates.add(actor_id)
                boost_seen += 1
                car_id = comp_to_car_map.get(actor_id)
                if not car_id and actor_id in car_pri_map:
                    car_id = actor_id
                raw_boost = _extract_numeric(
                    attrs,
                    preferred_keys=("boost_amount", "Byte", "Int", "Float", "ReplicatedBoostAmount", "CurrentBoostAmount"),
                )
                if raw_boost is None:
                    raw_boost = val
                normalized_boost = _boost_to_percent(raw_boost)
                if car_id:
                    car_boost_state[car_id] = normalized_boost
                    boost_mapped += 1
                else:
                    unresolved_boost_by_component[actor_id] = normalized_boost

            # 2. INPUTS
            if "ReplicatedThrottle" in prop_name:
                name = pri_map.get(car_pri_map.get(actor_id))
                if name:
                    row[f'{name}_throttle'] = round((val - 128) / 128.0, 3)

            if "ReplicatedSteer" in prop_name:
                name = pri_map.get(car_pri_map.get(actor_id))
                if name:
                    row[f'{name}_steer'] = round((val - 128) / 128.0, 3)

            if "bReplicatedHandbrake" in prop_name:
                name = pri_map.get(car_pri_map.get(actor_id))
                if name:
                    row[f'{name}_handbrake'] = 1 if val else 0

            # 3. PHYSICS (Cars AND Ball)
            if "RigidBody" in prop_name or "ReplicatedRBState" in prop_name:
                rb = attrs.get('RigidBody')
                if not rb and attrs:
                    rb = next(iter(attrs.values()))
                if isinstance(rb, dict) and 'location' in rb:
                    loc = rb['location']
                    rot = rb.get('rotation') or {}
                    ang = rb.get('angular_velocity') or {}
                    lin = rb.get('linear_velocity') or rb.get('velocity') or {}

                    qx = _to_float(rot.get('x', 0.0))
                    qy = _to_float(rot.get('y', 0.0))
                    qz = _to_float(rot.get('z', 0.0))
                    qw = _to_float(rot.get('w', 1.0))
                    yaw, pitch, roll = _quat_to_euler_zyx(qx, qy, qz, qw)

                    wx = _to_float(ang.get('x', 0.0))
                    wy = _to_float(ang.get('y', 0.0))
                    wz = _to_float(ang.get('z', 0.0))
                    lvx = _to_float(lin.get('x', 0.0))
                    lvy = _to_float(lin.get('y', 0.0))
                    lvz = _to_float(lin.get('z', 0.0))

                    # Check if Car
                    if actor_id in car_pri_map:
                        name = pri_map.get(car_pri_map[actor_id])
                        if name:
                            row[f'{name}_x'] = loc.get('x')
                            row[f'{name}_y'] = loc.get('y')
                            row[f'{name}_z'] = loc.get('z')
                            row[f'{name}_rot_x'] = qx
                            row[f'{name}_rot_y'] = qy
                            row[f'{name}_rot_z'] = qz
                            row[f'{name}_rot_w'] = qw
                            row[f'{name}_yaw'] = yaw
                            row[f'{name}_pitch'] = pitch
                            row[f'{name}_roll'] = roll
                            row[f'{name}_ang_vel_x'] = wx
                            row[f'{name}_ang_vel_y'] = wy
                            row[f'{name}_ang_vel_z'] = wz
                            row[f'{name}_vel_x'] = lvx
                            row[f'{name}_vel_y'] = lvy
                            row[f'{name}_vel_z'] = lvz

                    # Check if Ball
                    elif actor_id in ball_actor_ids:
                        row['Ball_x'] = loc.get('x')
                        row['Ball_y'] = loc.get('y')
                        row['Ball_z'] = loc.get('z')
                        row['Ball_rot_x'] = qx
                        row['Ball_rot_y'] = qy
                        row['Ball_rot_z'] = qz
                        row['Ball_rot_w'] = qw
                        row['Ball_ang_vel_x'] = wx
                        row['Ball_ang_vel_y'] = wy
                        row['Ball_ang_vel_z'] = wz
                        row['Ball_vel_x'] = lvx
                        row['Ball_vel_y'] = lvy
                        row['Ball_vel_z'] = lvz

        # Persist latest known boost state once player mappings exist.
        for car_id, pri_id in list(car_pri_map.items()):
            player_name = pri_map.get(pri_id)
            if player_name and car_id in car_boost_state:
                row[f"{player_name}_boost"] = car_boost_state[car_id]
                boost_rows_written += 1

        extracted_rows.append(row)

    print("🔨 Building DataFrame...")
    df = pd.DataFrame(extracted_rows)

    # Ensure analyzer-required baseline columns always exist.
    required_global = [
        'Ball_x', 'Ball_y', 'Ball_z',
        'Ball_rot_x', 'Ball_rot_y', 'Ball_rot_z', 'Ball_rot_w',
        'Ball_vel_x', 'Ball_vel_y', 'Ball_vel_z',
        'Ball_ang_vel_x', 'Ball_ang_vel_y', 'Ball_ang_vel_z',
        'time', 'frame'
    ]
    for col in required_global:
        if col not in df.columns:
            df[col] = 0

    # Ensure all per-player columns expected by analyzer.py exist.
    required_suffixes = [
        '_x', '_y', '_z', '_boost', '_handbrake',
        '_throttle', '_steer', '_jump', '_double_jump',
        '_rot_x', '_rot_y', '_rot_z', '_rot_w',
        '_yaw', '_pitch', '_roll',
        '_vel_x', '_vel_y', '_vel_z',
        '_ang_vel_x', '_ang_vel_y', '_ang_vel_z'
    ]
    if not seen_players:
        for c in df.columns:
            for suffix in required_suffixes:
                if c.endswith(suffix) and not c.startswith('Ball'):
                    seen_players.add(c[:-len(suffix)])

    for player in sorted(seen_players):
        for suffix in required_suffixes:
            col = f'{player}{suffix}'
            if col not in df.columns:
                df[col] = 0

    # Sort columns to put Ball first
    cols = list(df.columns)
    for c in ['Ball_x', 'Ball_y', 'Ball_z', 'time', 'frame']:
        if c in cols:
            cols.insert(0, cols.pop(cols.index(c)))
    df = df[cols]

    print("✨ Smoothing Data (Forward Fill)...")
    # Crucial: Physics updates don't happen every frame for every object
    df = df.ffill().fillna(0)

    # ---------------------------------------------------------
    # ⚡ JUMP DERIVATION (Kept from previous version)
    # ---------------------------------------------------------
    print("🚀 Calculating Jumps...")
    df['dt'] = df['time'].diff().fillna(0.03)
    df.loc[df['dt'] == 0, 'dt'] = 0.03

    player_cols = [c.replace('_z', '') for c in df.columns if c.endswith('_z') and 'Ball' not in c]

    for player in player_cols:
        z_col = f"{player}_z"
        if z_col not in df.columns:
            continue

        vz = df[z_col].diff() / df['dt']
        az = vz.diff() / df['dt']

        is_impulse = az > 2000
        is_ground = df[z_col] < 50

        df[f'{player}_jump'] = (is_impulse & is_ground).astype(int)
        df[f'{player}_double_jump'] = (is_impulse & ~is_ground).astype(int)

    boost_cols = [c for c in df.columns if c.endswith('_boost')]
    if boost_cols:
        all_zero = True
        player_max = {}
        for c in boost_cols:
            mx = pd.to_numeric(df[c], errors='coerce').fillna(0).max()
            player_max[c] = float(mx)
            if mx > 0:
                all_zero = False
        if all_zero:
            print("WARNING: All player boost columns are zero after extraction.")
            print("         Replay may have missing boost-component mappings.")
        else:
            print(f"Boost per-player maxima: {player_max}")
    print(
        f"Boost diagnostics: seen_updates={boost_seen}, mapped_updates={boost_mapped}, "
        f"rows_written={boost_rows_written}"
    )

    df.drop(columns=['dt'], inplace=True)

    output_csv = _normalize_output_csv(output_csv)
    df.to_csv(output_csv, index=False)
    print(f"💾 Saved COMPLETE data to: {output_csv}")
    print("   (Now includes Ball_x, Ball_y, Ball_z)")


import subprocess
import shutil


def _is_compatible_rrrocket_binary(path: str) -> bool:
    """
    Basic OS compatibility check for rrrocket binaries.
    - On Windows: require a PE executable (MZ header) and prefer .exe naming.
    - On non-Windows: allow regular executable files.
    """
    if not os.path.isfile(path):
        return False

    if os.name != "nt":
        return True

    # Most sane Windows setups will use rrrocket.exe.
    if not path.lower().endswith(".exe"):
        return False

    try:
        with open(path, "rb") as f:
            return f.read(2) == b"MZ"
    except OSError:
        return False


def _resolve_rrrocket_path(explicit_path: str | None = None) -> str | None:
    """
    Try to locate the rrrocket binary.
    Priority:
      1) --rrrocket argument (explicit_path)
      2) RRROCKET_BIN env var
      3) PATH via shutil.which('rrrocket' or 'rrrocket.exe')
      4) Common local paths: project root, script dir
    Returns an absolute path or None if not found.
    """
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    env_bin = os.environ.get('RRROCKET_BIN')
    if env_bin:
        candidates.append(env_bin)

    which_candidates = [shutil.which('rrrocket.exe'), shutil.which('rrrocket')]
    candidates.extend([c for c in which_candidates if c])

    # Local common spots
    here = os.path.dirname(__file__)
    repo_root = os.path.abspath(os.path.join(here, '../rlbot_training', '..', '..'))
    candidates.extend([
        os.path.join(repo_root, 'rrrocket'),
        os.path.join(repo_root, 'rrrocket.exe'),
        os.path.join(here, 'rrrocket'),
        os.path.join(here, 'rrrocket.exe'),
    ])

    for c in candidates:
        if not c:
            continue
        c = os.path.expanduser(c)
        if _is_compatible_rrrocket_binary(c):
            return os.path.abspath(c)
    return None


def _run_rrrocket_to_json(rrrocket_bin: str, replay_path: str, json_out_path: str) -> bool:
    """
    Execute: rrrocket -n -j <replay> > json_out_path
    We capture stdout and write it to the target file to match the expected 1-line JSON format.
    Returns True on success.
    """
    print(f"▶️ Running rrrocket on replay: {replay_path}")
    print(f"   Binary: {rrrocket_bin}")
    try:
        # rrrocket prints one big JSON object to stdout
        proc = subprocess.run(
            [rrrocket_bin, '-n', '-j', replay_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        if proc.returncode != 0:
            print("❌ rrrocket failed:")
            # Show a small tail of stderr for context
            tail = proc.stderr[-500:] if proc.stderr else ''
            print(tail)
            return False
        out_dir = os.path.dirname(json_out_path) or '.'
        os.makedirs(out_dir, exist_ok=True)
        with open(json_out_path, 'w', encoding='utf-8') as f:
            f.write(proc.stdout.strip() + "\n")
        print(f"✅ rrrocket JSON written: {json_out_path}")
        return True
    except FileNotFoundError:
        print(f"❌ rrrocket binary not found: {rrrocket_bin}")
    except OSError as e:
        # WinError 193 typically means wrong binary format (e.g., Linux ELF on Windows).
        if getattr(e, "winerror", None) == 193:
            print("❌ rrrocket binary is not a valid Windows executable.")
            print(f"   Selected binary: {rrrocket_bin}")
            print("   Install/use a Windows rrrocket release (.exe), then pass --rrrocket PATH\\to\\rrrocket.exe")
            return False
        print(f"❌ OS error running rrrocket: {e}")
    except Exception as e:
        print(f"❌ Error running rrrocket: {e}")
    return False


def _derive_paths_from_user_or_args() -> tuple[str | None, str | None, str | None]:
    """
    Returns a tuple: (json_path, csv_path, replay_path)
    - If json_path is provided/exists, replay_path may be None.
    - If json_path is None and replay_path is provided, caller should run rrrocket to create json_path.
    """
    parser = argparse.ArgumentParser(description="Run rrrocket on a .replay and extract player/ball data into CSV")
    parser.add_argument('-i', '--input', dest='input_arg', help='Path to rrrocket JSON, or a base name without .json (e.g., 300F73EE...)')
    parser.add_argument('-r', '--replay', dest='replay_path', help='Path to a Rocket League .replay file to parse with rrrocket')
    parser.add_argument('--rrrocket', dest='rrrocket_bin', help='Path to rrrocket/rrrocket.exe (optional if in PATH)')
    parser.add_argument('-o', '--output', dest='output_csv', help='Output CSV path (default: <replay_name>.csv)')
    parser.add_argument('--no-prompt', action='store_true', help='Do not prompt; fallback to physics_data.json if nothing provided')
    args = parser.parse_args()

    # Case A: Replay provided via argument
    if args.replay_path:
        rp = args.replay_path.strip().strip('"').strip("'")
        base_name = os.path.splitext(os.path.basename(rp))[0]
        input_json = f"{base_name}.json"
        output_csv = args.output_csv or f"{base_name}.csv"
        return input_json, output_csv, rp

    # Case B: Explicit JSON input provided
    if args.input_arg:
        inp = args.input_arg.strip().strip('"').strip("'")
        if inp.lower().endswith('.json'):
            input_json = inp
            base_name = os.path.splitext(os.path.basename(inp))[0]
        else:
            input_json = f"{inp}.json"
            base_name = os.path.basename(inp)
        output_csv = args.output_csv or f"{base_name}.csv"
        return input_json, output_csv, None

    # Case C: No replay/json args were provided.
    # Standard flow is to launch via scripts/replay_extract.ps1, which opens File Explorer.
    if not args.no_prompt:
        print("🚀 Rocket League Replay Data Extractor")
        print("=====================================")
        print("No replay argument was provided.")
        print("Use scripts/replay_extract.ps1 to select a replay in File Explorer,")
        print("or pass --replay / --input explicitly.")

    # Case D: Fallback legacy
    input_json = 'physics_data.json'
    output_csv = args.output_csv or 'complete_gameplay_data.csv'
    return input_json, output_csv, None


if __name__ == "__main__":
    in_json, out_csv, replay = _derive_paths_from_user_or_args()

    if not in_json or not out_csv:
        print("❌ Invalid input. Please provide a valid .replay file.")
        exit(1)

    # If JSON doesn't exist but we have a replay, try to run rrrocket
    if (not os.path.exists(in_json)) and replay:
        print(f"\n📁 Processing replay: {os.path.basename(replay)}")

        # Get rrrocket binary path
        rr_bin = _resolve_rrrocket_path(explicit_path=None)
        # Check for --rrrocket argument
        try:
            ap = argparse.ArgumentParser(add_help=False)
            ap.add_argument('--rrrocket')
            ns, _ = ap.parse_known_args()
            if ns.rrrocket:
                rr_bin = _resolve_rrrocket_path(ns.rrrocket)
        except Exception:
            pass

        if not rr_bin:
            print("❌ Could not locate rrrocket binary.")
            if os.name == "nt":
                print("   On Windows, install rrrocket.exe and provide it with --rrrocket")
            else:
                print("   Please install rrrocket or provide path with --rrrocket")
            print("   Download from: https://github.com/nickbabcock/rrrocket/releases")
            exit(1)

        print("⚡ Running rrrocket to parse replay...")
        if _run_rrrocket_to_json(rr_bin, replay, in_json):
            print("🔄 Processing JSON and extracting player data...")
            extract_final(in_json, out_csv)
            print(f"\n🎉 Complete! Your data is saved as: {out_csv}")
        else:
            print("❌ Failed to parse replay with rrrocket.")
            exit(1)
    elif os.path.exists(in_json):
        # JSON exists, process it directly
        print(f"📂 Found existing JSON: {in_json}")
        print("🔄 Processing JSON and extracting player data...")
        extract_final(in_json, out_csv)
        print(f"\n🎉 Complete! Your data is saved as: {out_csv}")
    else:
        print(f"❌ Input file not found: {in_json}")
        print("   Please provide a valid .replay file or existing JSON.")
        exit(1)
