"""Closed-loop discrete-event simulation engine for Charger Truth.

All data is strictly SIMULATED.
"""
from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple
import numpy as np

from ct.config import Config
from ct.schemas import (
    ChargerStatusEvent,
    ReportedStatus,
    SessionOutcome,
    VehicleRequestEvent,
    VehicleSessionEvent,
)
from ct.sim.demand import VehicleDemandGenerator
from ct.sim.failures import (
    FailureSchedule,
    FaultEvent,
    FirmwareBug,
    HiddenState,
    OperatorOutage,
    SiteOutage,
    StatusHeartbeatGenerator,
)
from ct.sim.network import ConnectorSim, RoadGraph, SiteSim, build_synthetic_network


@dataclass(frozen=True)
class ConnectorMetadata:
    """Public observable metadata for a connector (no hidden state)."""
    connector_id: str
    site_id: str
    operator_id: str
    model_id: str
    firmware_version: str
    rated_kw: float
    site_lat: float
    site_lon: float


class ObservableSimulationView:
    """View exposed to routing policies.
    
    Contains ONLY observable events, connector metadata, and road graph.
    Hidden state and fault injection schedules are strictly hidden.
    """
    def __init__(
        self,
        connectors_meta: Dict[str, ConnectorMetadata],
        sites: Dict[str, SiteSim],
        graph: RoadGraph,
    ):
        self._connectors_meta = connectors_meta
        self._sites = sites
        self._graph = graph
        self._recent_statuses: Dict[str, ChargerStatusEvent] = {}
        self._session_history: List[VehicleSessionEvent] = []

    @property
    def connectors(self) -> Dict[str, ConnectorMetadata]:
        return self._connectors_meta

    @property
    def sites(self) -> Dict[str, SiteSim]:
        return self._sites

    @property
    def graph(self) -> RoadGraph:
        return self._graph

    @property
    def latest_statuses(self) -> Dict[str, ChargerStatusEvent]:
        return self._recent_statuses

    @property
    def session_history(self) -> List[VehicleSessionEvent]:
        return self._session_history

    def get_latest_status(self, connector_id: str) -> Optional[ChargerStatusEvent]:
        return self._recent_statuses.get(connector_id)

    def record_status(self, event: ChargerStatusEvent) -> None:
        self._recent_statuses[event.connector_id] = event

    def record_session(self, event: VehicleSessionEvent) -> None:
        self._session_history.append(event)


class Policy(ABC):
    """Abstract base class for routing and connector selection policies."""
    @abstractmethod
    def choose(
        self,
        request: VehicleRequestEvent,
        view: ObservableSimulationView,
    ) -> List[str]:
        """Rank connector IDs in preferred order using ONLY observable information."""
        pass


def make_attempt_rng(seed: int, vehicle_id: str, attempt_no: int) -> np.random.RandomState:
    """Common Random Numbers: Deterministically seed RNG per (seed, vehicle_id, attempt_no)."""
    key_str = f"{seed}:{vehicle_id}:{attempt_no}"
    hash_val = int(hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:8], 16)
    return np.random.RandomState(hash_val)


class SimEngine:
    """Closed-loop simulator running vehicles, charging attempts, and telemetry."""
    def __init__(
        self,
        config: Config,
        seed: int = 42,
        schedule: Optional[FailureSchedule] = None,
        duration_sec: int = 7200,  # default 2 hours
        start_ts: int = 1700000000000,
    ):
        self.config = config
        self.seed = seed
        self.duration_sec = duration_sec
        self.start_ts = start_ts
        self.schedule = schedule or FailureSchedule([])

        self.sites, self.connectors, self.graph = build_synthetic_network(config, seed=seed)
        self.heartbeat_gen = StatusHeartbeatGenerator(config)

        # Build public metadata view
        connectors_meta: Dict[str, ConnectorMetadata] = {}
        for c_id, c in self.connectors.items():
            site = self.sites[c.site_id]
            connectors_meta[c_id] = ConnectorMetadata(
                connector_id=c.connector_id,
                site_id=c.site_id,
                operator_id=c.operator_id,
                model_id=c.model_id,
                firmware_version=c.firmware_version,
                rated_kw=c.rated_kw,
                site_lat=site.lat,
                site_lon=site.lon,
            )

        self.view = ObservableSimulationView(connectors_meta, self.sites, self.graph)
        self.events: List[Any] = []
        self.session_events: List[VehicleSessionEvent] = []

    def run(self, policy: Policy) -> List[Any]:
        """Execute closed-loop simulation under given policy."""
        demand_gen = VehicleDemandGenerator(self.config, seed=self.seed)
        requests = demand_gen.generate_requests(self.start_ts, self.duration_sec)

        # Simulation timeline variables
        current_ts = self.start_ts
        heartbeat_interval_sec = 60
        next_heartbeat_sec = 0

        # Generate initial heartbeat status for all connectors
        hb_rng = np.random.RandomState(self.seed + 1)
        for c_id, conn in self.connectors.items():
            state = self.schedule.get_effective_state(conn, current_ts)
            rep_status = self.heartbeat_gen.sample_reported_status(state, conn.is_occupied, hb_rng)
            ev = ChargerStatusEvent(
                event_ts=current_ts,
                connector_id=c_id,
                site_id=conn.site_id,
                reported_status=rep_status,
            )
            self.events.append(ev)
            self.view.record_status(ev)

        # Process vehicle requests sequentially
        for req in requests:
            req_time_sec = (req.event_ts - self.start_ts) / 1000.0

            # Emit periodic heartbeats up to req_time_sec
            while next_heartbeat_sec <= req_time_sec:
                hb_ts = self.start_ts + int(next_heartbeat_sec * 1000)
                for c_id, conn in self.connectors.items():
                    # Release occupancy if completed
                    if conn.is_occupied and conn.occupied_until_ts <= hb_ts:
                        conn.is_occupied = False

                    state = self.schedule.get_effective_state(conn, hb_ts)
                    rep_status = self.heartbeat_gen.sample_reported_status(
                        state, conn.is_occupied, hb_rng
                    )
                    hb_ev = ChargerStatusEvent(
                        event_ts=hb_ts,
                        connector_id=c_id,
                        site_id=conn.site_id,
                        reported_status=rep_status,
                    )
                    self.events.append(hb_ev)
                    self.view.record_status(hb_ev)
                next_heartbeat_sec += heartbeat_interval_sec

            self.events.append(req)

            # Policy selects candidate connectors
            ranked_connector_ids = policy.choose(req, self.view)
            if not ranked_connector_ids:
                # No connector found, vehicle leaves
                continue

            # Vehicle attempts candidate connectors (up to 3 follow-ups)
            max_attempts = min(3, len(ranked_connector_ids))
            vehicle_current_ts = req.event_ts

            for attempt_no in range(1, max_attempts + 1):
                target_conn_id = ranked_connector_ids[attempt_no - 1]
                target_conn = self.connectors[target_conn_id]
                site = self.sites[target_conn.site_id]

                # Travel time to site
                travel_sec = self.graph.travel_time_sec(
                    req.current_lat, req.current_lon, site.lat, site.lon
                )
                arrival_ts = vehicle_current_ts + int(travel_sec * 1000)

                # Check if connector freed up
                if target_conn.is_occupied and target_conn.occupied_until_ts <= arrival_ts:
                    target_conn.is_occupied = False

                # Evaluate attempt outcome using Common Random Numbers
                attempt_rng = make_attempt_rng(self.seed, req.vehicle_id, attempt_no)
                state = self.schedule.get_effective_state(target_conn, arrival_ts)

                # 1. Check vehicle-side independent failure
                veh_fail = attempt_rng.uniform(0.0, 1.0) < self.config.vehicle_failure_rate
                if veh_fail:
                    outcome = SessionOutcome.FAILED
                    delivered_kw = 0.0
                    duration_sec = 0.0
                    time_to_current = self.config.timeout_cost_sec
                    failure_reason = "vehicle_handshake_fault"
                    vehicle_current_ts = arrival_ts + int(self.config.timeout_cost_sec * 1000)
                else:
                    # 2. Check charger state mechanics
                    if state == HiddenState.HEALTHY:
                        success = attempt_rng.uniform(0.0, 1.0) < self.config.p_start_healthy
                        if success:
                            outcome = SessionOutcome.STARTED
                            ratio = attempt_rng.uniform(
                                self.config.power_ratio_healthy_min,
                                self.config.power_ratio_healthy_max,
                            )
                            delivered_kw = round(target_conn.rated_kw * ratio, 1)
                            energy_needed_kwh = req.battery_kwh * (req.target_soc - req.current_soc)
                            duration_sec = round((energy_needed_kwh / delivered_kw) * 3600.0, 1)
                            time_to_current = round(attempt_rng.uniform(3.0, 8.0), 1)
                            failure_reason = None
                            # Mark connector occupied
                            target_conn.is_occupied = True
                            target_conn.occupied_until_ts = arrival_ts + int(duration_sec * 1000)
                        else:
                            outcome = SessionOutcome.FAILED
                            delivered_kw = 0.0
                            duration_sec = 0.0
                            time_to_current = self.config.timeout_cost_sec
                            failure_reason = "charger_internal_interlock"
                            vehicle_current_ts = arrival_ts + int(self.config.timeout_cost_sec * 1000)

                    elif state == HiddenState.DEGRADED:
                        success = attempt_rng.uniform(0.0, 1.0) < self.config.p_start_degraded
                        if success:
                            outcome = SessionOutcome.STARTED
                            ratio = attempt_rng.uniform(
                                self.config.power_ratio_degraded_min,
                                self.config.power_ratio_degraded_max,
                            )
                            delivered_kw = round(target_conn.rated_kw * ratio, 1)
                            energy_needed_kwh = req.battery_kwh * (req.target_soc - req.current_soc)
                            duration_sec = round((energy_needed_kwh / delivered_kw) * 3600.0, 1)
                            time_to_current = round(attempt_rng.uniform(5.0, 15.0), 1)
                            failure_reason = None
                            target_conn.is_occupied = True
                            target_conn.occupied_until_ts = arrival_ts + int(duration_sec * 1000)
                        else:
                            outcome = SessionOutcome.FAILED
                            delivered_kw = 0.0
                            duration_sec = 0.0
                            time_to_current = self.config.timeout_cost_sec
                            failure_reason = "degraded_inverter_fault"
                            vehicle_current_ts = arrival_ts + int(self.config.timeout_cost_sec * 1000)

                    elif state == HiddenState.DEADEND:
                        success = attempt_rng.uniform(0.0, 1.0) < self.config.p_start_deadend
                        if success:
                            outcome = SessionOutcome.STARTED
                            delivered_kw = target_conn.rated_kw
                            duration_sec = 1800.0
                            time_to_current = 10.0
                            failure_reason = None
                        else:
                            outcome = SessionOutcome.TIMEOUT
                            delivered_kw = 0.0
                            duration_sec = 0.0
                            time_to_current = self.config.timeout_cost_sec
                            failure_reason = "session_handshake_timeout"
                            vehicle_current_ts = arrival_ts + int(self.config.timeout_cost_sec * 1000)

                    elif state == HiddenState.OFFLINE:
                        outcome = SessionOutcome.FAILED
                        delivered_kw = 0.0
                        duration_sec = 0.0
                        time_to_current = 10.0
                        failure_reason = "connector_offline_unreachable"
                        vehicle_current_ts = arrival_ts + 10000

                sess_ev = VehicleSessionEvent(
                    event_ts=arrival_ts,
                    session_id=f"sess_{req.vehicle_id}_{attempt_no}",
                    connector_id=target_conn_id,
                    vehicle_id=req.vehicle_id,
                    outcome=outcome,
                    delivered_kw=delivered_kw,
                    rated_kw=target_conn.rated_kw,
                    time_to_current_sec=time_to_current,
                    failure_reason=failure_reason,
                    duration_sec=duration_sec,
                )

                self.events.append(sess_ev)
                self.session_events.append(sess_ev)
                self.view.record_session(sess_ev)

                if outcome == SessionOutcome.STARTED:
                    # Successfully started charging; vehicle completes request
                    break

        return self.events


def build_scenario_schedule(
    scenario: str,
    connectors: Dict[str, ConnectorSim],
    sites: Dict[str, SiteSim],
    start_ts: int,
    seed: int = 42,
    config: Optional[Config] = None,
) -> FailureSchedule:
    """Build scheduled fault injections for preset scenarios."""
    rng = np.random.RandomState(seed)
    faults: List[FaultEvent] = []
    cfg = config or Config()

    if scenario == "site_outage":
        # Outage at one prominent site starting at t = 1 hour, lasting 1 hour
        chosen_site_id = sorted(sites.keys())[0]
        faults.append(
            SiteOutage(
                start_ts=start_ts + (3600 * 1000),
                duration_sec=3600,
                name="site_substation_trip",
                site_id=chosen_site_id,
            )
        )

    elif scenario == "operator_outage":
        # Backend outage for OP_1 hitting ~30% of their connectors at t = 1.5 hours
        op_conn_ids = [c.connector_id for c in connectors.values() if c.operator_id == "OP_1"]
        num_affected = max(1, int(len(op_conn_ids) * 0.30))
        affected = set(rng.choice(op_conn_ids, size=num_affected, replace=False))
        faults.append(
            OperatorOutage(
                start_ts=start_ts + (5400 * 1000),
                duration_sec=3600,
                name="operator_cloud_timeout",
                operator_id="OP_1",
                affected_fraction=0.30,
                affected_connector_ids=affected,
            )
        )

    elif scenario == "firmware_bug":
        # Firmware bug on FW_v2.0 starting at t = 1.0 hour
        faults.append(
            FirmwareBug(
                start_ts=start_ts + (3600 * 1000),
                duration_sec=7200,
                name="firmware_handshake_crash",
                firmware_version="FW_v2.0",
            )
        )

    elif scenario == "slow_degradation":
        # Introduce degraded hidden state on connectors
        conn_ids = sorted(connectors.keys())
        for cid in conn_ids[: cfg.baseline_degraded_count]:
            connectors[cid].hidden_state = HiddenState.DEGRADED

    elif scenario == "baseline":
        # Background dead-end and degraded connectors calibrated to ~71% first-attempt success
        conn_ids = sorted(connectors.keys())
        rng.shuffle(conn_ids)
        num_dead = cfg.baseline_deadend_count
        num_deg = cfg.baseline_degraded_count
        for cid in conn_ids[:num_dead]:
            connectors[cid].hidden_state = HiddenState.DEADEND
        for cid in conn_ids[num_dead : num_dead + num_deg]:
            connectors[cid].hidden_state = HiddenState.DEGRADED

    return FailureSchedule(faults)


def export_events_jsonl(events: List[Any], file_path: str | Path) -> None:
    """Write events to JSONL file."""
    with open(file_path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(ev.to_json() + "\n")


def replay_events_jsonl(
    file_path: str | Path,
    acceleration: float = 1.0,
    callback: Optional[Callable[[Any], None]] = None,
) -> Iterator[Any]:
    """Replay events from a JSONL file, respecting event_ts deltas / acceleration."""
    last_event_ts: Optional[int] = None
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            event_ts = data["event_ts"]
            if last_event_ts is not None and acceleration > 0:
                delta_sec = (event_ts - last_event_ts) / 1000.0
                sleep_sec = delta_sec / acceleration
                if sleep_sec > 0.001:
                    time.sleep(min(sleep_sec, 0.5))  # cap single pause in dev
            last_event_ts = event_ts

            if callback:
                callback(data)
            yield data
