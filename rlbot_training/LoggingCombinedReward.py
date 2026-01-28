import os
import numpy as np
from rlgym.api import RewardFunction


class CombinedReward(RewardFunction):
    def __init__(self, *rewards_with_weights, log_dir="reward_logs"):
        self.rewards_with_weights = rewards_with_weights
        self.reward_names = [r.__class__.__name__ for r, _ in rewards_with_weights]

        # LOGGING SETUP
        self.log_dir = log_dir
        self.step_count = 0
        self.log_interval = 1000  # Log every 1000 steps

        # Ensure directory exists (redundant safety check)
        os.makedirs(self.log_dir, exist_ok=True)

        # CRITICAL FIX: Combine folder path + filename
        self.log_file = os.path.join(self.log_dir, f"rewards_process_{os.getpid()}.csv")

        # Initialize stats
        self.current_stats = {name: 0.0 for name in self.reward_names}
        self.current_stats['Total'] = 0.0

        # Create CSV header if it doesn't exist
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w") as f:
                header = ["Step_Count"] + self.reward_names + ["Total"]
                f.write(",".join(header) + "\n")

    def reset(self, agents, initial_state, shared_info):
        for reward_fn, _ in self.rewards_with_weights:
            reward_fn.reset(agents, initial_state, shared_info)

    def get_rewards(self, agents, state, is_terminated, is_truncated, shared_info):
        combined_rewards = {agent: 0.0 for agent in agents}

        # 1. Calculate Rewards
        for reward_fn, weight in self.rewards_with_weights:
            rewards = reward_fn.get_rewards(agents, state, is_terminated, is_truncated, shared_info)
            name = reward_fn.__class__.__name__

            # Sum weighted rewards for this step
            total_weighted_reward_for_step = 0.0

            for agent in agents:
                val = rewards.get(agent, 0.0)
                weighted_val = val * weight
                combined_rewards[agent] += weighted_val
                total_weighted_reward_for_step += weighted_val

            # Log raw accumulated value (averaged by team size)
            avg_agent_reward = total_weighted_reward_for_step / max(1, len(agents))
            self.current_stats[name] += avg_agent_reward
            self.current_stats['Total'] += avg_agent_reward

        self.step_count += 1

        # 2. Write to Log if interval met
        if self.step_count % self.log_interval == 0:
            self._write_log()
            self._reset_stats()

        return combined_rewards

    def _write_log(self):
        try:
            with open(self.log_file, "a") as f:
                row_values = [str(self.step_count)]

                # Write averages
                for name in self.reward_names:
                    avg_val = self.current_stats[name] / self.log_interval
                    row_values.append(f"{avg_val:.5f}")

                # Write total
                total_avg = self.current_stats['Total'] / self.log_interval
                row_values.append(f"{total_avg:.5f}")

                f.write(",".join(row_values) + "\n")
        except Exception as e:
            print(f"Error writing to reward log: {e}")

    def _reset_stats(self):
        self.current_stats = {name: 0.0 for name in self.reward_names}
        self.current_stats['Total'] = 0.0