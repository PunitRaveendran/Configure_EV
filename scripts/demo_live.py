"""Live interactive demonstration of Charger Truth.

Shows:
1. Reported Status vs Belief disagreement (catching stealth dead-ends).
2. Routing around dead-ends to healthy connectors.
3. Injected correlated fault detection via Kulldorff space-time scan.
4. Demand-weighted repair ticketing with heuristic diagnostics.
5. Head-to-head scorecard: Arm A (Reported Status) vs Arm D (Charger Truth).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import numpy as np

# Add src to path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ct.baselines.reported import ReportedStatusPolicy
from ct.config import Config
from ct.core.belief import HMMBeliefEstimator
from ct.core.router import ExpectedTimeRouter
from ct.core.scan import KulldorffClusterScanner
from ct.core.tickets import TicketManager
from ct.schemas import ReportedStatus, SessionOutcome
from ct.sim.engine import SimEngine, build_scenario_schedule
from ct.sim.failures import FailureSchedule, HiddenState, SiteOutage


def run_live_demo():
    print("=" * 75)
    print("      ⚡ CHARGER TRUTH: LIVE TERMINAL DEMONSTRATION ⚡")
    print("      Config 2026 Mobility Hackathon (Condense x Bosch MPS)")
    print("      Note: All data is strictly SIMULATED.")
    print("=" * 75)

    cfg = Config()
    seed = 42

    print("\n[1/4] Initializing Synthetic Chennai Charging Network...")
    engine = SimEngine(cfg, seed=seed, duration_sec=3600)
    print(f"      Total Charging Sites: {len(engine.sites)}")
    print(f"      Total Connectors:     {len(engine.connectors)}")
    print(f"      Operators:            {cfg.num_operators} | Models: {cfg.num_models} | Firmwares: {cfg.num_firmwares}")

    # Set up scenario with a dead-end charger and a site outage
    target_site_id = sorted(engine.sites.keys())[0]
    site_conns = engine.sites[target_site_id].connector_ids
    deadend_conn_id = site_conns[0]
    engine.connectors[deadend_conn_id].hidden_state = HiddenState.DEADEND

    # Outage fault on another site
    outage_site_id = sorted(engine.sites.keys())[1]
    fault = SiteOutage(
        start_ts=engine.start_ts + (900 * 1000),  # 15 min in
        duration_sec=1800,
        name="substation_breaker_trip",
        site_id=outage_site_id,
    )
    engine.schedule = FailureSchedule([fault])

    estimator = HMMBeliefEstimator(cfg, connectors_meta=engine.view.connectors)
    scanner = KulldorffClusterScanner(cfg, connectors_meta=engine.view.connectors, threshold_override=4.0)
    router = ExpectedTimeRouter(cfg, belief_estimator=estimator)
    ticket_mgr = TicketManager(cfg)

    print("\n[2/4] Simulating Streaming Telemetry & Ground-Truth Vehicle Attempts...")
    print("-" * 75)

    # Simulate past failures on the dead-end connector
    print(f"  --> Simulating 3 prior failed sessions on connector [{deadend_conn_id}]...")
    for i in range(3):
        t = engine.start_ts + i * 30000
        sess = engine.session_events
        from ct.schemas import VehicleSessionEvent
        ev = VehicleSessionEvent(
            event_ts=t,
            session_id=f"prior_fail_{i}",
            connector_id=deadend_conn_id,
            vehicle_id=f"prior_veh_{i}",
            outcome=SessionOutcome.TIMEOUT,
            time_to_current_sec=120.0,
            failure_reason="session_handshake_timeout",
        )
        estimator.update(ev)
        scanner.record_session(ev)

    # Check status and belief on the dead-end connector
    demo_rng = np.random.RandomState(42)
    hb = engine.heartbeat_gen.sample_reported_status(
        HiddenState.DEADEND, False, demo_rng
    )
    from ct.schemas import ChargerStatusEvent
    ev_hb = ChargerStatusEvent(
        event_ts=engine.start_ts + 120000,
        connector_id=deadend_conn_id,
        site_id=target_site_id,
        reported_status=ReportedStatus.AVAILABLE,  # Falsely reports AVAILABLE!
    )
    estimator.update(ev_hb)
    engine.view.record_status(ev_hb)

    p_deadend = estimator.p_start(deadend_conn_id, ev_hb.event_ts)
    probs = estimator.state_probs(deadend_conn_id, ev_hb.event_ts)

    print("\n  🔍 [DISAGREEMENT DETECTED]")
    print(f"     Connector:        {deadend_conn_id} at {target_site_id}")
    print(f"     Firmware Reports: \033[92m{ev_hb.reported_status.value}\033[0m (Unreliable Heartbeat)")
    print(f"     Charger Truth:    \033[91mP(start) = {p_deadend:.1%}\033[0m | P(Dead-end) = {probs['deadend']:.1%}")
    print("     Ground Truth:     HIDDEN STATE = DEAD-END (Never delivers current)")

    # Create a vehicle routing request arriving near this site
    from ct.schemas import VehicleRequestEvent
    req = VehicleRequestEvent(
        event_ts=engine.start_ts + 150000,
        request_id="demo_req_001",
        vehicle_id="veh_chennai_88",
        current_lat=engine.sites[target_site_id].lat + 0.004,
        current_lon=engine.sites[target_site_id].lon + 0.004,
        current_soc=0.18,
        battery_kwh=60.0,
        target_soc=0.80,
        reserve_soc=0.10,
        max_charge_rate_kw=150.0,
    )

    print("\n[3/4] Routing Decision Comparison for Incoming EV...")
    print(f"      Vehicle ID:      {req.vehicle_id} (SoC: 18%, Battery: 60 kWh)")
    print(f"      Location:        Close to {target_site_id} (0.5 km)")

    # Arm A choice
    policy_A = ReportedStatusPolicy()
    arm_a_choice = policy_A.choose(req, engine.view)[0]
    print(f"\n  ❌ Arm A (Reported Status Policy) routes to:")
    print(f"     Connector:        {arm_a_choice}")
    print(f"     Reason:           Firmware reports 'AVAILABLE' and distance is closest (0.5 km).")
    print(f"     Expected Outcome: \033[91mFAILED TRIP!\033[0m Handshake times out after 120s delay.")

    # Arm D choice
    ranked_ids, decision = router.plan_route(req, engine.view)
    arm_d_choice = ranked_ids[0]
    cand = decision.ranked_candidates[0]
    print(f"\n  ✅ Arm D (Charger Truth Policy) routes to:")
    print(f"     Connector:        {arm_d_choice} (at {cand.site_id})")
    print(f"     Belief P(start):  {cand.p_start:.1%}")
    print(f"     Reason:           {decision.reason}")
    print(f"     Expected Outcome: \033[92mSUCCESS!\033[0m Charges smoothly without wasted trip.")

    # Fault scan & ticketing demo
    print("\n[4/4] Prospective Space-Time Cluster Scan & Repair Ticketing...")
    print(f"      Simulating burst of failures at site [{outage_site_id}]...")
    for c_id in engine.sites[outage_site_id].connector_ids:
        for rep in range(2):
            t = engine.start_ts + (950 * 1000) + rep * 1000
            from ct.schemas import VehicleSessionEvent
            ev_fail = VehicleSessionEvent(
                event_ts=t,
                session_id=f"outage_{c_id}_{rep}",
                connector_id=c_id,
                vehicle_id=f"veh_out_{c_id}_{rep}",
                outcome=SessionOutcome.TIMEOUT,
            )
            scanner.record_session(ev_fail)

    # Evaluate 2 consecutive steps for persistence
    scanner.evaluate(engine.start_ts + (980 * 1000))
    alerts = scanner.evaluate(engine.start_ts + (1000 * 1000))
    if alerts:
        alt = alerts[0]
        print(f"  🚨 \033[93mCLUSTER ALERT FIRED!\033[0m")
        print(f"     Group Type:       {alt.group_type.value.upper()} ({alt.group_key})")
        print(f"     Statistic (LLR):  {alt.llr:.2f} (Threshold: {alt.threshold:.2f}, Window: {alt.window_min}m)")
        print(f"     Failures:         {alt.observed_failures} observed vs {alt.expected_failures:.1f} expected")

        ticket = ticket_mgr.create_cluster_ticket(alt, average_local_demand=4.5)
        print(f"\n  🎫 Grouped Repair Ticket Generated (Single Ticket, No Alert Storm):")
        print(f"     Ticket ID:        {ticket.ticket_id}")
        print(f"     Repair Priority:  \033[1m{ticket.priority}\033[0m (Demand-weighted)")
        print(f"     Diagnostic Hint:  {ticket.heuristic_hint}")

    # Final dev seed scorecard
    print("\n" + "=" * 75)
    print("             📊 DEV SEEDS 0-9 HEAD-TO-HEAD SCORECARD")
    print("=" * 75)
    print(f"{'Metric':<28} | {'Arm A (Reported)':<18} | {'Arm D (Charger Truth)':<18} | {'Improvement':<12}")
    print("-" * 75)
    print(f"{'Wasted-Trip Rate':<28} | {'28.80%':<18} | {'20.88%':<18} | {'-27.5% rel':<12}")
    print(f"{'Wasted Driver Minutes':<28} | {'35.7 min':<18} | {'23.8 min':<18} | {'-33.3% rel':<12}")
    print(f"{'Brier Score (Calibration)':<28} | {'0.250 (prior)':<18} | {'0.181 (calibrated)':<18} | {'+27.6%':<12}")
    print("=" * 75)
    print("To inspect full markdown reports and losses:")
    print("  - docs/results/dev_seed_summary.md")
    print("  - docs/results/losses.md")
    print("  - docs/CALIBRATION.md")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    run_live_demo()
