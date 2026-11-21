"""Tests for event schemas and topic constants."""
import pytest
from ct.schemas import (
    ALL_TOPICS,
    TOPIC_CHARGER_STATUS,
    TOPIC_VEHICLE_SESSION,
    TOPIC_VEHICLE_REQUEST,
    TOPIC_CONNECTOR_BELIEF,
    TOPIC_CLUSTER_ALERT,
    TOPIC_ROUTE_DECISION,
    TOPIC_OPS_TICKET,
    ChargerStatusEvent,
    VehicleSessionEvent,
    VehicleRequestEvent,
    ConnectorBeliefEvent,
    ClusterAlertEvent,
    RouteDecisionEvent,
    RouteCandidate,
    OpsTicketEvent,
    SessionOutcome,
    ReportedStatus,
    GroupType,
    TargetType,
    TicketStatus,
)


def test_topic_constants():
    assert TOPIC_CHARGER_STATUS == "charger.status"
    assert TOPIC_VEHICLE_SESSION == "vehicle.session"
    assert TOPIC_VEHICLE_REQUEST == "vehicle.request"
    assert TOPIC_CONNECTOR_BELIEF == "connector.belief"
    assert TOPIC_CLUSTER_ALERT == "cluster.alert"
    assert TOPIC_ROUTE_DECISION == "route.decision"
    assert TOPIC_OPS_TICKET == "ops.ticket"
    assert len(ALL_TOPICS) == 7


def test_charger_status_event_roundtrip():
    event = ChargerStatusEvent(
        event_ts=1700000000000,
        connector_id="conn-101",
        site_id="site-12",
        reported_status=ReportedStatus.AVAILABLE,
        error_code=None,
        meter_reading_kwh=145.2,
    )
    assert event.key == "conn-101"
    json_str = event.to_json()
    recovered = ChargerStatusEvent.from_json(json_str)
    assert recovered == event
    assert recovered.reported_status == ReportedStatus.AVAILABLE


def test_vehicle_session_event_roundtrip():
    event = VehicleSessionEvent(
        event_ts=1700000001000,
        session_id="sess-001",
        connector_id="conn-101",
        vehicle_id="veh-42",
        outcome=SessionOutcome.STARTED,
        delivered_kw=48.5,
        rated_kw=50.0,
        time_to_current_sec=4.2,
        failure_reason=None,
        duration_sec=1200.0,
    )
    assert event.key == "conn-101"
    json_str = event.to_json()
    recovered = VehicleSessionEvent.from_json(json_str)
    assert recovered == event
    assert recovered.outcome == SessionOutcome.STARTED
    assert recovered.delivered_kw == 48.5
    assert recovered.rated_kw == 50.0


def test_vehicle_session_event_failed():
    event = VehicleSessionEvent(
        event_ts=1700000002000,
        session_id="sess-002",
        connector_id="conn-102",
        vehicle_id="veh-43",
        outcome=SessionOutcome.TIMEOUT,
        delivered_kw=0.0,
        rated_kw=50.0,
        time_to_current_sec=120.0,
        failure_reason="handshake_timeout",
    )
    assert event.key == "conn-102"
    json_str = event.to_json()
    recovered = VehicleSessionEvent.from_json(json_str)
    assert recovered.outcome == SessionOutcome.TIMEOUT


def test_vehicle_request_event_roundtrip():
    event = VehicleRequestEvent(
        event_ts=1700000003000,
        request_id="req-999",
        vehicle_id="veh-42",
        current_lat=13.04,
        current_lon=80.25,
        current_soc=0.18,
        battery_kwh=60.0,
        target_soc=0.80,
        reserve_soc=0.10,
        max_charge_rate_kw=100.0,
    )
    assert event.key == "veh-42"
    json_str = event.to_json()
    recovered = VehicleRequestEvent.from_json(json_str)
    assert recovered == event


def test_connector_belief_event_roundtrip():
    event = ConnectorBeliefEvent(
        event_ts=1700000004000,
        connector_id="conn-101",
        p_healthy=0.85,
        p_degraded=0.10,
        p_deadend=0.04,
        p_offline=0.01,
        p_start=0.91,
        uncertainty=0.45,
        evidence_count=12,
        last_evidence_ts=1700000003500,
    )
    assert event.key == "conn-101"
    json_str = event.to_json()
    recovered = ConnectorBeliefEvent.from_json(json_str)
    assert recovered == event


def test_cluster_alert_event_roundtrip():
    event = ClusterAlertEvent(
        event_ts=1700000005000,
        alert_id="alt-01",
        group_type=GroupType.OPERATOR,
        group_key="op_chargepoint",
        window_min=30,
        llr=14.8,
        threshold=9.2,
        observed_failures=8,
        expected_failures=1.5,
        member_connector_ids=["conn-101", "conn-102", "conn-103"],
        consecutive_count=2,
    )
    assert event.key == "op_chargepoint"
    json_str = event.to_json()
    recovered = ClusterAlertEvent.from_json(json_str)
    assert recovered == event


def test_route_decision_event_roundtrip():
    candidate = RouteCandidate(
        connector_id="conn-101",
        site_id="site-1",
        expected_time_min=24.5,
        p_start=0.95,
        travel_time_min=10.0,
        wait_time_min=0.0,
        charge_time_min=14.5,
    )
    event = RouteDecisionEvent(
        event_ts=1700000006000,
        request_id="req-999",
        vehicle_id="veh-42",
        selected_connector_id="conn-101",
        ranked_candidates=[candidate],
        reason="p=0.95, minimal total expected time 24.5 min",
    )
    assert event.key == "veh-42"
    json_str = event.to_json()
    recovered = RouteDecisionEvent.from_json(json_str)
    assert recovered == event
    assert len(recovered.ranked_candidates) == 1
    assert recovered.ranked_candidates[0].connector_id == "conn-101"


def test_ops_ticket_event_roundtrip():
    event = OpsTicketEvent(
        event_ts=1700000007000,
        ticket_id="tkt-77",
        target_type=TargetType.CONNECTOR,
        target_id="conn-102",
        site_id="site-1",
        priority=3.85,
        demand_rate=5.5,
        p_start=0.30,
        heuristic_hint="Dead-end behavior: reports Available but consecutive session timeouts",
        cluster_alert_id=None,
        status=TicketStatus.OPEN,
    )
    assert event.key == "tkt-77"
    json_str = event.to_json()
    recovered = OpsTicketEvent.from_json(json_str)
    assert recovered == event
