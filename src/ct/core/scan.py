"""Prospective Kulldorff-style space-time cluster scan for Charger Truth.

Pure Python and numpy, no Kafka or Condense dependencies.

Monitors groups: site, operator, firmware, operator x firmware across
rolling windows (15, 30, 60, 120 min) to detect correlated hardware,
backend, or firmware failure bursts.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from ct.config import Config
from ct.schemas import (
    ClusterAlertEvent,
    GroupType,
    SessionOutcome,
    VehicleSessionEvent,
)


@dataclass(frozen=True)
class AttemptRecord:
    """Historical session attempt record for scan windows."""
    event_ts: int
    connector_id: str
    site_id: str
    operator_id: str
    firmware_version: str
    is_failure: bool


@dataclass
class GroupEvaluationState:
    """Tracking consecutive threshold exceedance for persistence."""
    consecutive_hits: int = 0
    last_eval_ts: int = 0
    last_alert: Optional[ClusterAlertEvent] = None


class KulldorffClusterScanner:
    """Prospective space-time scan statistic evaluator."""
    def __init__(
        self,
        config: Config,
        connectors_meta: Optional[Dict[str, Any]] = None,
        baseline_failure_rate: float = 0.25,
        threshold_override: Optional[float] = None,
    ):
        self.config = config
        self.connectors_meta = connectors_meta or {}
        self.baseline_failure_rate = baseline_failure_rate

        # Calibrated Monte Carlo null threshold for false-alarm budget (default 1 per week)
        # Sized so P(max LLR > threshold under null) <= 1 / 10080 per evaluation
        self.threshold = threshold_override if threshold_override is not None else 8.50

        # Attempt history buffer
        self.history: deque[AttemptRecord] = deque()
        # Group persistence tracking: key -> GroupEvaluationState
        self.eval_states: Dict[str, GroupEvaluationState] = {}
        # Active alerts: group_key -> ClusterAlertEvent
        self.active_alerts: Dict[str, ClusterAlertEvent] = {}

    def record_session(self, event: VehicleSessionEvent) -> None:
        """Ingest vehicle session attempt outcome."""
        meta = self.connectors_meta.get(event.connector_id)
        site_id = getattr(meta, "site_id", "")
        op_id = getattr(meta, "operator_id", "")
        fw = getattr(meta, "firmware_version", "")

        is_fail = event.outcome in (SessionOutcome.FAILED, SessionOutcome.TIMEOUT)
        rec = AttemptRecord(
            event_ts=event.event_ts,
            connector_id=event.connector_id,
            site_id=site_id,
            operator_id=op_id,
            firmware_version=fw,
            is_failure=is_fail,
        )
        self.history.append(rec)

        # Evict records older than maximum window (120 min = 7200 sec)
        max_window_ms = max(self.config.scan_windows_min) * 60 * 1000
        cutoff_ts = event.event_ts - max_window_ms
        while self.history and self.history[0].event_ts < cutoff_ts:
            self.history.popleft()

    @staticmethod
    def calculate_llr(n: int, c: int, expected_e: float) -> float:
        """Calculate Poisson/Binomial Log-Likelihood Ratio (LLR) for cluster detection.
        
        LLR = c * ln(c/e) + (n-c) * ln((n-c)/(n-e)) when c > e
        Handles edge cases (n == c, e == 0) safely.
        """
        if c <= expected_e or expected_e <= 0.0 or n <= 0:
            return 0.0

        if n == c:
            # All attempts failed: second term approaches 0
            return float(c * math.log(c / expected_e))

        # Regular case: c > expected_e and c < n
        denom = n - expected_e
        if denom <= 0.0:
            return float(c * math.log(c / expected_e))

        term1 = c * math.log(c / expected_e)
        term2 = (n - c) * math.log((n - c) / denom)
        return float(max(0.0, term1 + term2))

    def evaluate(self, current_ts: int) -> List[ClusterAlertEvent]:
        """Evaluate prospective space-time scan across all groups and windows."""
        new_alerts: List[ClusterAlertEvent] = []
        windows_min = self.config.scan_windows_min

        # Group attempts into candidate clusters
        groups: Dict[Tuple[GroupType, str], List[AttemptRecord]] = {}

        for rec in self.history:
            # 1. Site group
            if rec.site_id:
                groups.setdefault((GroupType.SITE, rec.site_id), []).append(rec)
            # 2. Operator group
            if rec.operator_id:
                groups.setdefault((GroupType.OPERATOR, rec.operator_id), []).append(rec)
            # 3. Firmware group
            if rec.firmware_version:
                groups.setdefault((GroupType.FIRMWARE, rec.firmware_version), []).append(rec)
            # 4. Operator x Firmware
            if rec.operator_id and rec.firmware_version:
                op_fw_key = f"{rec.operator_id}:{rec.firmware_version}"
                groups.setdefault((GroupType.OPERATOR_X_FIRMWARE, op_fw_key), []).append(rec)

        # Track which groups exceed threshold in this evaluation
        candidates_exceeding: Dict[str, Tuple[GroupType, str, int, float, int, float, List[str]]] = {}

        for (g_type, g_key), recs in groups.items():
            best_llr = 0.0
            best_window = 15
            best_n, best_c, best_e = 0, 0, 0.0
            best_conn_ids: Set[str] = set()

            for w_min in windows_min:
                cutoff = current_ts - (w_min * 60 * 1000)
                window_recs = [r for r in recs if r.event_ts >= cutoff]
                n = len(window_recs)
                if n < 3:
                    # Require minimum sample size to avoid false alarms on tiny n
                    continue

                # Operator or Firmware cluster faults must span >= 2 distinct sites
                # If all failures are at a single site, it is a local site fault, not a fleet fault
                if g_type in (GroupType.OPERATOR, GroupType.FIRMWARE, GroupType.OPERATOR_X_FIRMWARE):
                    failing_sites = {r.site_id for r in window_recs if r.is_failure}
                    if len(failing_sites) < 2:
                        continue

                c = sum(1 for r in window_recs if r.is_failure)
                e = n * self.baseline_failure_rate
                llr = self.calculate_llr(n, c, e)

                if llr > best_llr:
                    best_llr = llr
                    best_window = w_min
                    best_n = n
                    best_c = c
                    best_e = e
                    best_conn_ids = {r.connector_id for r in window_recs}

            if best_llr >= self.threshold:
                full_key = f"{g_type.value}:{g_key}"
                candidates_exceeding[full_key] = (
                    g_type,
                    g_key,
                    best_window,
                    best_llr,
                    best_c,
                    best_e,
                    sorted(best_conn_ids),
                )

        # Check persistence (must exceed threshold on 2 consecutive evaluations)
        active_group_keys: Set[str] = set()
        unsuppressed_alerts: List[ClusterAlertEvent] = []

        for full_key, (g_type, g_key, w_min, llr, c, e, conn_ids) in candidates_exceeding.items():
            if full_key not in self.eval_states:
                self.eval_states[full_key] = GroupEvaluationState()

            st = self.eval_states[full_key]
            st.consecutive_hits += 1
            st.last_eval_ts = current_ts

            if st.consecutive_hits >= self.config.scan_persistence:
                alert = ClusterAlertEvent(
                    event_ts=current_ts,
                    alert_id=f"alt_{g_type.value}_{g_key}_{current_ts}",
                    group_type=g_type,
                    group_key=g_key,
                    window_min=w_min,
                    llr=round(llr, 2),
                    threshold=round(self.threshold, 2),
                    observed_failures=c,
                    expected_failures=round(e, 2),
                    member_connector_ids=conn_ids,
                    consecutive_count=st.consecutive_hits,
                )
                unsuppressed_alerts.append(alert)
                active_group_keys.add(full_key)

        # Reset consecutive count for groups that did not exceed threshold in this eval
        for full_key, st in list(self.eval_states.items()):
            if full_key not in candidates_exceeding:
                st.consecutive_hits = 0
                if full_key in self.active_alerts:
                    del self.active_alerts[full_key]

        # Suppress nested alerts:
        # If an operator or firmware alert is active, suppress child site alerts belonging to that group
        suppressed_alerts: List[ClusterAlertEvent] = []
        active_operators = {a.group_key for a in unsuppressed_alerts if a.group_type == GroupType.OPERATOR}
        active_firmwares = {a.group_key for a in unsuppressed_alerts if a.group_type == GroupType.FIRMWARE}

        for alert in unsuppressed_alerts:
            if alert.group_type == GroupType.SITE:
                # Check if site's operator or firmware is already alerting
                site_meta = [m for m in self.connectors_meta.values() if getattr(m, "site_id", None) == alert.group_key]
                if site_meta:
                    op = getattr(site_meta[0], "operator_id", "")
                    fw = getattr(site_meta[0], "firmware_version", "")
                    if op in active_operators or fw in active_firmwares:
                        # Suppress nested site alert
                        continue

            suppressed_alerts.append(alert)
            self.active_alerts[f"{alert.group_type.value}:{alert.group_key}"] = alert

        return suppressed_alerts
