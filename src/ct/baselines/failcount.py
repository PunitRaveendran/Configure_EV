"""Arm B: Consecutive failure counter baseline policy.

Flags a connector as faulty after k consecutive failed sessions.
Routes vehicles around flagged connectors.

Notice: This is a simplified reimplementation of common rule-based
EV charging heuristics (e.g. fleet threshold triggers), not a proprietary
or published commercial system.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from ct.schemas import ReportedStatus, SessionOutcome, VehicleRequestEvent, VehicleSessionEvent
from ct.sim.engine import ObservableSimulationView, Policy


class FailCountPolicy(Policy):
    """Arm B: Consecutive failure count flagger and router."""
    def __init__(self, k_consecutive: int = 2, cooldown_sec: float = 7200.0):
        self.k_consecutive = k_consecutive
        self.cooldown_sec = cooldown_sec
        # connector_id -> consecutive failure count
        self.failure_counts: Dict[str, int] = {}
        # connector_id -> timestamp when flagged
        self.flagged_at_ts: Dict[str, int] = {}
        self.last_outcome_ts: Dict[str, int] = {}

    def record_session(self, event: VehicleSessionEvent) -> None:
        """Update consecutive failure counters from session outcomes."""
        c_id = event.connector_id
        self.last_outcome_ts[c_id] = event.event_ts

        if event.outcome == SessionOutcome.STARTED:
            self.failure_counts[c_id] = 0
            if c_id in self.flagged_at_ts:
                del self.flagged_at_ts[c_id]
        else:
            self.failure_counts[c_id] = self.failure_counts.get(c_id, 0) + 1
            if self.failure_counts[c_id] >= self.k_consecutive:
                if c_id not in self.flagged_at_ts:
                    self.flagged_at_ts[c_id] = event.event_ts

    def is_flagged(self, connector_id: str, now: int) -> bool:
        """Check if connector is currently flagged as faulty."""
        if connector_id not in self.flagged_at_ts:
            return False
        # Cooldown check
        flag_ts = self.flagged_at_ts[connector_id]
        if (now - flag_ts) / 1000.0 > self.cooldown_sec:
            del self.flagged_at_ts[connector_id]
            self.failure_counts[connector_id] = 0
            return False
        return True

    def choose(
        self,
        request: VehicleRequestEvent,
        view: ObservableSimulationView,
    ) -> List[str]:
        # Process any recent sessions from view history
        for sess in view.session_history:
            if sess.event_ts > self.last_outcome_ts.get(sess.connector_id, 0):
                self.record_session(sess)

        candidates = []
        for c_id, meta in view.connectors.items():
            st = view.get_latest_status(c_id)
            is_avail = (st is not None and st.reported_status == ReportedStatus.AVAILABLE)
            flagged = self.is_flagged(c_id, request.event_ts)

            travel_sec = view.graph.travel_time_sec(
                request.current_lat, request.current_lon, meta.site_lat, meta.site_lon
            )

            # Preference tier:
            # 0: Available and NOT flagged
            # 1: Not available, but NOT flagged
            # 2: Flagged as faulty (routed around)
            tier = 2 if flagged else (0 if is_avail else 1)
            candidates.append((tier, travel_sec, c_id))

        candidates.sort(key=lambda x: (x[0], x[1]))
        return [c_id for _, _, c_id in candidates]
