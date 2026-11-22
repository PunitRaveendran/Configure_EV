# Charger Truth: Independent Verification & Audit Report

**Audit Date:** 2026-11-22  
**Commit Audited:** `5ced9ef` (`Add interactive live terminal demo script`)  
**Auditor:** Rudra Modi (`rudra-modi27`)  
**Branch:** `rudra-modi`  
**Scope:** Offline phase (Prompts 1 to 5: `src/ct/{schemas,config}.py`, `src/ct/sim`, `src/ct/core`, `src/ct/baselines`, `src/ct/eval`, `tests/`, `docs/`).  
**Status:** **OFFLINE PHASE NOT VERIFIED** (Open BLOCKERs present).

---

## 1. Master Verdict Table

| ID | Area / Item | Status | Severity | Evidence | Audit Findings / Notes |
|---|---|---|---|---|---|
| **A1** | Environment & Install | **PASS** | - | `python3 --version` -> 3.12.3; `.venv/bin/pip install -e ".[dev]"` succeeded | Clean install per `pyproject.toml`. |
| **A2** | Pytest Suite | **PASS** | - | `env -u PYTHONPATH .venv/bin/pytest -q` -> `35 passed in 0.42s` | All 35 tests pass. (Note: ROS Jazzy host env required unsetting PYTHONPATH to prevent `launch_testing` collision). |
| **A3** | Work Tree & Results | **PASS** | - | `git diff docs/results/` is empty | Results files match committed repository state. |
| **H1** | Core Architecture | **PASS** | - | `grep -rniE "kafka\|confluent\|condense\|redpanda" src/ct/core` -> 0 code imports | Core logic is pure Python + NumPy with zero messaging dependencies. |
| **H2** | Simulator Independence | **PASS** | - | `grep -rnE "ct\.core\|from ct import core" src/ct/sim` -> 0 matches | Sim never imports `ct.core`. |
| **H3** | Hidden State Visibility | **PASS** | - | `src/ct/sim/engine.py:50-96`, `tests/test_sim.py:155-168` | `ObservableSimulationView` exposes only public metadata, graph, and history. |
| **H4** | Common Random Numbers | **PASS** | - | `src/ct/sim/engine.py:110-112`, `233` | Keyed strictly by `(seed, vehicle_id, attempt_no)`. |
| **H5** | Invariant Environment | **PASS** | - | `scripts/verify/audit_hard_rules.py` | Arm A and Arm D face byte-for-byte identical request streams and fault timelines. |
| **H6** | Secrets & Credentials | **PASS** | - | `grep -rniE "(api[_-]?key\|secret\|password\|token)\s*=" .` -> 0 matches | No hardcoded credentials or API keys. |
| **H7** | Magic Numbers | **PARTIAL** | **MINOR** | `src/ct/eval/metrics.py:38`, `src/ct/core/router.py:85`, `src/ct/sim/engine.py:162` | Unconfigured constants exist (e.g. 5.0 min detour penalty in `metrics.py`, 12.0 min wait heuristic in `router.py`, 60s heartbeat in `engine.py`). |
| **H8** | Synthetic Disclosure | **PASS** | - | `grep -rn "SIMULATED" docs/ scripts/` -> 10 matches | "SIMULATED" prominently stated across all docs and scripts. |
| **H9** | Eval Seed Partition | **PASS** | - | `git log -- docs/PREREG.md docs/results/` | Seeds 100–119 have NOT been run. |
| **H10** | PREREG Commit Hash | **FAIL** | **MINOR** | `docs/results/dev_seed_summary.md`, `docs/results/losses.md` | Neither results file records the git commit hash of `PREREG.md` (`da38da9`). |
| **C1.1** | Pydantic Event Topics | **PASS** | - | `src/ct/schemas.py:10-18` | All 7 topic constants and models defined. |
| **C1.2** | Event Schemas & Keys | **PASS** | - | `src/ct/schemas.py:20-185`, `tests/test_schemas.py` | Fields match SPEC; `event_ts` is int UTC ms; stable partition keys implemented. |
| **C1.3** | Session Enums & kW | **PASS** | - | `src/ct/schemas.py:23-28`, `51-52` | `SessionOutcome` (STARTED, FAILED, TIMEOUT), `delivered_kw`, `rated_kw` present. |
| **C1.4** | JSON Serialization | **PASS** | - | `tests/test_schemas.py` (9 passed) | `to_json()` and `from_json()` round-trip verified for all models. |
| **C1.5** | Frozen Config & Scale | **PASS** | - | `src/ct/config.py:24-95`, `tests/test_config.py` | Config is frozen dataclass; YAML override and `prior_scale` verified. |
| **C1.6** | Spec Parameters | **PASS** | - | `src/ct/config.py` | Missing parameters handled without inventing ungrounded magic defaults. |
| **C1.7** | Makefile Targets | **PASS** | - | `Makefile:1-12` | `test`, `lint`, `sim`, `eval` targets exist and function. |
| **C2.1** | Synthetic Network Size | **PASS** | - | `src/ct/sim/network.py:133-145` | 200 connectors, 60 sites, 4 operators, 5 models, 3 firmwares in Chennai bbox. |
| **C2.2** | Hidden States & Power | **PASS** | - | `src/ct/sim/engine.py:245-315` | Dead-end uses `p_start=0.03`, reports Available ~92%; Degraded delivers 20-60%. |
| **C2.3** | Correlated Faults | **PASS** | - | `src/ct/sim/failures.py:32-53`, `tests/test_sim.py:80-153` | Site outage, operator outage (~30%), and firmware bug inject correctly. |
| **C2.4** | Poisson Vehicle Demand | **PASS** | - | `src/ct/sim/demand.py:20-65` | Poisson arrivals with diurnal evening peak, queueing, and road graph travel times. |
| **C2.5** | Vehicle-Side Failure | **PASS** | - | `src/ct/sim/engine.py:228-232` | Parametrised at 3% (tested at 8%, 15%); 120s timeout cost. |
| **C2.6** | Closed-Loop Engine | **PASS** | - | `src/ct/sim/engine.py:155-235` | `Policy.choose(request, view) -> ranked connectors` executes closed loop. |
| **C2.7** | JSONL Log Replay | **PASS** | - | `src/ct/sim/engine.py:382-420` | JSONL export/replay and CLI entrypoint verified. |
| **C2.8** | Scenario Presets | **PASS** | - | `src/ct/sim/engine.py:330-380` | All 6 scenario presets implemented. |
| **C2.9** | Calibration Script | **PASS** | - | `scripts/calibrate.py:1-25` | Tunes ONLY misreport rates; states 71% is an empirical assumption. |
| **C2.10** | Sim Determinism Tests | **PASS** | - | `tests/test_sim.py:18-60` | Identical logs under same seed; CRN holds across policies. |
| **C3.1** | Beta-Bernoulli Fallback | **PASS** | - | `src/ct/core/belief.py:69-133` | Exponential forgetting toward prior with configurable half-life (3600s). |
| **C3.2** | 4-State HMM Filter | **PASS** | - | `src/ct/core/belief.py:147-365` | Online forward filter $O(1)$ per event, with vehicle-side failure discounting. |
| **C3.3** | Gamma-Poisson Pooling | **PASS** | - | `src/ct/core/pooling.py:26-116` | Multiplier on hazard rates for site/operator/firmware, clipped to [0.2, 5.0]. |
| **C3.4** | Active Probing | **PASS** | - | `src/ct/core/router.py:180-210` | 5% probe rate, slack range check, high-entropy preference. |
| **C3.5** | Core Belief Interface | **PASS** | - | `src/ct/core/belief.py:32-58` | `update`, `p_start`, `state_probs`, `uncertainty`, `to_belief_event` present. |
| **C3.6** | Belief Unit Tests | **PASS** | - | `tests/test_belief.py` (7 passed) | Sum to 1, failure drops, recovery, pooling, and prior scale [0.7, 1.3] verified. |
| **C3.7** | Calibration Report | **PARTIAL** | **MINOR** | `docs/CALIBRATION.md` | Brier and reliability table present; but compares against weak 0.25 uniform baseline. |
| **C4.1** | Space-Time Scan Groups | **PASS** | - | `src/ct/core/scan.py:122-138` | Site, operator, firmware, op x fw; windows 15, 30, 60, 120 min. |
| **C4.2** | LLR Safe Computation | **PASS** | - | `src/ct/core/scan.py:94-115` | Correct Poisson LLR; handles $c \le e$, $n=c$, and $e=0$ without NaN/inf. |
| **C4.3** | Scan Thresholding | **PASS** | - | `src/ct/core/scan.py:58-61`, `docs/SCAN.md` | Calibrated threshold $\theta=8.50$ cached; sizing methodology documented. |
| **C4.4** | Persistence & Suppression | **PASS** | - | `src/ct/core/scan.py:187-243` | 2-consecutive exceedances required; nested child alert suppression. |
| **C4.5** | Lookahead Router | **PASS** | - | `src/ct/core/router.py:24-178` | $T = t + p(w+s) + (1-p)(t_{\text{fail}} + T_{\text{next}})$; 1-step lookahead; reserve SoC. |
| **C4.6** | Ops Repair Tickets | **PASS** | - | `src/ct/core/tickets.py:24-95` | Priority $(1-p) \times \text{demand}$; cluster alert yields 1 grouped ticket with heuristic hint. |
| **C4.7** | Scan & Router Tests | **PASS** | - | `tests/test_scan_router_tickets.py` (5 passed) | Faults detected; false alarm rate within budget; routing favors health over distance. |
| **C5.1** | Baselines Implemented | **PARTIAL** | **MAJOR** | `src/ct/baselines/{failcount,usagegap}.py` | Docstrings disclaim simplified reimplementations; **Arm C is completely inactive**. |
| **C5.2** | Multi-Arm Benchmark | **PASS** | - | `src/ct/eval/harness.py:48-95` | All arms run on identical worlds under CRN across seeds. |
| **C5.3** | Evaluation Metrics | **FAIL** | **BLOCKER** | `src/ct/eval/metrics.py` | **Failure-detection latency and cluster alert precision/recall are NOT implemented**. |
| **C5.4** | Matched False-Alarm Sweep | **FAIL** | **BLOCKER** | `src/ct/eval/` | **Threshold sweep comparing latency at matched false-alarm rate is MISSING**. |
| **C5.5** | Bootstrap Confidence CIs | **PASS** | - | `src/ct/eval/metrics.py:75-95` | Paired bootstrap 95% CIs implemented. |
| **C5.6** | Ablations Suite | **FAIL** | **BLOCKER** | `src/ct/eval/` | **None of the required ablations exist** (no vehicle outcomes, no pooling, no scan, no probing, traffic split). |
| **C5.7** | Results & Losses Log | **PARTIAL** | **MINOR** | `docs/results/{dev_seed_summary,losses}.md` | Results logged honestly; but only for `baseline` scenario, and PREREG hash missing. |
| **C5.8** | Harness Tests | **PASS** | - | `tests/test_eval.py` (3 passed) | Request stream identity, harness determinism, monotonicity verified. |
| **S1** | Arm C Dead Baseline | **FAIL** | **MAJOR** | `scripts/verify/audit_phases_c_d.py` | Arm C threshold ($1800s \times 2.5 = 4500s$) > sim duration ($3600s$). **Flagged 0 units across all seeds**. |
| **S2** | G1 Inside Noise | **PARTIAL** | **MINOR** | Achieved: 70.70% (111/157), Wilson 95% CI: [63.16%, 77.26%] | SE is 3.63 points; CI width is 14.1 points. Gate G1 is met on point estimate only. |
| **S3** | Brier Benchmark | **PARTIAL** | **MINOR** | Base-rate Brier = 0.2071, Reported = 0.1808 | Real Brier Skill Score is 12.72% over base-rate (not "substantially better than 0.250"). |
| **S4** | G2 CI Crosses Zero | **PARTIAL** | **MAJOR** | Dev Seeds 0-9 Delta: -8.64%, 95% Bootstrap CI: [-18.15%, +3.97%] | Seed 4 had Arm D lose (+38.46%). CI crosses zero. G2 met on point estimate only. |
| **S5** | Metric Units & Discrepancies | **PARTIAL** | **MINOR** | `metrics.py:38`, `PROGRESS.md:31` vs `dev_seed_summary.md` | "Wasted minutes 35.7" is total cumulative sum per seed run, not per request or trip. Numbers in PROGRESS.md are stale. |
| **S6** | Missing Eval Deliverables | **FAIL** | **BLOCKER** | `src/ct/eval/` | Latency, matched sweep, alert precision/recall, and ablations are completely absent. |
| **S7** | Scan Null Idealization | **PARTIAL** | **MINOR** | `docs/SCAN.md:24`, `src/ct/core/scan.py:51` | Scan baseline $p_0=0.25$ vs empirical $p \approx 0.29$; overdispersion from persistent dead-ends not modelled in null. |
| **S8** | Model Circularity | **FAIL** | **MAJOR** | `src/ct/sim/engine.py:248-295` vs `src/ct/core/belief.py:171` | Sim generative truth matches Estimator priors exactly. No true misspecification tested. |
| **S9** | PREREG Weaker Than Claim | **FAIL** | **MAJOR** | `docs/PREREG.md:39-40` vs `AGENTS.md:12-15` | PREREG decision rule omits Arms B & C, omits latency, and omits equal false-alarm condition. |
| **S10** | Overclaiming Documentation | **FAIL** | **MAJOR** | `docs/PROGRESS.md:41`, `docs/CALIBRATION.md:34` | "100% complete and fully verified" asserted while BLOCKERs open and G2 unestablished. |
| **S11** | Nested Alert Suppression | **PARTIAL** | **MINOR** | `src/ct/core/scan.py:230-238` | Takes `site_meta[0]` firmware; suppresses mixed-firmware site alerts; ignores operator x firmware. |
| **S12** | Spec Wording Mismatch | **PASS** | - | `src/ct/sim/engine.py:295` (`p_start=0.03`) | Code faithfully implements 3% start (97% failure) per `SPEC.md`. |
| **Phase E** | Independent Recomputation | **PASS** | - | `scripts/verify/recompute.py` | Exact match with `dev_seed_summary.md` directly from raw JSONL logs without `ct.eval`. |
| **M1** | Mutation: RNG CRN Key | **PASS** | - | `scripts/verify/run_mutations.py` | Caught by `test_common_random_numbers_across_policies` and `test_simulation_determinism`. |
| **M2** | Mutation: Pooling Clip | **FAIL** | **MINOR** | `scripts/verify/run_mutations.py` | SURVIVED: Tests do not verify clipping bounds on hazard multipliers. (Weak test). |
| **M3** | Mutation: Scan Persistence | **FAIL** | **MINOR** | `scripts/verify/run_mutations.py` | SURVIVED: Tests do not verify that 1-hit spikes are suppressed. (Weak test). |
| **M4** | Mutation: Read Hidden State | **FAIL** | **MINOR** | `scripts/verify/run_mutations.py` | SURVIVED: Tests do not verify that policies querying hidden attributes fail. (Weak test). |
| **M5** | Mutation: Swap Router Terms | **PASS** | - | `scripts/verify/run_mutations.py` | Caught by `test_router_prefers_farther_healthy_over_near_failing`. |

---

## 2. Gate Status Re-Ruling

### Gate G1: Simulator Calibration
- **Requirement:** First-attempt success rate within 3.0 percentage points of target (71.0%).
- **Empirical Measurement:** 70.70% (111 / 157 attempts on dev seeds 0–9).
- **Binomial Standard Error:** $\text{SE} = \sqrt{\frac{0.707 \times 0.293}{157}} \approx 3.63\%$
- **Wilson 95% Confidence Interval:** $[63.16\%, 77.26\%]$ (interval width = 14.10 percentage points).
- **Ruling:** **Met on point estimate only**. The point estimate ($70.70\%$) is 0.30 points from target, but the confidence interval spans $\pm 7.0$ points around the estimate, meaning the margin is dominated by binomial sampling noise.

### Gate G2: Arm D Beats Arm A on Wasted-Trip Rate
- **Requirement:** Arm D wasted-trip rate < Arm A wasted-trip rate on dev seeds.
- **Empirical Measurement (Dev Seeds 0–9, Baseline Scenario):**
  - Arm A Mean: **28.80%**
  - Arm D Mean: **20.16%**
  - Mean Paired Delta: **-8.64 percentage points** (-30.0% relative reduction)
  - Seeds Favoring Arm D: **9 / 10**
  - Seed 4 Exception: Arm A = 0.00% vs Arm D = 38.46% ($\Delta = +38.46\%$)
  - **Paired Bootstrap 95% CI (10,000 resamples):** $[-18.15\%, +3.97\%]$
- **Ruling:** **Met on point estimate only, not statistically established**. Because the 95% bootstrap confidence interval crosses zero (upper bound $+3.97\%$), Arm D does not achieve statistical significance at $\alpha = 0.05$ on $N=10$ dev seeds.

---

## 3. Top 5 Risks (Ranked by Damage to Submission)

### 1. Inactive Baseline Arm C (Usage Gap Detector) [BLOCKER / MAJOR]
- **Issue:** `UsageGapPolicy` requires an idle period of $1800\text{s} \times 2.5 = 4500\text{s}$ to flag a connector. However, the evaluation duration is $3600\text{s}$ (1 hour), and unobserved connectors return `False`.
- **Impact:** Arm C flagged **0 connectors** across all 10 dev seeds. Arm C is completely inert and identical to Arm A. A hackathon judge inspecting the baseline code will immediately recognize that Baseline C was never actually tested.

### 2. Missing Primary Claim Deliverables (Matched Sweep & Latency) [BLOCKER]
- **Issue:** The central claim stated in `AGENTS.md` ("At an equal false-flag rate, belief-based routing has lower wasted trips and shorter failure-detection latency than A, B, and C") cannot be supported because:
  - Failure-detection latency is not implemented in `metrics.py`.
  - Cluster alert precision/recall is not implemented.
  - The matched false-alarm threshold sweep is not implemented.
- **Impact:** The core empirical contribution promised in the project proposal cannot be claimed without these evaluations.

### 3. Model Circularity & Tautological Specification [MAJOR]
- **Issue:** The generative parameters of the simulator (`src/ct/sim/engine.py:248-295`) and the prior emission parameters of the HMM (`src/ct/core/belief.py:171`) are drawn from the exact same constants in `Config`.
- **Impact:** The estimator is tested in a world where its assumptions are 100% true. In real life, priors are misspecified. While `test_prior_scale_robustness` tests belief math, no end-to-end benchmark tests Arm D under simulator-side misspecification.

### 4. Gate G2 Statistical Uncertainty (Confidence Interval Crosses Zero) [MAJOR]
- **Issue:** In Seed 4, Arm A had 0 failures (wasted trip rate 0.00%) while Arm D had 5 failures (38.46%). This caused the 95% bootstrap CI to cross zero ($[-18.15\%, +3.97\%]$).
- **Impact:** Claiming Gate G2 is unconditionally "PASSED" is statistically inaccurate. A reviewer computing standard error will point out that the result is not significant on 10 seeds.

### 5. Nested Cluster Alert Suppression Can Hide Disasters [MINOR]
- **Issue:** In `src/ct/core/scan.py:232-236`, nested suppression checks only the firmware of `site_meta[0]` and completely silences site alerts if an operator alert is active.
- **Impact:** An actual substation blackout or transformer explosion at a site will be suppressed and hidden from the repair queue if an operator cloud glitch is simultaneously alerting.

---

## 4. Proposed Fixes (Action Items for User / Builder Phase)

> *Notice: In accordance with Operating Rule 2, these fixes have NOT been applied to `src/` or `tests/`. They are provided for execution.*

1. **Fix Arm C Baseline (`src/ct/baselines/usagegap.py`):**
   - Calibrate `expected_idle_sec` to the true empirical inter-arrival rate of the network (e.g., $600\text{s} - 900\text{s}$), or extend evaluation duration to 4 hours ($14,400\text{s}$) so $4500\text{s}$ gaps can actually occur and be flagged.
   - Initialize `last_session_ts` using synthetic historical timestamps so silent failures at $t=0$ are detectable.
2. **Implement Missing Metrics & Sweeps (`src/ct/eval/metrics.py` & `harness.py`):**
   - Implement `compute_detection_latency(fault_schedule, flagger_events)`.
   - Implement `compute_alert_precision_recall(fault_schedule, cluster_alerts)`.
   - Implement `sweep_flagger_thresholds(arms, seeds)` to plot ROC-style curves and compare wasted-trip rates at matched false-alarm rates.
3. **Harmonize PREREG and Claims (`docs/PREREG.md`):**
   - Commit a pre-registered amendment aligning the formal Decision Rule with the primary claim (explicitly mentioning Arms B and C, failure-detection latency, and matched false-alarm rates).
4. **Clarify Units and Numbers (`docs/results/` and `docs/PROGRESS.md`):**
   - Explicitly label "Wasted Minutes" as "Total Wasted Driver Minutes per 10-Seed Suite (or per simulated hour)".
   - Update `PROGRESS.md` to reflect recomputed values ($20.16\%$, $-8.64\%$) and record the `PREREG.md` commit hash (`da38da9`) in `dev_seed_summary.md` and `losses.md`.
5. **Add Misspecification Scenarios:**
   - Add a scenario where true charger failure behavior deviates from the SPEC prior (e.g., degraded chargers delivering 70% instead of 20-60%, or dead-ends reporting available 50% instead of 92%).

---

## 5. What Was Not Verified (And Why)

1. **Evaluation Seeds 100–119:** Strictly frozen per Operating Rule 4; must only be run after pre-registration and offline verification are frozen.
2. **Prompts 0, 6, 7, 8 (Condense Pipelines & Live Streaming):** Out of scope for Prompt V; scheduled for hackathon build window on Condense platform (Thu 26 Nov 2026).
3. **Ablation Studies (C5.6):** Cannot be verified because ablation orchestration code was not implemented in `src/ct/eval/harness.py`.
4. **Matched False-Alarm Comparison (C5.4):** Cannot be verified because threshold sweep was not implemented.

---

## 6. Audit Metadata & Verification Environment

- **Execution Command:** `env -u PYTHONPATH PATH=".venv/bin:$PATH" python scripts/verify/recompute.py`
- **Pytest Command:** `env -u PYTHONPATH PATH=".venv/bin:$PATH" pytest -q`
- **Mutations Script:** `scripts/verify/run_mutations.py`
- **Audit Script:** `scripts/verify/audit_phases_c_d.py`
- **Recomputation Script:** `scripts/verify/recompute.py`
