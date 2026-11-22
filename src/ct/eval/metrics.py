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

from ct.config import Config
from ct.schemas import (
    ClusterAlertEvent,
    SessionOutcome,
    VehicleRequestEvent,
    VehicleSessionEvent,
)
from ct.sim.failures import FaultEvent, FirmwareBug, OperatorOutage, SiteOutage


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
    config: Optional[Config] = None,
) -> float:
    """Total driver minutes wasted on failed attempts and timeout delays."""
    cfg = config or Config()
    detour_min = cfg.detour_penalty_min
    total_wasted = 0.0
    for s in session_events:
        if s.outcome != SessionOutcome.STARTED:
            timeout_min = (s.time_to_current_sec or (cfg.timeout_cost_sec)) / 60.0
            total_wasted += timeout_min + detour_min
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


def compute_detection_latency(
    faults: List[FaultEvent],
    flag_times: Dict[str, int],
    horizon_sec: float = 3600.0,
    connectors_meta: Optional[Dict[str, Any]] = None,
) -> float:
    """Average detection latency in minutes from fault start until connector/group is flagged.
    
    If not flagged during the horizon, penalized by horizon duration.
    """
    if not faults:
        return 0.0

    latencies_min: List[float] = []
    for f in faults:
        start_ts = f.start_ts
        # Identify affected target keys
        target_keys: List[str] = []
        if isinstance(f, SiteOutage):
            target_keys.append(f.site_id)
            if connectors_meta:
                target_keys.extend([
                    cid for cid, m in connectors_meta.items()
                    if getattr(m, "site_id", None) == f.site_id
                ])
        elif isinstance(f, OperatorOutage):
            target_keys.append(f.operator_id)
            if f.affected_connector_ids:
                target_keys.extend(list(f.affected_connector_ids))
            elif connectors_meta:
                target_keys.extend([
                    cid for cid, m in connectors_meta.items()
                    if getattr(m, "operator_id", None) == f.operator_id
                ])
        elif isinstance(f, FirmwareBug):
            target_keys.append(f.firmware_version)
            if connectors_meta:
                target_keys.extend([
                    cid for cid, m in connectors_meta.items()
                    if getattr(m, "firmware_version", None) == f.firmware_version
                ])

        # Earliest flag time for any affected key
        valid_flag_times = [
            flag_times[k] for k in target_keys
            if k in flag_times and flag_times[k] >= start_ts
        ]

        if valid_flag_times:
            earliest_ts = min(valid_flag_times)
            latency_min = max(0.0, (earliest_ts - start_ts) / 60000.0)
            latencies_min.append(latency_min)
        else:
            # Penalized by horizon
            latencies_min.append(horizon_sec / 60.0)

    return round(float(np.mean(latencies_min)), 2)


def compute_cluster_alert_precision_recall(
    faults: List[FaultEvent],
    alerts: List[ClusterAlertEvent],
) -> Tuple[float, float]:
    """Calculate precision and recall for cluster alerts against injected fault schedule."""
    if not alerts and not faults:
        return 1.0, 1.0
    if not alerts and faults:
        return 0.0, 0.0
    if alerts and not faults:
        return 0.0, 1.0

    # Build lookup of fault intervals by key
    fault_lookup: Dict[str, List[Tuple[int, int]]] = {}
    for f in faults:
        keys = []
        if isinstance(f, SiteOutage):
            keys.append(f.site_id)
        elif isinstance(f, OperatorOutage):
            keys.append(f.operator_id)
        elif isinstance(f, FirmwareBug):
            keys.append(f.firmware_version)

        for k in keys:
            fault_lookup.setdefault(k, []).append((f.start_ts, f.end_ts))

    tp = 0
    fp = 0
    detected_fault_keys = set()

    for alt in alerts:
        g_key = alt.group_key
        ts = alt.event_ts
        is_true_positive = False
        if g_key in fault_lookup:
            for start, end in fault_lookup[g_key]:
                if start <= ts <= end + 300000:  # 5 min tolerance
                    is_true_positive = True
                    detected_fault_keys.add(g_key)
                    break
        if is_true_positive:
            tp += 1
        else:
            fp += 1

    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(len(detected_fault_keys) / len(fault_lookup)) if fault_lookup else 1.0
    return round(precision, 3), round(recall, 3)


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
