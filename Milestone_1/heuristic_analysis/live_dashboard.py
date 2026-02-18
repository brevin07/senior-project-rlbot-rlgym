import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from rlbot.utils.structures.game_data_struct import GameTickPacket
from rlbot.setup_manager import SetupManager
y

# --- CONFIGURATION ---
HISTORY_SECONDS = 10  # How much time to show on the graph
UPDATE_INTERVAL = 33  # Update every 33ms (~30 FPS)


class PlayerAnalysis:
    """
    Holds the state for a single player to calculate derived metrics
    (Whiffs, Boost Waste) that depend on previous frames.
    """

    def __init__(self):
        self.prev_boost = 0
        self.prev_time = 0
        self.prev_ball_vel = np.array([0, 0, 0])
        self.prev_dist_to_ball = 99999
        self.is_moving_away_from_ball = False

        # Metric Trackers
        self.boost_waste_active = False
        self.whiff_detected = False
        self.hesitation_active = False

    def update(self, packet: GameTickPacket, player_index=0):
        car = packet.game_cars[player_index]
        ball = packet.game_ball
        game_time = packet.game_info.seconds_elapsed

        # 1. Physics Vectors
        car_pos = np.array([car.physics.location.x, car.physics.location.y, car.physics.location.z])
        car_vel = np.array([car.physics.velocity.x, car.physics.velocity.y, car.physics.velocity.z])
        ball_pos = np.array([ball.physics.location.x, ball.physics.location.y, ball.physics.location.z])
        ball_vel = np.array([ball.physics.velocity.x, ball.physics.velocity.y, ball.physics.velocity.z])

        car_speed = np.linalg.norm(car_vel)
        dist_to_ball = np.linalg.norm(car_pos - ball_pos)

        # --- HEURISTIC 1: HESITATION ---
        # Logic: Moving slow (< 500) but not completely stopped (dead time)
        self.hesitation_active = 50 < car_speed < 500

        # --- HEURISTIC 2: BOOST WASTE ---
        # Logic: Supersonic (> 2200) AND Boost amount decreased
        # Note: packet.game_cars[i].boost ranges 0-100
        current_boost = car.boost
        is_boosting = current_boost < self.prev_boost  # Simple check if boost dropped

        # Filter out "picked up pad" (boost increase)
        if current_boost > self.prev_boost:
            is_boosting = False

        self.boost_waste_active = (car_speed > 2200) and is_boosting

        # --- HEURISTIC 3: WHIFF DETECTION ---
        # Logic: Local minimum distance < 300 AND Ball did not accelerate (hit)

        # Check if ball was hit (sudden velocity change)
        # 4000 uu/s^2 is a reasonable threshold for a "hit"
        ball_accel = np.linalg.norm(ball_vel - self.prev_ball_vel) / max(0.001, (game_time - self.prev_time))
        ball_was_hit = ball_accel > 1500

        # Whiff Logic:
        # 1. We were getting closer, now we are moving away (Local Min)
        # 2. We were very close (< 280 uu)
        # 3. The ball was NOT hit hard recently

        moving_away = dist_to_ball > self.prev_dist_to_ball

        if moving_away and not self.is_moving_away_from_ball:
            # We just passed the "Closest Point of Approach"
            if self.prev_dist_to_ball < 280 and not ball_was_hit:
                self.whiff_detected = True  # Trigger the flag
            else:
                self.whiff_detected = False
        else:
            self.whiff_detected = False  # Reset flag immediately after frame

        self.is_moving_away_from_ball = moving_away

        # Update History
        self.prev_boost = current_boost
        self.prev_time = game_time
        self.prev_ball_vel = ball_vel
        self.prev_dist_to_ball = dist_to_ball

        return car_speed, dist_to_ball, current_boost


class LiveDashboard:
    def __init__(self):
        self.player_analysis = PlayerAnalysis()

        # Setup Plots
        plt.style.use('dark_background')
        self.fig, (self.ax_speed, self.ax_boost, self.ax_whiff) = plt.subplots(3, 1, figsize=(8, 10), sharex=True)
        self.fig.canvas.manager.set_window_title("RocketCoach Live Telemetry")

        # Data Buffers
        self.times = []
        self.speeds = []
        self.hesitations = []
        self.boosts = []
        self.wastes = []
        self.dists = []
        self.whiffs = []

        self.start_time = time.time()

        # Initialize Lines
        self.line_speed, = self.ax_speed.plot([], [], 'c-', lw=2, label='Car Speed')
        self.line_boost, = self.ax_boost.plot([], [], 'y-', lw=2, label='Boost Amount')
        self.line_dist, = self.ax_whiff.plot([], [], 'm-', lw=1, label='Dist to Ball')

        # Setup Axes
        self.ax_speed.set_ylabel("Speed (uu/s)")
        self.ax_speed.set_ylim(0, 2400)
        self.ax_speed.legend(loc='upper right')

        self.ax_boost.set_ylabel("Boost (%)")
        self.ax_boost.set_ylim(0, 105)
        self.ax_boost.legend(loc='upper right')

        self.ax_whiff.set_ylabel("Distance (uu)")
        self.ax_whiff.set_ylim(0, 2000)
        self.ax_whiff.legend(loc='upper right')
        self.ax_whiff.set_xlabel("Time (s)")

    def update_plot(self, packet):
        # 1. Run Analysis
        speed, dist, boost = self.player_analysis.update(packet)

        current_t = packet.game_info.seconds_elapsed
        if not self.times:
            self.start_game_time = current_t

        rel_time = current_t - (self.start_game_time if self.times else current_t)

        # 2. Append Data
        self.times.append(rel_time)
        self.speeds.append(speed)
        self.hesitations.append(self.player_analysis.hesitation_active)
        self.boosts.append(boost)
        self.wastes.append(self.player_analysis.boost_waste_active)
        self.dists.append(dist)
        self.whiffs.append(self.player_analysis.whiff_detected)

        # 3. Trim Data (Keep last N seconds)
        if rel_time > HISTORY_SECONDS:
            idx = 0
            while self.times[-1] - self.times[idx] > HISTORY_SECONDS:
                idx += 1
            if idx > 0:
                self.times = self.times[idx:]
                self.speeds = self.speeds[idx:]
                self.hesitations = self.hesitations[idx:]
                self.boosts = self.boosts[idx:]
                self.wastes = self.wastes[idx:]
                self.dists = self.dists[idx:]
                self.whiffs = self.whiffs[idx:]

        # 4. Update Lines
        self.line_speed.set_data(self.times, self.speeds)
        self.line_boost.set_data(self.times, self.boosts)
        self.line_dist.set_data(self.times, self.dists)

        # 5. Draw Events (Fill/Scatter)
        self.ax_speed.collections.clear()
        self.ax_boost.collections.clear()
        self.ax_whiff.collections.clear()

        # Hesitation: Red Background
        self.ax_speed.fill_between(self.times, 0, 2400, where=self.hesitations,
                                   color='red', alpha=0.3, label='Hesitation')

        # Boost Waste: Red Background
        self.ax_boost.fill_between(self.times, 0, 100, where=self.wastes,
                                   color='red', alpha=0.5, label='Waste')

        # Whiff: Red Vertical Line / Marker
        whiff_times = [t for t, w in zip(self.times, self.whiffs) if w]
        whiff_y = [0] * len(whiff_times)
        if whiff_times:
            self.ax_whiff.vlines(whiff_times, 0, 2000, colors='red', lw=2, label='Whiff')

        # Auto-scroll X axis
        if self.times:
            self.ax_speed.set_xlim(self.times[0], self.times[-1] + 0.1)

        return self.line_speed, self.line_boost, self.line_dist


# --- MAIN EXECUTION ---
def run_dashboard():
    print("Waiting for Rocket League...")
    manager = SetupManager()
    manager.connect_to_game()
    print("Connected! Launching Dashboard...")

    dashboard = LiveDashboard()

    def animate(frame):
        packet = GameTickPacket()
        manager.game_interface.update_live_data_packet(packet)
        # Ensure game is running (check for players)
        if packet.game_info.is_round_active and packet.num_cars > 0:
            dashboard.update_plot(packet)
        return []

    ani = FuncAnimation(dashboard.fig, animate, interval=UPDATE_INTERVAL)
    plt.show()


if __name__ == "__main__":
    run_dashboard()