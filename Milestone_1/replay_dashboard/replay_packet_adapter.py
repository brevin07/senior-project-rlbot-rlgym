from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import List

import pandas as pd


def _vec(x: float, y: float, z: float) -> SimpleNamespace:
    return SimpleNamespace(x=float(x), y=float(y), z=float(z))


@dataclass
class ReplayPacketBuilder:
    df: pd.DataFrame
    players: List[str]

    def build(self, idx: int):
        row = self.df.iloc[idx]
        prev_idx = max(0, idx - 1)
        prev = self.df.iloc[prev_idx]

        dt = float(row["time"] - prev["time"]) if idx > 0 else 1.0 / 30.0
        if dt <= 1e-6:
            dt = 1.0 / 30.0

        cars = []
        for player in self.players:
            px, py, pz = float(row[f"{player}_x"]), float(row[f"{player}_y"]), float(row[f"{player}_z"])
            ppx, ppy, ppz = float(prev[f"{player}_x"]), float(prev[f"{player}_y"]), float(prev[f"{player}_z"])
            vx = float(row.get(f"{player}_vel_x", (px - ppx) / dt))
            vy = float(row.get(f"{player}_vel_y", (py - ppy) / dt))
            vz = float(row.get(f"{player}_vel_z", (pz - ppz) / dt))
            has_wheel_contact = pz <= 35.0
            boost = float(row.get(f"{player}_boost", 0.0))

            cars.append(
                SimpleNamespace(
                    physics=SimpleNamespace(
                        location=_vec(px, py, pz),
                        velocity=_vec(vx, vy, vz),
                        angular_velocity=_vec(0.0, 0.0, 0.0),
                    ),
                    boost=boost,
                    has_wheel_contact=has_wheel_contact,
                )
            )

        bx, by, bz = float(row["Ball_x"]), float(row["Ball_y"]), float(row["Ball_z"])
        pbx, pby, pbz = float(prev["Ball_x"]), float(prev["Ball_y"]), float(prev["Ball_z"])
        bvx = float(row.get("Ball_vel_x", (bx - pbx) / dt))
        bvy = float(row.get("Ball_vel_y", (by - pby) / dt))
        bvz = float(row.get("Ball_vel_z", (bz - pbz) / dt))

        ball = SimpleNamespace(
            physics=SimpleNamespace(
                location=_vec(bx, by, bz),
                velocity=_vec(bvx, bvy, bvz),
                angular_velocity=_vec(0.0, 0.0, 0.0),
            ),
            latest_touch=None,
        )

        return SimpleNamespace(
            num_cars=len(cars),
            game_cars=cars,
            game_ball=ball,
            game_info=SimpleNamespace(seconds_elapsed=float(row["time"])),
        )
