"""Unit tests for Evaluation Harness and Baselines (Prompt 5)."""
import pytest
from ct.baselines.failcount import FailCountPolicy
from ct.baselines.reported import ReportedStatusPolicy
from ct.baselines.usagegap import UsageGapPolicy
from ct.config import Config
from ct.core.router import BeliefPolicy
from ct.eval.harness import EvaluationHarness
from ct.schemas import ReportedStatus, SessionOutcome, VehicleRequestEvent, VehicleSessionEvent
from ct.sim.engine import SimEngine, build_scenario_schedule


def test_arms_receive_identical_request_streams():
    """Verify that different arms face byte-for-byte identical vehicle request streams."""
    cfg = Config()
    seed = 42

    engine_A = SimEngine(cfg, seed=seed, duration_sec=1800)
    engine_D = SimEngine(cfg, seed=seed, duration_sec=1800)

    policy_A = ReportedStatusPolicy()
    policy_D = BeliefPolicy(cfg)

    events_A = engine_A.run(policy_A)
    events_D = engine_D.run(policy_D)

    requests_A = [e for e in events_A if isinstance(e, VehicleRequestEvent)]
    requests_D = [e for e in events_D if isinstance(e, VehicleRequestEvent)]

    assert len(requests_A) == len(requests_D)
    for r_a, r_d in zip(requests_A, requests_D):
        assert r_a.request_id == r_d.request_id
        assert r_a.vehicle_id == r_d.vehicle_id
        assert r_a.event_ts == r_d.event_ts
        assert r_a.current_lat == r_d.current_lat
        assert r_a.current_lon == r_d.current_lon


def test_harness_determinism_for_fixed_seed():
    """Verify EvaluationHarness is deterministic for a fixed seed."""
    harness = EvaluationHarness()
    res1 = harness.run_arm("A_reported", "baseline", seed=7, duration_sec=1200)
    res2 = harness.run_arm("A_reported", "baseline", seed=7, duration_sec=1200)

    assert res1["wasted_trip_rate"] == res2["wasted_trip_rate"]
    assert res1["wasted_minutes"] == res2["wasted_minutes"]
    assert res1["total_sessions"] == res2["total_sessions"]


def test_failcount_threshold_monotonicity():
    """Verify increasing failure count threshold k monotonically reduces or maintains flag rate."""
    cfg = Config()
    # Higher k means harder to flag
    policy_k1 = FailCountPolicy(k_consecutive=1)
    policy_k3 = FailCountPolicy(k_consecutive=3)

    now = 1700000000000
    # Feed 2 failures
    for rep in range(2):
        ev = VehicleSessionEvent(
            event_ts=now + rep * 1000,
            session_id=f"sf_{rep}",
            connector_id="conn_mono_01",
            vehicle_id=f"vf_{rep}",
            outcome=SessionOutcome.TIMEOUT,
        )
        policy_k1.record_session(ev)
        policy_k3.record_session(ev)

    # k=1 flags after 1 failure -> flagged!
    assert policy_k1.is_flagged("conn_mono_01", now + 5000) is True
    # k=3 needs 3 failures -> NOT flagged!
    assert policy_k3.is_flagged("conn_mono_01", now + 5000) is False


def test_detection_latency_and_precision_recall():
    """Verify failure detection latency and precision/recall metrics."""
    from ct.eval.metrics import compute_detection_latency, compute_cluster_alert_precision_recall
    from ct.sim.failures import SiteOutage
    from ct.schemas import ClusterAlertEvent, GroupType

    fault = SiteOutage(start_ts=100000, duration_sec=300, name="site_down", site_id="site_alpha")
    faults = [fault]

    # Flagged 60 seconds after fault starts
    flag_times = {"site_alpha": 160000}
    lat = compute_detection_latency(faults, flag_times, horizon_sec=600.0)
    assert lat == 1.0  # 60s = 1.0 min

    # Alert matching
    alert = ClusterAlertEvent(
        event_ts=160000,
        alert_id="alt_01",
        group_type=GroupType.SITE,
        group_key="site_alpha",
        window_min=15,
        llr=12.5,
        threshold=8.5,
        observed_failures=5,
        expected_failures=1.2,
        member_connector_ids=["conn_1", "conn_2"],
    )
    prec, rec = compute_cluster_alert_precision_recall(faults, [alert])
    assert prec == 1.0
    assert rec == 1.0


def test_matched_sweep_and_ablations_run():
    """Smoke test for matched false alarm sweep and ablations on short duration."""
    harness = EvaluationHarness()
    # Fast test on seed 0
    sweep = harness.sweep_matched_false_alarm(seeds=(0,), scenario="baseline")
    assert len(sweep) == 15
    for entry in sweep:
        assert "false_flag_rate" in entry
        assert "detection_latency_min" in entry
        assert "wasted_trip_rate" in entry

    abl = harness.run_ablations(seeds=(0,), scenario="baseline")
    assert "ablations" in abl
    assert "traffic_split" in abl
    assert len(abl["ablations"]) == 10

