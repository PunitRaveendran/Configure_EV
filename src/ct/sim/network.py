"""Synthetic road graph and charging site layout for Charger Truth.

All data is strictly SIMULATED.
Sites are placed within a synthetic Chennai bounding box for spatial display.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np

from ct.config import Config


class HiddenState(str, Enum):
    """Ground truth hidden connector health state.
    
    Policies NEVER have access to this state.
    """
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DEADEND = "DEADEND"
    OFFLINE = "OFFLINE"


@dataclass
class ConnectorSim:
    """Internal simulator connector entity holding true hidden state."""
    connector_id: str
    site_id: str
    operator_id: str
    model_id: str
    firmware_version: str
    rated_kw: float
    hidden_state: HiddenState = HiddenState.HEALTHY
    is_occupied: bool = False
    occupied_until_ts: int = 0
    degradation_factor: float = 1.0  # multiplier on power (0.2 to 0.6 when degraded)


@dataclass(frozen=True)
class SiteSim:
    """Charging site entity located in synthetic spatial graph."""
    site_id: str
    name: str
    lat: float
    lon: float
    connector_ids: Tuple[str, ...]


class RoadGraph:
    """Synthetic road graph for travel distance and duration estimation."""
    def __init__(self, avg_speed_kmh: float = 32.0):
        self.avg_speed_kmh = avg_speed_kmh

    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance between two points in km."""
        r = 6371.0  # Earth radius in km
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    def travel_time_min(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Travel time in minutes, assuming synthetic road detour factor 1.25."""
        dist_km = self.haversine_km(lat1, lon1, lat2, lon2) * 1.25
        return (dist_km / self.avg_speed_kmh) * 60.0

    def travel_time_sec(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Travel time in seconds."""
        return self.travel_time_min(lat1, lon1, lat2, lon2) * 60.0


def build_synthetic_network(
    config: Config, seed: int = 42
) -> Tuple[Dict[str, SiteSim], Dict[str, ConnectorSim], RoadGraph]:
    """Deterministically generate sites and connectors within Chennai bounds."""
    rng = np.random.RandomState(seed)

    operators = [f"OP_{i+1}" for i in range(config.num_operators)]
    models = [f"HW_{i+1}" for i in range(config.num_models)]
    firmwares = [f"FW_v{i+1}.0" for i in range(config.num_firmwares)]
    power_ratings = [50.0, 120.0, 150.0, 240.0, 350.0]

    # Distribute connectors among sites (~3-4 connectors per site for 200 total across 60 sites)
    connectors_per_site = [config.num_connectors // config.num_sites] * config.num_sites
    remainder = config.num_connectors - sum(connectors_per_site)
    for i in range(remainder):
        connectors_per_site[i] += 1

    sites: Dict[str, SiteSim] = {}
    connectors: Dict[str, ConnectorSim] = {}
    conn_counter = 1

    for site_idx in range(config.num_sites):
        site_id = f"site_{site_idx + 1:03d}"
        lat = rng.uniform(config.lat_min, config.lat_max)
        lon = rng.uniform(config.lon_min, config.lon_max)
        site_operator = rng.choice(operators)

        site_conn_ids: List[str] = []
        num_c = connectors_per_site[site_idx]
        for _ in range(num_c):
            conn_id = f"conn_{conn_counter:04d}"
            conn_counter += 1
            site_conn_ids.append(conn_id)

            model = rng.choice(models)
            fw = rng.choice(firmwares)
            rated_kw = float(rng.choice(power_ratings))

            connectors[conn_id] = ConnectorSim(
                connector_id=conn_id,
                site_id=site_id,
                operator_id=site_operator,
                model_id=model,
                firmware_version=fw,
                rated_kw=rated_kw,
                hidden_state=HiddenState.HEALTHY,
            )

        sites[site_id] = SiteSim(
            site_id=site_id,
            name=f"Chennai Hub {site_idx + 1}",
            lat=float(lat),
            lon=float(lon),
            connector_ids=tuple(site_conn_ids),
        )

    graph = RoadGraph(avg_speed_kmh=32.0)
    return sites, connectors, graph
