import requests
import os
import glob
import sys
import json

# --- CONFIGURATION ---
API_KEY = "td4dBE8FuwEQDcPCwvBOvu4Ok5rr1qSWxLiNpNW5"  # <--- PASTE KEY HERE

# WSL/OneDrive Path
REPLAY_FOLDER = "/mnt/c/Users/brevi/OneDrive/Documents/My Games/Rocket League/TAGame/DemosEpic/*.replay"

OUTPUT_FILE = "match_stats.json"


def get_latest_replay():
    # Check folder exists
    folder_path = os.path.dirname(REPLAY_FOLDER)
    if not os.path.exists(folder_path):
        print(f"ERROR: Path not found: {folder_path}")
        return None

    list_of_files = glob.glob(REPLAY_FOLDER)
    if not list_of_files:
        print(f"No replays found in: {REPLAY_FOLDER}")
        return None

    return max(list_of_files, key=os.path.getctime)


def main():
    # 1. FIND REPLAY
    latest_replay = get_latest_replay()
    if not latest_replay:
        sys.exit(1)

    print(f"--- Processing Replay: {os.path.basename(latest_replay)} ---")

    # 2. UPLOAD
    print("1. Uploading...", end=" ")
    headers = {'Authorization': API_KEY}

    with open(latest_replay, 'rb') as f:
        r = requests.post(
            'https://ballchasing.com/api/v2/upload',
            headers=headers,
            files={'file': f},
            params={'visibility': 'private'}
        )

    if r.status_code == 201:
        # Success - New Upload
        replay_id = r.json()['id']
        print(f"Success! (ID: {replay_id})")

    elif r.status_code == 409:
        # Duplicate - Replay already exists
        print("Duplicate (Already Uploaded).")
        replay_id = r.json()['id']
        print(f"Using existing ID: {replay_id}")

    else:
        print(f"\nError Uploading: {r.status_code}\n{r.text}")
        sys.exit(1)

    # 3. GET JSON
    print("2. Fetching JSON...", end=" ")

    # The JSON data is available at the main replay endpoint
    json_url = f"https://ballchasing.com/api/replays/{replay_id}"

    r = requests.get(json_url, headers=headers)

    if r.status_code == 200:
        data = r.json()

        # Save to file
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(data, f, indent=4)

        print("Success!")
        print(f"Saved to: {os.path.abspath(OUTPUT_FILE)}")

    elif r.status_code == 404:
        print("\nERROR: 404 Not Found.")
        print("The replay exists but is set to PRIVATE by the original owner.")
        print("You cannot download stats for this specific file unless you are the owner.")
    else:
        print(f"\nFailed to download JSON: {r.status_code}")


if __name__ == "__main__":
    main()