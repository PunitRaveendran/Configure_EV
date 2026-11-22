"""Expected trip-time router with 1-step lookahead for Charger Truth.

Pure Python, no Kafka or Condense dependencies.

Ranks candidate connectors by expected total duration:
T = t + p*(w + s) + (1-p)*(t_fail + T_next)
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

from ct.config import Config
from ct.core.belief import BaseBeliefEstimator
from ct.schemas import (
    ReportedStatus,
    RouteCandidate,
    RouteDecisionEvent,
    VehicleRequestEvent,
)
from ct.sim.engine import ObservableSimulationView, Policy


class ExpectedTimeRouter(Policy):
    """Arm D: Belief-based router minimizing expected trip + charge time with 1-step lookahead."""
    def __init__(
        self,
        config: Config,
        belief_estimator: BaseBeliefEstimator,
        active_alert_group_keys: Optional[Set[str]] = None,
        kwh_per_km: float = 0.18,
    ):
        self.config = config
        self.belief_estimator = belief_estimator
        self.active_alert_group_keys = active_alert_group_keys or set()
        self.kwh_per_km = kwh_per_km

    def _is_reachable(
        self,
        request: VehicleRequestEvent,
        site_lat: float,
        site_lon: float,
        view: ObservableSimulationView,
    ) -> Tuple[bool, float]:
        """Check if vehicle has sufficient range to reach site with reserve SoC."""
        dist_km = view.graph.haversine_km(
            request.current_lat, request.current_lon, site_lat, site_lon
        ) * 1.25  # detour factor

        energy_needed_kwh = dist_km * self.kwh_per_km
        usable_soc = max(0.0, request.current_soc - request.reserve_soc)
        usable_kwh = request.battery_kwh * usable_soc

        return (usable_kwh >= energy_needed_kwh), dist_km

    def plan_route(
        self,
        request: VehicleRequestEvent,
        view: ObservableSimulationView,
    ) -> Tuple[List[str], RouteDecisionEvent]:
        """Compute ranked candidates and structured RouteDecisionEvent."""
        now = request.event_ts
        timeout_cost_min = self.config.timeout_cost_sec / 60.0
        energy_to_charge_kwh = request.battery_kwh * max(0.0, request.target_soc - request.current_soc)

        candidate_scores: List[Tuple[float, RouteCandidate, str]] = []

        for c_id, meta in view.connectors.items():
            # Range check with reserve
            reachable, dist_km = self._is_reachable(request, meta.site_lat, meta.site_lon, view)
            if not reachable:
                continue

            travel_min = view.graph.travel_time_min(
                request.current_lat, request.current_lon, meta.site_lat, meta.site_lon
            )

            # Retrieve belief P(start)
            p = self.belief_estimator.p_start(c_id, now)

            # Wait time estimate (check latest status)
            st = view.get_latest_status(c_id)
            wait_min = 0.0
            if st and st.reported_status == ReportedStatus.CHARGING:
                wait_min = self.config.wait_heuristic_charging_min
            elif st and st.reported_status in (ReportedStatus.FAULTED, ReportedStatus.OFFLINE):
                wait_min = self.config.wait_heuristic_faulted_min

            # Charging time estimate
            charge_power = min(request.max_charge_rate_kw, meta.rated_kw)
            charge_min = (energy_to_charge_kwh / max(10.0, charge_power)) * 60.0

            # Direct expected time: t + p*(w + s) + (1-p)*(t_fail + fallback)
            direct_t = travel_min + p * (wait_min + charge_min) + (1.0 - p) * (timeout_cost_min + 15.0)

            cand = RouteCandidate(
                connector_id=c_id,
                site_id=meta.site_id,
                expected_time_min=round(direct_t, 1),
                p_start=round(p, 3),
                travel_time_min=round(travel_min, 1),
                wait_time_min=round(wait_min, 1),
                charge_time_min=round(charge_min, 1),
            )
            candidate_scores.append((direct_t, cand, meta.operator_id))

        if not candidate_scores:
            # Fallback if no reachable connector found within reserve
            empty_decision = RouteDecisionEvent(
                event_ts=now,
                request_id=request.request_id,
                vehicle_id=request.vehicle_id,
                selected_connector_id=None,
                ranked_candidates=[],
                reason="No reachable connector within reserve range",
            )
            return [], empty_decision

        # Sort candidate scores preliminarily
        candidate_scores.sort(key=lambda x: x[0])

        # Apply 1-step lookahead recursion:
        # T = t + p*(w + s) + (1-p)*(t_fail + T_next)
        refined_scores: List[Tuple[float, RouteCandidate, str]] = []
        top_candidates = candidate_scores[:10]

        for i, (dir_t, cand, op_id) in enumerate(top_candidates):
            p = cand.p_start
            t = cand.travel_time_min
            w = cand.wait_time_min
            s = cand.charge_time_min

            # T_next = best follow-up among next 3 candidates
            follow_ups = [c.expected_time_min for j, (_, c, _) in enumerate(top_candidates) if j != i]
            t_next = min(follow_ups[:3]) if follow_ups else dir_t

            # Expected total time with 1-step lookahead
            lookahead_t = t + p * (w + s) + (1.0 - p) * (timeout_cost_min + t_next)

            # Check if cluster alert is active on this connector's site or operator
            alert_active = (
                cand.site_id in self.active_alert_group_keys
                or op_id in self.active_alert_group_keys
            )
            if alert_active:
                lookahead_t += 10.0  # penalty for active cluster alert

            updated_cand = RouteCandidate(
                connector_id=cand.connector_id,
                site_id=cand.site_id,
                expected_time_min=round(lookahead_t, 1),
                p_start=cand.p_start,
                travel_time_min=cand.travel_time_min,
                wait_time_min=cand.wait_time_min,
                charge_time_min=cand.charge_time_min,
            )
            refined_scores.append((lookahead_t, updated_cand, op_id))

        refined_scores.sort(key=lambda x: x[0])
        ranked_candidates = [c for _, c, _ in refined_scores]
        selected = ranked_candidates[0]

        # Construct clear decision reason string
        top_p = selected.p_start
        if top_p < 0.40:
            reason = f"p={top_p:.2f} (degraded/suspicious); expected T={selected.expected_time_min:.1f}m"
        else:
            reason = (
                f"p={top_p:.2f}, travel={selected.travel_time_min:.1f}m, "
                f"charge={selected.charge_time_min:.1f}m; optimal expected total T={selected.expected_time_min:.1f}m"
            )

        decision_event = RouteDecisionEvent(
            event_ts=now,
            request_id=request.request_id,
            vehicle_id=request.vehicle_id,
            selected_connector_id=selected.connector_id,
            ranked_candidates=ranked_candidates[:5],
            reason=reason,
        )

        ranked_ids = [c.connector_id for c in ranked_candidates]
        return ranked_ids, decision_event

    def choose(
        self,
        request: VehicleRequestEvent,
        view: ObservableSimulationView,
    ) -> List[str]:
        """Policy interface implementation."""
        ranked_ids, _ = self.plan_route(request, view)
        return ranked_ids


class BeliefPolicy(Policy):
    """Full Arm D policy: Online HMM belief filter + Group Pooling + Space-Time Scan + Router."""
    def __init__(
        self,
        config: Config,
        enable_pooling: bool = True,
        enable_scan: bool = True,
        enable_probing: bool = True,
        enable_vehicle_outcomes: bool = True,
        p_flag_threshold: float = 0.50,
    ):
        self.config = config
        self.enable_pooling = enable_pooling
        self.enable_scan = enable_scan
        self.enable_probing = enable_probing
        self.enable_vehicle_outcomes = enable_vehicle_outcomes
        self.p_flag_threshold = p_flag_threshold

        from ct.core.belief import HMMBeliefEstimator
        from ct.core.pooling import GroupPooler
        from ct.core.scan import KulldorffClusterScanner

        self.pooler = GroupPooler(config) if enable_pooling else None
        self.estimator: Optional[HMMBeliefEstimator] = None
        self.scanner: Optional[KulldorffClusterScanner] = None
        self.router: Optional[ExpectedTimeRouter] = None

        self.flagged_at_ts: Dict[str, int] = {}
        self._last_processed_status_ts: Dict[str, int] = {}
        self._last_processed_sess_idx = 0

    def is_flagged(self, connector_id: str, now: int) -> bool:
        """Check if connector is flagged as degraded/unhealthy by belief threshold."""
        if self.estimator is None:
            return False
        return bool(self.estimator.p_start(connector_id, now) < self.p_flag_threshold)

    def _init_components_if_needed(self, view: ObservableSimulationView) -> None:
        if self.estimator is None:
            from ct.core.belief import HMMBeliefEstimator
            from ct.core.scan import KulldorffClusterScanner

            self.estimator = HMMBeliefEstimator(
                self.config, connectors_meta=view.connectors, pooler=self.pooler
            )
            self.scanner = KulldorffClusterScanner(self.config, connectors_meta=view.connectors)
            self.router = ExpectedTimeRouter(
                self.config,
                belief_estimator=self.estimator,
                active_alert_group_keys=set(),
            )

    def choose(
        self,
        request: VehicleRequestEvent,
        view: ObservableSimulationView,
    ) -> List[str]:
        self._init_components_if_needed(view)
        now = request.event_ts

        # Ingest new status heartbeats
        for c_id, st in view.latest_statuses.items():
            if st.event_ts > self._last_processed_status_ts.get(c_id, 0):
                self.estimator.update(st)
                self._last_processed_status_ts[c_id] = st.event_ts

        # Ingest new session outcomes
        history = view.session_history
        while self._last_processed_sess_idx < len(history):
            sess = history[self._last_processed_sess_idx]
            if self.enable_vehicle_outcomes:
                self.estimator.update(sess)
            if self.enable_scan:
                self.scanner.record_session(sess)
            self._last_processed_sess_idx += 1

        # Evaluate scan alerts if enabled
        if self.enable_scan:
            alerts = self.scanner.evaluate(now)
            active_keys = {a.group_key for a in alerts}
            self.router.active_alert_group_keys = active_keys
            for a in alerts:
                if a.group_key not in self.flagged_at_ts:
                    self.flagged_at_ts[a.group_key] = a.event_ts

        # Update connector-level flag timestamps
        for c_id in view.connectors:
            p = self.estimator.p_start(c_id, now)
            if p < self.p_flag_threshold:
                if c_id not in self.flagged_at_ts:
                    self.flagged_at_ts[c_id] = now
            elif p >= self.p_flag_threshold and c_id in self.flagged_at_ts:
                del self.flagged_at_ts[c_id]

        # Check active probing if enabled
        if self.enable_probing:
            probes = self.estimator.probe_candidates(request, now)
            if probes and (request.current_soc - request.reserve_soc) > 0.15:
                # 5% probe rate
                hash_val = abs(hash(f"probe_{request.request_id}")) % 100
                if hash_val < int(self.config.probe_rate * 100):
                    return probes + self.router.choose(request, view)

        return self.router.choose(request, view)
