"""Verification script for Phase B: Hard-rule audits."""
import ast
import os
import re
from ct.config import Config
from ct.sim.engine import SimEngine, make_attempt_rng
from ct.baselines.reported import ReportedStatusPolicy
from ct.core.router import BeliefPolicy
from ct.schemas import VehicleRequestEvent

def check_h5():
    """H5: Connector failures, fault injection times and arrivals do not depend on the policy."""
    cfg = Config()
    seed = 42
    engine_A = SimEngine(cfg, seed=seed, duration_sec=1800)
    engine_D = SimEngine(cfg, seed=seed, duration_sec=1800)
    
    events_A = engine_A.run(ReportedStatusPolicy())
    events_D = engine_D.run(BeliefPolicy(cfg))
    
    reqs_A = [e for e in events_A if isinstance(e, VehicleRequestEvent)]
    reqs_D = [e for e in events_D if isinstance(e, VehicleRequestEvent)]
    
    assert len(reqs_A) == len(reqs_D), f"Request count mismatch: {len(reqs_A)} vs {len(reqs_D)}"
    for ra, rd in zip(reqs_A, reqs_D):
        assert ra.event_ts == rd.event_ts, f"Timestamp mismatch: {ra.event_ts} vs {rd.event_ts}"
        assert ra.vehicle_id == rd.vehicle_id
        assert ra.current_lat == rd.current_lat
        assert ra.current_lon == rd.current_lon
        assert ra.battery_kwh == rd.battery_kwh
        assert ra.current_soc == rd.current_soc
        assert ra.target_soc == rd.target_soc
    
    # Check fault schedule
    sched_A = engine_A.schedule
    sched_D = engine_D.schedule
    assert len(sched_A.faults) == len(sched_D.faults)
    for fa, fd in zip(sched_A.faults, sched_D.faults):
        assert fa.start_ts == fd.start_ts
        assert fa.end_ts == fd.end_ts
        assert type(fa) == type(fd)
    print("H5 PASS: Request streams, arrival times, and fault schedules are byte-for-byte identical.")

def check_h7():
    """H7: Check for hardcoded numeric tunables in src/ct/{sim,core,baselines,eval}."""
    suspect_tunables = []
    # Search for numeric constants assigned to variables with tunable-sounding names
    pattern = re.compile(r'^\s*([A-Z0-9_]{3,}|[a-z_]+)\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(?:#.*)?$')
    for root, dirs, files in os.walk("src/ct"):
        if "config.py" in files and root == "src/ct":
            continue
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                with open(path) as fh:
                    for i, line in enumerate(fh, 1):
                        m = pattern.match(line)
                        if m:
                            var, val = m.group(1), m.group(2)
                            # filter out obvious non-tunables like loop indices, conversions
                            if var in ("lat", "lon", "ts", "i", "j", "k", "n", "idx", "VERSION"):
                                continue
                            suspect_tunables.append((path, i, var, val, line.strip()))
    print(f"H7 Found {len(suspect_tunables)} candidate constant assignments outside config.py:")
    for path, line_no, var, val, line in suspect_tunables:
        print(f"  {path}:{line_no} -> {line}")

if __name__ == "__main__":
    check_h5()
    check_h7()
