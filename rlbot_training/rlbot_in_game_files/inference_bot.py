import numpy as np
import torch
import torch.nn as nn
from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket

from rlgym_sim.utils.gamestates import GameState

# --- IMPORT YOUR SETUP ---
# We need the exact same Observation Builder you used during training.
# Assuming 'build_rlgym_v2_env' is in 'rlbot_starting_code.py'
from rlbot_training.rlbot_starting_code import build_rlgym_v2_env


# --- RE-DEFINE THE NETWORK ---
# This must match your training config: [2048, 2048, 1024, 1024]
class AgentPolicy(nn.Module):
    def __init__(self, input_dim, output_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 2048),
            nn.Tanh(),
            nn.Linear(2048, 2048),
            nn.Tanh(),
            nn.Linear(2048, 1024),
            nn.Tanh(),
            nn.Linear(1024, 1024),
            nn.Tanh(),
            nn.Linear(1024, output_dim),
            nn.Softmax(dim=-1)
        )

    def forward(self, x):
        return self.net(x)


class MyBot(BaseAgent):
    def __init__(self, name, team, index):
        super().__init__(name, team, index)
        self.obs_builder = None
        self.policy = None
        self.game_state = None
        self.action_parser = None

    def initialize_agent(self):
        # 1. Setup the Environment helper
        # We create a dummy env just to get the obs_builder and action_parser
        env = build_rlgym_v2_env()
        self.obs_builder = env.obs_builder
        self.action_parser = env.action_parser

        # 2. Load the Model
        # OBS SIZE: 89 (Default) - Change if you used a custom one
        # ACT SIZE: 8 (Default discrete)
        obs_size = env.observation_space.shape[0]
        act_size = env.action_space.n

        self.policy = AgentPolicy(obs_size, act_size)

        # LOAD YOUR CHECKPOINT HERE
        # Make sure 'my_model.pt' is in the same folder, or provide full path
        checkpoint = torch.load("my_model.pt", map_location=torch.device('cpu'))

        # If the checkpoint is a state dict (common in rlgym-ppo), load it:
        if isinstance(checkpoint, dict):
            self.policy.load_state_dict(checkpoint)
        else:
            self.policy = checkpoint  # It might be a full scripted module

        self.policy.eval()  # Set to evaluation mode
        self.game_state = GameState(self.get_field_info())

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        # 1. Update Game State
        self.game_state.decode(packet)

        # 2. Build Observation
        player = self.game_state.players[self.index]
        obs = self.obs_builder.build_obs(player, self.game_state, self.action_parser)
        obs_tensor = torch.as_tensor(obs, dtype=torch.float32)

        # 3. Query Policy
        with torch.no_grad():
            action_probs = self.policy(obs_tensor)
            action_idx = torch.argmax(action_probs).item()

        # 4. Convert to Controls
        # The Action Parser turns the number (0-7) into [Throttle, Steer, Jump...]
        controls = self.action_parser.parse_actions([action_idx], self.game_state)[0]

        # Return to RLBot
        controller = SimpleControllerState()
        controller.throttle = controls[0]
        controller.steer = controls[1]
        controller.pitch = controls[2]
        controller.yaw = controls[3]
        controller.roll = controls[4]
        controller.jump = controls[5] > 0
        controller.boost = controls[6] > 0
        controller.handbrake = controls[7] > 0

        return controller