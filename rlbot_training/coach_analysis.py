import pandas as pd
import torch
import numpy as np
import pickle

# --- CONFIG ---
REPLAY_DATA = "match_data.pkl"  # The file you created in KR 1
MODEL_FILE = "./rlbot_in_game_files/my_model.pt"


# --- RE-DEFINE YOUR AGENT (Same as inference_bot.py) ---
class AgentPolicy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        # Define the layers exactly as trained
        self.model = torch.nn.Sequential(
            torch.nn.Linear(92, 2048),  # Input size 89 (adjust if needed)
            torch.nn.Tanh(),
            torch.nn.Linear(2048, 2048),
            torch.nn.Tanh(),
            torch.nn.Linear(2048, 1024),
            torch.nn.Tanh(),
            torch.nn.Linear(1024, 1024),
            torch.nn.Tanh(),
            torch.nn.Linear(1024, 90),  # Output actions
            torch.nn.Softmax(dim=-1)
        )

    def forward(self, x):
        return self.model(x)


def load_data():
    print("Loading Ballchasing CSV...")
    # Read the Ballchasing file
    df = pd.read_csv("ballchasing_stats.csv", sep=';')  # Ballchasing uses ; as separator sometimes

    # FILTER: Find your player
    # Ballchasing columns look like: "color", "player name", "time", "pos_x"
    # We want to filter for just YOU.
    my_name = "BrevinsPC"  # CHANGE THIS to your in-game name

    human_df = df[df['player name'] == my_name].copy()

    # RENAME columns to match what our bot expects
    # Ballchasing headers -> Our headers
    human_df = human_df.rename(columns={
        'pos_x': 'vel_x',  # Note: We need velocity, sometimes ballchasing gives pos
        'pos_y': 'vel_y',
        'pos_z': 'vel_z'
    })

    # CRITICAL: Ballchasing CSV often gives Position, but our Bot needs Velocity.
    # We must calculate velocity manually (Position Now - Position Before).
    human_df['vel_x'] = human_df['pos_x'].diff() / human_df['time'].diff()
    human_df['vel_y'] = human_df['pos_y'].diff() / human_df['time'].diff()
    human_df['vel_z'] = human_df['pos_z'].diff() / human_df['time'].diff()

    return human_df


def run_analysis():
    # 1. Load Model
    model = torch.load(MODEL_FILE, map_location='cpu')
    if isinstance(model, dict):
        # Handle state dict loading if necessary
        policy = AgentPolicy()
        policy.load_state_dict(model)
        model = policy
    model.eval()

    # 2. Load Human Data
    data = load_data()

    mistakes = []

    print("Analyzing player decisions...")
    # Iterate through frames (skip every 10 to be faster)
    for i in range(0, len(data), 10):
        row = data.iloc[i]

        # --- BUILD OBSERVATION ---
        # This is the HARD part. You have to reconstruct the "Observation Array" (89 numbers)
        # from the replay data exactly how RLGym does it.
        # For this prototype, we will just use placeholders to show the logic.

        # Realistically, you need to map:
        # row['vel_x'] -> obs[0]
        # row['vel_y'] -> obs[1]
        # ... etc

        # diverse placeholder for demo
        fake_obs = torch.zeros(92)
        fake_obs[0] = row.get('vel_x', 0) / 2300.0  # Normalize inputs!

        # --- ASK THE BOT ---
        with torch.no_grad():
            action_probs = model(fake_obs)
            bot_action = torch.argmax(action_probs).item()

        # --- COMPARE ---
        # Replays don't easily store "What button you pressed", they store "Resulting Physics"
        # So we infer: If z_velocity suddenly jumped positive, Human Pressed JUMP.

        human_jumped = row.get('vel_z', 0) > 300  # Rough heuristic
        bot_wanted_jump = (bot_action == 5)  # Assuming index 5 is Jump

        if bot_wanted_jump and not human_jumped:
            mistakes.append(f"Frame {i}: Bot would have jumped (Aerial Opportunity?)")

    # 3. Report
    print(f"\nAnalysis Complete. Found {len(mistakes)} potential improvements.")
    for m in mistakes[:10]:
        print(m)


if __name__ == "__main__":
    run_analysis()