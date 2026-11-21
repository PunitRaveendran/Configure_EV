"""Tests for Charger Truth simulation engine (Prompt 2).

Verifies:
- Determinism: same seed gives identical logs.
- Common random numbers: keyed RNG produces identical attempt outcomes across different policies.
- Correlated faults: site outage, operator outage, firmware bug activate at scheduled time.
- Security / Isolation: policies cannot inspect hidden state via the observable view.
"""
import pytest
from ct.config import Config
from ct.schemas import ReportedStatus, SessionOutcome, VehicleRequestEvent
from ct.sim.engine import (
    ObservableSimulationView,
    Policy,
    SimEngine,
    build_scenario_schedule,
    make_attempt_rng,
)
from ct.sim.failures import FailureSchedule, FirmwareBug, HiddenState, OperatorOutage, SiteOutage
from ct.sim.network import build_synthetic_network


class DummyFirstAvailablePolicy(Policy):
    """Picks the first available connector in the list."""
    def choose(self, request: VehicleRequestEvent, view: ObservableSimulationView) -> list[str]:
        candidates = []
        for c_id, meta in view.connectors.items():
            st = view.get_latest_status(c_id)
            if st and st.reported_status == ReportedStatus.AVAILABLE:
                candidates.append(c_id)
        return candidates


class DummyReversedPolicy(Policy):
    """Picks available connectors in reverse order."""
    def choose(self, request: VehicleRequestEvent, view: ObservableSimulationView) -> list[str]:
        candidates = []
        for c_id, meta in sorted(view.connectors.items(), reverse=True):
            st = view.get_latest_status(c_id)
            if st and st.reported_status == ReportedStatus.AVAILABLE:
                candidates.append(c_id)
        return candidates


def test_simulation_determinism():
    """Verify same seed produces byte-for-byte identical event streams."""
    cfg = Config()
    policy = DummyFirstAvailablePolicy()

    engine1 = SimEngine(cfg, seed=123, duration_sec=1800)
    events1 = engine1.run(policy)

    engine2 = SimEngine(cfg, seed=123, duration_sec=1800)
    events2 = engine2.run(policy)

    assert len(events1) == len(events2)
    for ev1, ev2 in zip(events1, events2):
        assert ev1.to_json() == ev2.to_json()


def test_common_random_numbers_across_policies():
    """Verify common random numbers: RNG is uniquely keyed by (seed, vehicle_id, attempt_no)."""
    seed = 42
    veh_id = "veh_42_00001"
    attempt_no = 1

    rng1 = make_attempt_rng(seed, veh_id, attempt_no)
    rng2 = make_attempt_rng(seed, veh_id, attempt_no)

    val1 = rng1.uniform(0.0, 1.0)
    val2 = rng2.uniform(0.0, 1.0)
    assert val1 == val2

    # Different attempt number must yield different sample
    rng3 = make_attempt_rng(seed, veh_id, attempt_no + 1)
    val3 = rng3.uniform(0.0, 1.0)
    assert val1 != val3


def test_correlated_fault_site_outage():
    """Verify site outage activates at scheduled time and affects site's connectors."""
    cfg = Config()
    sites, connectors, _ = build_synthetic_network(cfg, seed=7)
    site_id = sorted(sites.keys())[0]
    site_conn_ids = sites[site_id].connector_ids

    start_ts = 1700000000000
    fault_duration_sec = 1800
    fault = SiteOutage(
        start_ts=start_ts + 10000,
        duration_sec=fault_duration_sec,
        name="test_site_outage",
        site_id=site_id,
    )
    schedule = FailureSchedule([fault])

    test_conn = connectors[site_conn_ids[0]]

    # Before fault: healthy
    assert schedule.get_effective_state(test_conn, start_ts) == HiddenState.HEALTHY
    # During fault: OFFLINE
    assert schedule.get_effective_state(test_conn, start_ts + 20000) == HiddenState.OFFLINE
    # After fault: restored
    assert schedule.get_effective_state(test_conn, start_ts + 2000000) == HiddenState.HEALTHY


def test_correlated_fault_operator_outage():
    """Verify operator outage hits ~30% of operator connectors at the right time."""
    cfg = Config()
    sites, connectors, _ = build_synthetic_network(cfg, seed=7)
    start_ts = 1700000000000

    schedule = build_scenario_schedule("operator_outage", connectors, sites, start_ts, seed=7)
    op_fault = schedule.faults[0]
    assert isinstance(op_fault, OperatorOutage)
    assert len(op_fault.affected_connector_ids) > 0

    affected_conn_id = next(iter(op_fault.affected_connector_ids))
    affected_conn = connectors[affected_conn_id]

    # Before outage: HEALTHY
    assert schedule.get_effective_state(affected_conn, start_ts) == HiddenState.HEALTHY
    # During outage: DEADEND
    mid_ts = op_fault.start_ts + 1000
    assert schedule.get_effective_state(affected_conn, mid_ts) == HiddenState.DEADEND
    # After outage: restored
    assert schedule.get_effective_state(affected_conn, op_fault.end_ts + 1000) == HiddenState.HEALTHY


def test_correlated_fault_firmware_bug():
    """Verify firmware bug affects all connectors with target firmware at scheduled time."""
    cfg = Config()
    sites, connectors, _ = build_synthetic_network(cfg, seed=7)
    start_ts = 1700000000000

    schedule = build_scenario_schedule("firmware_bug", connectors, sites, start_ts, seed=7)
    fw_fault = schedule.faults[0]
    assert isinstance(fw_fault, FirmwareBug)
    target_fw = fw_fault.firmware_version

    fw_conns = [c for c in connectors.values() if c.firmware_version == target_fw]
    other_conns = [c for c in connectors.values() if c.firmware_version != target_fw]

    assert len(fw_conns) > 0
    mid_ts = fw_fault.start_ts + 1000

    for c in fw_conns:
        assert schedule.get_effective_state(c, mid_ts) == HiddenState.DEADEND

    for c in other_conns:
        assert schedule.get_effective_state(c, mid_ts) == HiddenState.HEALTHY


def test_policies_cannot_read_hidden_state():
    """Verify ObservableSimulationView does not leak hidden_state or fault schedule."""
    cfg = Config()
    engine = SimEngine(cfg, seed=7, duration_sec=600)
    view = engine.view

    for c_id, meta in view.connectors.items():
        assert not hasattr(meta, "hidden_state")
        assert not hasattr(meta, "is_occupied")
        assert not hasattr(meta, "degradation_factor")

    assert not hasattr(view, "schedule")
    assert not hasattr(view, "connectors_sim")
