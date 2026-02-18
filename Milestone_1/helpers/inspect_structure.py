import json

filename = "../physics_data.json"

print(f"🕵️ Inspecting {filename}...")
try:
    with open(filename, 'r') as f:
        # Read the first line (the whole JSON object)
        line = f.readline()
        if not line:
            print("❌ Error: File is empty. Make sure you exported with rrrocket and included network frames (-n).")
            raise SystemExit(1)
        data = json.loads(line)

    # Validate presence of network frames
    if not isinstance(data, dict) or 'network_frames' not in data or data['network_frames'] in (None, {}):
        print("❌ Error: 'network_frames' is missing or null. Re-export the replay with rrrocket using the -n flag.")
        raise SystemExit(1)

    frames = data['network_frames'].get('frames') or []
    if not isinstance(frames, list) or len(frames) == 0:
        print("❌ Error: No frames found inside 'network_frames'. Re-export with rrrocket using the -n flag.")
        raise SystemExit(1)

    # Find the first frame that actually has actor updates
    for i, frame in enumerate(frames):
        actors = frame.get('updated_actors')

        # If we found data and it's a list (which caused the error)
        if actors and isinstance(actors, list) and len(actors) > 0:
            print(f"\n✅ Found Data in Frame {i}!")
            print("------------------------------------------------")
            print("Here is the structure of ONE actor update:")
            print(json.dumps(actors[0], indent=4))
            print("------------------------------------------------")
            break

except Exception as e:
    print(f"❌ Error: {e}")