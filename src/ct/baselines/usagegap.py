"""Arm C: Usage gap anomaly detector baseline policy.

Flags a connector as potentially faulty if it reports AVAILABLE but remains
idle longer than an expected inter-usage threshold without a successful charge.

Notice: This is a simplified reimplementation of usage-gap anomaly detection
(inspired by academic silent-failure detection literature such as Caltrans /
UC Davis EV studies), not the published production system.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from ct.config import Config
from ct.schemas import ReportedStatus, SessionOutcome, VehicleRequestEvent, VehicleSessionEvent
from ct.sim.engine import ObservableSimulationView, Policy


class UsageGapPolicy(Policy):
    """Arm C: Usage gap silent failure detector and router."""
    def __init__(
        self,
        config: Optional[Config] = None,
        gap_multiplier: Optional[float] = None,
        expected_idle_sec: Optional[float] = None,
    ):
        cfg = config or Config()
        self.config = cfg
        self.gap_multiplier = gap_multiplier if gap_multiplier is not None else cfg.usage_gap_multiplier
        self.expected_idle_sec = expected_idle_sec if expected_idle_sec is not None else cfg.usage_gap_expected_idle_sec
        # connector_id -> last successful session timestamp
        self.last_session_ts: Dict[str, int] = {}
        # connector_id -> timestamp when flagged
        self.flagged_at_ts: Dict[str, int] = {}
        self.last_processed_sess_ts = 0
        self._initialized_connectors = False

    def _ensure_initialized(self, view: ObservableSimulationView, now: int) -> None:
        """Seed initial prior timestamps for all connectors in network."""
        if not self._initialized_connectors:
            for c_id in view.connectors:
                if c_id not in self.last_session_ts:
                    # Synthetic prior history: connectors start with baseline idle age
                    self.last_session_ts[c_id] = now - int(self.expected_idle_sec * 500)
            self._initialized_connectors = True

    def record_session(self, event: VehicleSessionEvent) -> None:
        """Record session outcome: only successful charge resets the usage gap timer."""
        c_id = event.connector_id
        if event.outcome == SessionOutcome.STARTED:
            self.last_session_ts[c_id] = event.event_ts
            if c_id in self.flagged_at_ts:
                del self.flagged_at_ts[c_id]
        else:
            # Failed session confirms lack of valid charging; does not reset successful timer
            pass

    def is_flagged(self, connector_id: str, now: int) -> bool:
        """Check if connector is flagged due to an abnormal usage gap."""
        if connector_id not in self.last_session_ts:
            return False

        last_ts = self.last_session_ts[connector_id]
        idle_duration_sec = (now - last_ts) / 1000.0
        max_allowed_idle = self.expected_idle_sec * self.gap_multiplier

        if idle_duration_sec > max_allowed_idle:
            self.flagged_at_ts[connector_id] = now
            return True
        return False

    def choose(
        self,
        request: VehicleRequestEvent,
        view: ObservableSimulationView,
    ) -> List[str]:
        now = request.event_ts
        self._ensure_initialized(view, now)

        # Process session history
        for sess in view.session_history:
            if sess.event_ts > self.last_processed_sess_ts:
                self.record_session(sess)
        if view.session_history:
            self.last_processed_sess_ts = view.session_history[-1].event_ts

        candidates = []
        for c_id, meta in view.connectors.items():
            st = view.get_latest_status(c_id)
            is_avail = (st is not None and st.reported_status == ReportedStatus.AVAILABLE)
            flagged = self.is_flagged(c_id, now)

            travel_sec = view.graph.travel_time_sec(
                request.current_lat, request.current_lon, meta.site_lat, meta.site_lon
            )

            # Preference tier:
            # 0: Available and NOT flagged
            # 1: Not available, but NOT flagged
            # 2: Flagged as abnormal usage gap (routed around)
            tier = 2 if flagged else (0 if is_avail else 1)
            candidates.append((tier, travel_sec, c_id))

        candidates.sort(key=lambda x: (x[0], x[1]))
        return [c_id for _, _, c_id in candidates]
