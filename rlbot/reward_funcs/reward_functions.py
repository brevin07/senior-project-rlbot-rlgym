import os
from typing import List, Dict, Any
from rlgym.api import RewardFunction, AgentID
from rlgym.rocket_league.api import GameState
from rlgym.rocket_league import common_values
import numpy as np


class SpeedTowardBallReward(RewardFunction[AgentID, GameState, float]):
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(self, agents: List[AgentID], state: GameState, is_terminated: Dict[AgentID, bool],
                    is_truncated: Dict[AgentID, bool], shared_info: Dict[str, Any]) -> Dict[AgentID, float]:
        rewards = {}
        for agent in agents:
            car = state.cars[agent]
            car_physics = car.physics if car.is_orange else car.inverted_physics
            ball_physics = state.ball if car.is_orange else state.inverted_ball

            player_vel = car_physics.linear_velocity
            pos_diff = ball_physics.position - car_physics.position
            dist_to_ball = np.linalg.norm(pos_diff)
            dir_to_ball = pos_diff / dist_to_ball

            speed_toward_ball = np.dot(player_vel, dir_to_ball)
            reward = max(speed_toward_ball / common_values.CAR_MAX_SPEED, 0.0)

            if np.isnan(reward):
                reward = 0.0

            rewards[agent] = np.clip(reward, 0.0, 1.0)

        #print(f"Rewards from SpeedTowardBallReward: {rewards}")
        return rewards


class InAirReward(RewardFunction[AgentID, GameState, float]):
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(self, agents: List[AgentID], state: GameState, is_terminated: Dict[AgentID, bool],
                    is_truncated: Dict[AgentID, bool], shared_info: Dict[str, Any]) -> Dict[AgentID, float]:
        rewards = {}
        for agent in agents:
            reward = float(not state.cars[agent].on_ground)
            if np.isnan(reward):
                reward = 0.0
            rewards[agent] = reward
        return rewards


class VelocityBallToGoalReward(RewardFunction[AgentID, GameState, float]):
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(self, agents: List[AgentID], state: GameState, is_terminated: Dict[AgentID, bool],
                    is_truncated: Dict[AgentID, bool], shared_info: Dict[str, Any]) -> Dict[AgentID, float]:
        rewards = {}
        for agent in agents:
            car = state.cars[agent]
            ball = state.ball
            goal_y = -common_values.BACK_NET_Y if car.is_orange else common_values.BACK_NET_Y

            ball_vel = ball.linear_velocity
            pos_diff = np.array([0, goal_y, 0]) - ball.position
            dist = np.linalg.norm(pos_diff)
            dir_to_goal = pos_diff / dist

            vel_toward_goal = np.dot(ball_vel, dir_to_goal)
            reward = max(vel_toward_goal / common_values.BALL_MAX_SPEED, 0)

            if np.isnan(reward):
                reward = 0.0

            rewards[agent] = np.clip(reward, 0.0, 1.0)

        #print(f"Rewards from VelocityTowardBallReward: {rewards}")
        return rewards


# Adjust this import for your package layout
import math

import math
from typing import Dict

from typing import Dict, Any

class DeltaDistanceToBallReward(RewardFunction):
    """
    +reward when distance(agent, ball) decreases (prev - current).
    """
    def __init__(self, epsilon: float = 1e-6):
        self.eps = float(epsilon)
        self.prev_dist: Dict[Any, float] = {}

    def reset(self, agents, initial_state, shared_info):
        self.prev_dist.clear()
        bx, by, bz = _ball_pos(initial_state)
        for agent in agents:
            car = initial_state.cars[agent]
            cx, cy, cz = _get_pos(car)
            d = _norm3(bx - cx, by - cy, bz - cz) + self.eps
            self.prev_dist[agent] = d

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards: Dict[Any, float] = {}
        bx, by, bz = _ball_pos(state)
        for agent in agents:
            car = state.cars[agent]
            cx, cy, cz = _get_pos(car)
            d = _norm3(bx - cx, by - cy, bz - cz) + self.eps
            prev = self.prev_dist.get(agent, d)
            rewards[agent] = prev - d  # >0 when moving closer
            self.prev_dist[agent] = d
        return rewards








class FaceBallReward(RewardFunction[AgentID, GameState, float]):
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(self, agents: List[AgentID], state: GameState,
                    is_terminated: Dict[AgentID, bool],
                    is_truncated: Dict[AgentID, bool],
                    shared_info: Dict[str, Any]) -> Dict[AgentID, float]:
        rewards = {}
        for agent in agents:
            car = state.cars[agent]
            car_physics = car.physics if car.is_orange else car.inverted_physics
            ball_physics = state.ball if car.is_orange else state.inverted_ball

            car_pos = car_physics.position
            ball_pos = ball_physics.position
            car_forward = car_physics.forward

            dir_to_ball = ball_pos - car_pos
            norm = np.linalg.norm(dir_to_ball)
            if norm < 1e-6:
                reward = 0.0
            else:
                dir_to_ball /= norm
                reward = np.dot(car_forward, dir_to_ball)

            if np.isnan(reward) or np.isinf(reward):
                reward = 0.0

            # Scale [-1, 1] dot product to [0, 1]
            rewards[agent] = np.clip((reward + 1) / 2, 0.0, 1.0)

        #print(f"Rewards from FaceTowardBallReward: {rewards}")
        return rewards




class HitBallWhileFacingReward(RewardFunction[AgentID, GameState, float]):
    """
    Rewards the agent if it touches the ball while facing it (within an angle threshold).
    """

    def __init__(self, angle_threshold_degrees=30.0, reward_amount=1.0):
        self.threshold_cos = np.cos(np.deg2rad(angle_threshold_degrees))
        self.reward_amount = reward_amount

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(self, agents: List[AgentID], state: GameState,
                    is_terminated: Dict[AgentID, bool],
                    is_truncated: Dict[AgentID, bool],
                    shared_info: Dict[str, Any]) -> Dict[AgentID, float]:

        rewards = {}

        for agent in agents:
            car = state.cars[agent]

            # Check if car touched the ball
            if car.ball_touches <= 0:
                rewards[agent] = 0.0
                continue

            # Calculate if facing the ball
            to_ball = state.ball.position - car.physics.position
            to_ball_norm = np.linalg.norm(to_ball)
            if to_ball_norm < 1e-6:
                rewards[agent] = 0.0
                continue

            to_ball_unit = to_ball / to_ball_norm
            forward = car.physics.forward
            forward_norm = np.linalg.norm(forward)
            if forward_norm < 1e-6:
                rewards[agent] = 0.0
                continue

            forward_unit = forward / forward_norm
            dot = np.dot(forward_unit, to_ball_unit)

            rewards[agent] = self.reward_amount if dot >= self.threshold_cos else 0.0

        #print(f"Rewards from HitBallWhileFacingReward: {rewards}")
        return rewards


class FrontFlipHitReward(RewardFunction[AgentID, GameState, float]):
    def __init__(self, flip_window_ticks: int = 12, pitch_threshold: float = -1.5):
        """
        :param flip_window_ticks: How many ticks after a jump to consider a flip (12 ticks ~0.2s at 60Hz)
        :param pitch_threshold: Angular velocity threshold to detect front flip (usually negative pitch)
        """
        self.flip_window_ticks = flip_window_ticks
        self.pitch_threshold = pitch_threshold
        self.last_jump_tick = {}

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        self.last_jump_tick = {agent: -9999 for agent in agents}

    def get_rewards(self, agents: List[AgentID], state: GameState, is_terminated: Dict[AgentID, bool],
                    is_truncated: Dict[AgentID, bool], shared_info: Dict[str, Any]) -> Dict[AgentID, float]:
        rewards = {}
        current_tick = state.tick_count

        for agent in agents:
            car = state.cars[agent]
            reward = 0.0

            # If the car just jumped and is going up, save the tick
            if car.on_ground is False and car.physics.linear_velocity[2] > 100:
                self.last_jump_tick[agent] = current_tick

            ticks_since_jump = current_tick - self.last_jump_tick.get(agent, -9999)

            is_front_flip = (
                0 < ticks_since_jump <= self.flip_window_ticks and
                car.physics.angular_velocity[1] < self.pitch_threshold
            )

            if is_front_flip and car.ball_touches > 0:
                reward = 1.0

            rewards[agent] = reward

        #print(f"Rewards from FrontFlipHitReward: {rewards}")
        return rewards



# class PenalizeNonForwardFlips(RewardFunction[AgentID, GameState, float]):
#     """
#     Penalizes flips that are not forward (i.e., sideways or backward).
#     """
#
#     def __init__(self, penalty: float = -1.0, threshold: float = 0.3):
#         self.penalty = penalty
#         self.threshold = threshold  # Controls how lenient we are on sideways torque
#
#     def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
#         pass
#
#     def get_rewards(
#         self,
#         agents: List[AgentID],
#         state: GameState,
#         is_terminal: Dict[AgentID, bool],
#         is_truncated: Dict[AgentID, bool],
#         shared_info: Dict[str, Any]
#     ) -> Dict[AgentID, float]:
#         rewards = {}
#
#         for agent in agents:
#             car = state.cars[agent]
#
#             reward = 0.0
#
#             # Detect if the bot is flipping
#             if car.is_flipping:
#                 flip_torque = car.flip_torque  # np.array([x, y, z])
#
#                 x, y, _ = flip_torque
#                 # Penalize if it's not a forward flip (strong negative X, little Y)
#                 if x > -self.threshold or abs(y) > self.threshold:
#                     reward += self.penalty
#
#             rewards[agent] = reward
#
#         #print(f"Rewards from PenalizeNonForwardFlips: {rewards}")
#         return rewards







class ShootTowardsGoalReward(RewardFunction[AgentID, GameState, float]):
    """
    Rewards the agent when the ball's velocity is aimed toward the opponent's goal.
    """

    def __init__(self, reward_amount: float = 1.0):
        self.reward_amount = reward_amount

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(
        self,
        agents: List[AgentID],
        state: GameState,
        is_terminated: Dict[AgentID, bool],
        is_truncated: Dict[AgentID, bool],
        shared_info: Dict[str, Any],) -> Dict[AgentID, float]:

        rewards = {}
        for agent in agents:
            car = state.cars[agent]
            ball = state.ball

            goal_y = -common_values.BACK_NET_Y if car.is_orange else common_values.BACK_NET_Y
            goal_pos = np.array([0, goal_y, ball.position[2]])
            to_goal = goal_pos - ball.position
            norm = np.linalg.norm(to_goal)
            if norm < 1e-6:
                rewards[agent] = 0.0
                continue

            to_goal /= norm
            ball_velocity = ball.linear_velocity
            dot = np.dot(ball_velocity, to_goal)
            reward = max(dot / common_values.BALL_MAX_SPEED, 0.0)

            rewards[agent] = reward * self.reward_amount

        #print(f"Rewards from ShootTowardsGoalReward {rewards}")
        return rewards


class CollectBoostReward(RewardFunction[AgentID, GameState, float]):
    def __init__(self, threshold: float = 20.0, reward: float = 0.2):
        self.threshold = threshold  # only reward if boost gain exceeds this (to avoid abuse of small pads)
        self.reward_value = reward

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        for agent in agents:
            shared_info[f"prev_boost_{agent}"] = initial_state.cars[agent].boost_amount

    def get_rewards(self, agents: List[AgentID], state: GameState,
                    is_terminated: Dict[AgentID, bool],
                    is_truncated: Dict[AgentID, bool],
                    shared_info: Dict[str, Any]) -> Dict[AgentID, float]:
        rewards = {}

        for agent in agents:
            car = state.cars[agent]
            prev_boost = shared_info.get(f"prev_boost_{agent}", car.boost_amount)
            shared_info[f"prev_boost_{agent}"] = car.boost_amount

            boost_delta = car.boost_amount - prev_boost

            # Only reward significant pickups (like 100 boost pads)
            if boost_delta >= self.threshold:
                rewards[agent] = self.reward_value
            else:
                rewards[agent] = 0.0
        #print(f"Rewards from CollectBoostReward: {rewards}")
        return rewards



class PenalizeIdleBoostCollecting(RewardFunction[AgentID, GameState, float]):
    def __init__(self, penalty=-0.01):
        self.penalty = penalty
        self.prev_boosts = {}

    def reset(self, agents, initial_state, shared_info):
        self.prev_boosts = {agent: initial_state.cars[agent].boost_amount for agent in agents}

    def get_rewards(self, agents, state, is_terminal, is_truncated, shared_info):
        rewards = {}
        for agent in agents:
            car = state.cars[agent]
            prev_boost = self.prev_boosts.get(agent, 0.0)
            gained_boost = car.boost_amount > prev_boost
            far_from_ball = np.linalg.norm(car.physics.position - state.ball.position) > 2000
            is_full_boost = car.boost_amount > 90

            if gained_boost and (is_full_boost or far_from_ball):
                rewards[agent] = self.penalty
            else:
                rewards[agent] = 0.0
            self.prev_boosts[agent] = car.boost_amount

        #print(f"Rewards from PenalizeIdleBoostCollecting: {rewards}")
        return rewards


class RewardBoostTowardBall(RewardFunction[AgentID, GameState, float]):
    def __init__(self, reward_amount=0.2):
        self.reward_amount = reward_amount
        self.prev_boosts = {}

    def reset(self, agents, initial_state, shared_info):
        self.prev_boosts = {agent: initial_state.cars[agent].boost_amount for agent in agents}

    def get_rewards(self, agents, state, is_terminal, is_truncated, shared_info):
        rewards = {}
        for agent in agents:
            car = state.cars[agent]
            prev_boost = self.prev_boosts.get(agent, 0.0)
            reward = 0.0

            if car.boost_amount > prev_boost:
                direction = state.ball.position - car.physics.position
                norm = np.linalg.norm(direction)
                if norm > 1e-6:
                    direction /= norm
                    velocity = car.physics.linear_velocity
                    speed_toward_ball = np.dot(direction, velocity)
                    if speed_toward_ball > 0:
                        reward = self.reward_amount * (speed_toward_ball / 2300)
            rewards[agent] = reward
            self.prev_boosts[agent] = car.boost_amount

        #print(f"Rewards from RewardBoostTowardBall: {rewards}")
        return rewards





class BoostIntoBallReward(RewardFunction):
    """
    Rewards the bot for touching the ball while recently using boost.
    Uses tick count and boost.active_atime to approximate boost usage.
    """

    def __init__(self, reward_amount: float = 1.0, tick_threshold: int = 3, tick_rate: int = 60):
        """
        :param reward_amount: Reward given for hitting the ball while boosting.
        :param tick_threshold: How many ticks ago boost must have been activated.
        :param tick_rate: Game ticks per second (default 60 for Rocket League).
        """
        self.reward_amount = reward_amount
        self.tick_threshold = tick_threshold
        self.tick_rate = tick_rate

    def reset(self, agents: List[int], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(self,
                    agents: List[int],
                    state: GameState,
                    is_terminal: Dict[int, bool],
                    is_truncated: Dict[int, bool],
                    shared_info: Dict[str, Any]) -> Dict[int, float]:

        rewards = {}
        current_time = state.tick_count / self.tick_rate  # Approximate seconds

        for agent in agents:
            car = state.cars[agent]

            # Time since last boost activation in seconds
            time_since_boost = current_time - car.boost_active_time

            if car.ball_touches > 0 and time_since_boost <= self.tick_threshold / self.tick_rate:
                rewards[agent] = self.reward_amount
            else:
                rewards[agent] = 0.0
        #print(f"Rewards from BoostIntoBallReward: {rewards}")
        return rewards



class ProductiveCollectBoost(CollectBoostReward):
    def __init__(self, min_boost_level=40.0):
        super().__init__()
        self.min_boost_level = min_boost_level

    def get_rewards(self, agents, state, is_term, is_trunc, shared):
        base = super().get_rewards(agents, state, is_term, is_trunc, shared)
        out = {}
        for a in agents:
            low = state.boost[a] < self.min_boost_level
            recent_progress = shared.get("recent_progress", {}).get(a, False)
            out[a] = base[a] if (low or recent_progress) else 0.0
        return out





import math
import numpy as np
from typing import Dict, Any, List, Hashable

AgentID = Hashable  # or your project’s AgentID

class PenalizeNonForwardFlips(RewardFunction[AgentID, GameState, float]):
    """
    Penalize non-forward (side/back) flips that don't turn into a touch soon.
    Edge-triggered: at most one penalty per flip start.
    Robust to different Car/GameState schemas.
    """

    def __init__(
        self,
        penalty: float = -0.01,
        horizon: int = 18,
        align_mode: str = "ball",   # "ball" or "goal"
        min_speed: float = 300.0,   # uu/s; ignore slow recovery hops
        min_align_dot: float = 0.35,
        near_ball_dist: float = 1600.0
    ):
        self.penalty = float(penalty)
        self.horizon = int(horizon)
        self.align_mode = align_mode
        self.min_speed = float(min_speed)
        self.min_align_dot = float(min_align_dot)
        self.near_ball_dist = float(near_ball_dist)

        self.prev_flipping: Dict[AgentID, bool] = {}
        self.armed: Dict[AgentID, bool] = {}
        self.frames_left: Dict[AgentID, int] = {}

    # ========= schema helpers (adapt to whatever exists) =========
    # Position -----------------------------------------------------
    def _pos3(self, obj):
        # Try common layouts
        for path in (
            ("position",),
            ("pos",),
            ("car_data","position"),
            ("physics","position"),
            ("physics","location"),
            ("loc",),
        ):
            try:
                v = self._get_attr_chain(obj, path)
                arr = np.asarray(v, dtype=float)
                if arr.size >= 3:
                    return arr[:3]
            except Exception:
                pass
        raise AttributeError("Could not find 3D position on object")

    # Velocity -----------------------------------------------------
    def _vel3(self, obj):
        for path in (
            ("linear_velocity",),
            ("velocity",),
            ("vel",),
            ("car_data","linear_velocity"),
            ("physics","linear_velocity"),
            ("physics","velocity"),
        ):
            try:
                v = self._get_attr_chain(obj, path)
                arr = np.asarray(v, dtype=float)
                if arr.size >= 3:
                    return arr[:3]
            except Exception:
                pass
        # Fallback to zeros if not exposed; this only weakens the speed gate
        return np.zeros(3, dtype=float)

    # Forward unit vector (XY) ------------------------------------
    def _fwd_xy(self, car):
        # 1) direct forward vector
        for path in (
            ("forward",),
            ("forward_vec",),
            ("car_data","forward"),
            ("car_data","forward_vec"),
        ):
            try:
                v = self._get_attr_chain(car, path)
                v = np.asarray(v, dtype=float)
                if v.size >= 2:
                    xy = v[:2]
                    n = np.linalg.norm(xy) + 1e-9
                    return xy / n
            except Exception:
                pass

        # 2) rotation matrix
        for path in (
            ("rotation_matrix",),
            ("rot_mat",),
            ("orientation",),  # sometimes a 3x3
            ("car_data","rotation_matrix"),
        ):
            try:
                R = np.asarray(self._get_attr_chain(car, path), dtype=float)
                if R.shape == (3,3):
                    # forward is often the first or second column — try a couple:
                    candidates = (R[:,0], R[:,1], R[0,:], R[1,:])
                    for c in candidates:
                        xy = np.asarray(c[:2], dtype=float)
                        n = np.linalg.norm(xy)
                        if n > 1e-6:
                            return xy / n
            except Exception:
                pass

        # 3) quaternion
        for path in (
            ("quat",),
            ("quaternion",),
            ("car_data","quat"),
        ):
            try:
                q = np.asarray(self._get_attr_chain(car, path), dtype=float).flatten()
                if q.size >= 4:
                    # Convert quaternion -> forward (x-axis) unit vector
                    # q = [w, x, y, z] or [x,y,z,w]; try to detect:
                    if abs(q[0]) <= 1.0 and abs(q[-1]) <= 1.0:
                        # assume [w, x, y, z]
                        w, x, y, z = q[0], q[1], q[2], q[3]
                    else:
                        # assume [x, y, z, w]
                        x, y, z, w = q[0], q[1], q[2], q[3]
                    # forward X of body frame in world:
                    fx = 1 - 2*(y*y + z*z)
                    fy = 2*(x*y + w*z)
                    # fz = 2*(x*z - w*y)  # unused
                    xy = np.array([fx, fy], dtype=float)
                    n = np.linalg.norm(xy) + 1e-9
                    return xy / n
            except Exception:
                pass

        # 4) yaw (radians)
        for path in (
            ("yaw",),
            ("car_data","yaw"),
            ("rotation","yaw"),
            ("euler","yaw"),
        ):
            try:
                yaw = float(self._get_attr_chain(car, path))
                return np.array([math.cos(yaw), math.sin(yaw)], dtype=float)
            except Exception:
                pass

        # Last resort: assume +X forward
        return np.array([1.0, 0.0], dtype=float)

    # Team id ------------------------------------------------------
    def _team(self, car, default=0):
        for path in (("team",), ("team_num",), ("car_data","team")):
            try:
                return int(self._get_attr_chain(car, path))
            except Exception:
                pass
        return default

    # Vector toward ball / goal -----------------------------------
    def _to_ball_xy(self, state, car):
        d = self._pos3(state.ball) - self._pos3(car)
        dxy = d[:2]
        dist = float(np.linalg.norm(dxy))
        u = dxy / (dist + 1e-9)
        return u, dist

    def _to_goal_xy(self, state, car):
        # Prefer an explicit field if provided by your env:
        for path in (("opponent_goal_center",), ("goal_opponent",)):
            try:
                g = np.asarray(self._get_attr_chain(state, path), dtype=float)
                d = g[:2] - self._pos3(car)[:2]
                n = np.linalg.norm(d) + 1e-9
                return d / n
            except Exception:
                pass
        # Otherwise pick based on team (Standard map y=±5120)
        y_goal = 5120.0 if self._team(car, 0) == 0 else -5120.0
        d = np.array([0.0, y_goal], dtype=float) - self._pos3(car)[:2]
        n = np.linalg.norm(d) + 1e-9
        return d / n

    def _useful_dir_xy(self, state, car):
        return self._to_goal_xy(state, car) if self.align_mode == "goal" else self._to_ball_xy(state, car)[0]

    # Generic attribute chain getter -------------------------------
    def _get_attr_chain(self, obj, path):
        x = obj
        for name in path:
            x = getattr(x, name)
        return x
    # ===============================================================

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        self.prev_flipping = {a: False for a in agents}
        self.armed = {a: False for a in agents}
        self.frames_left = {a: 0 for a in agents}

    def get_rewards(
        self,
        agents: List[AgentID],
        state: GameState,
        is_terminal: Dict[AgentID, bool],
        is_truncated: Dict[AgentID, bool],
        shared_info: Dict[str, Any]
    ) -> Dict[AgentID, float]:

        out = {a: 0.0 for a in agents}
        touched = shared_info.get("recent_touched_ball", {}) if isinstance(shared_info, dict) else {}

        for a in agents:
            car = state.cars[a]

            flipping = bool(getattr(car, "is_flipping", False))
            flip_started = flipping and not self.prev_flipping.get(a, False)
            self.prev_flipping[a] = flipping

            if flip_started and not self.armed.get(a, False):
                # Your original torque criterion (check sign once on your env!)
                torque = np.asarray(getattr(car, "flip_torque", [0.0, 0.0, 0.0]), dtype=float)
                tx, ty = float(torque[0]), float(torque[1])
                non_forward = (tx > -0.3) or (abs(ty) > 0.3)

                # Context gates
                fwd = self._fwd_xy(car)
                useful = self._useful_dir_xy(state, car)
                align = float(np.dot(fwd, useful))
                speed = float(np.linalg.norm(self._vel3(car)[:2]))
                _, dist_ball = self._to_ball_xy(state, car)

                near_and_aligned = (dist_ball < self.near_ball_dist) and (align >= self.min_align_dot)

                if non_forward and (speed >= self.min_speed) and (not near_and_aligned):
                    self.armed[a] = True
                    self.frames_left[a] = self.horizon

            if self.armed.get(a, False):
                if bool(touched.get(a, False)):
                    self.armed[a] = False
                    self.frames_left[a] = 0
                else:
                    self.frames_left[a] -= 1
                    if self.frames_left[a] <= 0:
                        out[a] += self.penalty
                        self.armed[a] = False

        return out



from typing import Dict, Tuple

def _normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    x, y, z = v
    n = math.sqrt(x*x + y*y + z*z) + 1e-6
    return x / n, y / n, z / n

from typing import Dict, Any

class GatedNonForwardFlipPenalty(RewardFunction):
    """
    Applies a penalty only when ALL are true:
      - shared_info["non_forward_flip_event"].get(agent, False) is True,
      - distance to ball <= max_range,
      - facing quality toward ball < min_face_dot
    Notes:
      • Provide the event flag via `shared_info` each step. A simple pattern is:
          shared_info["non_forward_flip_event"] = {agent_id: True/False, ...}
      • Penalty value is negative.
    """
    def __init__(self, per_event: float = -0.15, max_range: float = 2200.0, min_face_dot: float = 0.2):
        self.per_event = float(per_event)
        self.max_range = float(max_range)
        self.min_face_dot = float(min_face_dot)

    def reset(self, agents, initial_state, shared_info):
        # Ensure the key exists to avoid KeyErrors (not required, but convenient)
        if isinstance(shared_info, dict) and "non_forward_flip_event" not in shared_info:
            shared_info["non_forward_flip_event"] = {}

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards: Dict[Any, float] = {}
        bx, by, bz = _ball_pos(state)
        events = {}
        if isinstance(shared_info, dict):
            events = shared_info.get("non_forward_flip_event", {}) or {}

        for agent in agents:
            # Only consider steps where your detector flagged a non-forward flip.
            if not bool(events.get(agent, False)):
                rewards[agent] = 0.0
                continue

            car = state.cars[agent]
            cx, cy, cz = _get_pos(car)
            dist = _norm3(bx - cx, by - cy, bz - cz)
            if dist > self.max_range:
                rewards[agent] = 0.0
                continue

            fvx, fvy, fvz = _get_vel_forward_proxy(car)
            dirx, diry, dirz = _normalize3(bx - cx, by - cy, bz - cz)
            face_dot = fvx*dirx + fvy*diry + fvz*dirz

            rewards[agent] = self.per_event if face_dot < self.min_face_dot else 0.0

        return rewards



import math
from typing import Dict, Tuple

def _norm3(x: float, y: float, z: float) -> float:
    return math.sqrt(x*x + y*y + z*z)

def _normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    x, y, z = v
    n = _norm3(x, y, z) + 1e-6
    return (x/n, y/n, z/n)

def _approx_forward_vec(car) -> Tuple[float, float, float]:
    """
    Your fork doesn't expose rotation directly. Use velocity dir as a proxy for 'facing'.
    If the car is nearly stationary, fall back to world +X.
    """
    v = getattr(getattr(car, "physics", None), "linear_velocity", (0.0, 0.0, 0.0))
    vx = getattr(v, "x", v[0] if isinstance(v, (list, tuple)) else 0.0)
    vy = getattr(v, "y", v[1] if isinstance(v, (list, tuple)) else 0.0)
    vz = getattr(v, "z", v[2] if isinstance(v, (list, tuple)) else 0.0)
    if _norm3(vx, vy, vz) < 1e-3:
        return (1.0, 0.0, 0.0)
    return _normalize((vx, vy, vz))

from typing import Dict, Any

class ContextualCollectBoostReward(RewardFunction):
    """
    Reward boost collection only when:
      - boost% < min_boost, and
      - no immediate ball play: (dist_to_ball > min_dist_to_ball) or (facing quality < min_face_dot)
    You don’t have to detect collection events; this is a per‑step shaping reward.
    """
    def __init__(self, base: float = 0.02, min_boost: int = 30,
                 min_dist_to_ball: float = 1400.0, min_face_dot: float = 0.2):
        self.base = float(base)
        self.min_boost = int(min_boost)
        self.min_dist_to_ball = float(min_dist_to_ball)
        self.min_face_dot = float(min_face_dot)

    def reset(self, agents, initial_state, shared_info):
        pass  # stateless

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards: Dict[Any, float] = {}
        bx, by, bz = _ball_pos(state)
        for agent in agents:
            car = state.cars[agent]

            # Boost percentage: many forks store [0,1]; multiplying by 100 makes threshold intuitive.
            boost_pct = float(getattr(car, "boost_amount", 0.0)) * 100.0
            low_boost = boost_pct < self.min_boost

            cx, cy, cz = _get_pos(car)
            dist = _norm3(bx - cx, by - cy, bz - cz)

            fvx, fvy, fvz = _get_vel_forward_proxy(car)
            dirx, diry, dirz = _normalize3(bx - cx, by - cy, bz - cz)
            face_dot = fvx*dirx + fvy*diry + fvz*dirz  # alignment toward ball

            no_immediate_play = (dist > self.min_dist_to_ball) or (face_dot < self.min_face_dot)
            rewards[agent] = self.base if (low_boost and no_immediate_play) else 0.0
        return rewards



import math
from typing import Tuple, Any

def _norm3(x: float, y: float, z: float) -> float:
    return math.sqrt(x*x + y*y + z*z)

def _normalize3(x: float, y: float, z: float) -> Tuple[float, float, float]:
    n = _norm3(x, y, z) + 1e-6
    return (x/n, y/n, z/n)

def _get_pos(car: Any) -> Tuple[float, float, float]:
    # Prefer car.position; fall back to car.physics.position if needed.
    if hasattr(car, "position"):
        p = car.position
        return (float(p[0]), float(p[1]), float(p[2]))
    p = getattr(getattr(car, "physics", None), "position", (0.0, 0.0, 0.0))
    if isinstance(p, (list, tuple)):
        return (float(p[0]), float(p[1]), float(p[2]))
    # RLBot-style Vector3
    return (float(getattr(p, "x", 0.0)), float(getattr(p, "y", 0.0)), float(getattr(p, "z", 0.0)))

def _get_vel_forward_proxy(car: Any) -> Tuple[float, float, float]:
    # Use velocity direction as a proxy for facing (since rotation isn’t directly available).
    v = getattr(getattr(car, "physics", None), "linear_velocity", (0.0, 0.0, 0.0))
    if isinstance(v, (list, tuple)):
        vx, vy, vz = float(v[0]), float(v[1]), float(v[2])
    else:
        vx = float(getattr(v, "x", 0.0)); vy = float(getattr(v, "y", 0.0)); vz = float(getattr(v, "z", 0.0))
    if _norm3(vx, vy, vz) < 1e-3:
        return (1.0, 0.0, 0.0)  # default forward if nearly stationary
    return _normalize3(vx, vy, vz)

def _ball_pos(state: Any) -> Tuple[float, float, float]:
    bp = state.ball.position
    return (float(bp[0]), float(bp[1]), float(bp[2]))


# rewards_custom.py
from typing import Dict, Any
import math

def _pos(car):
    p = getattr(getattr(car, "physics", None), "position", (0,0,0))
    if isinstance(p, (list, tuple)): return float(p[0]), float(p[1]), float(p[2])
    return float(getattr(p, "x", 0.0)), float(getattr(p, "y", 0.0)), float(getattr(p, "z", 0.0))



def _dist(a, b):  # a,b: (x,y,z)
    dx,dy,dz = a[0]-b[0], a[1]-b[1], a[2]-b[2]
    return math.sqrt(dx*dx + dy*dy + dz*dz)

class AirborneFarPenalty(RewardFunction):
    """
    Penalize being airborne when far from ball: discourages random flips / jumps.
    """
    def __init__(self, per_step: float = -0.01, min_dist: float = 1400.0, min_z: float = 60.0):
        self.per_step = float(per_step)
        self.min_dist = float(min_dist)
        self.min_z = float(min_z)  # consider > min_z to be 'airborne' in forks without wheel contact

    def reset(self, agents, initial_state, shared_info): pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards: Dict[Any, float] = {}
        ball = _ball_pos(state)
        for a in agents:
            car = state.cars[a]
            pos = _pos(car)
            d = _dist(pos, ball)
            z = pos[2]
            airborne_far = (z > self.min_z) and (d > self.min_dist)
            rewards[a] = self.per_step if airborne_far else 0.0
        return rewards


# rewards_custom.py
from typing import Dict, Any

class PostTouchVelocityToGoalReward(RewardFunction):
    def __init__(self, window_s: float = 0.7):
        self.window_s = float(window_s)
        self.last_touch_time: Dict[Any, float] = {}

    def reset(self, agents, initial_state, shared_info):
        self.last_touch_time.clear()

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        # Expect shared_info["last_touch_time"][agent] updated by your env/wrapper when agent touches the ball.
        rewards: Dict[Any, float] = {}
        lt = (shared_info.get("last_touch_time", {}) if isinstance(shared_info, dict) else {}) or {}
        tnow = getattr(state, "game_seconds", 0.0)

        # Compute ball velocity toward opponent goal
        # Replace with your field’s actual opponent goal center for the agent’s team.
        # For a simple one-net drill, define goal_pos once.
        goal = getattr(shared_info, "opponent_goal", None)
        if goal is None and isinstance(shared_info, dict):
            goal = shared_info.get("opponent_goal", (0.0, 5120.0, 0.0))  # example for blue shooting +Y

        bx, by, bz = state.ball.position
        bv = getattr(state.ball, "linear_velocity", (0.0, 0.0, 0.0))
        if isinstance(bv, (list, tuple)):
            bvx, bvy, bvz = float(bv[0]), float(bv[1]), float(bv[2])
        else:
            bvx = float(getattr(bv, "x", 0.0)); bvy = float(getattr(bv, "y", 0.0)); bvz = float(getattr(bv, "z", 0.0))

        gx, gy, gz = goal
        dx, dy, dz = gx - bx, gy - by, gz - bz
        # unit direction to goal
        norm = (dx*dx + dy*dy + dz*dz) ** 0.5 + 1e-6
        ux, uy, uz = dx/norm, dy/norm, dz/norm
        # projection: ball speed along goal direction (can be negative)
        v_to_goal = bvx*ux + bvy*uy + bvz*uz

        for a in agents:
            last_t = lt.get(a, -1e9)
            active = (tnow - last_t) <= self.window_s
            rewards[a] = v_to_goal if active else 0.0
        return rewards


class GatedSpeedTowardBall(RewardFunction):
    def __init__(self, base_rf, max_dist=2200.0, min_z=30.0, weight=1.0):
        self.base = base_rf
        self.max_dist = float(max_dist)
        self.min_z = float(min_z)
        self.weight = float(weight)
    def reset(self, agents, initial_state, shared_info):
        if hasattr(self.base, "reset"): self.base.reset(agents, initial_state, shared_info)
    def get_rewards(self, agents, state, is_term, is_trunc, shared_info):
        bx, by, bz = state.ball.position
        out = self.base.get_rewards(agents, state, is_term, is_trunc, shared_info)
        gated = {}
        for a in agents:
            car = state.cars[a]
            cx, cy, cz = getattr(car, "position", state.cars[a].physics.position)
            dist = ((bx-cx)**2 + (by-cy)**2 + (bz-cz)**2)**0.5
            grounded = (cz <= self.min_z)  # or car.has_wheel_contact if available
            gated[a] = (out[a] * self.weight) if (grounded and dist <= self.max_dist) else 0.0
        return gated



# rewards_custom.py
from typing import Dict, Any, Tuple
import math

def _pos3(obj) -> Tuple[float, float, float]:
    p = getattr(getattr(obj, "physics", None), "position", getattr(obj, "position", (0.0,0.0,0.0)))
    if isinstance(p, (list, tuple)):
        return float(p[0]), float(p[1]), float(p[2])
    return float(getattr(p, "x", 0.0)), float(getattr(p, "y", 0.0)), float(getattr(p, "z", 0.0))

def _vel3(obj) -> Tuple[float, float, float]:
    v = getattr(getattr(obj, "physics", None), "linear_velocity", (0.0,0.0,0.0))
    if isinstance(v, (list, tuple)):
        return float(v[0]), float(v[1]), float(v[2])
    return float(getattr(v, "x", 0.0)), float(getattr(v, "y", 0.0)), float(getattr(v, "z", 0.0))

def _unit(dx: float, dy: float, dz: float) -> Tuple[float, float, float]:
    n = math.sqrt(dx*dx + dy*dy + dz*dz) + 1e-6
    return dx/n, dy/n, dz/n

from rlgym.rocket_league import common_values as CV

class OnTouchVelocityToGoalReward(RewardFunction):
    def __init__(
        self,
        min_ball_speed_on_touch: float = 150.0,  # ↓ lower to make it fire more
        min_align_dot: float = 0.25,             # 0..1; how "on target" the touch must be
        use_goal_center: bool = True,            # center of goal line vs back net
        scale: float = 1.0 / 1000.0              # tame units (uu/s) into ~0..1ish
    ):
        self.min_ball_speed_on_touch = float(min_ball_speed_on_touch)
        self.min_align_dot = float(min_align_dot)
        self.use_goal_center = bool(use_goal_center)
        self.scale = float(scale)

    def reset(self, *args, **kwargs):
        pass

    def _opp_goal_target(self, team: int):
        if self.use_goal_center:
            # aim at the *goal line center* so we don't over-penalize near-net touches
            y = CV.GOAL_THRESHOLD if team == CV.BLUE_TEAM else -CV.GOAL_THRESHOLD
        else:
            # original behavior: back of net
            y = CV.BACK_NET_Y if team == CV.BLUE_TEAM else -CV.BACK_NET_Y
        return np.array([0.0, y, CV.GOAL_HEIGHT / 2.0], dtype=float)

    def get_rewards(self, agents, state, *_):
        bx, by, bz = state.ball.position
        bv = np.asarray(state.ball.linear_velocity, dtype=float)
        vmag = float(np.linalg.norm(bv) + 1e-9)
        ball_pos = np.array([bx, by, bz], dtype=float)

        out = {}
        for a in agents:
            car = state.cars[a]
            if not bool(getattr(car, "ball_touched", False)):
                out[a] = 0.0
                continue

            # speed gate
            if vmag < self.min_ball_speed_on_touch:
                out[a] = 0.0
                continue

            # alignment gate
            goal = self._opp_goal_target(car.team_num)
            u_goal = _unit(goal - ball_pos)          # toward goal
            u_vel = _unit(bv)                        # ball direction after touch
            align = float(np.dot(u_vel, u_goal))     # -1..1

            if align < self.min_align_dot:
                out[a] = 0.0
                continue

            # pay projection (speed * alignment), scaled
            out[a] = max(0.0, vmag * align) * self.scale
        return out


from rlgym.api import RewardFunction, AgentID
from rlgym.rocket_league.api import GameState
import numpy as np


# --- Custom Reward Definitions for RLGym v2 ---

class SaveBoostReward(RewardFunction):
    def reset(self, agents, initial_state, shared_info):
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        return {agent: state.cars[agent].boost_amount for agent in agents}


class DemoReward(RewardFunction):
    def reset(self, agents, initial_state, shared_info):
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards = {agent: 0.0 for agent in agents}
        for agent in agents:
            # If the car is demoed, it means someone demoed it.
            # (Note: This is a simplified check. For perfect attribution
            # we'd check the 'attacker' ID, but this works for basic training)
            if state.cars[agent].is_demoed:
                # We need to find who killed them.
                # In 1v1, it's always the opponent.
                pass
        return rewards


# For simplicity, let's just use a simplified Event/Demo reward
# or skip it if it's too complex to track attacker IDs in the snippet.


# 2) Pay near the ball when (a) close and (b) roughly facing it (using velocity dir as facing proxy)
class NearBallVelocityToGoalReward(RewardFunction):
    """
    Rewards ball velocity toward goal when the agent is close enough to plausibly be influencing play,
    and roughly facing the ball (using car velocity as facing proxy).
    """
    def __init__(self, max_dist_to_ball: float = 1700.0, min_face_dot: float = 0.15,
                 opponent_goal=(0.0, 5120.0, 0.0)):
        self.max_dist = float(max_dist_to_ball)
        self.min_face_dot = float(min_face_dot)
        self.goal = tuple(float(x) for x in opponent_goal)

    def reset(self, agents, initial_state, shared_info):  # stateless
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        bx, by, bz = _pos3(state.ball)
        bvx, bvy, bvz = _vel3(state.ball)
        gx, gy, gz = self.goal
        ugx, ugy, ugz = _unit(gx - bx, gy - by, gz - bz)      # goal direction from ball
        v_to_goal = bvx*ugx + bvy*ugy + bvz*ugz               # projection of ball vel toward goal

        out: Dict[Any, float] = {}
        for a in agents:
            car = state.cars[a]
            cx, cy, cz = _pos3(car)
            dx, dy, dz = bx - cx, by - cy, bz - cz
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            # facing proxy = velocity direction toward the ball
            cvx, cvy, cvz = _vel3(car)
            spd = math.sqrt(cvx*cvx + cvy*cvy + cvz*cvz)
            if spd < 1e-3:
                face_dot = -1.0  # stationary: treat as not facing well
            else:
                ux, uy, uz = _unit(cvx, cvy, cvz)
                bxdirx, bxdiry, bxdirz = _unit(dx, dy, dz)
                face_dot = ux*bxdirx + uy*bxdiry + uz*bxdirz

            active = (dist <= self.max_dist) and (face_dot >= self.min_face_dot)
            out[a] = v_to_goal if active else 0.0
        return out


# class GoalReward(RewardFunction[AgentID, GameState, float]):
#     """
#     A RewardFunction that gives a reward of 1 if the agent's team scored a goal, -1 if the opposing team scored a goal,
#     """
#
#     def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
#         pass
#
#     def get_rewards(self, agents: List[AgentID], state: GameState, is_terminated: Dict[AgentID, bool],
#                     is_truncated: Dict[AgentID, bool], shared_info: Dict[str, Any]) -> Dict[AgentID, float]:
#
#         agent_reward_dict = {agent: self._get_reward(agent, state) for agent in agents}
#
#         # with open("./combined_fns_logs/Goalreward.txt", "a") as f:
#         #     f.write(f"Agent Rewards: {agent_reward_dict}")
#         return agent_reward_dict
#
#     def _get_reward(self, agent: AgentID, state: GameState) -> float:
#         if state.goal_scored:
#             #print(f"Scored by team {state.scoring_team}")
#             return 1 if state.scoring_team == state.cars[agent].team_num else -1
#         else:
#             return 0



# rewards_flip.py
def _team_num(car) -> int:
    # Works across forks that use team OR team_num
    return int(getattr(car, "team", getattr(car, "team_num", 0)))

def _ang3(obj) -> Tuple[float, float, float]:
    # <- This is the missing helper
    w = getattr(getattr(obj, "physics", None), "angular_velocity", getattr(obj, "angular_velocity", (0, 0, 0)))
    if isinstance(w, (list, tuple)):
        return float(w[0]), float(w[1]), float(w[2])
    return float(getattr(w, "x", 0.0)), float(getattr(w, "y", 0.0)), float(getattr(w, "z", 0.0))


import numpy as np
from typing import Dict, List, Any, Tuple
from rlgym.api import AgentID, RewardFunction
from rlgym.rocket_league.api import GameState

class FlipTowardBallReward(RewardFunction[AgentID, GameState, float]):
    """
    Pays ONLY when the agent actually flips toward the ball.
    - Reward once at flip onset if velocity points toward ball.
    - Small per-step reward while actively flipping and aligned.
    - Touch bonus if a touch happens during/after the flip.
    """

    def __init__(
        self,
        min_dist_to_ball: float = 1400.0,
        min_speed: float = 400.0,
        min_align_dot: float = 0.35,
        onset_reward: float = 0.6,
        per_step_reward: float = 0.05,
        touch_bonus: float = 0.06,
        cooldown_steps: int = 8
    ):
        self.min_dist = float(min_dist_to_ball)
        self.min_speed = float(min_speed)
        self.min_align = float(min_align_dot)
        self.onset_reward = float(onset_reward)
        self.per_step_reward = float(per_step_reward)
        self.touch_bonus = float(touch_bonus)
        self.cooldown_steps = int(cooldown_steps)

        self.prev_has_flipped: Dict[AgentID, bool] = {}
        self.prev_ball_touches: Dict[AgentID, int] = {}
        self.cooldown: Dict[AgentID, int] = {}

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        self.prev_has_flipped = {a: False for a in agents}
        self.prev_ball_touches = {a: 0 for a in agents}
        self.cooldown = {a: 0 for a in agents}

    def _align_toward_ball(self, car, ball_pos) -> Tuple[float, float, float]:
        """Return (alignment_dot, speed, dist). Always a tuple."""
        car_pos = car.physics.position
        car_vel = car.physics.linear_velocity

        to_ball = ball_pos - car_pos
        vnorm = float(np.linalg.norm(car_vel))
        dnorm = float(np.linalg.norm(to_ball))

        if vnorm < 1e-6 or dnorm < 1e-6:
            return (-1.0, 0.0, float("inf"))

        car_vel_dir = car_vel / vnorm
        to_ball_dir = to_ball / dnorm
        align = float(np.dot(car_vel_dir, to_ball_dir))  # [-1, 1]
        return (align, vnorm, dnorm)

    def get_rewards(
        self,
        agents: List[AgentID],
        state: GameState,
        is_terminated: Dict[AgentID, bool],
        is_truncated: Dict[AgentID, bool],
        shared_info: Dict[str, Any],
    ) -> Dict[AgentID, float]:
        rewards: Dict[AgentID, float] = {a: 0.0 for a in agents}
        ball_pos = state.ball.position

        for a in agents:
            car = state.cars[a]

            # Decrement cooldown if active
            if self.cooldown[a] > 0:
                self.cooldown[a] -= 1

            align, speed, dist = self._align_toward_ball(car, ball_pos)
            alignment_ok = align >= self.min_align
            speed_ok = speed >= self.min_speed
            dist_ok = dist <= self.min_dist

            # Rising edge detection for flip onset
            just_flipped = (car.has_flipped and not self.prev_has_flipped[a])

            # Pay on flip onset only if aligned, close enough, moving fast enough, and off cooldown
            if just_flipped and self.cooldown[a] == 0 and alignment_ok and speed_ok and dist_ok:
                # scale onset by alignment in [min_align..1]
                scale = (align - self.min_align) / (1.0 - self.min_align + 1e-6)
                scale = max(0.0, min(1.0, scale))
                rewards[a] += self.onset_reward * scale
                self.cooldown[a] = self.cooldown_steps

            # Small per-step reward while actively flipping and aligned
            if car.is_flipping and alignment_ok and speed_ok and dist_ok:
                rewards[a] += self.per_step_reward * align

            # Touch bonus if ball_touches increased during/just after flip
            if car.ball_touches > self.prev_ball_touches[a] and (car.is_flipping or just_flipped):
                rewards[a] += self.touch_bonus

            # Update trackers
            self.prev_has_flipped[a] = bool(car.has_flipped)
            self.prev_ball_touches[a] = int(car.ball_touches)

        return rewards







class GoalConeVelocityReward(RewardFunction):
    """
    Rewards ball velocity that would pass between the posts (goal cone),
    and lightly penalizes lateral (sidewall) exits in attacking third.
    No shared_info needed. Assumes attacking toward +Y.
    """
    def __init__(self, post_x=892.0, goal_y=5120.0, cone_pad=120.0,
                 y_gate=3000.0, lateral_penalty=0.001):
        self.post_x = float(post_x)
        self.goal_y = float(goal_y)
        self.cone_x = self.post_x - float(cone_pad)  # slightly inside posts
        self.y_gate = float(y_gate)
        self.lat_pen = float(lateral_penalty)

    def reset(self, agents, initial_state, shared_info): pass

    def get_rewards(self, agents, state, is_term, is_trunc, shared_info):
        (bx,by,bz) = _pos3(state.ball)
        (bvx,bvy,bvz) = _vel3(state.ball)

        # in-cone scalar (prefer velocity that heads through the posts)
        # project one step; gate by x inside posts
        in_posts = (abs(bx) <= self.cone_x)
        v_to_goal_line = max(bvy, 0.0)  # +Y only

        # lateral penalty in attacking third (discourage slamming into side wall near net)
        lat = abs(bvx)
        near_goal_third = by > self.y_gate
        base = (v_to_goal_line * (1.0 if in_posts else 0.3))  # still give a little if slightly off
        cone_reward = 0.001 * base  # small scale; we’ll weight in CombinedReward
        side_pen = -self.lat_pen * lat if (near_goal_third and not in_posts) else 0.0

        agent_reward_dict = {a: cone_reward + side_pen for a in agents}


        log_folder = "./combined_fns_logs"
        log_file_path = os.path.join(log_folder, "GoalConeVelocityReward.txt")

        with open(log_file_path, "a") as f:
            f.write(f"Cone reward per agent: {agent_reward_dict}")

        return agent_reward_dict



class ChallengeFlipReward(RewardFunction):
    """
    Detect flip (airborne+high angular vel). If both agent and nearest opponent are close to ball,
    reward car velocity toward ball for a short window, with touch bonus.
    """
    def __init__(self, window_steps=12, agent_ball_max=1400.0, opp_ball_max=1500.0,
                 min_z_air=40.0, min_angvel=4.0, touch_bonus=0.05, v_scale=0.001):
        self.win = int(window_steps)
        self.ab_max = float(agent_ball_max)
        self.ob_max = float(opp_ball_max)
        self.min_z = float(min_z_air)
        self.min_w = float(min_angvel)
        self.touch_bonus = float(touch_bonus)
        self.v_scale = float(v_scale)
        self._timer: Dict[Any, int] = {}
        self._prev_air: Dict[Any, bool] = {}

    def reset(self, agents, initial_state, shared_info):
        self._timer = {a:0 for a in agents}
        self._prev_air = {a:False for a in agents}

    def get_rewards(self, agents, state, is_term, is_trunc, shared_info):
        (bx,by,bz) = _pos3(state.ball)
        out: Dict[Any, float] = {}

        # Pre-make a list of opponents per agent
        car_ids = list(agents)
        for a in agents:
            car_a = state.cars[a]
            (ax,ay,az) = _pos3(car_a)
            (avx,avy,avz) = _vel3(car_a)
            aw = getattr(getattr(car_a,"physics",None), "angular_velocity", (0,0,0))
            if not isinstance(aw,(list,tuple)):
                aw = (float(getattr(aw,"x",0.0)), float(getattr(aw,"y",0.0)), float(getattr(aw,"z",0.0)))
            wx,wy,wz = aw
            wmag = _norm3(wx,wy,wz)
            airborne = az > self.min_z

            # detect flip start
            if (not self._prev_air.get(a,False)) and airborne and wmag >= self.min_w:
                self._timer[a] = self.win
            self._prev_air[a] = airborne

            # find nearest opponent
            best_d = 1e9
            for b in car_ids:
                if b == a: continue
                if _team_num(state.cars[b]) == _team_num(state.cars[a]):
                    continue
                (ox,oy,oz) = _pos3(state.cars[b])
                d = _norm3(bx-ox, by-oy, bz-oz)
                if d < best_d: best_d = d

            r = 0.0
            if self._timer.get(a,0) > 0:
                d_agent = _norm3(bx-ax, by-ay, bz-az)
                # active only if both are contesting
                if (d_agent <= self.ab_max) and (best_d <= self.ob_max):
                    ubx,uby,ubz = _unit(bx-ax, by-ay, bz-az)
                    v_to_ball = max(avx*ubx + avy*uby + avz*ubz, 0.0)
                    r += self.v_scale * v_to_ball
                    if bool(getattr(car_a,"ball_touched",False)):
                        r += self.touch_bonus
                self._timer[a] -= 1

            out[a] = r
        return out

# This reward encourages the bot to:
# - rotate back when the opponent is near the ball on the bot’s half,
# - intercept the ball if the opponent is threatening a shot

class DefensiveRotationReward(RewardFunction[AgentID, GameState, float]):

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass  # No internal state needed

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards = {agent: 0.0 for agent in agents}
        ball_pos = state.ball.position

        for agent in agents:
            car = state.cars[agent]
            if car.is_demoed:
                continue

            # Find nearest opponent
            opponent_cars = [
                state.cars[other]
                for other in state.cars
                if other != agent and car.team_num != state.cars[other].team_num
            ]
            if not opponent_cars:
                continue

            closest_opp = min(opponent_cars, key=lambda opp: np.linalg.norm(opp.physics.position - ball_pos))

            # Check if bot is on its own half
            own_half_sign = 1 if car.team_num == 0 else -1
            on_own_half = np.sign(car.physics.position[1]) == own_half_sign

            # Check if opponent is close to ball
            opp_close = np.linalg.norm(closest_opp.physics.position - ball_pos) < 900

            # Check if bot is retreating (velocity vector points toward its own half)
            retreating = np.dot(car.physics.linear_velocity, np.array([0, own_half_sign, 0])) < 0

            if on_own_half and opp_close:
                if retreating:
                    rewards[agent] += 0.2

                # Reward for being close to own goal under pressure
                own_goal_y = -5120 if car.team_num == 0 else 5120
                dist_to_goal = np.linalg.norm(car.physics.position - np.array([0, own_goal_y, 0]))
                if dist_to_goal < 1200:
                    rewards[agent] += 0.3

                # Reward for clearing the ball with speed and direction
                if (
                        np.linalg.norm(car.physics.linear_velocity) > 500 and
                        np.dot(car.physics.linear_velocity, ball_pos - car.physics.position) > 0
                ):
                    rewards[agent] += 0.3

        return rewards


class AerialAwarenessReward(RewardFunction[AgentID, GameState, float]):
    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass  # No internal state needed

    def get_rewards(self, agents: List[AgentID], state: GameState, is_terminated: Dict[AgentID, bool],
                    is_truncated: Dict[AgentID, bool], shared_info: Dict[str, Any]) -> Dict[AgentID, float]:
        rewards = {agent: 0.0 for agent in agents}
        ball_pos = state.ball.position
        ball_vel = state.ball.linear_velocity

        for agent in agents:
            car = state.cars[agent]
            if car.is_demoed:
                continue

            ball_is_rising = ball_vel[2] > 0 and ball_pos[2] > 800
            ball_is_falling = ball_vel[2] < 0 and ball_pos[2] > 250

            if ball_is_rising and car.boost_amount < 40:
                rewards[agent] += 0.05

            dist_to_ball = np.linalg.norm(ball_pos - car.physics.position)
            is_jumping = not car.on_ground and car.physics.position[2] > 50

            if ball_is_falling and is_jumping and dist_to_ball < 800:
                rewards[agent] += 0.3

        return rewards


class BallVelocityToGoalAlignmentReward(RewardFunction[AgentID, GameState, float]):
    def __init__(self, min_ball_speed: float = 300.0, weight: float = 1.0):
        self.min_ball_speed = float(min_ball_speed)
        self.weight = float(weight)

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(
        self, agents: List[AgentID], state: GameState,
        is_terminated: Dict[AgentID, bool], is_truncated: Dict[AgentID, bool],
        shared_info: Dict[str, Any]
    ) -> Dict[AgentID, float]:
        rewards = {a: 0.0 for a in agents}

        ball_pos = state.ball.position
        ball_vel = state.ball.linear_velocity
        speed = float(np.linalg.norm(ball_vel))
        if speed < self.min_ball_speed:
            return rewards

        for a in agents:
            team = state.cars[a].team_num
            target = np.array([0.0, 5120.0, 0.0]) if team == 0 else np.array([0.0, -5120.0, 0.0])
            to_goal = target - ball_pos

            vdir = ball_vel / (speed + 1e-9)
            gdir = to_goal / (np.linalg.norm(to_goal) + 1e-9)
            dot = max(0.0, float(np.dot(vdir, gdir)))  # only reward forward-to-goal component

            rewards[a] = self.weight * dot
        return rewards


def _safe_norm(v):
    n = np.linalg.norm(v)
    return v / (n + 1e-9)

class CarToBallAlignmentReward(RewardFunction[AgentID, GameState, float]):
    def __init__(self, max_dist: float = 2200.0, min_speed: float = 0.0, weight: float = 1.0):
        self.max_dist = float(max_dist)
        self.min_speed = float(min_speed)
        self.weight = float(weight)

    def reset(self, agents: List[AgentID], initial_state: GameState, shared_info: Dict[str, Any]) -> None:
        pass

    def get_rewards(
        self, agents: List[AgentID], state: GameState,
        is_terminated: Dict[AgentID, bool], is_truncated: Dict[AgentID, bool],
        shared_info: Dict[str, Any]
    ) -> Dict[AgentID, float]:
        rewards = {a: 0.0 for a in agents}
        ball_pos = state.ball.position

        for a in agents:
            car = state.cars[a]
            car_pos = car.physics.position
            car_fwd = _safe_norm(car.physics.rotation_mtx @ np.array([1.0, 0.0, 0.0]))  # car forward vector
            to_ball = ball_pos - car_pos
            dist = np.linalg.norm(to_ball)
            if dist > self.max_dist:
                continue

            to_ball_dir = _safe_norm(to_ball)
            dot = float(np.dot(car_fwd, to_ball_dir))  # [-1,1]
            # map [-1,1] -> [0,1] and scale by proximity
            proximity = max(0.0, 1.0 - dist / self.max_dist)
            rewards[a] = self.weight * max(0.0, dot) * (0.5 + 0.5 * proximity)

        return rewards


# goal_event_reward.py
import numpy as np
from typing import Optional, Dict
from . import goal_buffer

class GoalEventReward(RewardFunction[AgentID, GameState, float]):
    def __init__(self, own_goal=1.0, concede_penalty=0.0):
        self.own_goal = float(own_goal)
        self.concede_penalty = float(concede_penalty)
        self.prev_ball = None
        self.cooldown = 0

    def reset(self, agents, initial_state, shared):
        self.prev_ball = np.array(initial_state.ball.position, dtype=float)
        self.cooldown = 0
        # DO NOT touch goal_buffer.pending_team here

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared):
        r: Dict[AgentID, float] = {a: 0.0 for a in agents}

        # 1) PAY on first non-terminal tick after a goal (works even if a reset happened)
        if goal_buffer.pending_team is not None and not any(is_terminated.values()):
            st = goal_buffer.pending_team
            goal_buffer.pending_team = None
            for a in agents:
                r[a] = self.own_goal if state.cars[a].team_num == st else self.concede_penalty
            # print("GOAL PAY", st)  # debug
            return r

        # 2) DETECT on terminal goal frame, but don't pay now
        if getattr(state, "goal_scored", False) and state.scoring_team is not None:
            goal_buffer.pending_team = int(state.scoring_team)
            # print("GOAL DETECT", goal_buffer.pending_team)  # debug
            return r  # zeros on terminal frame

        # (optional) your crossing fallback can also set goal_buffer.pending_team here

        return r


class ManualGoalReward(RewardFunction):
    def reset(self, agents, initial_state, shared_info):
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards = {agent: 0.0 for agent in agents}

        # 1. Check the Simulator's Official Flag (Most reliable)
        # Note: This requires the correct termination condition in rlgym_env
        sim_says_goal = getattr(state, "goal_scored", False)
        sim_scoring_team = getattr(state, "scoring_team", -1)

        # 2. Check Manual Position (Backup if sim resets too fast)
        ball_y = state.ball.position[1]
        manual_team_0_score = ball_y > 5100
        manual_team_1_score = ball_y < -5100

        # --- LOGIC ---
        # BLUE TEAM SCORES (Team 0)
        if (sim_says_goal and sim_scoring_team == 0) or manual_team_0_score:
            # print("!!! BLUE GOAL !!!") # Uncomment to debug
            for agent in agents:
                if state.cars[agent].team_num == 0:
                    rewards[agent] = 100.0  # Reward Attacker


        # ORANGE TEAM SCORES (Team 1)
        elif (sim_says_goal and sim_scoring_team == 1) or manual_team_1_score:
            # print("!!! ORANGE GOAL !!!") # Uncomment to debug
            for agent in agents:
                if state.cars[agent].team_num == 1:
                    rewards[agent] = 100.0  # Reward Attacker


        return rewards

class ManualSaveReward(RewardFunction):
    def reset(self, agents, initial_state, shared_info):
        pass

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        rewards = {agent: 0.0 for agent in agents}
        ball_y = state.ball.position[1]
        ball_vy = state.ball.linear_velocity[1]

        for agent in agents:
            car = state.cars[agent]
            # IF TOUCHING BALL
            if car.ball_touches > 0:
                # BLUE TEAM (Defends Negative Y Goal)
                if car.team_num == 0:
                    # Ball in Blue Half (< 0) AND Moving Down (<-100)
                    if ball_y < -500 and ball_vy < -100:
                        rewards[agent] = 1.0

                # ORANGE TEAM (Defends Positive Y Goal)
                elif car.team_num == 1:
                    # Ball in Orange Half (> 0) AND Moving Up (> 100)
                    if ball_y > 500 and ball_vy > 100:
                        rewards[agent] = 1.0
        return rewards