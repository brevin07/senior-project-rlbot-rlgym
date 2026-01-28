import os
from datetime import datetime

from rlgym_sim.utils.reward_functions import RewardFunction
from rlgym_sim.utils.gamestates import GameState, PlayerData
from rlgym_sim.utils.math import cosine_similarity
from rlgym.rocket_league.done_conditions import GoalCondition, TimeoutCondition, NoTouchTimeoutCondition

from rlgym.rocket_league.rlviser import RLViserRenderer  # Make sure this import is at the top
# Disable RLViser visualization to prevent WSL2/software rendering issues

from typing import Dict, Any
import json
import socket
import subprocess

import numpy as np
from rlgym.api import Renderer, RLGym
from rlgym.rocket_league.api import GameState, Car

# Local imports - adjust paths as needed for your project structure
from rlgym_ppo.util import RLGymV2GymWrapper
from rlgym_sim.utils.reward_functions.common_rewards import SaveBoostReward

from reward_funcs.reward_functions import *
from LoggingCombinedReward import CombinedReward


def get_windows_host_ip() -> str:
    """Get the Windows host IP from WSL2 for UDP communication."""
    try:
        # Method 1: Get from resolv.conf (most reliable)
        result = subprocess.run(
            ["cat", "/etc/resolv.conf"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if "nameserver" in line:
                return line.split()[1]
    except Exception:
        pass
    # Fallback to localhost (works if not in WSL2)
    return "127.0.0.1"


WINDOWS_HOST_IP = get_windows_host_ip()
print(f"Windows host IP for RocketSimVis: {WINDOWS_HOST_IP}")


class RocketSimVisRenderer(Renderer[GameState]):
    """
    A renderer that sends game state information to RocketSimVis.
    Run RocketSimVis.exe on Windows first: https://github.com/ZealanL/RocketSimVis
    """

    def __init__(self, udp_ip=None, udp_port=9273):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_ip = udp_ip or WINDOWS_HOST_IP
        self.udp_port = udp_port
        print(f"RocketSimVisRenderer sending to {self.udp_ip}:{self.udp_port}")

    @staticmethod
    def write_physobj(physobj):
        return {
            'pos': physobj.position.tolist(),
            'forward': physobj.forward.tolist(),
            'up': physobj.up.tolist(),
            'vel': physobj.linear_velocity.tolist(),
            'ang_vel': physobj.angular_velocity.tolist()
        }

    @staticmethod
    def write_car(car: Car, controls=None):
        j = {
            'team_num': int(car.team_num),
            'phys': RocketSimVisRenderer.write_physobj(car.physics),
            'boost_amount': car.boost_amount,
            'on_ground': bool(car.on_ground),
            "has_flipped_or_double_jumped": bool(car.has_flipped or car.has_double_jumped),
            'is_demoed': bool(car.is_demoed),
            'has_flip': bool(car.can_flip)
        }
        if controls is not None:
            if isinstance(controls, np.ndarray):
                controls = {k: float(v) for k, v in zip(
                    ("throttle", "steer", "pitch", "yaw", "roll", "jump", "boost", "handbrake"),
                    controls
                )}
            j['controls'] = controls
        return j

    def render(self, state: GameState, shared_info: Dict[str, Any]) -> Any:
        controls = shared_info.get("controls", {})
        j = {
            'ball_phys': self.write_physobj(state.ball),
            'cars': [
                self.write_car(car, controls.get(agent_id))
                for agent_id, car in state.cars.items()
            ],
            'boost_pad_states': (state.boost_pad_timers <= 0).tolist()
        }
        try:
            self.sock.sendto(json.dumps(j).encode('utf-8'), (self.udp_ip, self.udp_port))
        except Exception as e:
            pass  # Don't crash training if visualization fails

    def close(self):
        self.sock.close()


class BallPositionRenderer(Renderer[GameState]):
    """A simple renderer that prints the ball's position."""

    def render(self, state: GameState, shared_info: Dict[str, Any]) -> Any:
        print(f"Ball position: {state.ball.position}")

    def close(self):
        """Called when the environment is closed."""
        pass


def build_rlgym_v2_env(log_dir="reward_logs"):
    from rlgym.rocket_league.action_parsers import LookupTableAction, RepeatAction
    from rlgym.rocket_league.done_conditions import GoalCondition, NoTouchTimeoutCondition, TimeoutCondition, AnyCondition
    from rlgym.rocket_league.obs_builders import DefaultObs
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import MutatorSequence, FixedTeamSizeMutator, KickoffMutator
    from rlgym.rocket_league import common_values
    from rlgym.rocket_league.reward_functions import TouchReward, GoalReward
    # IMPORTANT: This import allows the bot to talk to the window
    from rlgym.rocket_league.rlviser import RLViserRenderer

    spawn_opponents = True
    team_size = 1
    blue_team_size = team_size
    orange_team_size = team_size if spawn_opponents else 0
    action_repeat = 8
    no_touch_timeout_seconds = 30
    game_timeout_seconds = 300

    action_parser = RepeatAction(LookupTableAction(), repeats=action_repeat)
    termination_condition = GoalCondition()
    truncation_condition = TimeoutCondition(timeout_seconds=300)

    # --- THE OVERNIGHT "COMPLETE PLAYER" CONFIG ---
    reward_fn = CombinedReward(
        # 1. SCORING (The King)
        # Keeps the main focus on winning.
        (ManualGoalReward(), 10.0),

        # 2. DEFENSE (The Queen)
        # Teaches rotation. If they aren't attacking, they must be between ball and goal.
        (DefensivePositionReward(), 2.0),

        # 3. OFFENSE (The Driver)
        # Replaces "ShootTowardsGoal". Rewarded for moving ball to opponent net.
        (VelocityBallToGoalReward(), 1.0),

        # 4. MECHANICS (The Teacher)
        # Replaces standard "TouchReward".
        # Ground touch = 1.0 * 1.5 = 1.5 pts
        # Air touch = 2.0 * 1.5 = 3.0 pts (Incentivizes aerials)
        (HighTouchReward(min_height=150, aerial_multiplier=2.0), 1.5),

        # 5. ENGAGEMENT (The Helper)
        # Lower weight. Just keeps them moving if they are far away.
        (SpeedTowardBallReward(), 0.1),

        # 6. FUNDAMENTALS
        (FaceBallReward(), 0.05),
        (SaveBoostReward(), 0.001),  # Tiny weight so they don't fear using boost

        log_dir=log_dir
    )

    obs_builder = DefaultObs(
        zero_padding=None,
        pos_coef=np.asarray([1 / common_values.SIDE_WALL_X,
                             1 / common_values.BACK_NET_Y,
                             1 / common_values.CEILING_Z]),
        ang_coef=1 / np.pi,
        lin_vel_coef=1 / common_values.CAR_MAX_SPEED,
        ang_vel_coef=1 / common_values.CAR_MAX_ANG_VEL,
        boost_coef=1 / 100.0
    )

    state_mutator = MutatorSequence(
        FixedTeamSizeMutator(blue_size=blue_team_size, orange_size=orange_team_size),
        KickoffMutator()
    )

    # Use the standard library renderer
    renderer = RLViserRenderer()

    rlgym_env = RLGym(
        state_mutator=state_mutator,
        obs_builder=obs_builder,
        action_parser=action_parser,
        reward_fn=reward_fn,

        # Pass them separately here:
        termination_cond=termination_condition,
        truncation_cond=truncation_condition,

        transition_engine=RocketSimEngine(),
        renderer=renderer
    )

    return RLGymV2GymWrapper(rlgym_env)


if __name__ == "__main__":
    from rlgym_ppo import Learner

    # --- 1. SETUP LOGGING FOLDER STRUCTURE ---
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_folder_name = f"Session_{timestamp}"
    current_log_dir = os.path.join("reward_logs", session_folder_name)

    os.makedirs(current_log_dir, exist_ok=True)
    print(f"NEW SESSION: Logging rewards to: {current_log_dir}")


    # Number of parallel environments
    n_proc = 12
    min_inference_size = max(1, int(round(n_proc * 0.9)))

    learner = Learner(
        build_rlgym_v2_env,
        n_proc=n_proc,
        min_inference_size=min_inference_size,
        metrics_logger=None,
        ppo_batch_size=100_000,
        policy_layer_sizes=[2048, 2048, 1024, 1024],
        critic_layer_sizes=[2048, 2048, 1024, 1024],
        ts_per_iteration=100_000,
        exp_buffer_size=300_000,
        ppo_minibatch_size=50_000,
        ppo_ent_coef=0.01,
        policy_lr=1e-5,
        critic_lr=1e-5,
        ppo_epochs=2,
        standardize_returns=True,
        standardize_obs=False,
        save_every_ts=1_000_000,
        timestep_limit=5_000_000_000,
        log_to_wandb=False,
        render=False,  # Sends visualization to RocketSimVis on Windows

       checkpoint_load_folder="D:\\PycharmProjects\\RLGym_Bot_Training\\rlbot\\data\\checkpoints\\rlgym-ppo-run-1769157999478113400\\2245131382"
    )
    learner.learn()
    input()