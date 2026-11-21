# Charger Truth: Development Progress Log

## Definition of Done Checklist (Every Step)
- [x] `pytest` passes; new behaviour has unit tests.
- [x] `docs/PROGRESS.md` updated: what changed, what is unverified, next step.
- [x] Short git commit.
- [x] No TODOs left silently.

---

## Log Entry: 2026-11-22 (Prompt 3 Complete)

### What Changed:
1. **Group Hazard Rate Pooling (`src/ct/core/pooling.py`)**:
   - Implemented `GroupPooler` calculating empirical Bayes Gamma-Poisson hazard multipliers shared across `site`, `operator`, and `firmware` groups.
   - Applies exponential forgetting on group statistics and clips multipliers strictly to `[Config.pooling_clip_min, Config.pooling_clip_max]`.
2. **Belief Estimation Filter (`src/ct/core/belief.py`)**:
   - **Step A:** `BetaBernoulliEstimator` tracking session starts/failures with conjugate Beta updates and exponential decay toward prior.
   - **Step B:** `HMMBeliefEstimator` implementing an online 4-state forward filter ($O(1)$ per event) across states: *Healthy*, *Degraded*, *Dead-end*, and *Offline*.
   - Features:
     - Continuous-time exponential forgetting toward the group-pooled prior ($t_{1/2} = 3600$s).
     - Vehicle-side failure buffer so isolated single failures do not prematurely condemn healthy chargers.
     - Delivered vs rated power ratio incorporation for degraded state detection.
     - Unreliability/entropy calculation ($H \in [0.0, 1.0]$) and active probing candidate selection (~5% requests for vehicles with slack range).
     - Streaming serialization to `ConnectorBeliefEvent`.
3. **Verification & Tests (`tests/test_belief.py`)**:
   - Probabilities sum to 1.0 under updates and continuous time decay.
   - $P(\text{start})$ falls sharply under consecutive timeouts and recovers after successful sessions.
   - One failure alone does not mark a connector as Dead-end ($P(\text{deadend}) < 0.40$).
   - Stale belief decays back to baseline prior over 4 half-lives.
   - Sibling connector failure in the same firmware/site group raises suspicion on unvisited connectors.
   - Numerically robust under `prior_scale = 0.7` and `1.3`.
   - Beta-Bernoulli fallback verified.
4. **Dev Seeds Calibration (`scripts/check_calibration.py` & `docs/CALIBRATION.md`)**:
   - Replayed dev seeds 0–9 through `HMMBeliefEstimator` and evaluated first-attempt predictions.
   - **Brier Score:** **0.1808** (vs uninformative baseline of ~0.250).
   - Produced 5-bin reliability table and documented calibration gap in intermediate bins due to stealth dead-end misreporting.
   - Total test suite: 27 passed.

### Needs Decision / Parameter Values:
- None.

### What is Unverified:
- Prospective space-time scan (LLR and Monte Carlo thresholding), expected-time router, and repair queue tickets (Prompt 4).

### Next Step:
- Execute **Prompt 4**: Implement `src/ct/core/scan.py` (prospective Kulldorff space-time scan), `src/ct/core/router.py` (expected trip-time router with 1-step lookahead), and `src/ct/core/tickets.py` (demand-weighted repair queue).
