from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import sqrt
from typing import Any, Deque, Dict, List, Tuple
import time

SUPERSONIC_SPEED = 2200.0
BALL_HIT_ACCEL_THRESHOLD = 1500.0

ACTIVE_SPEED = 100.0
PRESSURE_DISTANCE = 1800.0
LOW_BOOST_THRESHOLD = 8.0
PRESSURE_MIN_TOWARD_SPEED = 120.0
PRESSURE_NEAR_DISTANCE = 800.0
PRESSURE_MIN_SPEED_FOR_CLOSING = 600.0

HESITATION_ENTER_THRESHOLD = 0.72
HESITATION_EXIT_THRESHOLD = 0.45
HESITATION_FRAME_THRESHOLD = 0.55
HESITATION_RECOVERY_GRACE_SECONDS = 0.60

WHIFF_APPROACH_START_DISTANCE = 1600.0
WHIFF_NEAR_DISTANCE = 460.0
WHIFF_CLOSE_MISS_DISTANCE = 420.0
WHIFF_TOUCH_SUPPRESS_DISTANCE = 185.0
WHIFF_MAX_APPROACH_SECONDS = 2.8
WHIFF_COOLDOWN_SECONDS = 0.7
WHIFF_RECENT_TOUCH_SECONDS = 0.35
CONTEST_WINDOW_SECONDS = 0.30
CONTEST_BALL_RADIUS = 380.0
CONTEST_PLAYER_RADIUS = 750.0
CONTEST_MIN_ATTACK_DIST = 520.0

JUMP_OVER_Z_MARGIN = 140.0
JUMP_VEL_Z_THRESHOLD = 250.0
FLIP_ANG_VEL_THRESHOLD = 4.5
WHIFF_OPPORTUNITY_MIN = 0.52
WHIFF_DISENGAGE_SPEED_MIN = 500.0
WHIFF_DISENGAGE_BALL_SPEED_MIN = 1400.0
WHIFF_BUMP_SELF_TO_OTHER_MAX = 520.0
WHIFF_BUMP_OTHER_TO_BALL_MIN = 700.0
WHIFF_OPP_FIRST_TOUCH_WINDOW = 0.30

HESITATION_REPOSITION_MIN_LATERAL = 280.0
HESITATION_REPOSITION_MAX_DECEL = -260.0
HESITATION_REPOSITION_CLOSING_DIST = 1800.0
HESITATION_SETUP_WALL_Y = 4300.0
HESITATION_DYNAMIC_ENTER_BONUS = 0.10


@dataclass
class MetricSample:
    t: float
    speed: float
    hesitation_score: float
    hesitation_pct: float
    boost_waste_pct: float
    supersonic_pct: float
    useful_supersonic_pct: float
    pressure_pct: float
    whiff_rate_per_min: float
    approach_efficiency: float
    recovery_time_avg_s: float


def _norm3(x: float, y: float, z: float) -> float:
    return sqrt(x * x + y * y + z * z)


def _safe_dot3(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _safe_unit3(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    mag = _norm3(v[0], v[1], v[2])
    if mag <= 1e-6:
        return (0.0, 0.0, 0.0)
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


class LiveMetricsEngine:
    def __init__(self, window_seconds: float = 10.0):
        self.window_seconds = window_seconds
        self.samples: Deque[MetricSample] = deque()
        self.events: Deque[Dict[str, Any]] = deque(maxlen=120)

        self.total_frames = 0
        self.active_frames = 0
        self.pressure_frames = 0
        self.hesitation_frames = 0
        self.supersonic_frames = 0
        self.useful_supersonic_frames = 0

        self.total_boost_used = 0.0
        self.wasted_boost = 0.0
        self.useful_boost = 0.0

        self.approach_progress_total = 0.0
        self.approach_boost_used = 0.0

        self.recovery_count = 0
        self.recovery_total_time = 0.0

        self.hesitation_event_active = False
        self.hesitation_event_start = 0.0
        self.max_hesitation_streak_seconds = 0.0
        self.last_landing_time = -999.0

        self.prev_time = None
        self.prev_ball_vel = (0.0, 0.0, 0.0)
        self.prev_car_vel = (0.0, 0.0, 0.0)
        self.prev_dist_to_ball = 99999.0
        self.prev_speed = 0.0
        self.prev_boost = None
        self.prev_has_wheel_contact = None

        # Whiff classifier state
        self.attack_active = False
        self.attack_start_time = 0.0
        self.attack_start_dist = 0.0
        self.attack_min_dist = 99999.0
        self.attack_closing_frames = 0
        self.attack_near_frames = 0
        self.attack_intent_frames = 0
        self.attack_had_jump = False
        self.attack_had_flip = False
        self.last_whiff_time = -999.0
        self.last_confirmed_touch_time = -999.0
        self.last_external_contested_touch_time = -999.0
        self.last_external_contested_touch_confidence = 0.0
        self.last_external_contested_touch_dist_to_ball = 99999.0
        self.contest_suppressed_whiffs = 0
        self.clear_miss_under_contest = 0
        self.pressure_gated_frames = 0
        self.suppressed_whiff_flip_commit = 0
        self.suppressed_whiff_disengage = 0
        self.suppressed_whiff_bump_intent = 0
        self.suppressed_whiff_opponent_first_touch = 0
        self.suppressed_hesitation_reposition = 0
        self.suppressed_hesitation_setup = 0
        self.suppressed_hesitation_spacing = 0
        self.last_other_touch_time = -999.0

        # Recovery state
        self.airborne_start_time = None
        self.recovery_active = False
        self.recovery_start_time = 0.0

    def _prune_window(self, now: float) -> None:
        while self.samples and now - self.samples[0].t > self.window_seconds:
            self.samples.popleft()

    @staticmethod
    def _is_airborne(car, car_pos: Tuple[float, float, float]) -> bool:
        has_wheel_contact = getattr(car, "has_wheel_contact", None)
        if has_wheel_contact is not None:
            return not bool(has_wheel_contact)
        return car_pos[2] > 35.0

    @staticmethod
    def _angular_velocity(car) -> Tuple[float, float, float]:
        ang = getattr(car.physics, "angular_velocity", None)
        if ang is None:
            return (0.0, 0.0, 0.0)
        return (float(getattr(ang, "x", 0.0)), float(getattr(ang, "y", 0.0)), float(getattr(ang, "z", 0.0)))

    @staticmethod
    def _self_touched_ball_recently(ball, player_index: int, now: float) -> bool:
        latest_touch = getattr(ball, "latest_touch", None)
        if latest_touch is None:
            return False
        touch_player = int(getattr(latest_touch, "player_index", -1))
        if touch_player != player_index:
            return False
        touch_time = getattr(latest_touch, "time_seconds", None)
        if touch_time is None:
            return True
        touch_time = float(touch_time)
        return 0.0 <= (now - touch_time) <= WHIFF_RECENT_TOUCH_SECONDS

    def _recent_confirmed_touch(self, now: float) -> bool:
        return (now - self.last_confirmed_touch_time) <= WHIFF_RECENT_TOUCH_SECONDS

    def _clear_attack(self) -> None:
        self.attack_active = False
        self.attack_start_time = 0.0
        self.attack_start_dist = 0.0
        self.attack_min_dist = 99999.0
        self.attack_closing_frames = 0
        self.attack_near_frames = 0
        self.attack_intent_frames = 0
        self.attack_had_jump = False
        self.attack_had_flip = False

    def _start_attack(self, now: float, dist_to_ball: float) -> None:
        self.attack_active = True
        self.attack_start_time = now
        self.attack_start_dist = dist_to_ball
        self.attack_min_dist = dist_to_ball
        self.attack_closing_frames = 0
        self.attack_near_frames = 0
        self.attack_intent_frames = 0
        self.attack_had_jump = False
        self.attack_had_flip = False

    def _finalize_whiff_if_needed(
        self,
        *,
        now: float,
        speed: float,
        car_pos: Tuple[float, float, float],
        ball_pos: Tuple[float, float, float],
        toward_speed: float,
        moving_away: bool,
        contest_recent: bool,
        contest_confidence: float,
        nearest_other_ball: float,
        nearest_other_self: float,
        nearest_other_toward_speed: float,
        ball_speed: float,
        latest_touch_by_other_recent: bool,
    ) -> None:
        if not self.attack_active or self._recent_confirmed_touch(now):
            self._clear_attack()
            return

        if self.attack_min_dist > WHIFF_CLOSE_MISS_DISTANCE:
            self._clear_attack()
            return
        if self.attack_min_dist <= WHIFF_TOUCH_SUPPRESS_DISTANCE:
            self._clear_attack()
            return

        attack_duration = max(1e-6, now - self.attack_start_time)
        progress = max(0.0, self.attack_start_dist - self.attack_min_dist)

        if contest_recent:
            clear_miss_under_challenge = (
                (self.attack_had_flip and self.attack_min_dist > 320.0)
                or (self.attack_had_jump and car_pos[2] > ball_pos[2] + JUMP_OVER_Z_MARGIN and self.attack_min_dist > 300.0)
                or (progress < 100.0 and moving_away)
            )
            if not clear_miss_under_challenge:
                self.contest_suppressed_whiffs += 1
                self._clear_attack()
                return
            self.clear_miss_under_contest += 1

        progress_score = _clamp01(progress / 240.0)
        near_score = _clamp01((self.attack_near_frames * 0.016) / 0.24)
        intent_score = _clamp01((self.attack_intent_frames * 0.016) / 0.30)
        duration_score = _clamp01(attack_duration / 0.40)
        opportunity_score = 0.35 * progress_score + 0.25 * near_score + 0.25 * intent_score + 0.15 * duration_score

        if opportunity_score < WHIFF_OPPORTUNITY_MIN:
            self._clear_attack()
            return

        # Suppress false positives from committed flips/flicks where contact window moves away.
        if self.attack_had_flip and moving_away and (toward_speed > 120.0):
            self.suppressed_whiff_flip_commit += 1
            self._clear_attack()
            return

        # Suppress intentional disengage when ball is clearly moving away at pace.
        if (
            moving_away
            and speed >= WHIFF_DISENGAGE_SPEED_MIN
            and ball_speed >= WHIFF_DISENGAGE_BALL_SPEED_MIN
            and self.attack_min_dist > 260.0
        ):
            self.suppressed_whiff_disengage += 1
            self._clear_attack()
            return

        # Suppress bump/demo style intent when nearest opponent is target, not the ball lane.
        if (
            nearest_other_self < WHIFF_BUMP_SELF_TO_OTHER_MAX
            and nearest_other_ball > WHIFF_BUMP_OTHER_TO_BALL_MIN
            and nearest_other_toward_speed > 180.0
            and moving_away
        ):
            self.suppressed_whiff_bump_intent += 1
            self._clear_attack()
            return

        # Suppress when another player touched first and removed the opportunity window.
        if latest_touch_by_other_recent and moving_away:
            self.suppressed_whiff_opponent_first_touch += 1
            self._clear_attack()
            return

        if (now - self.last_whiff_time) <= WHIFF_COOLDOWN_SECONDS:
            self._clear_attack()
            return

        reason = "drive_miss"
        if self.attack_had_flip:
            reason = "flip_miss"
        elif self.attack_had_jump and car_pos[2] > ball_pos[2] + JUMP_OVER_Z_MARGIN:
            reason = "jump_miss"
        elif speed < 420.0 or toward_speed < 260.0:
            reason = "slow_control_miss"

        confidence = _clamp01(0.5 + 0.5 * opportunity_score)
        context = []
        if speed < 600.0:
            context.append("low_speed")
        if car_pos[2] > 120.0:
            context.append("airborne")
        if contest_recent:
            context.append("contested_clear_miss")
        if self.attack_had_flip:
            context.append("flip_attempt")

        self.events.appendleft(
            {
                "time": round(now, 3),
                "type": "whiff",
                "reason": reason,
                "distance": round(self.attack_min_dist, 2),
                "opportunity_score": round(opportunity_score, 3),
                "confidence": round(confidence, 3),
                "suppressed_by_contest": False,
                "contest_confidence": round(contest_confidence if contest_recent else 0.0, 3),
                "context": context,
                "intent_flags": ["whiff_attempt"],
                "suppression_reason": "",
                "opportunity_blocked": False,
            }
        )
        self.last_whiff_time = now
        self._clear_attack()

    @staticmethod
    def _latest_touch_by_other_recent(ball, player_index: int, now: float) -> bool:
        latest_touch = getattr(ball, "latest_touch", None)
        if latest_touch is None:
            return False
        touch_player = int(getattr(latest_touch, "player_index", -1))
        if touch_player < 0 or touch_player == player_index:
            return False
        touch_time = getattr(latest_touch, "time_seconds", None)
        if touch_time is None:
            return True
        return 0.0 <= (now - float(touch_time)) <= WHIFF_OPP_FIRST_TOUCH_WINDOW

    @staticmethod
    def _nearest_other_geometry(packet, player_index: int, car_pos, car_vel, ball_pos):
        nearest_other_ball = 99999.0
        nearest_other_self = 99999.0
        nearest_other_toward_speed = 0.0
        nearest_other_pos = None
        for i in range(int(getattr(packet, "num_cars", 0))):
            if i == player_index:
                continue
            oc = packet.game_cars[i]
            op = (
                float(oc.physics.location.x),
                float(oc.physics.location.y),
                float(oc.physics.location.z),
            )
            ov = (
                float(oc.physics.velocity.x),
                float(oc.physics.velocity.y),
                float(oc.physics.velocity.z),
            )
            d_ball = _norm3(op[0] - ball_pos[0], op[1] - ball_pos[1], op[2] - ball_pos[2])
            d_self = _norm3(op[0] - car_pos[0], op[1] - car_pos[1], op[2] - car_pos[2])
            if d_ball < nearest_other_ball:
                nearest_other_ball = d_ball
            if d_self < nearest_other_self:
                nearest_other_self = d_self
                nearest_other_pos = op
                toward_other = _safe_unit3((op[0] - car_pos[0], op[1] - car_pos[1], op[2] - car_pos[2]))
                nearest_other_toward_speed = _safe_dot3(car_vel, toward_other) - _safe_dot3(ov, toward_other)
        return nearest_other_ball, nearest_other_self, nearest_other_toward_speed, nearest_other_pos

    def _update_recovery_state(self, *, now: float, airborne: bool, speed: float, toward_speed: float) -> None:
        if airborne and self.airborne_start_time is None:
            self.airborne_start_time = now

        if not airborne and self.airborne_start_time is not None:
            air_time = now - self.airborne_start_time
            self.airborne_start_time = None
            self.last_landing_time = now
            if air_time >= 0.08:
                self.recovery_active = True
                self.recovery_start_time = now

        if self.recovery_active:
            playable = (speed > 900.0) or (toward_speed > 380.0)
            timeout = (now - self.recovery_start_time) > 2.5
            if playable or timeout:
                self.recovery_count += 1
                self.recovery_total_time += max(0.0, now - self.recovery_start_time)
                self.recovery_active = False

    def _hesitation_score(
        self,
        *,
        active: bool,
        pressure: bool,
        speed: float,
        toward_speed: float,
        lateral_speed: float,
        accel: float,
        cur_boost: float,
        airborne: bool,
        now: float,
    ) -> float:
        if not active or not pressure:
            return 0.0

        if airborne:
            return 0.0
        if (now - self.last_landing_time) <= HESITATION_RECOVERY_GRACE_SECONDS:
            return 0.0

        progress_penalty = 1.0 - _clamp01(max(0.0, toward_speed) / 900.0)
        turning_penalty = _clamp01(lateral_speed / max(350.0, speed))
        acceleration_penalty = _clamp01((180.0 - accel) / 380.0)
        threat_scale = _clamp01((PRESSURE_DISTANCE - self.prev_dist_to_ball) / PRESSURE_DISTANCE)

        score = 0.45 * progress_penalty + 0.30 * turning_penalty + 0.25 * acceleration_penalty
        score *= 0.6 + 0.4 * threat_scale

        if cur_boost < LOW_BOOST_THRESHOLD and toward_speed > 180.0:
            score *= 0.55

        return _clamp01(score)

    def _update_hesitation_events(
        self,
        now: float,
        score: float,
        pressure: bool,
        suppression_reason: str = "",
        enter_threshold: float = HESITATION_ENTER_THRESHOLD,
    ) -> None:
        if not pressure:
            if self.hesitation_event_active:
                streak = now - self.hesitation_event_start
                self.max_hesitation_streak_seconds = max(self.max_hesitation_streak_seconds, streak)
                self.hesitation_event_active = False
            return

        if (not self.hesitation_event_active) and score >= enter_threshold:
            self.hesitation_event_active = True
            self.hesitation_event_start = now
            context = ["pressure"]
            if suppression_reason:
                context.append(f"suppression_override={suppression_reason}")
            self.events.appendleft(
                {
                    "time": round(now, 3),
                    "type": "hesitation",
                    "reason": "indecision_under_pressure",
                    "distance": round(self.prev_dist_to_ball, 2),
                    "confidence": round(score, 3),
                    "opportunity_score": round(score, 3),
                    "context": context,
                    "intent_flags": ["hesitation_window"],
                    "suppression_reason": suppression_reason,
                    "opportunity_blocked": False,
                }
            )

        if self.hesitation_event_active and score <= HESITATION_EXIT_THRESHOLD:
            streak = now - self.hesitation_event_start
            self.max_hesitation_streak_seconds = max(self.max_hesitation_streak_seconds, streak)
            self.hesitation_event_active = False

    def _count_recent_events(self, now: float, event_type: str) -> int:
        cutoff = now - self.window_seconds
        return len([e for e in self.events if e.get("type") == event_type and float(e.get("time", 0.0)) >= cutoff])

    @staticmethod
    def _nearest_other_distances(packet, player_index: int, car_pos: Tuple[float, float, float], ball_pos: Tuple[float, float, float]) -> Tuple[float, float]:
        nearest_other_to_ball = 99999.0
        nearest_other_to_self = 99999.0
        for i in range(int(getattr(packet, "num_cars", 0))):
            if i == player_index:
                continue
            oc = packet.game_cars[i]
            op = (
                float(oc.physics.location.x),
                float(oc.physics.location.y),
                float(oc.physics.location.z),
            )
            d_ball = _norm3(op[0] - ball_pos[0], op[1] - ball_pos[1], op[2] - ball_pos[2])
            d_self = _norm3(op[0] - car_pos[0], op[1] - car_pos[1], op[2] - car_pos[2])
            if d_ball < nearest_other_to_ball:
                nearest_other_to_ball = d_ball
            if d_self < nearest_other_to_self:
                nearest_other_to_self = d_self
        return nearest_other_to_ball, nearest_other_to_self

    def update(self, packet, player_index: int = 0) -> None:
        if packet.num_cars <= player_index:
            return

        car = packet.game_cars[player_index]
        ball = packet.game_ball
        now = float(packet.game_info.seconds_elapsed)

        car_pos = (float(car.physics.location.x), float(car.physics.location.y), float(car.physics.location.z))
        car_vel = (float(car.physics.velocity.x), float(car.physics.velocity.y), float(car.physics.velocity.z))
        ball_pos = (float(ball.physics.location.x), float(ball.physics.location.y), float(ball.physics.location.z))
        ball_vel = (float(ball.physics.velocity.x), float(ball.physics.velocity.y), float(ball.physics.velocity.z))

        speed = _norm3(*car_vel)
        dist_to_ball = _norm3(car_pos[0] - ball_pos[0], car_pos[1] - ball_pos[1], car_pos[2] - ball_pos[2])

        dt = 1 / 60.0
        if self.prev_time is not None and now > self.prev_time:
            dt = max(1e-5, now - self.prev_time)

        to_ball = (ball_pos[0] - car_pos[0], ball_pos[1] - car_pos[1], ball_pos[2] - car_pos[2])
        to_ball_dir = _safe_unit3(to_ball)
        toward_speed = _safe_dot3(car_vel, to_ball_dir)
        lateral_speed_sq = max(0.0, speed * speed - toward_speed * toward_speed)
        lateral_speed = lateral_speed_sq ** 0.5
        ball_speed = _norm3(*ball_vel)
        nearest_other_ball, nearest_other_self, nearest_other_toward_speed, nearest_other_pos = self._nearest_other_geometry(
            packet, player_index, car_pos, car_vel, ball_pos
        )

        speed_accel = (speed - self.prev_speed) / dt if self.prev_time is not None else 0.0
        closing = dist_to_ball + 4.0 < self.prev_dist_to_ball
        moving_away = dist_to_ball > self.prev_dist_to_ball + 6.0

        self.total_frames += 1
        active = speed > ACTIVE_SPEED or dist_to_ball < 2500.0
        pressure_raw = dist_to_ball < PRESSURE_DISTANCE or (closing and dist_to_ball < 2400.0)
        approach_intent = (
            toward_speed > PRESSURE_MIN_TOWARD_SPEED
            or (closing and speed > PRESSURE_MIN_SPEED_FOR_CLOSING)
            or dist_to_ball < PRESSURE_NEAR_DISTANCE
        )
        demoed = bool(getattr(car, "is_demolished", False))
        pressure = pressure_raw and approach_intent and (not demoed)
        if pressure_raw and not pressure:
            self.pressure_gated_frames += 1
        if active:
            self.active_frames += 1
        if pressure:
            self.pressure_frames += 1

        airborne = self._is_airborne(car, car_pos)
        self._update_recovery_state(now=now, airborne=airborne, speed=speed, toward_speed=toward_speed)

        hesitation_score = self._hesitation_score(
            active=active,
            pressure=pressure,
            speed=speed,
            toward_speed=toward_speed,
            lateral_speed=lateral_speed,
            accel=speed_accel,
            cur_boost=float(car.boost),
            airborne=airborne,
            now=now,
        )
        suppression_reason = ""
        repositioning = (
            pressure
            and dist_to_ball < HESITATION_REPOSITION_CLOSING_DIST
            and lateral_speed > HESITATION_REPOSITION_MIN_LATERAL
            and speed_accel > HESITATION_REPOSITION_MAX_DECEL
            and speed > 300.0
        )
        wall_setup = pressure and abs(car_pos[1]) > HESITATION_SETUP_WALL_Y and speed < 900.0 and toward_speed > -120.0
        spacing_adjust = pressure and moving_away and dist_to_ball > 700.0 and speed > 450.0 and toward_speed > -280.0
        dynamic_enter_threshold = HESITATION_ENTER_THRESHOLD
        if toward_speed > 180.0 or closing:
            dynamic_enter_threshold += HESITATION_DYNAMIC_ENTER_BONUS

        if repositioning:
            self.suppressed_hesitation_reposition += 1
            hesitation_score *= 0.55
            suppression_reason = "repositioning"
        elif wall_setup:
            self.suppressed_hesitation_setup += 1
            hesitation_score *= 0.45
            suppression_reason = "wall_setup"
        elif spacing_adjust:
            self.suppressed_hesitation_spacing += 1
            hesitation_score *= 0.5
            suppression_reason = "spacing_adjust"

        is_hesitating = pressure and hesitation_score >= HESITATION_FRAME_THRESHOLD and hesitation_score >= dynamic_enter_threshold - 0.08
        if is_hesitating:
            self.hesitation_frames += 1
        self._update_hesitation_events(
            now,
            hesitation_score,
            pressure,
            suppression_reason=suppression_reason,
            enter_threshold=dynamic_enter_threshold,
        )

        is_supersonic = speed > SUPERSONIC_SPEED
        if is_supersonic:
            self.supersonic_frames += 1
            if pressure or toward_speed > 280.0:
                self.useful_supersonic_frames += 1

        cur_boost = float(car.boost)
        if self.prev_boost is None:
            self.prev_boost = cur_boost

        boost_drop = max(0.0, self.prev_boost - cur_boost)
        if boost_drop > 0:
            self.total_boost_used += boost_drop

            useful_context = pressure or toward_speed > 250.0 or speed_accel > 120.0
            if useful_context:
                self.useful_boost += boost_drop
            else:
                self.wasted_boost += boost_drop

            if closing:
                self.approach_boost_used += boost_drop

        if self.prev_time is not None:
            self.approach_progress_total += max(0.0, self.prev_dist_to_ball - dist_to_ball)

        ball_accel = _norm3(
            ball_vel[0] - self.prev_ball_vel[0],
            ball_vel[1] - self.prev_ball_vel[1],
            ball_vel[2] - self.prev_ball_vel[2],
        ) / max(dt, 1e-6)
        ball_was_hit = ball_accel > BALL_HIT_ACCEL_THRESHOLD

        if not self.attack_active:
            start_by_closing = closing and dist_to_ball < WHIFF_APPROACH_START_DISTANCE
            start_by_near = dist_to_ball < WHIFF_NEAR_DISTANCE and speed > 80.0
            start_by_air_attempt = airborne and dist_to_ball < 950.0 and (car_vel[2] > JUMP_VEL_Z_THRESHOLD)
            if start_by_closing or start_by_near or start_by_air_attempt:
                self._start_attack(now, dist_to_ball)

        if self.attack_active:
            self.attack_min_dist = min(self.attack_min_dist, dist_to_ball)
            if closing:
                self.attack_closing_frames += 1
            if dist_to_ball <= WHIFF_NEAR_DISTANCE:
                self.attack_near_frames += 1
            if abs(toward_speed) > 140.0 or speed > 160.0 or airborne:
                self.attack_intent_frames += 1

            if airborne and car_vel[2] > JUMP_VEL_Z_THRESHOLD:
                self.attack_had_jump = True

            ang_vel = self._angular_velocity(car)
            ang_speed = _norm3(*ang_vel)
            if airborne and ang_speed > FLIP_ANG_VEL_THRESHOLD and speed > 280.0:
                self.attack_had_flip = True

        self_touched = self._self_touched_ball_recently(ball, player_index, now)
        other_touched_recent = self._latest_touch_by_other_recent(ball, player_index, now)
        if ball_was_hit and self.attack_active and (not self_touched) and self.attack_min_dist <= CONTEST_MIN_ATTACK_DIST:
            nearest_other_ball, nearest_other_self = self._nearest_other_distances(packet, player_index, car_pos, ball_pos)
            if nearest_other_ball <= CONTEST_BALL_RADIUS and nearest_other_self <= CONTEST_PLAYER_RADIUS:
                ball_factor = _clamp01((CONTEST_BALL_RADIUS - nearest_other_ball) / CONTEST_BALL_RADIUS)
                self_factor = _clamp01((CONTEST_PLAYER_RADIUS - nearest_other_self) / CONTEST_PLAYER_RADIUS)
                conf = 0.55 * ball_factor + 0.45 * self_factor
                if conf >= 0.2:
                    self.last_external_contested_touch_time = now
                    self.last_external_contested_touch_confidence = conf
                    self.last_external_contested_touch_dist_to_ball = self.attack_min_dist

        if self_touched:
            self.last_confirmed_touch_time = now
            self._clear_attack()
        elif ball_was_hit and self.attack_active and self.attack_min_dist < WHIFF_TOUCH_SUPPRESS_DISTANCE:
            self.last_confirmed_touch_time = now
            self._clear_attack()

        timed_out = self.attack_active and ((now - self.attack_start_time) > WHIFF_MAX_APPROACH_SECONDS)
        disengaged = self.attack_active and moving_away and self.attack_closing_frames > 0
        if timed_out or disengaged:
            contest_recent = (now - self.last_external_contested_touch_time) <= CONTEST_WINDOW_SECONDS
            self._finalize_whiff_if_needed(
                now=now,
                speed=speed,
                car_pos=car_pos,
                ball_pos=ball_pos,
                toward_speed=toward_speed,
                moving_away=moving_away,
                contest_recent=contest_recent,
                contest_confidence=self.last_external_contested_touch_confidence,
                nearest_other_ball=nearest_other_ball,
                nearest_other_self=nearest_other_self,
                nearest_other_toward_speed=nearest_other_toward_speed,
                ball_speed=ball_speed,
                latest_touch_by_other_recent=other_touched_recent,
            )

        hesitation_pct = (100.0 * self.hesitation_frames / max(1, self.pressure_frames))
        boost_waste_pct = (100.0 * self.wasted_boost / max(1e-6, self.total_boost_used))
        supersonic_pct = (100.0 * self.supersonic_frames / max(1, self.total_frames))
        useful_supersonic_pct = (100.0 * self.useful_supersonic_frames / max(1, self.supersonic_frames))
        pressure_pct = (100.0 * self.pressure_frames / max(1, self.total_frames))

        whiff_events_recent = self._count_recent_events(now, "whiff")
        whiff_rate_per_min = whiff_events_recent * (60.0 / max(1e-6, self.window_seconds))

        approach_efficiency = self.approach_progress_total / max(1e-6, self.approach_boost_used)
        recovery_time_avg_s = self.recovery_total_time / max(1, self.recovery_count)

        self.samples.append(
            MetricSample(
                t=now,
                speed=speed,
                hesitation_score=hesitation_score,
                hesitation_pct=hesitation_pct,
                boost_waste_pct=boost_waste_pct,
                supersonic_pct=supersonic_pct,
                useful_supersonic_pct=useful_supersonic_pct,
                pressure_pct=pressure_pct,
                whiff_rate_per_min=whiff_rate_per_min,
                approach_efficiency=approach_efficiency,
                recovery_time_avg_s=recovery_time_avg_s,
            )
        )
        self._prune_window(now)

        self.prev_time = now
        self.prev_ball_vel = ball_vel
        self.prev_car_vel = car_vel
        self.prev_dist_to_ball = dist_to_ball
        self.prev_speed = speed
        self.prev_boost = cur_boost
        self.prev_has_wheel_contact = getattr(car, "has_wheel_contact", None)

    def snapshot(self) -> Tuple[Dict[str, Any], Dict[str, List[Dict[str, float]]], List[Dict[str, Any]]]:
        if self.samples:
            latest = self.samples[-1]
            now = latest.t
            current = {
                "timestamp": latest.t,
                "speed": round(latest.speed, 2),
                "hesitation_score": round(latest.hesitation_score, 3),
                "hesitation_percent": round(latest.hesitation_pct, 2),
                "boost_waste_percent": round(latest.boost_waste_pct, 2),
                "supersonic_percent": round(latest.supersonic_pct, 2),
                "useful_supersonic_percent": round(latest.useful_supersonic_pct, 2),
                "pressure_percent": round(latest.pressure_pct, 2),
                "whiff_rate_per_min": round(latest.whiff_rate_per_min, 2),
                "approach_efficiency": round(latest.approach_efficiency, 2),
                "recovery_time_avg_s": round(latest.recovery_time_avg_s, 3),
                "hesitation_streak_max_s": round(self.max_hesitation_streak_seconds, 3),
                "whiff_events_recent": self._count_recent_events(now, "whiff"),
                "hesitation_events_recent": self._count_recent_events(now, "hesitation"),
                "contest_suppressed_whiffs": int(self.contest_suppressed_whiffs),
                "clear_miss_under_contest": int(self.clear_miss_under_contest),
                "pressure_gated_frames": int(self.pressure_gated_frames),
                "suppressed_whiff_flip_commit": int(self.suppressed_whiff_flip_commit),
                "suppressed_whiff_disengage": int(self.suppressed_whiff_disengage),
                "suppressed_whiff_bump_intent": int(self.suppressed_whiff_bump_intent),
                "suppressed_whiff_opponent_first_touch": int(self.suppressed_whiff_opponent_first_touch),
                "suppressed_hesitation_reposition": int(self.suppressed_hesitation_reposition),
                "suppressed_hesitation_setup": int(self.suppressed_hesitation_setup),
                "suppressed_hesitation_spacing": int(self.suppressed_hesitation_spacing),
            }
        else:
            current = {
                "timestamp": time.time(),
                "speed": 0.0,
                "hesitation_score": 0.0,
                "hesitation_percent": 0.0,
                "boost_waste_percent": 0.0,
                "supersonic_percent": 0.0,
                "useful_supersonic_percent": 0.0,
                "pressure_percent": 0.0,
                "whiff_rate_per_min": 0.0,
                "approach_efficiency": 0.0,
                "recovery_time_avg_s": 0.0,
                "hesitation_streak_max_s": 0.0,
                "whiff_events_recent": 0,
                "hesitation_events_recent": 0,
                "contest_suppressed_whiffs": 0,
                "clear_miss_under_contest": 0,
                "pressure_gated_frames": 0,
                "suppressed_whiff_flip_commit": 0,
                "suppressed_whiff_disengage": 0,
                "suppressed_whiff_bump_intent": 0,
                "suppressed_whiff_opponent_first_touch": 0,
                "suppressed_hesitation_reposition": 0,
                "suppressed_hesitation_setup": 0,
                "suppressed_hesitation_spacing": 0,
            }

        history = {
            "speed": [{"t": s.t, "v": round(s.speed, 4)} for s in self.samples],
            "hesitation_score": [{"t": s.t, "v": round(s.hesitation_score, 4)} for s in self.samples],
            "hesitation_percent": [{"t": s.t, "v": round(s.hesitation_pct, 4)} for s in self.samples],
            "boost_waste_percent": [{"t": s.t, "v": round(s.boost_waste_pct, 4)} for s in self.samples],
            "supersonic_percent": [{"t": s.t, "v": round(s.supersonic_pct, 4)} for s in self.samples],
            "useful_supersonic_percent": [{"t": s.t, "v": round(s.useful_supersonic_pct, 4)} for s in self.samples],
            "pressure_percent": [{"t": s.t, "v": round(s.pressure_pct, 4)} for s in self.samples],
            "whiff_rate_per_min": [{"t": s.t, "v": round(s.whiff_rate_per_min, 4)} for s in self.samples],
            "approach_efficiency": [{"t": s.t, "v": round(s.approach_efficiency, 4)} for s in self.samples],
            "recovery_time_avg_s": [{"t": s.t, "v": round(s.recovery_time_avg_s, 4)} for s in self.samples],
        }

        return current, history, list(self.events)
