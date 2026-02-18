import json

INPUT_FILE = "physics_data.json"


def scan_properties():
    print(f"📂 Scanning {INPUT_FILE} for all available metadata...")
    try:
        with open(INPUT_FILE, 'r') as f:
            # Read header
            data = json.loads(f.readline())

            # 1. Get the Decoder Ring (All possible properties in this file)
            objects = data.get('objects', [])

            # Filter for interesting ones (ignore common boring structures)
            interesting_props = sorted([
                obj for obj in objects
                if ":" in obj  # Properties usually look like "Class:Property"
                   and "HardAttach" not in obj
                   and "History" not in obj
            ])

            print("\n" + "=" * 50)
            print(f"📋 FOUND {len(interesting_props)} UNIQUE DATA FIELDS")
            print("=" * 50)

            # Group by Category for readability
            categories = {
                "Stats": ["Score", "Goals", "Saves", "Assists", "Demolish"],
                "Inputs": ["Throttle", "Steer", "Handbrake", "Jump", "Dodge"],
                "Physics": ["RigidBody", "Location", "Rotation", "Velocity"],
                "Boost": ["Boost", "Pickup"],
                "Game": ["SecondsRemaining", "Time", "Team", "OverTime"],
                "Cosmetic": ["Loadout", "Paint", "Title"]
            }

            for cat, keywords in categories.items():
                print(f"\n--- {cat.upper()} ---")
                found = [p for p in interesting_props if any(k in p for k in keywords)]
                for p in found:
                    print(f"  • {p}")
                    # Remove from main list so we don't print duplicates
                    if p in interesting_props: interesting_props.remove(p)

            print("\n--- EVERYTHING ELSE (Other Metadata) ---")
            for p in interesting_props:
                print(f"  • {p}")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    scan_properties()