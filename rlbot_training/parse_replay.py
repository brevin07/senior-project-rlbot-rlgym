import os
import sys
import json
import subprocess
import pandas as pd
import platform
import stat
import tarfile

# --- CONFIG ---
REPLAY_FILE = "my_replay.replay"
OUTPUT_FILE = "match_data.pkl"
JSON_TEMP = "temp_dump.json"

# Rattletrap v14.1.4
RATTLETRAP_VERSION = "14.1.4"
ARCHIVE_NAME = "rattletrap.tar.gz"
BINARY_NAME = "rattletrap"
RATTLETRAP_URL = f"https://github.com/tfausak/rattletrap/releases/download/{RATTLETRAP_VERSION}/rattletrap-{RATTLETRAP_VERSION}-linux-x64.tar.gz"


def install_rattletrap():
    """Downloads and extracts Rattletrap."""
    if os.path.exists(BINARY_NAME) and os.path.getsize(BINARY_NAME) > 1000000:
        return True

    print(f"Downloading Rattletrap v{RATTLETRAP_VERSION}...")
    try:
        subprocess.run(["curl", "-L", "-o", ARCHIVE_NAME, RATTLETRAP_URL], check=True)

        print("Extracting...")
        with tarfile.open(ARCHIVE_NAME, "r:gz") as tar:
            tar.extractall()

        if os.path.exists(ARCHIVE_NAME):
            os.remove(ARCHIVE_NAME)

        if os.path.exists(BINARY_NAME):
            os.chmod(BINARY_NAME, os.stat(BINARY_NAME).st_mode | stat.S_IEXEC)
            print("Rattletrap installed successfully!")
            return True
        return False
    except Exception as e:
        print(f"Installation failed: {e}")
        return False


def parse_with_rattletrap(replay_file):
    """Runs Rattletrap to convert Replay -> JSON."""
    if not os.path.exists(replay_file):
        print(f"Error: {replay_file} not found.")
        return False

    print(f"Decoding {replay_file} to JSON...")
    try:
        cmd = [f"./{BINARY_NAME}", "--compact", "-i", replay_file, "-o", JSON_TEMP]
        subprocess.run(cmd, check=True)
        return True
    except Exception as e:
        print(f"Rattletrap execution failed: {e}")
        return False


def extract_data_from_json():
    """Parses the JSON to extract physics data."""
    if not os.path.exists(JSON_TEMP):
        print("Error: JSON file was not created.")
        return

    print("Loading JSON into Python (This handles the massive file)...")
    try:
        with open(JSON_TEMP, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to load JSON: {e}")
        return

    print("Extracting frames...")
    frames = data.get('content', {}).get('body', {}).get('frames', [])

    actor_data = {}

    # --- HELPER FUNCTION FOR ROBUST EXTRACTION ---
    def safe_get_float(container, key):
        """Safely extracts a float from a dict that might be None or wrapped."""
        if not container or not isinstance(container, dict):
            return 0.0

        val = container.get(key, 0.0)

        # Handle { 'value': 123.45 } wrapper
        if isinstance(val, dict):
            return float(val.get('value', 0.0))

        # Handle None or direct value
        if val is None:
            return 0.0

        return float(val)

    for frame in frames:
        replications = frame.get('replications', [])
        for rep in replications:
            # 1. Safe Actor ID Unwrapping
            actor_id_raw = rep.get('actor_id')
            if isinstance(actor_id_raw, dict):
                actor_id = actor_id_raw.get('value')
            else:
                actor_id = actor_id_raw

            # 2. Safe Value Unwrapping
            value_raw = rep.get('value')
            if isinstance(value_raw, dict) and 'updated' not in value_raw:
                value = value_raw.get('value', {})
            else:
                value = value_raw

            # 3. Process Updates
            if not isinstance(value, dict): continue  # Skip if bad data
            updates = value.get('updated', [])

            for update in updates:
                attr_name = update.get('name', '')

                # 'ReplicatedRBState' is the standard physics attribute
                if 'ReplicatedRBState' in attr_name:
                    rb_val = update.get('value', {})
                    if not rb_val: continue

                    rb_state = rb_val.get('rigid_body_state', {})
                    if not rb_state: continue  # Skip empty states

                    if actor_id not in actor_data:
                        actor_data[actor_id] = {'vel_x': [], 'vel_y': [], 'vel_z': []}

                    # Extract Velocity
                    # CRITICAL FIX: explicit 'or {}' to prevent NoneType error
                    vel = rb_state.get('linear_velocity') or {}

                    vx = safe_get_float(vel, 'x')
                    vy = safe_get_float(vel, 'y')
                    vz = safe_get_float(vel, 'z')

                    actor_data[actor_id]['vel_x'].append(vx)
                    actor_data[actor_id]['vel_y'].append(vy)
                    actor_data[actor_id]['vel_z'].append(vz)

    print("Building DataFrame...")
    valid_players = {}
    for aid, stats in actor_data.items():
        if len(stats['vel_x']) > 50:
            name = f"Car_Actor_{aid}"
            df_p = pd.DataFrame(stats)
            df_p['boost'] = 0
            valid_players[name] = df_p

    if not valid_players:
        print("No physics actors found.")
        return

    df = pd.concat(valid_players.values(), axis=1, keys=valid_players.keys())
    df.to_pickle(OUTPUT_FILE)
    print(f"Success! Data saved to {OUTPUT_FILE}")

    if os.path.exists(JSON_TEMP):
        os.remove(JSON_TEMP)


if __name__ == "__main__":
    install_rattletrap()
    if parse_with_rattletrap(REPLAY_FILE):
        extract_data_from_json()