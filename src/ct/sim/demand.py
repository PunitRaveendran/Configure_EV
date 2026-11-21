"""Vehicle demand generation with diurnal Poisson arrivals for Charger Truth simulator.

All data is strictly SIMULATED.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator, List, Optional
import numpy as np

from ct.config import Config
from ct.schemas import VehicleRequestEvent


@dataclass
class VehicleDemandGenerator:
    """Generates synthetic EV charging requests across the urban road network."""
    config: Config
    seed: int = 42
    base_rate_per_min: float = 1.2  # ~72 arrivals per hour baseline

    def __post_init__(self):
        self.rng = np.random.RandomState(self.seed)

    def diurnal_multiplier(self, sim_time_sec: float) -> float:
        """Diurnal demand curve with evening peak around 19:00 (7 PM)."""
        hour = (sim_time_sec / 3600.0) % 24.0
        # Peak around hour 18-20, trough around hour 3-5
        diurnal = 0.4 + 0.6 * math.sin(math.pi * (hour - 8.0) / 12.0)
        evening_boost = 0.5 * math.exp(-((hour - 19.0) ** 2) / 8.0)
        return max(0.2, diurnal + evening_boost)

    def generate_requests(
        self,
        start_ts: int,
        duration_sec: int,
    ) -> List[VehicleRequestEvent]:
        """Generate a deterministic sequence of vehicle charging requests."""
        requests: List[VehicleRequestEvent] = []
        current_time_sec = 0.0
        req_counter = 1

        while current_time_sec < duration_sec:
            mult = self.diurnal_multiplier(current_time_sec)
            rate_per_sec = (self.base_rate_per_min / 60.0) * mult
            # Inter-arrival time exponential
            dt = self.rng.exponential(1.0 / rate_per_sec)
            current_time_sec += dt

            if current_time_sec >= duration_sec:
                break

            event_ts = start_ts + int(current_time_sec * 1000)
            req_id = f"req_{self.seed}_{req_counter:05d}"
            veh_id = f"veh_{self.seed}_{req_counter:05d}"
            req_counter += 1

            lat = float(self.rng.uniform(self.config.lat_min, self.config.lat_max))
            lon = float(self.rng.uniform(self.config.lon_min, self.config.lon_max))
            battery_kwh = float(self.rng.choice([40.0, 60.0, 75.0, 100.0]))
            current_soc = float(self.rng.uniform(0.12, 0.28))
            target_soc = 0.80
            reserve_soc = 0.10
            max_kw = float(self.rng.choice([50.0, 100.0, 150.0, 250.0]))

            requests.append(
                VehicleRequestEvent(
                    event_ts=event_ts,
                    request_id=req_id,
                    vehicle_id=veh_id,
                    current_lat=lat,
                    current_lon=lon,
                    current_soc=current_soc,
                    battery_kwh=battery_kwh,
                    target_soc=target_soc,
                    reserve_soc=reserve_soc,
                    max_charge_rate_kw=max_kw,
                )
            )

        return requests
