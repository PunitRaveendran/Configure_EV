"""Unit tests for Cluster Scanner, Router, and Repair Tickets (Prompt 4)."""
import pytest
import numpy as np

from ct.config import Config
from ct.core.belief import HMMBeliefEstimator
from ct.core.router import ExpectedTimeRouter
from ct.core.scan import KulldorffClusterScanner
from ct.core.tickets import TicketManager
from ct.schemas import (
    ClusterAlertEvent,
    GroupType,
    SessionOutcome,
    TargetType,
    VehicleRequestEvent,
    VehicleSessionEvent,
)
from ct.sim.engine import ObservableSimulationView
from ct.sim.network import build_synthetic_network


class DummyConnectorMeta:
    def __init__(self, c_id, site_id, op_id, fw, rated_kw=150.0, lat=13.0, lon=80.2):
        self.connector_id = c_id
        self.site_id = site_id
        self.operator_id = op_id
        self.firmware_version = fw
        self.rated_kw = rated_kw
        self.site_lat = lat
        self.site_lon = lon


def test_cluster_scanner_detects_injected_faults():
    """Verify site outage, operator outage, and firmware bug are each detected by scan."""
    cfg = Config()
    meta_dict = {
        f"conn_{i:02d}": DummyConnectorMeta(
            f"conn_{i:02d}",
            site_id="site_outage_01" if i < 4 else f"site_{i//2:02d}",
            op_id="OP_OUTAGE" if 4 <= i < 10 else "OP_NORMAL",
            fw="FW_BUGGY" if 10 <= i < 16 else "FW_STABLE",
        )
        for i in range(20)
    }

    scanner = KulldorffClusterScanner(cfg, connectors_meta=meta_dict, threshold_override=5.0)
    now = 1700000000000

    # 1. Inject bursts of failures for site_outage_01
    for i in range(4):
        for rep in range(2):
            ev = VehicleSessionEvent(
                event_ts=now + rep * 1000,
                session_id=f"sess_site_{i}_{rep}",
                connector_id=f"conn_{i:02d}",
                vehicle_id=f"veh_s_{i}_{rep}",
                outcome=SessionOutcome.TIMEOUT,
            )
            scanner.record_session(ev)

    # Evaluate 2 consecutive steps for persistence
    scanner.evaluate(now + 2000)
    site_alerts = scanner.evaluate(now + 62000)
    site_keys = [a.group_key for a in site_alerts if a.group_type == GroupType.SITE]
    assert "site_outage_01" in site_keys, f"Site outage not detected: {site_alerts}"

    # 2. Inject bursts of failures for OP_OUTAGE
    for i in range(4, 10):
        for rep in range(2):
            ev = VehicleSessionEvent(
                event_ts=now + 70000 + rep * 1000,
                session_id=f"sess_op_{i}_{rep}",
                connector_id=f"conn_{i:02d}",
                vehicle_id=f"veh_op_{i}_{rep}",
                outcome=SessionOutcome.TIMEOUT,
            )
            scanner.record_session(ev)

    scanner.evaluate(now + 75000)
    op_alerts = scanner.evaluate(now + 135000)
    op_keys = [a.group_key for a in op_alerts if a.group_type == GroupType.OPERATOR]
    assert "OP_OUTAGE" in op_keys, f"Operator outage not detected: {op_alerts}"

    # 3. Inject bursts of failures for FW_BUGGY
    for i in range(10, 16):
        for rep in range(2):
            ev = VehicleSessionEvent(
                event_ts=now + 140000 + rep * 1000,
                session_id=f"sess_fw_{i}_{rep}",
                connector_id=f"conn_{i:02d}",
                vehicle_id=f"veh_fw_{i}_{rep}",
                outcome=SessionOutcome.TIMEOUT,
            )
            scanner.record_session(ev)

    scanner.evaluate(now + 145000)
    fw_alerts = scanner.evaluate(now + 205000)
    fw_keys = [a.group_key for a in fw_alerts if a.group_type == GroupType.FIRMWARE]
    assert "FW_BUGGY" in fw_keys, f"Firmware bug not detected: {fw_alerts}"


def test_nested_alert_suppression():
    """Verify child site alert is suppressed when parent operator alert is active."""
    cfg = Config()
    # Sites site_A and site_B belong to operator OP_PARENT
    meta_dict = {
        "conn_A1": DummyConnectorMeta("conn_A1", "site_A", "OP_PARENT", "FW_1"),
        "conn_A2": DummyConnectorMeta("conn_A2", "site_A", "OP_PARENT", "FW_1"),
        "conn_B1": DummyConnectorMeta("conn_B1", "site_B", "OP_PARENT", "FW_1"),
        "conn_B2": DummyConnectorMeta("conn_B2", "site_B", "OP_PARENT", "FW_1"),
    }
    scanner = KulldorffClusterScanner(cfg, connectors_meta=meta_dict, threshold_override=3.0)
    now = 1700000000000

    # Inject failures across both sites of OP_PARENT
    for c_id in ["conn_A1", "conn_A2", "conn_B1", "conn_B2"]:
        for rep in range(3):
            ev = VehicleSessionEvent(
                event_ts=now + rep * 1000,
                session_id=f"s_{c_id}_{rep}",
                connector_id=c_id,
                vehicle_id=f"v_{c_id}_{rep}",
                outcome=SessionOutcome.TIMEOUT,
            )
            scanner.record_session(ev)

    scanner.evaluate(now + 5000)
    alerts = scanner.evaluate(now + 65000)

    alert_types = [a.group_type for a in alerts]
    assert GroupType.OPERATOR in alert_types
    # Child site alerts should be suppressed!
    assert GroupType.SITE not in alert_types, f"Child site alert should be suppressed: {alerts}"


def test_false_alarm_rate_under_null_within_budget():
    """Verify that on null simulation without correlated faults, false alarm count is <= budget."""
    cfg = Config()
    rng = np.random.RandomState(42)
    meta_dict = {
        f"conn_{i:02d}": DummyConnectorMeta(
            f"conn_{i:02d}",
            site_id=f"site_{i//4:02d}",
            op_id=f"OP_{i//8}",
            fw=f"FW_{i%2}",
        )
        for i in range(16)
    }

    scanner = KulldorffClusterScanner(cfg, connectors_meta=meta_dict, threshold_override=8.5)
    now = 1700000000000
    alert_count = 0

    # Simulate 50 evaluations under null (independent random baseline failures at rate 0.20)
    for step in range(50):
        t = now + step * 60000
        # Normal Poisson sessions
        for i in range(16):
            if rng.uniform(0.0, 1.0) < 0.3:
                is_fail = rng.uniform(0.0, 1.0) < 0.20  # baseline failure
                ev = VehicleSessionEvent(
                    event_ts=t,
                    session_id=f"null_{step}_{i}",
                    connector_id=f"conn_{i:02d}",
                    vehicle_id=f"v_null_{step}_{i}",
                    outcome=SessionOutcome.TIMEOUT if is_fail else SessionOutcome.STARTED,
                )
                scanner.record_session(ev)

        alerts = scanner.evaluate(t)
        alert_count += len(alerts)

    # Under calibrated threshold 8.50 and persistence = 2, false alarms on 50 steps should be 0
    assert alert_count <= cfg.false_alarm_budget_per_week, f"False alarm count too high: {alert_count}"


def test_router_prefers_farther_healthy_over_near_failing():
    """Verify router chooses farther healthy connector (high p) over nearer failing connector (low p)."""
    cfg = Config()
    sites, connectors, graph = build_synthetic_network(cfg, seed=1)

    # Select two candidate connectors
    c_ids = list(connectors.keys())
    near_cid = c_ids[0]
    far_cid = c_ids[1]

    near_site = sites[connectors[near_cid].site_id]
    far_site = sites[connectors[far_cid].site_id]

    # Vehicle located very close to near_site, further from far_site
    req = VehicleRequestEvent(
        event_ts=1700000000000,
        request_id="req_test_01",
        vehicle_id="veh_test_01",
        current_lat=near_site.lat + 0.005,  # ~0.5 km away
        current_lon=near_site.lon + 0.005,
        current_soc=0.25,
        battery_kwh=60.0,
        target_soc=0.80,
        reserve_soc=0.10,
        max_charge_rate_kw=150.0,
    )

    estimator = HMMBeliefEstimator(cfg)

    # Drive near connector belief way down (p ~ 0.15) with 4 consecutive failures
    for i in range(4):
        estimator.update(
            VehicleSessionEvent(
                event_ts=req.event_ts + i * 1000,
                session_id=f"sf_{i}",
                connector_id=near_cid,
                vehicle_id=f"vf_{i}",
                outcome=SessionOutcome.TIMEOUT,
            )
        )

    # Confirm near connector has low p
    assert estimator.p_start(near_cid, req.event_ts) < 0.30

    # Confirm far connector has high healthy belief (p ~ 0.90+)
    assert estimator.p_start(far_cid, req.event_ts) > 0.80

    connectors_meta = {
        near_cid: DummyConnectorMeta(near_cid, near_site.site_id, "OP_1", "FW_1", lat=near_site.lat, lon=near_site.lon),
        far_cid: DummyConnectorMeta(far_cid, far_site.site_id, "OP_1", "FW_1", lat=far_site.lat, lon=far_site.lon),
    }

    view = ObservableSimulationView(connectors_meta, sites, graph)
    router = ExpectedTimeRouter(cfg, belief_estimator=estimator)

    ranked_ids, decision = router.plan_route(req, view)
    assert len(ranked_ids) >= 2
    # Router must pick the farther healthy connector first!
    assert ranked_ids[0] == far_cid, f"Router should prefer farther healthy connector over near failing, got: {ranked_ids[0]}"


def test_ticket_priority_changes_with_demand():
    """Verify repair ticket priority = (1 - p) * demand ranks high-demand sites first."""
    cfg = Config()
    mgr = TicketManager(cfg)
    now = 1700000000000

    # Low demand site: demand = 1.0, p_start = 0.10 -> priority = 0.90 * 1.0 = 0.90
    tkt_low = mgr.create_connector_ticket(
        connector_id="conn_low_demand",
        site_id="site_low",
        p_start=0.10,
        local_demand_rate=1.0,
        event_ts=now,
    )

    # High demand site: demand = 10.0, p_start = 0.35 -> priority = 0.65 * 10.0 = 6.50
    tkt_high = mgr.create_connector_ticket(
        connector_id="conn_high_demand",
        site_id="site_high",
        p_start=0.35,
        local_demand_rate=10.0,
        event_ts=now,
    )

    queue = mgr.get_ranked_repair_queue()
    assert len(queue) == 2
    # Even though conn_low_demand has a lower p_start (0.10 vs 0.35),
    # conn_high_demand has much higher demand, so it must be ranked first!
    assert queue[0].ticket_id == tkt_high.ticket_id
    assert queue[1].ticket_id == tkt_low.ticket_id
    assert queue[0].priority > queue[1].priority
