
import os
from typing import Dict, List

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
    import seaborn as sns

    HAVE_PLOTTING = True
except Exception:
    HAVE_PLOTTING = False

HERE = os.path.dirname(__file__)
CSV_DIR = os.path.join(HERE, "csv_files")
PLOTS_DIR = os.path.join(HERE, "analysis_pngs")
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)


def _list_csv_files(directory: str) -> List[str]:
    return sorted([f for f in os.listdir(directory) if f.lower().endswith(".csv")])


def _prompt_for_csv(directory: str) -> str | None:
    files = _list_csv_files(directory)
    if not files:
        print(f"No CSV files found in: {directory}")
        print("Place exported gameplay CSV files into this folder and run again.")
        return None

    print("Select a CSV to analyze:")
    for i, f in enumerate(files, start=1):
        print(f"  {i}) {f}")

    while True:
        resp = input("> ").strip()
        if resp.isdigit():
            idx = int(resp)
            if 1 <= idx <= len(files):
                return os.path.join(directory, files[idx - 1])
        if resp in files:
            return os.path.join(directory, resp)
        print(f"Please enter a number 1-{len(files)} or an exact filename.")


def _ensure_dt(df: pd.DataFrame) -> pd.DataFrame:
    if "dt" not in df.columns:
        df["dt"] = df["time"].diff().fillna(0.03)
    df.loc[df["dt"] <= 0, "dt"] = 0.03
    return df


def _player_names(df: pd.DataFrame) -> List[str]:
    suffixes = ["_double_jump", "_handbrake", "_throttle", "_boost", "_steer", "_jump", "_x", "_y", "_z"]
    names = set()
    for c in df.columns:
        for s in suffixes:
            if c.endswith(s) and not c.startswith("Ball"):
                names.add(c[: -len(s)])
                break
    return sorted(names)


def _save_plot(fig, out_name: str) -> None:
    if not HAVE_PLOTTING:
        return
    out_path = os.path.join(PLOTS_DIR, out_name)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Saved plot: {out_path}")


def _sorted_results(stats: List[Dict], sort_by: str, ascending: bool, columns: List[str]) -> pd.DataFrame:
    if not stats:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(stats).sort_values(sort_by, ascending=ascending)


def _ball_hit_window(df: pd.DataFrame) -> np.ndarray:
    b_cols = ["Ball_x", "Ball_y", "Ball_z"]
    if not all(c in df.columns for c in b_cols):
        return np.zeros(len(df), dtype=float)
    b_vel = df[b_cols].diff().fillna(0)
    b_accel = b_vel.diff().fillna(0)
    b_jerk_mag = np.sqrt(b_accel["Ball_x"] ** 2 + b_accel["Ball_y"] ** 2 + b_accel["Ball_z"] ** 2)
    is_hit = b_jerk_mag > 30
    return is_hit.rolling(window=5, center=True).max().fillna(0).to_numpy(dtype=float)


def _player_frame_features(df: pd.DataFrame, player: str) -> Dict[str, np.ndarray] | None:
    cols = [f"{player}_x", f"{player}_y", f"{player}_z"]
    if not all(c in df.columns for c in cols):
        return None
    if not all(c in df.columns for c in ["Ball_x", "Ball_y", "Ball_z"]):
        return None

    dt = df["dt"].to_numpy(dtype=float)
    px = df[cols[0]].to_numpy(dtype=float)
    py = df[cols[1]].to_numpy(dtype=float)
    pz = df[cols[2]].to_numpy(dtype=float)
    bx = df["Ball_x"].to_numpy(dtype=float)
    by = df["Ball_y"].to_numpy(dtype=float)
    bz = df["Ball_z"].to_numpy(dtype=float)

    vx = np.diff(px, prepend=px[0]) / dt
    vy = np.diff(py, prepend=py[0]) / dt
    vz = np.diff(pz, prepend=pz[0]) / dt

    dx = bx - px
    dy = by - py
    dz = bz - pz
    dist = np.sqrt(dx**2 + dy**2 + dz**2)

    speed = np.sqrt(vx**2 + vy**2 + vz**2)
    to_ball_norm = np.maximum(dist, 1e-6)
    ux = dx / to_ball_norm
    uy = dy / to_ball_norm
    uz = dz / to_ball_norm
    toward_speed = vx * ux + vy * uy + vz * uz
    lateral_speed = np.sqrt(np.maximum(0.0, speed**2 - toward_speed**2))

    closing = np.zeros_like(dist, dtype=bool)
    closing[1:] = dist[1:] + 4.0 < dist[:-1]
    pressure = (dist < 1800.0) | (closing & (dist < 2400.0))

    airborne = (pz > 80.0) & (np.abs(vz) > 50.0)
    recovery = pd.Series(airborne).rolling(window=20, min_periods=1).max().to_numpy(dtype=bool)

    boost_col = f"{player}_boost"
    boost = df[boost_col].to_numpy(dtype=float) if boost_col in df.columns else None

    return {
        "dt": dt,
        "dist": dist,
        "speed": speed,
        "toward_speed": toward_speed,
        "lateral_speed": lateral_speed,
        "closing": closing,
        "pressure": pressure,
        "airborne": airborne,
        "recovery": recovery,
        "boost": boost,
    }

def analyze_boost_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_dt(df.copy())
    players = [c.replace("_boost", "") for c in df.columns if c.endswith("_boost")]
    stats = []

    for p in players:
        feat = _player_frame_features(df, p)
        if feat is None or feat["boost"] is None:
            continue

        speed = feat["speed"]
        toward = feat["toward_speed"]
        pressure = feat["pressure"]
        boost = feat["boost"]

        boost_diff = np.diff(boost, prepend=boost[0])
        boost_drop = np.maximum(0.0, -boost_diff)
        is_boosting = boost_drop > 0
        useful = is_boosting & (pressure | (toward > 250) | (speed > 1700))

        total_used = float(boost_drop[is_boosting].sum())
        useful_used = float(boost_drop[useful].sum())
        wasted = max(0.0, total_used - useful_used)
        waste_pct = (wasted / total_used * 100.0) if total_used > 0 else 0.0

        stats.append(
            {
                "Player": p,
                "Total Boost Used": int(total_used),
                "Useful Boost": int(useful_used),
                "Waste %": round(float(waste_pct), 2),
            }
        )

    results = _sorted_results(stats, "Waste %", False, ["Player", "Total Boost Used", "Useful Boost", "Waste %"])
    print("\n--- BOOST EFFICIENCY REPORT ---")
    if not results.empty:
        print(results.to_string(index=False))
    else:
        print("No boost data found.")
    return results


def analyze_whiffs(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_dt(df.copy())
    players = _player_names(df)
    hit_window = _ball_hit_window(df)
    total_time = max(1e-6, float(df["dt"].sum()))

    stats = []
    for p in players:
        feat = _player_frame_features(df, p)
        if feat is None:
            continue

        dist = feat["dist"]
        speed = feat["speed"]
        toward = feat["toward_speed"]
        closing = feat["closing"]
        n = len(dist)

        whiff_count = 0
        opportunities = 0
        reason_counts = {"drive_miss": 0, "jump_miss": 0, "slow_control_miss": 0}

        attack_active = False
        start_idx = 0
        min_dist = 99999.0
        min_idx = 0
        near_frames = 0
        closing_frames = 0
        intent_frames = 0
        touched = False

        for i in range(n):
            moving_away = i > 0 and dist[i] > dist[i - 1] + 6.0
            start_attack = (closing[i] and dist[i] < 1600.0) or (dist[i] < 460.0 and speed[i] > 80.0)

            if (not attack_active) and start_attack:
                attack_active = True
                start_idx = i
                min_dist = dist[i]
                min_idx = i
                near_frames = 0
                closing_frames = 0
                intent_frames = 0
                touched = False

            if not attack_active:
                continue

            if dist[i] < min_dist:
                min_dist = dist[i]
                min_idx = i
            if closing[i]:
                closing_frames += 1
            if dist[i] <= 460.0:
                near_frames += 1
            if abs(toward[i]) > 140.0 or speed[i] > 160.0:
                intent_frames += 1

            if hit_window[i] > 0 and dist[i] < 210.0:
                touched = True

            duration_s = float(df["time"].iloc[i] - df["time"].iloc[start_idx]) if i > start_idx else 0.0
            timeout = duration_s > 2.8
            disengaged = moving_away and closing_frames > 0
            if not (timeout or disengaged or i == n - 1):
                continue

            opportunities += 1
            progress = max(0.0, dist[start_idx] - min_dist)
            dt_mean = max(1e-3, float(np.mean(feat["dt"])))
            opp_score = (
                0.35 * np.clip(progress / 240.0, 0.0, 1.0)
                + 0.25 * np.clip((near_frames * dt_mean) / 0.24, 0.0, 1.0)
                + 0.25 * np.clip((intent_frames * dt_mean) / 0.30, 0.0, 1.0)
                + 0.15 * np.clip(duration_s / 0.40, 0.0, 1.0)
            )

            if (not touched) and (185.0 < min_dist <= 420.0) and (opp_score >= 0.45):
                whiff_count += 1
                reason = "drive_miss"
                if speed[min_idx] < 420.0 or toward[min_idx] < 260.0:
                    reason = "slow_control_miss"
                if feat["airborne"][min_idx]:
                    reason = "jump_miss"
                reason_counts[reason] += 1

            attack_active = False

        whiff_rate = whiff_count * 60.0 / total_time
        stats.append(
            {
                "Player": p,
                "Whiff Count": int(whiff_count),
                "Whiff Rate / min": round(float(whiff_rate), 2),
                "Whiff Opportunity Count": int(opportunities),
                "Drive Misses": int(reason_counts["drive_miss"]),
                "Jump Misses": int(reason_counts["jump_miss"]),
                "Slow Control Misses": int(reason_counts["slow_control_miss"]),
            }
        )

    results = _sorted_results(
        stats,
        "Whiff Rate / min",
        False,
        ["Player", "Whiff Count", "Whiff Rate / min", "Whiff Opportunity Count", "Drive Misses", "Jump Misses", "Slow Control Misses"],
    )
    print("\n--- WHIFF REPORT (OPPORTUNITY-BASED) ---")
    if not results.empty:
        print(results.to_string(index=False))
    else:
        print("No player position data found.")
    return results


def analyze_hesitation(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_dt(df.copy())
    players = _player_names(df)
    stats = []

    for p in players:
        feat = _player_frame_features(df, p)
        if feat is None:
            continue

        speed = feat["speed"]
        toward = feat["toward_speed"]
        lateral = feat["lateral_speed"]
        pressure = feat["pressure"]
        recovery = feat["recovery"]
        boost = feat["boost"]
        dt = feat["dt"]

        accel = np.diff(speed, prepend=speed[0]) / dt
        progress_penalty = 1.0 - np.clip(np.maximum(0.0, toward) / 900.0, 0.0, 1.0)
        turning_penalty = np.clip(lateral / np.maximum(350.0, speed), 0.0, 1.0)
        accel_penalty = np.clip((180.0 - accel) / 380.0, 0.0, 1.0)
        threat_scale = np.clip((1800.0 - feat["dist"]) / 1800.0, 0.0, 1.0)

        score = (0.45 * progress_penalty + 0.30 * turning_penalty + 0.25 * accel_penalty) * (0.6 + 0.4 * threat_scale)
        if boost is not None:
            score[(boost < 8.0) & (toward > 180.0)] *= 0.55

        valid = pressure & ~recovery
        hes_frame = valid & (score >= 0.55)
        idle_under_pressure = valid & (speed < 450.0) & (toward < 120.0)

        hes_pct = float(hes_frame.sum() / max(1, valid.sum()) * 100.0)
        hes_events = int((np.diff(hes_frame.astype(int), prepend=0) == 1).sum())

        max_streak = 0.0
        streak = 0.0
        for i, is_hes in enumerate(hes_frame):
            if is_hes:
                streak += float(dt[i])
                if streak > max_streak:
                    max_streak = streak
            else:
                streak = 0.0

        status = "aggressive"
        if hes_pct > 20.0:
            status = "high_hesitation"
        elif hes_pct > 10.0:
            status = "hesitant"

        stats.append(
            {
                "Player": p,
                "Avg Speed (uu/s)": int(speed.mean()),
                "Hesitation (%)": round(hes_pct, 2),
                "Hesitation Events": hes_events,
                "Max Hesitation Streak (s)": round(max_streak, 3),
                "Idle Under Pressure (s)": round(float((idle_under_pressure.astype(float) * dt).sum()), 3),
                "Status": status,
            }
        )

    results = _sorted_results(
        stats,
        "Hesitation (%)",
        True,
        ["Player", "Avg Speed (uu/s)", "Hesitation (%)", "Hesitation Events", "Max Hesitation Streak (s)", "Idle Under Pressure (s)", "Status"],
    )
    print("\n--- HESITATION REPORT (PRESSURE-ADJUSTED) ---")
    if not results.empty:
        print(results.to_string(index=False))
    return results

def analyze_pressure_time(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_dt(df.copy())
    players = _player_names(df)
    stats = []

    for p in players:
        feat = _player_frame_features(df, p)
        if feat is None:
            continue
        pressure_seconds = float((feat["pressure"].astype(float) * feat["dt"]).sum())
        total_seconds = float(feat["dt"].sum())
        pressure_pct = pressure_seconds / max(1e-6, total_seconds) * 100.0
        stats.append({"Player": p, "Pressure %": round(pressure_pct, 2), "Pressure Time (s)": round(pressure_seconds, 2)})

    results = _sorted_results(stats, "Pressure %", False, ["Player", "Pressure %", "Pressure Time (s)"])
    print("\n--- PRESSURE TIME ---")
    if not results.empty:
        print(results.to_string(index=False))
    return results


def analyze_approach_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_dt(df.copy())
    players = _player_names(df)
    stats = []

    for p in players:
        feat = _player_frame_features(df, p)
        if feat is None:
            continue

        dist = feat["dist"]
        closing = feat["closing"]
        dist_drop = np.maximum(0.0, -np.diff(dist, prepend=dist[0]))
        closure_total = float(dist_drop.sum())

        close_progress = float(dist_drop[closing].sum())
        close_time = float(feat["dt"][closing].sum())
        close_rate = close_progress / max(1e-6, close_time)

        approach_eff = np.nan
        if feat["boost"] is not None:
            boost_drop = np.maximum(0.0, -np.diff(feat["boost"], prepend=feat["boost"][0]))
            approach_boost = float(boost_drop[closing].sum())
            approach_eff = closure_total / max(1e-6, approach_boost)

        stats.append(
            {
                "Player": p,
                "Approach Closure Total": round(closure_total, 1),
                "Approach Efficiency": round(float(approach_eff), 3) if not np.isnan(approach_eff) else np.nan,
                "Closure Rate (uu/s)": round(close_rate, 2),
            }
        )

    results = _sorted_results(
        stats,
        "Closure Rate (uu/s)",
        False,
        ["Player", "Approach Closure Total", "Approach Efficiency", "Closure Rate (uu/s)"],
    )
    print("\n--- APPROACH EFFICIENCY ---")
    if not results.empty:
        print(results.to_string(index=False))
    return results


def analyze_touch_gap(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_dt(df.copy())
    hit_window = _ball_hit_window(df)
    players = _player_names(df)
    stats = []

    for p in players:
        feat = _player_frame_features(df, p)
        if feat is None:
            continue

        touch_like = (hit_window > 0) & (feat["dist"] < 220.0)
        touch_indices = np.flatnonzero(touch_like)
        if len(touch_indices) == 0:
            stats.append({"Player": p, "Touch Count": 0, "Touch Gap Median (s)": np.nan, "Touch Rate / min": 0.0})
            continue

        events = [touch_indices[0]]
        for idx in touch_indices[1:]:
            if idx - events[-1] > 8:
                events.append(idx)

        event_times = df["time"].iloc[events].to_numpy(dtype=float)
        gaps = np.diff(event_times)
        median_gap = float(np.median(gaps)) if len(gaps) else np.nan

        total_time = max(1e-6, float(df["dt"].sum()))
        touch_rate = len(events) * 60.0 / total_time

        stats.append(
            {
                "Player": p,
                "Touch Count": int(len(events)),
                "Touch Gap Median (s)": round(median_gap, 3) if not np.isnan(median_gap) else np.nan,
                "Touch Rate / min": round(float(touch_rate), 2),
            }
        )

    results = _sorted_results(stats, "Touch Rate / min", False, ["Player", "Touch Count", "Touch Gap Median (s)", "Touch Rate / min"])
    print("\n--- TOUCH GAP / RATE ---")
    if not results.empty:
        print(results.to_string(index=False))
    return results


def analyze_supersonic_time(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_dt(df.copy())
    players = _player_names(df)
    stats = []

    for p in players:
        feat = _player_frame_features(df, p)
        if feat is None:
            continue
        speed = feat["speed"]
        supersonic_pct = float((speed > 2200.0).mean() * 100.0)
        useful_supersonic_pct = float(((speed > 2200.0) & (feat["pressure"] | (feat["toward_speed"] > 280.0))).mean() * 100.0)
        stats.append(
            {
                "Player": p,
                "Avg Speed (uu/s)": int(speed.mean()),
                "Supersonic %": round(supersonic_pct, 2),
                "Useful Supersonic %": round(useful_supersonic_pct, 2),
            }
        )

    results = _sorted_results(stats, "Supersonic %", False, ["Player", "Avg Speed (uu/s)", "Supersonic %", "Useful Supersonic %"])
    print("\n--- SPEED PROFILE ---")
    if not results.empty:
        print(results.to_string(index=False))
    return results


def analyze_possession_time(df: pd.DataFrame, radius: float = 300.0) -> pd.DataFrame:
    if not all(c in df.columns for c in ["Ball_x", "Ball_y", "Ball_z"]):
        return pd.DataFrame()
    players = _player_names(df)
    if not players:
        return pd.DataFrame()

    bpos = df[["Ball_x", "Ball_y", "Ball_z"]].to_numpy(dtype=float)
    nearest = {p: 0 for p in players}
    total = len(df)

    for idx in range(total):
        best_p = None
        best_d = float("inf")
        bx, by, bz = bpos[idx]
        for p in players:
            px_col, py_col, pz_col = f"{p}_x", f"{p}_y", f"{p}_z"
            if px_col not in df.columns or py_col not in df.columns or pz_col not in df.columns:
                continue
            dx = float(df[px_col].iloc[idx]) - bx
            dy = float(df[py_col].iloc[idx]) - by
            dz = float(df[pz_col].iloc[idx]) - bz
            d = float(np.sqrt(dx * dx + dy * dy + dz * dz))
            if d < best_d:
                best_d = d
                best_p = p
        if best_p is not None and best_d <= radius:
            nearest[best_p] += 1

    stats = [{"Player": p, "Possession %": round((nearest[p] / total) * 100.0, 2), "Frames in Possession": nearest[p]} for p in players]
    results = _sorted_results(stats, "Possession %", False, ["Player", "Possession %", "Frames in Possession"])
    print("\n--- POSSESSION (CLOSEST WITHIN 300uu) ---")
    if not results.empty:
        print(results.to_string(index=False))
    return results


def analyze_aerial_attempts(df: pd.DataFrame) -> pd.DataFrame:
    players = _player_names(df)
    stats = []
    for p in players:
        z_col = f"{p}_z"
        j_col = f"{p}_jump"
        dj_col = f"{p}_double_jump"
        if z_col not in df.columns:
            continue
        jumps = df[j_col] if j_col in df.columns else pd.Series([0] * len(df))
        djs = df[dj_col] if dj_col in df.columns else pd.Series([0] * len(df))
        is_rising = (df[z_col].shift(-5) - df[z_col]) > 150
        aerial_attempts = ((jumps == 1) & is_rising) | ((djs == 1) & (df[z_col] > 300))
        stats.append({"Player": p, "Aerial Attempts": int(aerial_attempts.sum())})

    results = _sorted_results(stats, "Aerial Attempts", False, ["Player", "Aerial Attempts"])
    print("\n--- AERIAL ATTEMPTS ---")
    if not results.empty:
        print(results.to_string(index=False))
    return results


def analyze_offensive_threat(df: pd.DataFrame) -> pd.DataFrame:
    if not all(c in df.columns for c in ["Ball_x", "Ball_y"]):
        return pd.DataFrame()
    players = _player_names(df)
    stats = []
    bx = df["Ball_x"].to_numpy(dtype=float)
    by = df["Ball_y"].to_numpy(dtype=float)
    goal_y = 5120.0

    for p in players:
        px_col, py_col = f"{p}_x", f"{p}_y"
        if px_col not in df.columns or py_col not in df.columns:
            continue
        px = df[px_col].to_numpy(dtype=float)
        py = df[py_col].to_numpy(dtype=float)
        vcbx = bx - px
        vcby = by - py
        vcb_norm = np.maximum(np.sqrt(vcbx**2 + vcby**2), 1e-6)
        vbg1x, vbg1y = -bx, goal_y - by
        vbg2x, vbg2y = -bx, -goal_y - by
        vbg1_norm = np.maximum(np.sqrt(vbg1x**2 + vbg1y**2), 1e-6)
        vbg2_norm = np.maximum(np.sqrt(vbg2x**2 + vbg2y**2), 1e-6)
        cos1 = (vcbx * vbg1x + vcby * vbg1y) / (vcb_norm * vbg1_norm)
        cos2 = (vcbx * vbg2x + vcby * vbg2y) / (vcb_norm * vbg2_norm)
        cos_align = np.maximum(cos1, cos2)
        threat_pct = float(((vcb_norm < 1200.0) & (cos_align > 0.85)).mean() * 100.0)
        stats.append({"Player": p, "Threat %": round(threat_pct, 2)})

    results = _sorted_results(stats, "Threat %", False, ["Player", "Threat %"])
    print("\n--- OFFENSIVE THREAT ---")
    if not results.empty:
        print(results.to_string(index=False))
    return results


def run_all_analyses(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    return {
        "boost_waste": analyze_boost_efficiency(df),
        "whiffs": analyze_whiffs(df),
        "hesitation": analyze_hesitation(df),
        "supersonic_time": analyze_supersonic_time(df),
        "possession": analyze_possession_time(df),
        "aerial_attempts": analyze_aerial_attempts(df),
        "offensive_threat": analyze_offensive_threat(df),
        "pressure_time": analyze_pressure_time(df),
        "approach_efficiency": analyze_approach_efficiency(df),
        "touch_gap": analyze_touch_gap(df),
    }


def _merge_player_tables(tables: List[pd.DataFrame], key: str = "Player") -> pd.DataFrame:
    non_empty = [t.set_index(key) for t in tables if isinstance(t, pd.DataFrame) and not t.empty and key in t.columns]
    if not non_empty:
        return pd.DataFrame()

    merged = non_empty[0]
    for t in non_empty[1:]:
        merged = merged.join(t, how="outer", rsuffix="_dup")
        dup_cols = [c for c in merged.columns if c.endswith("_dup")]
        if dup_cols:
            merged.drop(columns=dup_cols, inplace=True)
    return merged.reset_index()


def main():
    print("Rocket League Heuristic Analyzer")
    print("--------------------------------")
    print(f"CSV folder: {CSV_DIR}")
    csv_path = _prompt_for_csv(CSV_DIR)
    if not csv_path:
        return

    print(f"\nLoading: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Failed to read CSV: {e}")
        return

    outputs = run_all_analyses(df)
    merged = _merge_player_tables(list(outputs.values()))
    if not merged.empty:
        base = os.path.splitext(os.path.basename(csv_path))[0]
        out_summary = os.path.join(PLOTS_DIR, f"{base}_summary_metrics.csv")
        merged.to_csv(out_summary, index=False)
        print(f"\nSummary metrics saved: {out_summary}")
    else:
        print("\nNo per-player summary could be produced.")


if __name__ == "__main__":
    main()
