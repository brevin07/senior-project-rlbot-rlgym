import json

INPUT_FILE = "../physics_data.json"


def debug():
    with open(INPUT_FILE, 'r') as f:
        data = json.loads(f.readline())

    # 1. Create Decoder Ring
    objects = data['objects']
    id_to_name = {i: name for i, name in enumerate(objects)}

    print("--- 🕵️ LOOKING FOR CAR LINKS ---")

    # Scan frames for any property that looks like a link
    count = 0
    for frame in data['network_frames']['frames']:
        for actor in frame.get('updated_actors', []):
            obj_id = actor.get('object_id')
            prop_name = id_to_name.get(obj_id, "")

            # We are looking for "PlayerReplicationInfo" appearing in a PAWN (Car)
            # Standard name: "Engine.Pawn:PlayerReplicationInfo"
            if "PlayerReplicationInfo" in prop_name and "Pawn" in prop_name:
                print(f"\nFound Link Property: '{prop_name}'")
                print(f"Raw Value: {json.dumps(actor.get('attribute'), indent=2)}")
                count += 1
                if count >= 3: return  # Stop after 3 examples


debug()