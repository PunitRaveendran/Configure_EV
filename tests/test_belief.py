"""Unit tests for Belief Estimator, Group Pooling, and Probing (Prompt 3)."""
import pytest
from ct.config import Config
from ct.core.belief import BetaBernoulliEstimator, HMMBeliefEstimator
from ct.core.pooling import GroupPooler
from ct.schemas import (
    ChargerStatusEvent,
    ReportedStatus,
    SessionOutcome,
    VehicleRequestEvent,
    VehicleSessionEvent,
)


def test_state_probabilities_sum_to_one():
    """Verify state probabilities always sum to 1.0 under updates and decay."""
    cfg = Config()
    estimator = HMMBeliefEstimator(cfg)
    conn_id = "conn_0001"
    now = 1700000000000

    # Initial state
    probs = estimator.state_probs(conn_id, now)
    assert pytest.approx(sum(probs.values()), abs=1e-5) == 1.0

    # After a successful session
    ev1 = VehicleSessionEvent(
        event_ts=now + 1000,
        session_id="s1",
        connector_id=conn_id,
        vehicle_id="v1",
        outcome=SessionOutcome.STARTED,
        delivered_kw=50.0,
        rated_kw=50.0,
    )
    estimator.update(ev1)
    probs1 = estimator.state_probs(conn_id, now + 1000)
    assert pytest.approx(sum(probs1.values()), abs=1e-5) == 1.0

    # After decay (2 hours later)
    probs_decay = estimator.state_probs(conn_id, now + 7200 * 1000)
    assert pytest.approx(sum(probs_decay.values()), abs=1e-5) == 1.0


def test_p_start_falls_after_failures_and_recovers_after_successes():
    """Verify p_start drops after consecutive failures and rebounds upon success."""
    cfg = Config()
    estimator = HMMBeliefEstimator(cfg)
    conn_id = "conn_0002"
    now = 1700000000000

    initial_p = estimator.p_start(conn_id, now)
    assert initial_p > 0.70

    # Inject 3 consecutive timeouts (dead-end signal)
    for i in range(3):
        t = now + (i + 1) * 60000
        ev = VehicleSessionEvent(
            event_ts=t,
            session_id=f"s_fail_{i}",
            connector_id=conn_id,
            vehicle_id=f"v_{i}",
            outcome=SessionOutcome.TIMEOUT,
        )
        estimator.update(ev)

    after_fail_p = estimator.p_start(conn_id, now + 200000)
    assert after_fail_p < 0.35, f"p_start should fall sharply, got {after_fail_p}"

    # Inject 3 consecutive successes
    for i in range(3):
        t = now + 300000 + (i + 1) * 60000
        ev = VehicleSessionEvent(
            event_ts=t,
            session_id=f"s_succ_{i}",
            connector_id=conn_id,
            vehicle_id=f"v_succ_{i}",
            outcome=SessionOutcome.STARTED,
            delivered_kw=50.0,
            rated_kw=50.0,
        )
        estimator.update(ev)

    recovered_p = estimator.p_start(conn_id, now + 600000)
    assert recovered_p > after_fail_p
    assert recovered_p > 0.65


def test_one_failure_alone_does_not_mark_deadend():
    """Verify that a single failure (which could be vehicle-side) does not condemn a healthy charger."""
    cfg = Config()
    estimator = HMMBeliefEstimator(cfg)
    conn_id = "conn_0003"
    now = 1700000000000

    # Single failure
    ev = VehicleSessionEvent(
        event_ts=now,
        session_id="s_err",
        connector_id=conn_id,
        vehicle_id="v_err",
        outcome=SessionOutcome.FAILED,
    )
    estimator.update(ev)

    probs = estimator.state_probs(conn_id, now)
    # Healthy should remain dominant or significant; Dead-end must NOT dominate
    assert probs["deadend"] < 0.40, f"Dead-end probability too high after 1 failure: {probs['deadend']}"
    assert probs["healthy"] > probs["deadend"]


def test_forgetting_moves_stale_belief_toward_prior():
    """Verify continuous-time exponential forgetting returns stale belief to baseline prior."""
    cfg = Config(forgetting_half_life_sec=3600.0)
    estimator = HMMBeliefEstimator(cfg)
    conn_id = "conn_0004"
    now = 1700000000000

    # Drive connector into low belief with failures
    for i in range(4):
        estimator.update(
            VehicleSessionEvent(
                event_ts=now + i * 1000,
                session_id=f"sf_{i}",
                connector_id=conn_id,
                vehicle_id=f"vf_{i}",
                outcome=SessionOutcome.TIMEOUT,
            )
        )

    low_p = estimator.p_start(conn_id, now + 4000)
    assert low_p < 0.25

    # Advance time by 4 half-lives (4 hours = 14400 sec) without any new events
    future_ts = now + (14400 * 1000)
    decayed_p = estimator.p_start(conn_id, future_ts)

    # Belief should have decayed back toward healthy prior
    assert decayed_p > low_p
    assert decayed_p > 0.60


def test_group_pooling_raises_suspicion_when_siblings_fail():
    """Verify connector with no local data inherits suspicion when sibling connectors fail."""
    cfg = Config()
    pooler = GroupPooler(cfg)

    # Connectors conn_A and conn_B share FW_v2.0 and site_001
    class Meta:
        def __init__(self, c_id, site_id, op_id, fw):
            self.connector_id = c_id
            self.site_id = site_id
            self.operator_id = op_id
            self.firmware_version = fw

    meta_dict = {
        "conn_A": Meta("conn_A", "site_001", "OP_1", "FW_v2.0"),
        "conn_B": Meta("conn_B", "site_001", "OP_1", "FW_v2.0"),
    }

    estimator = HMMBeliefEstimator(cfg, connectors_meta=meta_dict, pooler=pooler)
    now = 1700000000000

    p_initial = estimator.p_start("conn_A", now)

    # Inject 5 failures on sibling conn_B
    for i in range(5):
        estimator.update(
            VehicleSessionEvent(
                event_ts=now + i * 10000,
                session_id=f"sb_{i}",
                connector_id="conn_B",
                vehicle_id=f"vb_{i}",
                outcome=SessionOutcome.TIMEOUT,
            )
        )

    # conn_A has had ZERO direct events, but its group failed!
    p_after_sibling_fails = estimator.p_start("conn_A", now + 60000)
    assert p_after_sibling_fails < p_initial, "Group pooling should lower conn_A's p_start"


def test_prior_scale_robustness():
    """Verify estimator remains stable and valid under prior_scale = 0.7 and 1.3."""
    for p_scale in [0.7, 1.3]:
        cfg = Config(prior_scale=p_scale)
        estimator = HMMBeliefEstimator(cfg)
        conn_id = "conn_scale_test"
        now = 1700000000000

        ev_start = VehicleSessionEvent(
            event_ts=now,
            session_id="s_start",
            connector_id=conn_id,
            vehicle_id="v_start",
            outcome=SessionOutcome.STARTED,
            delivered_kw=50.0,
            rated_kw=50.0,
        )
        estimator.update(ev_start)

        p = estimator.p_start(conn_id, now + 1000)
        assert 0.0 <= p <= 1.0
        probs = estimator.state_probs(conn_id, now + 1000)
        assert pytest.approx(sum(probs.values()), abs=1e-5) == 1.0
        u = estimator.uncertainty(conn_id, now + 1000)
        assert 0.0 <= u <= 1.0


def test_beta_bernoulli_fallback_step_a():
    """Verify Step A Beta-Bernoulli estimator behaves as a valid fallback."""
    cfg = Config()
    bb = BetaBernoulliEstimator(cfg)
    conn_id = "conn_bb_01"
    now = 1700000000000

    p_init = bb.p_start(conn_id, now)
    assert 0.70 < p_init < 0.90

    # Failure drops belief
    bb.update(
        VehicleSessionEvent(
            event_ts=now + 1000,
            session_id="s1",
            connector_id=conn_id,
            vehicle_id="v1",
            outcome=SessionOutcome.FAILED,
        )
    )
    assert bb.p_start(conn_id, now + 1000) < p_init
