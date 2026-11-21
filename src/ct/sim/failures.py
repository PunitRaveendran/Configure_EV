"""Failure dynamics and status misreporting model for Charger Truth simulator.

All data is strictly SIMULATED.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set
import numpy as np

from ct.config import Config
from ct.schemas import ReportedStatus
from ct.sim.network import ConnectorSim, HiddenState


@dataclass
class FaultEvent:
    """Base class for scheduled fault injection."""
    start_ts: int
    duration_sec: int
    name: str

    @property
    def end_ts(self) -> int:
        return self.start_ts + (self.duration_sec * 1000)

    def is_active(self, current_ts: int) -> bool:
        return self.start_ts <= current_ts < self.end_ts


@dataclass
class SiteOutage(FaultEvent):
    """Correlated site power or network outage hitting all connectors at a site."""
    site_id: str = ""


@dataclass
class OperatorOutage(FaultEvent):
    """Correlated operator cloud/backend outage hitting ~30% of their connectors."""
    operator_id: str = ""
    affected_fraction: float = 0.30
    affected_connector_ids: Set[str] = None  # populated at creation

    def __post_init__(self):
        if self.affected_connector_ids is None:
            self.affected_connector_ids = set()


@dataclass
class FirmwareBug(FaultEvent):
    """Firmware logic bug affecting all connectors running a specific firmware version."""
    firmware_version: str = ""


class FailureSchedule:
    """Manages scheduled fault injections and computes effective connector states."""
    def __init__(self, faults: Optional[List[FaultEvent]] = None):
        self.faults: List[FaultEvent] = faults or []

    def get_effective_state(
        self,
        connector: ConnectorSim,
        current_ts: int,
    ) -> HiddenState:
        """Evaluate connector's current hidden state under active fault injections."""
        # Check active firmware bug
        for fault in self.faults:
            if isinstance(fault, FirmwareBug) and fault.is_active(current_ts):
                if connector.firmware_version == fault.firmware_version:
                    return HiddenState.DEADEND

        # Check active site outage
        for fault in self.faults:
            if isinstance(fault, SiteOutage) and fault.is_active(current_ts):
                if connector.site_id == fault.site_id:
                    return HiddenState.OFFLINE

        # Check active operator outage
        for fault in self.faults:
            if isinstance(fault, OperatorOutage) and fault.is_active(current_ts):
                if connector.connector_id in fault.affected_connector_ids:
                    return HiddenState.DEADEND

        # Default to connector's baseline intrinsic state
        return connector.hidden_state


class StatusHeartbeatGenerator:
    """Simulates periodic charger heartbeat status telemetry with realistic misreporting.
    
    A Dead-end connector falsely reports 'AVAILABLE' ~90% of the time,
    deceiving simple status-based routing.
    """
    def __init__(self, config: Config):
        self.config = config

    def sample_reported_status(
        self,
        state: HiddenState,
        is_occupied: bool,
        rng: np.random.RandomState,
    ) -> ReportedStatus:
        """Sample reported status based on true hidden state."""
        roll = rng.uniform(0.0, 1.0)

        if is_occupied:
            # If occupied, typically reports CHARGING unless offline/faulted
            if state == HiddenState.OFFLINE:
                return ReportedStatus.OFFLINE if roll < 0.85 else ReportedStatus.CHARGING
            return ReportedStatus.CHARGING

        if state == HiddenState.HEALTHY:
            if roll < self.config.p_avail_healthy:
                return ReportedStatus.AVAILABLE
            elif roll < 0.98:
                return ReportedStatus.CHARGING
            else:
                return ReportedStatus.FAULTED

        elif state == HiddenState.DEGRADED:
            # Degraded connectors still report AVAILABLE normally
            if roll < self.config.p_avail_degraded:
                return ReportedStatus.AVAILABLE
            else:
                return ReportedStatus.FAULTED

        elif state == HiddenState.DEADEND:
            # Dead-end chargers deceive: report AVAILABLE ~90% of the time!
            if roll < self.config.p_avail_deadend:
                return ReportedStatus.AVAILABLE
            elif roll < 0.95:
                return ReportedStatus.FAULTED
            else:
                return ReportedStatus.OFFLINE

        elif state == HiddenState.OFFLINE:
            # Offline chargers mostly report OFFLINE or FAULTED, rarely AVAILABLE
            if roll < self.config.p_avail_offline:
                return ReportedStatus.AVAILABLE
            elif roll < 0.60:
                return ReportedStatus.OFFLINE
            else:
                return ReportedStatus.FAULTED

        return ReportedStatus.AVAILABLE
