"""Configuration parameters for Charger Truth."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import yaml


@dataclass(frozen=True)
class Config:
    """Frozen configuration holding all parameters specified in AGENTS.md and docs/SPEC.md.
    
    No magic numbers anywhere else in code.
    """
    # Emission priors (starting values, spec priors table)
    p_start_healthy: float = 0.97
    p_start_degraded: float = 0.90
    p_start_deadend: float = 0.03
    p_start_offline: float = 0.00

    p_avail_healthy: float = 0.95
    p_avail_degraded: float = 0.95
    p_avail_deadend: float = 0.90
    p_avail_offline: float = 0.15

    power_ratio_healthy_min: float = 0.90
    power_ratio_healthy_max: float = 1.00
    power_ratio_degraded_min: float = 0.20
    power_ratio_degraded_max: float = 0.60

    # Misspecification multiplier (+/- 30% evaluation)
    prior_scale: float = 1.0

    # Vehicle-side failure dynamics
    vehicle_failure_rate: float = 0.03
    timeout_cost_sec: float = 120.0

    # Forgetting & group pooling
    forgetting_half_life_sec: float = 3600.0  # ~1 hour
    pooling_clip_min: float = 0.20
    pooling_clip_max: float = 5.00
    probe_rate: float = 0.05

    # Space-time scan parameters
    scan_windows_min: Tuple[int, ...] = (15, 30, 60, 120)
    scan_persistence: int = 2
    false_alarm_budget_per_week: float = 1.0

    # Simulator dimensions & calibration
    num_connectors: int = 200
    num_sites: int = 60
    num_operators: int = 4
    num_models: int = 5
    num_firmwares: int = 3
    baseline_deadend_count: int = 44
    baseline_degraded_count: int = 20
    target_first_attempt_success: float = 0.71

    # Synthetic Chennai bounding box
    lat_min: float = 12.85
    lat_max: float = 13.20
    lon_min: float = 80.10
    lon_max: float = 80.35

    # Evaluation seeds
    dev_seeds: Tuple[int, ...] = tuple(range(10))
    eval_seeds: Tuple[int, ...] = tuple(range(100, 120))

    # Pipeline latency target (p95 latency in ms)
    p95_latency_target_ms: float = 500.0

    # Parameters not specified in spec are explicitly set to None (tracked in PROGRESS.md)
    unspecified_param_example: Optional[Any] = None

    def get_scaled_p_start(self) -> Dict[str, float]:
        """Return p_start values scaled by prior_scale and clipped to [0.0, 1.0]."""
        def scale(p: float) -> float:
            scaled = p * self.prior_scale
            return max(0.0, min(1.0, scaled))

        return {
            "healthy": scale(self.p_start_healthy),
            "degraded": scale(self.p_start_degraded),
            "deadend": scale(self.p_start_deadend),
            "offline": scale(self.p_start_offline),
        }

    def with_overrides(self, **kwargs: Any) -> Config:
        """Return a new Config instance with updated field values."""
        return dataclasses.replace(self, **kwargs)

    @classmethod
    def from_yaml(cls, path_or_stream: str | Path) -> Config:
        """Load configuration overrides from a YAML file or string."""
        if isinstance(path_or_stream, (str, Path)) and Path(path_or_stream).is_file():
            with open(path_or_stream, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = yaml.safe_load(path_or_stream) or {}

        # Convert list fields to tuple for frozen immutability if provided in yaml
        for list_field in ("scan_windows_min", "dev_seeds", "eval_seeds"):
            if list_field in data and isinstance(data[list_field], list):
                data[list_field] = tuple(data[list_field])

        return cls(**data)
