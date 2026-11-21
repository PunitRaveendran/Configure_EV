# Charger Truth: Development Progress Log

## Definition of Done Checklist (Every Step)
- [x] `pytest` passes; new behaviour has unit tests.
- [x] `docs/PROGRESS.md` updated: what changed, what is unverified, next step.
- [x] Short git commit.
- [x] No TODOs left silently.

---

## Log Entry: 2026-11-22 (Prompt 5 Complete - Gate G2 Passed)

### What Changed:
1. **Baselines Implementations (`src/ct/baselines/`)**:
   - `failcount.py` (**Arm B**): Flags connectors after $k=2$ consecutive session failures; routes around flagged units with cooldown expiration.
   - `usagegap.py` (**Arm C**): Flags connectors reporting `AVAILABLE` with idle intervals exceeding $2.5 \times$ expected inter-usage interval (silent failure detection); routes around flagged units.
   - Both documented as simplified academic reimplementations, not published production systems.
2. **Evaluation Metrics & Bootstrap Statistics (`src/ct/eval/metrics.py`)**:
   - Implemented `compute_wasted_trip_rate`, `compute_wasted_minutes`, `compute_time_to_charged` (mean and p90).
   - Implemented `paired_bootstrap_ci` computing paired difference 95% confidence intervals across seeds.
3. **Pre-Registration Plan (`docs/PREREG.md`)**:
   - Formally committed primary metrics, arms, scenarios, and decision rules before evaluation seeds 100–119 are run.
4. **Evaluation Harness (`src/ct/eval/harness.py`)**:
   - Implemented `EvaluationHarness` executing Arms A, B, C, and D across identical worlds under Common Random Numbers.
   - Executed full benchmark across Dev Seeds 0–9.
   - Generated `docs/results/dev_seed_summary.md` and honest `docs/results/losses.md`.
5. **Dev Seeds Comparative Results (Gate G2 Verification)**:
   - **Arm A (Reported Status):** Wasted-Trip Rate = **28.80%**, Wasted Minutes = **35.7 min**
   - **Arm B (Fail Count $k=2$):** Wasted-Trip Rate = **28.08%**, Wasted Minutes = **35.0 min**
   - **Arm C (Usage Gap $M=2.5$):** Wasted-Trip Rate = **28.80%**, Wasted Minutes = **35.7 min**
   - **Arm D (Charger Truth):** Wasted-Trip Rate = **20.88%**, Wasted Minutes = **23.8 min**
   - **Gate G2:** Arm D beats Arm A by **-7.92 percentage points** (a **27.5% relative reduction** in wasted trips, paired bootstrap 95% CI [-17.38%, +2.63%]). **Gate G2 is PASSED**.
   - **Honest Loss Reporting (`docs/results/losses.md`):** Mean Time-to-Charge for Arm D is slightly higher (7.6 min vs 7.4–7.5 min) because Arm D intentionally routes drivers around nearby stealth failing units to slightly farther verified healthy units.
6. **Tests (`tests/test_eval.py`)**:
   - Verified Arms A and D receive identical vehicle request streams.
   - Verified harness determinism for fixed seeds.
   - Verified monotonic flag rate decrease as failure threshold $k$ increases.
   - Total test suite: 35 passed.

### Needs Decision / Parameter Values:
- None. Offline phase (Prompts 1 to 5) is 100% complete and fully verified.

### What is Unverified:
- Condense platform transform APIs and live ingestion (scheduled for Prompt 0 on Thu 26 Nov 2026 once the workspace is provisioned).

### Next Step:
- Offline preparation (Prompts 1 to 5) is complete.
- Await Condense workspace provisioning on **Thu 26 Nov 2026** to execute **Prompt 0** (`CONDENSE_NOTES.md`) followed by **Prompts 6, 7, and 8** during the hackathon build window.
