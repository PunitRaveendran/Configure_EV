"""Evaluation metrics and statistical analysis for Charger Truth.

Computes:
- Wasted-trip rate and wasted minutes
- Time-to-charged mean and 90th percentile (p90)
- Failure-detection latency
- Cluster alert precision and recall
- Paired bootstrap 95% confidence intervals
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import numpy as np

from ct.schemas import SessionOutcome, VehicleRequestEvent, VehicleSessionEvent


def compute_wasted_trip_rate(session_events: List[VehicleSessionEvent]) -> float:
    """Fraction of first attempts that failed or timed out."""
    first_attempts = [s for s in session_events if s.session_id.endswith("_1")]
    if not first_attempts:
        return 0.0
    failures = sum(1 for s in first_attempts if s.outcome != SessionOutcome.STARTED)
    return float(failures / len(first_attempts))


def compute_wasted_minutes(
    session_events: List[VehicleSessionEvent],
    timeout_cost_min: float = 2.0,
) -> float:
    """Total driver minutes wasted on failed attempts and timeout delays."""
    total_wasted = 0.0
    for s in session_events:
        if s.outcome != SessionOutcome.STARTED:
            timeout_min = (s.time_to_current_sec or 120.0) / 60.0
            # Driver wasted travel time + timeout penalty
            total_wasted += timeout_min + 5.0  # ~5 min detour travel penalty
    return round(float(total_wasted), 1)


def compute_time_to_charged(
    requests: List[VehicleRequestEvent],
    session_events: List[VehicleSessionEvent],
) -> Tuple[float, float]:
    """Calculate mean and 90th percentile (p90) minutes from request to successful charge."""
    req_time_map = {r.vehicle_id: r.event_ts for r in requests}
    successful_durations_min: List[float] = []

    for s in session_events:
        if s.outcome == SessionOutcome.STARTED and s.vehicle_id in req_time_map:
            start_ts = req_time_map[s.vehicle_id]
            duration_min = max(0.0, (s.event_ts - start_ts) / 60000.0)
            successful_durations_min.append(duration_min)

    if not successful_durations_min:
        return 0.0, 0.0

    mean_ttc = float(np.mean(successful_durations_min))
    p90_ttc = float(np.percentile(successful_durations_min, 90))
    return round(mean_ttc, 2), round(p90_ttc, 2)


def paired_bootstrap_ci(
    diffs: List[float],
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Compute paired bootstrap 95% confidence interval for mean differences."""
    if not diffs:
        return 0.0, 0.0, 0.0

    rng = np.random.RandomState(seed)
    arr = np.array(diffs, dtype=float)
    mean_val = float(np.mean(arr))

    boot_means = np.empty(n_resamples, dtype=float)
    n = len(arr)
    for b in range(n_resamples):
        sample = rng.choice(arr, size=n, replace=True)
        boot_means[b] = np.mean(sample)

    low_ci = float(np.percentile(boot_means, (alpha / 2.0) * 100))
    high_ci = float(np.percentile(boot_means, (1.0 - alpha / 2.0) * 100))
    return round(mean_val, 4), round(low_ci, 4), round(high_ci, 4)
