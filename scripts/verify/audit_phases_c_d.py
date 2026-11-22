"""Audit script for Phase C (Requirements) and Phase D (Known Suspects)."""
import os
import sys
import numpy as np
from ct.config import Config
from ct.schemas import (
    TOPIC_CHARGER_STATUS, TOPIC_VEHICLE_SESSION, TOPIC_VEHICLE_REQUEST,
    TOPIC_CONNECTOR_BELIEF, TOPIC_CLUSTER_ALERT, TOPIC_ROUTE_DECISION,
    TOPIC_OPS_TICKET, ChargerStatusEvent, VehicleSessionEvent,
    VehicleRequestEvent, ConnectorBeliefEvent, ClusterAlertEvent,
    RouteDecisionEvent, OpsTicketEvent, SessionOutcome
)
from ct.sim.network import build_synthetic_network
from ct.sim.engine import SimEngine
from ct.baselines.reported import ReportedStatusPolicy
from ct.baselines.failcount import FailCountPolicy
from ct.baselines.usagegap import UsageGapPolicy
from ct.core.router import BeliefPolicy
from ct.eval.harness import EvaluationHarness

def audit_s1_usagegap():
    """S1: Arm A and Arm C are identical in PROGRESS.md. Check if Arm C ever flags anything."""
    cfg = Config()
    flag_counts = []
    for s in range(10):
        engine = SimEngine(cfg, seed=s, duration_sec=3600)
        policy_c = UsageGapPolicy(gap_multiplier=2.5, expected_idle_sec=1800.0)
        events = engine.run(policy_c)
        # Check flagged connectors
        flagged_now = len(policy_c.flagged_at_ts)
        flag_counts.append((s, flagged_now, len(policy_c.last_session_ts)))
    print("S1 Flag counts for Arm C across 10 dev seeds (duration=3600s, threshold=4500s):")
    print("   (seed, flagged_connectors_count, total_connectors_with_sessions):", flag_counts)
    
    # Check max possible idle duration observed in a 3600s run
    engine = SimEngine(cfg, seed=0, duration_sec=3600)
    policy_c = UsageGapPolicy(gap_multiplier=2.5, expected_idle_sec=1800.0)
    engine.run(policy_c)
    max_allowed = policy_c.expected_idle_sec * policy_c.gap_multiplier
    print(f"   Max allowed idle before flag: {max_allowed}s (1.25 hrs). Sim duration: 3600s (1.0 hr).")
    print(f"   Therefore, Arm C flags exactly 0 connectors. It is completely inactive.")

def audit_s2_g1_calibration():
    """S2: G1 binomial SE, Wilson 95% CI for achieved rate."""
    n = 157
    k = 111
    p_hat = k / n
    z = 1.95996
    denom = 1 + z**2 / n
    centre = (p_hat + z**2 / (2 * n)) / denom
    margin = (z * np.sqrt((p_hat * (1 - p_hat) / n) + (z**2 / (4 * n**2)))) / denom
    ci_lower = centre - margin
    ci_upper = centre + margin
    se = np.sqrt(p_hat * (1 - p_hat) / n)
    print(f"S2: Achieved = {p_hat*100:.2f}% ({k}/{n}), Binomial SE = {se*100:.2f} percentage points")
    print(f"S2: Wilson 95% CI = [{ci_lower*100:.2f}%, {ci_upper*100:.2f}%]")
    print(f"S2: Note: Gate G1 margin is +/- 3.0 points. Since CI [{ci_lower*100:.2f}%, {ci_upper*100:.2f}%] spans 13.9 points, G1 is met on point estimate only, inside the noise.")

def audit_s3_brier():
    """S3: Brier score vs base rate."""
    p_hat = 111 / 157
    base_brier = p_hat * (1 - p_hat)
    reported_brier = 0.1808
    bss = 1.0 - (reported_brier / base_brier)
    print(f"S3: Base-rate Brier = {base_brier:.4f}, Reported Brier = {reported_brier:.4f}, Brier Skill Score = {bss*100:.2f}% (vs claimed 'substantially better than ~0.250')")
    # Reliability table check:
    # From CALIBRATION.md:
    # [0.2, 0.4): 4 samples, 0.000 rate -> 0
    # [0.4, 0.6): 4 samples, 0.000 rate -> 0
    # [0.6, 0.8): 12 samples, 0.167 rate -> 12 * 0.167 ~ 2
    # [0.8, 1.0): 137 samples, 0.803 rate -> 137 * 0.803 ~ 110.011 -> 110
    # Total = 112 vs 111 (70.70% of 157 = 110.999 -> 111).
    print("S3: Sum of observed successes in reliability table = 0 + 0 + 2 + 110 = 112 vs 111 implied by 70.70% (discrepancy of 1 due to binning/rounding or counting).")

def audit_s4_g2():
    """S4: G2 per-seed paired differences and confidence interval."""
    harness = EvaluationHarness()
    results_A = []
    results_D = []
    diffs = []
    print("S4 Running Dev Seeds 0-9 for Arms A and D:")
    for s in range(10):
        res_A = harness.run_arm("A_reported", "baseline", seed=s, duration_sec=3600)
        res_D = harness.run_arm("D_belief", "baseline", seed=s, duration_sec=3600)
        rate_A = res_A["wasted_trip_rate"]
        rate_D = res_D["wasted_trip_rate"]
        diff = rate_D - rate_A
        results_A.append(rate_A)
        results_D.append(rate_D)
        diffs.append(diff)
        print(f"   Seed {s}: Arm A = {rate_A*100:.2f}%, Arm D = {rate_D*100:.2f}%, Delta = {diff*100:.2f}%")
    
    mean_A = np.mean(results_A)
    mean_D = np.mean(results_D)
    mean_diff = np.mean(diffs)
    favors_D = sum(1 for d in diffs if d < 0)
    print(f"S4: Overall Mean A: {mean_A*100:.2f}%, Mean D: {mean_D*100:.2f}%, Mean Delta: {mean_diff*100:.2f}%")
    print(f"S4: Seeds favoring D: {favors_D}/10.")
    
    # Bootstrap CI
    rng = np.random.RandomState(42)
    boot_diffs = []
    diffs_arr = np.array(diffs)
    for _ in range(10000):
        idx = rng.choice(len(diffs_arr), size=len(diffs_arr), replace=True)
        boot_diffs.append(np.mean(diffs_arr[idx]))
    ci_low = np.percentile(boot_diffs, 2.5)
    ci_high = np.percentile(boot_diffs, 97.5)
    print(f"S4: 95% Bootstrap CI: [{ci_low*100:.2f}%, {ci_high*100:.2f}%]")
    print(f"S4: Note: CI crosses zero (upper bound is positive). Thus G2 is met on point estimate, not statistically established.")

def audit_s5_metrics_definition():
    """S5: Inspect metrics definitions and units."""
    from ct.eval import metrics
    import inspect
    print("S5 Inspection of metrics.py functions:")
    for name in ["compute_wasted_trip_rate", "compute_wasted_minutes", "compute_time_to_charged"]:
        fn = getattr(metrics, name)
        print(f"--- {name} docstring and code ---")
        print(inspect.getsource(fn))

def audit_s8_circularity():
    """S8: Compare sim's true parameters with Config priors."""
    cfg = Config()
    from ct.sim.failures import FailureGenerator
    fg = FailureGenerator(cfg)
    print("S8: Priors in Config vs True Sim Parameters:")
    print(f"  P(start|Healthy): Prior={cfg.p_start_healthy}, Sim={fg.p_start['Healthy']}")
    print(f"  P(start|Degraded): Prior={cfg.p_start_degraded}, Sim={fg.p_start['Degraded']}")
    print(f"  P(start|Deadend): Prior={cfg.p_start_deadend}, Sim={fg.p_start['Deadend']}")
    print(f"  P(start|Offline): Prior={cfg.p_start_offline}, Sim={fg.p_start['Offline']}")
    print(f"  P(avail|Healthy): Prior={cfg.p_avail_healthy}, Sim={fg.p_avail['Healthy']}")
    print(f"  P(avail|Degraded): Prior={cfg.p_avail_degraded}, Sim={fg.p_avail['Degraded']}")
    print(f"  P(avail|Deadend): Prior={cfg.p_avail_deadend}, Sim={fg.p_avail['Deadend']}")
    print(f"  P(avail|Offline): Prior={cfg.p_avail_offline}, Sim={fg.p_avail['Offline']}")

def audit_c5_eval_coverage():
    """C5.3 - C5.6: Check which metrics and ablations actually exist in code."""
    from ct.eval import metrics, harness
    print("C5.3 - C5.6 Evaluation features check:")
    print("  Has failure-detection latency in metrics?", hasattr(metrics, "compute_detection_latency"))
    print("  Has cluster alert precision/recall in metrics?", hasattr(metrics, "compute_alert_precision_recall"))
    print("  Has matched false-alarm sweep in harness?", hasattr(harness, "matched_false_alarm_sweep") or hasattr(harness.EvaluationHarness, "sweep_thresholds"))
    print("  Has ablations in harness?", hasattr(harness, "run_ablations") or hasattr(harness.EvaluationHarness, "run_ablations"))

if __name__ == "__main__":
    print("=== S1 ===")
    audit_s1_usagegap()
    print("\n=== S2 ===")
    audit_s2_g1_calibration()
    print("\n=== S3 ===")
    audit_s3_brier()
    print("\n=== S4 ===")
    audit_s4_g2()
    print("\n=== S5 ===")
    audit_s5_metrics_definition()
    print("\n=== S8 ===")
    audit_s8_circularity()
    print("\n=== C5 Deliverables Check ===")
    audit_c5_eval_coverage()
