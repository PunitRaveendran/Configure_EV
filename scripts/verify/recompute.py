"""Phase E: Independent recomputation without importing ct.eval.

Audits dev seeds 0-9 for Arms A and D from raw JSONL event logs.
"""
import hashlib
import json
import os
import sys
import numpy as np

# DO NOT import ct.eval!
from ct.config import Config
from ct.sim.engine import SimEngine, build_scenario_schedule
from ct.baselines.reported import ReportedStatusPolicy
from ct.core.router import BeliefPolicy

LOG_DIR = "/tmp/verify_logs"
os.makedirs(LOG_DIR, exist_ok=True)

def run_simulation(arm_name: str, seed: int, duration_sec: int = 3600) -> str:
    """Run sim and write raw JSONL log."""
    cfg = Config()
    engine = SimEngine(cfg, seed=seed, duration_sec=duration_sec)
    engine.schedule = build_scenario_schedule(
        "baseline", engine.connectors, engine.sites, engine.start_ts, seed=seed, config=cfg
    )
    
    if arm_name == "A_reported":
        policy = ReportedStatusPolicy()
    elif arm_name == "D_belief":
        policy = BeliefPolicy(cfg)
    else:
        raise ValueError(f"Unknown arm {arm_name}")
        
    events = engine.run(policy)
    
    log_path = os.path.join(LOG_DIR, f"{arm_name}_seed_{seed}.jsonl")
    with open(log_path, "w") as fh:
        for ev in events:
            fh.write(ev.to_json() + "\n")
            
    return log_path

def parse_metrics_from_jsonl(log_path: str):
    """Parse session outcomes directly from raw JSONL without importing ct.eval.
    
    Definitions per S5:
    - first attempts: session_id ending with '_1'
    - wasted trip rate: fraction of first attempts where outcome != 'STARTED'
    - wasted minutes: for each failed session, timeout_min + 5.0 min detour penalty
    """
    first_attempts = []
    failed_sessions = []
    
    with open(log_path) as fh:
        for line in fh:
            data = json.loads(line)
            # check if vehicle session event
            if "session_id" in data and "outcome" in data:
                sess_id = data["session_id"]
                outcome = data["outcome"]
                time_to_curr = data.get("time_to_current_sec") or 120.0
                
                if sess_id.endswith("_1"):
                    first_attempts.append(outcome)
                    
                if outcome != "STARTED":
                    timeout_min = time_to_curr / 60.0
                    wasted_min = timeout_min + 5.0
                    failed_sessions.append(wasted_min)
                    
    total_first = len(first_attempts)
    failed_first = sum(1 for o in first_attempts if o != "STARTED")
    wasted_trip_rate = (failed_first / total_first) if total_first > 0 else 0.0
    wasted_minutes = round(sum(failed_sessions), 1)
    
    return {
        "total_first": total_first,
        "failed_first": failed_first,
        "wasted_trip_rate": wasted_trip_rate,
        "wasted_minutes": wasted_minutes,
    }

def compute_bootstrap_ci(diffs, n_boot=10000, seed=42):
    rng = np.random.RandomState(seed)
    arr = np.array(diffs)
    boot_means = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        boot_means.append(np.mean(sample))
    return np.percentile(boot_means, 2.5), np.percentile(boot_means, 97.5)

def main():
    print("=== Phase E: Independent Recomputation ===")
    
    # 1. Run determinism check on seed 0
    path_1 = run_simulation("A_reported", seed=0)
    hash_1 = hashlib.sha256(open(path_1, "rb").read()).hexdigest()
    
    path_2 = run_simulation("A_reported", seed=0)
    hash_2 = hashlib.sha256(open(path_2, "rb").read()).hexdigest()
    
    assert hash_1 == hash_2, "Non-deterministic simulation log detected!"
    print(f"Determinism Check: PASS (SHA256: {hash_1[:16]}...)")
    
    # 2. Run dev seeds 0-9 for Arms A and D
    rates_A, rates_D = [], []
    mins_A, mins_D = [], []
    diffs = []
    
    print("\nPer-seed raw log extraction:")
    for s in range(10):
        log_A = run_simulation("A_reported", seed=s)
        log_D = run_simulation("D_belief", seed=s)
        
        m_A = parse_metrics_from_jsonl(log_A)
        m_D = parse_metrics_from_jsonl(log_D)
        
        rate_A = m_A["wasted_trip_rate"]
        rate_D = m_D["wasted_trip_rate"]
        delta = rate_D - rate_A
        
        rates_A.append(rate_A)
        rates_D.append(rate_D)
        mins_A.append(m_A["wasted_minutes"])
        mins_D.append(m_D["wasted_minutes"])
        diffs.append(delta)
        
        print(f"  Seed {s}: A={rate_A*100:.2f}% ({m_A['failed_first']}/{m_A['total_first']}), "
              f"D={rate_D*100:.2f}% ({m_D['failed_first']}/{m_D['total_first']}), "
              f"Delta={delta*100:.2f}%, Mins A={m_A['wasted_minutes']}, D={m_D['wasted_minutes']}")
              
    mean_rate_A = np.mean(rates_A)
    mean_rate_D = np.mean(rates_D)
    mean_delta = np.mean(diffs)
    mean_mins_A = np.mean(mins_A)
    mean_mins_D = np.mean(mins_D)
    
    ci_low, ci_high = compute_bootstrap_ci(diffs, n_boot=10000, seed=42)
    
    print("\nSummary Across Dev Seeds 0-9:")
    print(f"  Arm A Wasted-Trip Rate: {mean_rate_A*100:.2f}%")
    print(f"  Arm D Wasted-Trip Rate: {mean_rate_D*100:.2f}%")
    print(f"  Mean Delta: {mean_delta*100:.2f}%")
    print(f"  Arm A Mean Wasted Minutes: {mean_mins_A:.1f}")
    print(f"  Arm D Mean Wasted Minutes: {mean_mins_D:.1f}")
    print(f"  95% Bootstrap CI: [{ci_low*100:.2f}%, {ci_high*100:.2f}%]")
    
    # Compare with docs/results/dev_seed_summary.md:
    # dev_seed_summary claimed:
    # A_reported: 28.80%, 35.7 min
    # D_belief: 20.16%, 23.1 min
    # Delta: -8.64%, CI: [-17.89%, +1.72%]
    print("\nComparison against docs/results/dev_seed_summary.md:")
    print(f"  Reported A: 28.80% | Recomputed A: {mean_rate_A*100:.2f}% -> Match: {abs(mean_rate_A*100 - 28.80) < 0.01}")
    print(f"  Reported D: 20.16% | Recomputed D: {mean_rate_D*100:.2f}% -> Match: {abs(mean_rate_D*100 - 20.16) < 0.01}")
    print(f"  Reported A Mins: 35.7 | Recomputed A Mins: {mean_mins_A:.1f} -> Match: {abs(mean_mins_A - 35.7) < 0.1}")
    print(f"  Reported D Mins: 23.1 | Recomputed D Mins: {mean_mins_D:.1f} -> Match: {abs(mean_mins_D - 23.1) < 0.1}")

if __name__ == "__main__":
    main()
