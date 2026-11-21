# Charger Truth: Development Progress Log

## Definition of Done Checklist (Every Step)
- [x] `pytest` passes; new behaviour has unit tests.
- [x] `docs/PROGRESS.md` updated: what changed, what is unverified, next step.
- [x] Short git commit.
- [x] No TODOs left silently.

---

## Log Entry: 2026-11-22 (Prompt 2 Complete - Gate G1 Passed)

### What Changed:
1. **Simulation Environment (`src/ct/sim/`)**:
   - `network.py`: Synthetic Chennai charging network with 60 sites and 200 connectors distributed across 4 operators, 5 hardware models, 3 firmware versions, and power ratings from 50 to 350 kW. Includes `RoadGraph` with great-circle distance and 32 km/h urban travel time calculation.
   - `failures.py`: Ground truth hidden states (`HEALTHY`, `DEGRADED`, `DEADEND`, `OFFLINE`). Correlated fault injection schedule supporting `SiteOutage` (site-wide blackout), `OperatorOutage` (hitting ~30% of operator connectors), `FirmwareBug` (affecting all connectors with targeted firmware), and `SlowDegradation`. Status misreporting model simulating unreliable charger heartbeats (e.g. dead-ends reporting `AVAILABLE` ~90% of the time).
   - `demand.py`: Non-homogeneous Poisson vehicle arrivals with a diurnal curve peaking in the evening (17:00-21:00) with battery capacity, SoC states, and travel destinations.
   - `engine.py`: Closed-loop simulation engine. Enforces strict information hiding via `ObservableSimulationView`. Generates attempts with Common Random Numbers keyed by `(seed, vehicle_id, attempt_no)`. Includes JSONL log export and accelerated replayer.
2. **Arm A Baseline (`src/ct/baselines/reported.py`)**:
   - Implemented `ReportedStatusPolicy` ranking connectors by reported status from heartbeats followed by travel duration.
3. **Calibration (`scripts/calibrate.py` & `docs/CALIBRATION.md`)**:
   - Calibrated baseline failure rates and misreport parameters across dev seeds 0–9.
   - Target first-attempt success: **71.0%**
   - Achieved first-attempt success: **70.70%** (Delta: 0.30% $\le$ 3.0 percentage points).
   - **Gate G1 condition PASSED**.
4. **Verification & Tests (`tests/test_sim.py`)**:
   - Determinism test: identical event logs on repeated runs with same seed.
   - Common random numbers: verified attempt RNG consistency across policies.
   - Fault activation: verified site outage, operator outage, and firmware bug alter hidden state at exact scheduled timestamps.
   - Information hiding: verified policies cannot read hidden states or fault schedules from `ObservableSimulationView`.
   - Total test suite: 20 passed.

### Needs Decision / Parameter Values:
- None.

### What is Unverified:
- Online belief estimation filter, group hazard rate pooling, and active probing (Prompt 3).

### Next Step:
- Execute **Prompt 3**: Implement `src/ct/core/belief.py` (Beta-Bernoulli fallback and 4-state online HMM forward filter), `src/ct/core/pooling.py` (Gamma-Poisson group hazard pooling across site/operator/firmware), active probing candidates, and calibration checks (Brier score & reliability table on dev seeds).
