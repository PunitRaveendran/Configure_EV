"""Event schemas and topic constants for Charger Truth."""
from __future__ import annotations

import json
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field

# Topic constants
TOPIC_CHARGER_STATUS = "charger.status"
TOPIC_VEHICLE_SESSION = "vehicle.session"
TOPIC_VEHICLE_REQUEST = "vehicle.request"
TOPIC_CONNECTOR_BELIEF = "connector.belief"
TOPIC_CLUSTER_ALERT = "cluster.alert"
TOPIC_ROUTE_DECISION = "route.decision"
TOPIC_OPS_TICKET = "ops.ticket"

ALL_TOPICS = (
    TOPIC_CHARGER_STATUS,
    TOPIC_VEHICLE_SESSION,
    TOPIC_VEHICLE_REQUEST,
    TOPIC_CONNECTOR_BELIEF,
    TOPIC_CLUSTER_ALERT,
    TOPIC_ROUTE_DECISION,
    TOPIC_OPS_TICKET,
)


class SessionOutcome(str, Enum):
    """Vehicle-side session outcome."""
    STARTED = "STARTED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class ReportedStatus(str, Enum):
    """Heartbeat reported status from charger firmware."""
    AVAILABLE = "AVAILABLE"
    CHARGING = "CHARGING"
    FAULTED = "FAULTED"
    OFFLINE = "OFFLINE"


class GroupType(str, Enum):
    """Cluster alert aggregation group type."""
    SITE = "site"
    OPERATOR = "operator"
    FIRMWARE = "firmware"
    OPERATOR_X_FIRMWARE = "operator_x_firmware"


class TargetType(str, Enum):
    """Maintenance ticket target."""
    CONNECTOR = "connector"
    CLUSTER = "cluster"


class TicketStatus(str, Enum):
    """Maintenance ticket status."""
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class EventBase(BaseModel):
    """Base model for all Charger Truth streaming events."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_ts: int = Field(description="Event timestamp (UTC unix milliseconds)")

    @property
    def key(self) -> str:
        """Stable partition/grouping key for streaming."""
        raise NotImplementedError

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> Any:
        """Deserialize event from JSON string."""
        return cls.model_validate_json(json_str)


class ChargerStatusEvent(EventBase):
    """Charger status heartbeat event."""
    connector_id: str
    site_id: str
    reported_status: ReportedStatus
    error_code: Optional[str] = None
    meter_reading_kwh: Optional[float] = None

    @property
    def key(self) -> str:
        return self.connector_id


class VehicleSessionEvent(EventBase):
    """Vehicle-side charging attempt outcome event."""
    session_id: str
    connector_id: str
    vehicle_id: str
    outcome: SessionOutcome
    delivered_kw: Optional[float] = None
    rated_kw: Optional[float] = None
    time_to_current_sec: Optional[float] = None
    failure_reason: Optional[str] = None
    duration_sec: Optional[float] = None

    @property
    def key(self) -> str:
        return self.connector_id


class VehicleRequestEvent(EventBase):
    """Vehicle routing request event."""
    request_id: str
    vehicle_id: str
    current_lat: float
    current_lon: float
    current_soc: float
    battery_kwh: float
    target_soc: float = 0.80
    reserve_soc: float = 0.10
    max_charge_rate_kw: float = 150.0

    @property
    def key(self) -> str:
        return self.vehicle_id


class ConnectorBeliefEvent(EventBase):
    """Connector state belief posterior event."""
    connector_id: str
    p_healthy: float
    p_degraded: float
    p_deadend: float
    p_offline: float
    p_start: float
    uncertainty: float
    evidence_count: int = 0
    last_evidence_ts: Optional[int] = None

    @property
    def key(self) -> str:
        return self.connector_id


class ClusterAlertEvent(EventBase):
    """Space-time scan cluster alert event."""
    alert_id: str
    group_type: GroupType
    group_key: str
    window_min: int
    llr: float
    threshold: float
    observed_failures: int
    expected_failures: float
    member_connector_ids: List[str] = Field(default_factory=list)
    consecutive_count: int = 2

    @property
    def key(self) -> str:
        return self.group_key


class RouteCandidate(BaseModel):
    """Ranked connector candidate in routing decision."""
    model_config = ConfigDict(frozen=True)

    connector_id: str
    site_id: str
    expected_time_min: float
    p_start: float
    travel_time_min: float
    wait_time_min: float = 0.0
    charge_time_min: float = 0.0


class RouteDecisionEvent(EventBase):
    """Routing decision event."""
    request_id: str
    vehicle_id: str
    selected_connector_id: Optional[str] = None
    ranked_candidates: List[RouteCandidate] = Field(default_factory=list)
    reason: str

    @property
    def key(self) -> str:
        return self.vehicle_id


class OpsTicketEvent(EventBase):
    """Maintenance repair queue ticket."""
    ticket_id: str
    target_type: TargetType
    target_id: str
    site_id: Optional[str] = None
    priority: float
    demand_rate: float
    p_start: float
    heuristic_hint: Optional[str] = None
    cluster_alert_id: Optional[str] = None
    status: TicketStatus = TicketStatus.OPEN

    @property
    def key(self) -> str:
        return self.ticket_id
