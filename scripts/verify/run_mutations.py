"""Phase F: Mutation spot checks on test suite."""
import os
import subprocess
import re

def run_pytest():
    res = subprocess.run(
        ["env", "-u", "PYTHONPATH", ".venv/bin/pytest", "-q"],
        capture_output=True,
        text=True
    )
    return res.returncode, res.stdout.strip(), res.stderr.strip()

def mutate_and_test(mutation_id, description, file_path, target_str, replacement_str):
    print(f"\n--- Testing {mutation_id}: {description} ---")
    with open(file_path, "r") as f:
        content = f.read()
    
    if target_str not in content:
        print(f"ERROR: target_str not found in {file_path}")
        return False
        
    mutated_content = content.replace(target_str, replacement_str, 1)
    with open(file_path, "w") as f:
        f.write(mutated_content)
        
    code, out, err = run_pytest()
    
    # Restore original content immediately
    with open(file_path, "w") as f:
        f.write(content)
        
    caught = (code != 0)
    print(f"Result: {'CAUGHT (Test Suite Failed)' if caught else 'SURVIVED (Tests Still Pass - WEAK TEST)'}")
    print(f"Exit code: {code}")
    print(f"Output summary:\n{out.splitlines()[-1] if out.splitlines() else err.splitlines()[-1]}")
    return caught

def main():
    # M1: Add policy_id to make_attempt_rng key or signature
    # In engine.py line 112: key_str = f"{seed}:{vehicle_id}:{attempt_no}"
    # Change to: key_str = f"{seed}:{vehicle_id}:{attempt_no}:{id(object())}" (random jitter per call)
    mutate_and_test(
        "M1",
        "Add policy/instance jitter to make_attempt_rng key",
        "src/ct/sim/engine.py",
        'key_str = f"{seed}:{vehicle_id}:{attempt_no}"',
        'key_str = f"{seed}:{vehicle_id}:{attempt_no}:{id(object())}"'
    )

    # M2: Change pooling clip bounds to [0.0, 100.0] in pooling.py
    mutate_and_test(
        "M2",
        "Change pooling clip bounds to [0.0, 100.0]",
        "src/ct/core/pooling.py",
        "self.config.pooling_clip_min,\n            min(self.config.pooling_clip_max, raw_mult),",
        "0.0,\n            min(100.0, raw_mult),"
    )

    # M3: Remove persistence (alert on 1 exceedance) in scan.py
    # In scan.py line 199: if st.consecutive_hits >= self.config.scan_persistence:
    mutate_and_test(
        "M3",
        "Remove persistence: alert on 1 exceedance instead of 2",
        "src/ct/core/scan.py",
        "if st.consecutive_hits >= self.config.scan_persistence:",
        "if st.consecutive_hits >= 1:"
    )

    # M4: Make Arm D read a hidden-state field
    # In router.py: access view._connectors_meta.get(c_id).hidden_state
    mutate_and_test(
        "M4",
        "Make Arm D router read hidden_state attribute",
        "src/ct/core/router.py",
        "for c_id, meta in view.connectors.items():",
        "for c_id, meta in view.connectors.items():\n            _ = getattr(meta, 'hidden_state', None)"
    )

    # M5: Swap the router p and 1-p terms
    mutate_and_test(
        "M5",
        "Swap router p and (1-p) terms",
        "src/ct/core/router.py",
        "lookahead_t = t + p * (w + s) + (1.0 - p) * (timeout_cost_min + t_next)",
        "lookahead_t = t + (1.0 - p) * (w + s) + p * (timeout_cost_min + t_next)"
    )

if __name__ == "__main__":
    main()
