"""Arm A: Reported status baseline policy.

Ranks connectors purely by reported status from heartbeats (AVAILABLE first)
and travel time on the road graph.

Notice: This is a simplified reimplementation of common real-world routing
apps that trust charger-reported availability without vehicle outcome verification.
"""
from __future__ import annotations

from typing import Dict, List
from ct.schemas import ReportedStatus, VehicleRequestEvent
from ct.sim.engine import ObservableSimulationView, Policy


class ReportedStatusPolicy(Policy):
    """Arm A: Rank by reported status (AVAILABLE), then travel time."""
    def __init__(self):
        # connector_id -> timestamp when flagged
        self.flagged_at_ts: Dict[str, int] = {}

    def is_flagged(self, connector_id: str, view: ObservableSimulationView) -> bool:
        """Check if connector is currently reported FAULTED or OFFLINE."""
        st = view.get_latest_status(connector_id)
        return st is not None and st.reported_status in (ReportedStatus.FAULTED, ReportedStatus.OFFLINE)

    def choose(
        self,
        request: VehicleRequestEvent,
        view: ObservableSimulationView,
    ) -> List[str]:
        candidates = []
        for c_id, meta in view.connectors.items():
            st = view.get_latest_status(c_id)
            is_avail = (st is not None and st.reported_status == ReportedStatus.AVAILABLE)
            
            # Record flag time if reported offline/faulted
            if st and st.reported_status in (ReportedStatus.FAULTED, ReportedStatus.OFFLINE):
                if c_id not in self.flagged_at_ts:
                    self.flagged_at_ts[c_id] = request.event_ts
            elif st and st.reported_status == ReportedStatus.AVAILABLE:
                if c_id in self.flagged_at_ts:
                    del self.flagged_at_ts[c_id]

            travel_sec = view.graph.travel_time_sec(
                request.current_lat,
                request.current_lon,
                meta.site_lat,
                meta.site_lon,
            )
            # Available chargers get priority (0), non-available get (1)
            candidates.append((0 if is_avail else 1, travel_sec, c_id))

        candidates.sort(key=lambda x: (x[0], x[1]))
        return [c_id for _, _, c_id in candidates]
