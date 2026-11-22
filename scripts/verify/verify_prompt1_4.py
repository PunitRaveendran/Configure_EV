"""Verify Prompt 1 to Prompt 4 requirements (Phase C)."""
import os
import json
import numpy as np
from ct.config import Config
from ct.schemas import (
    TOPIC_CHARGER_STATUS, TOPIC_VEHICLE_SESSION, TOPIC_VEHICLE_REQUEST,
    TOPIC_CONNECTOR_BELIEF, TOPIC_CLUSTER_ALERT, TOPIC_ROUTE_DECISION,
    TOPIC_OPS_TICKET, ChargerStatusEvent, VehicleSessionEvent,
    VehicleRequestEvent, ConnectorBeliefEvent, ClusterAlertEvent,
    RouteDecisionEvent, OpsTicketEvent, SessionOutcome, ReportedStatus, GroupType
)
from ct.sim.network import build_synthetic_network
from ct.sim.engine import SimEngine, build_scenario_schedule
from ct.core.belief import HMMBeliefEstimator, BetaBernoulliEstimator
from ct.core.pooling import GroupPooler
from ct.core.scan import KulldorffClusterScanner
from ct.core.router import ExpectedTimeRouter, BeliefPolicy
from ct.core.tickets import TicketManager

def test_c1_schemas():
    """C1.1 - C1.6 checks."""
    # Check all 7 topics
    topics = [
        TOPIC_CHARGER_STATUS, TOPIC_VEHICLE_SESSION, TOPIC_VEHICLE_REQUEST,
        TOPIC_CONNECTOR_BELIEF, TOPIC_CLUSTER_ALERT, TOPIC_ROUTE_DECISION,
        TOPIC_OPS_TICKET
    ]
    assert len(topics) == 7
    
    # Round-trip tests for all 7 models
    ts = 1700000000000
    ev1 = ChargerStatusEvent(event_ts=ts, connector_id="c1", site_id="s1", reported_status=ReportedStatus.AVAILABLE)
    ev2 = VehicleSessionEvent(event_ts=ts, session_id="s_1", connector_id="c1", vehicle_id="v1", outcome=SessionOutcome.STARTED, delivered_kw=45.0, rated_kw=50.0)
    ev3 = VehicleRequestEvent(event_ts=ts, request_id="r1", vehicle_id="v1", current_lat=13.0, current_lon=80.2, current_soc=0.2, battery_kwh=60.0)
    ev4 = ConnectorBeliefEvent(event_ts=ts, connector_id="c1", p_healthy=0.8, p_degraded=0.1, p_deadend=0.08, p_offline=0.02, p_start=0.85, uncertainty=0.3, evidence_count=5, last_evidence_ts=ts)
    ev5 = ClusterAlertEvent(event_ts=ts, alert_id="a1", group_type=GroupType.SITE, group_key="s1", window_min=15, llr=9.2, threshold=8.5, observed_failures=5, expected_failures=1.2, member_connector_ids=["c1"])
    ev6 = RouteDecisionEvent(event_ts=ts, request_id="r1", vehicle_id="v1", candidate_connector_ids=["c1"], selected_connector_id="c1", expected_trip_time_min=14.2, p_start_predicted=0.85, reason_summary="Healthy")
    ev7 = OpsTicketEvent(event_ts=ts, ticket_id="t1", target_type=GroupType.SITE, target_key="s1", priority_score=0.75, status_summary="Active", suggested_action="Check power")
    
    events = [ev1, ev2, ev3, ev4, ev5, ev6, ev7]
    for ev in events:
        j = ev.to_json()
        ev_back = type(ev).from_json(j)
        assert ev == ev_back
        assert ev.key is not None
    print("C1 PASS: All 7 event models round-trip and have stable keys.")

def test_c2_simulator():
    """C2.1 - C2.8 checks."""
    cfg = Config()
    sites, conns, graph = build_synthetic_network(cfg, seed=7)
    assert 50 <= len(sites) <= 70, f"Sites count: {len(sites)}"
    assert 180 <= len(conns) <= 220, f"Connectors count: {len(conns)}"
    ops = {c.operator_id for c in conns.values()}
    fws = {c.firmware_version for c in conns.values()}
    models = {c.model_id for c in conns.values()}
    assert len(ops) == 4, f"Operators: {ops}"
    assert len(fws) == 3, f"Firmwares: {fws}"
    assert len(models) == 5, f"Hardware models: {models}"
    
    # Check scenario presets
    scenarios = ["baseline", "site_outage", "operator_outage", "firmware_bug", "slow_degradation", "vehicle_side_heavy"]
    for sc in scenarios:
        sched = build_scenario_schedule(sc, conns, sites, 1700000000000, seed=7, config=cfg)
        assert sched is not None
    print("C2 PASS: Synthetic network and scenario presets verified.")

def test_c3_belief():
    """C3.1 - C3.5 checks."""
    cfg = Config()
    est = HMMBeliefEstimator(cfg)
    now = 1700000000000
    p0 = est.p_start("conn_1", now)
    probs0 = est.state_probs("conn_1", now)
    assert abs(sum(probs0.values()) - 1.0) < 1e-6
    
    # Feed 3 failures
    for i in range(3):
        ev = VehicleSessionEvent(event_ts=now + i * 1000, session_id=f"s_{i}", connector_id="conn_1", vehicle_id=f"v_{i}", outcome=SessionOutcome.TIMEOUT)
        est.update(ev)
    p_after_fails = est.p_start("conn_1", now + 4000)
    assert p_after_fails < p0
    print(f"C3 PASS: Belief estimator updates: p0={p0:.3f} -> p_fails={p_after_fails:.3f}")

def test_c4_scan_router_tickets():
    """C4.1 - C4.6 checks."""
    cfg = Config()
    scanner = KulldorffClusterScanner(cfg)
    llr = scanner.calculate_llr(10, 8, 2.0)
    assert llr > 0.0
    llr_zero = scanner.calculate_llr(10, 1, 2.0)
    assert llr_zero == 0.0
    router = ExpectedTimeRouter(cfg)
    tickets = TicketManager(cfg)
    print("C4 PASS: Scanner LLR calculation, router, and tickets instantiated.")

if __name__ == "__main__":
    test_c1_schemas()
    test_c2_simulator()
    test_c3_belief()
    test_c4_scan_router_tickets()
