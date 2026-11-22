# Charger Truth: Verification Spec (`docs/VERIFY_SPEC.md`)

> All data is SIMULATED. This is an independent audit of the offline phase (Prompts 1 to 5). It adds no features.

## 0. Purpose and scope
Check that the code matches `AGENTS.md`, `docs/SPEC.md`, `docs/PREREG.md`, `docs/SCAN.md` and the Prompt 1-5 requirements, and that every claim in `PROGRESS.md`, `CALIBRATION.md` and `docs/results/` is supported by evidence you reproduce yourself.

- **In scope:** `src/ct/{schemas,config}.py`, `src/ct/sim`, `src/ct/core`, `src/ct/baselines`, `src/ct/eval`, `tests/`, `docs/`.
- **Out of scope (not built yet):** `src/ct/pipeline`, `web/`, Condense (Prompts 0, 6, 7, 8; Gates G3 to G6). `CONDENSE_NOTES.md` being a placeholder is expected, not a failure.

## 1. Operating rules (read before every session)
1. **Read-only on `src/` and `tests/`.** You may write only to `docs/verification/` and scratch scripts in `scripts/verify/`.
2. **Do not fix anything.** Report it. Fixes go in a separate "Proposed fixes" list and wait for the user.
3. **Never tune the simulator or any parameter to change a result.** Any run with changed parameters is labelled `EXPLORATORY` and is never used as the verdict.
4. **Do NOT run evaluation seeds 100-119.** Only check whether they were already run (see H9).
5. **PASS needs evidence:** a command plus an output excerpt, or `file:line`. A statement in a doc is never evidence.
6. Never invent numbers. If you cannot determine something, write `unknown`.
7. Status values: `PASS`, `FAIL`, `PARTIAL`, `MISSING`, `UNVERIFIABLE`. Severity for non-PASS: `BLOCKER`, `MAJOR`, `MINOR`.
8. **Checkpoint:** after finishing each phase, append results to `docs/verification/report.md` and update `docs/verification/state.md` (phase done, next item). If you lose context, re-read `state.md` and continue.
9. One phase per step. Do not skip ahead. Keep command output short (`| tail`, `| head`).
10. Commit only `docs/verification/` and `scripts/verify/`.

## 2. Phase A: baseline
```bash
git status --short
git log --date=iso --format='%h %ad %s' | head -30
pytest -q 2>&1 | tail -15
pytest --collect-only -q | tail -3
make lint        # if the target exists
```
| ID | Check | Expected |
|---|---|---|
| A1 | Clean install per `pyproject.toml`, Python >= 3.11 | works |
| A2 | `pytest -q` | all pass; `PROGRESS.md` claims 35 passed. Record the real number |
| A3 | Work tree clean, results files match what is committed | yes |

## 3. Phase B: hard-rule audits (from AGENTS.md)
| ID | Rule | How to check | Pass condition |
|---|---|---|---|
| H1 | Core has no Kafka/Condense imports | `grep -rniE "kafka\|confluent\|condense\|redpanda" src/ct/core` | no matches |
| H2 | Sim never imports core | `grep -rnE "ct\.core\|from ct import core" src/ct/sim` | no matches |
| H3 | Policies cannot see hidden state | Read the `view` object passed to `Policy.choose`. `grep -rniE "true_state\|hidden\|latent" src/ct/core src/ct/baselines` | no hidden-state fields reachable; a test exists that proves it |
| H4 | Common random numbers keyed by `(seed, vehicle_id, attempt_no)` | Find the RNG construction in `src/ct/sim/engine.py` | key is exactly that tuple; nothing policy-dependent in the key |
| H5 | Connector failures, fault injection times and arrivals do not depend on the policy | Run arms A and D on one seed; diff request streams and fault timelines | identical |
| H6 | No secrets, synthetic pseudonymous IDs | `grep -rniE "(api[_-]?key\|secret\|password\|token)\s*=" .` | no matches |
| H7 | No magic numbers outside `config.py` | Grep numeric literals in `src/ct/{sim,core,baselines,eval}`; list any that look like tunables (rates, thresholds, half-lives, windows) | none, or each justified |
| H8 | "SIMULATED" stated in docs and in script headers | grep | present |
| H9 | Eval seeds 100-119 not run before `PREREG.md` was committed | `git log --date=iso --format='%h %ad %s' -- docs/PREREG.md docs/results/`; grep results for seeds >= 100 | PREREG commit predates any result touching seeds 100-119; if no eval results exist yet, PASS |
| H10 | Results files record the PREREG commit hash | open each file in `docs/results/` | hash present in every file |

## 4. Phase C: requirement checklist per prompt
For each row: locate the code (`file:line`), then confirm by running or by a test. Mark status.

### Prompt 1: schemas, config
| ID | Requirement |
|---|---|
| C1.1 | Pydantic v2 models for all 7 topics: `charger.status`, `vehicle.session`, `vehicle.request`, `connector.belief`, `cluster.alert`, `route.decision`, `ops.ticket`, with topic-name constants |
| C1.2 | Field names match the `SPEC.md` topics table exactly; `event_ts` is int UTC ms; stable partition key per topic |
| C1.3 | Outcome enum is STARTED/FAILED/TIMEOUT; `delivered_kw`, `rated_kw` present |
| C1.4 | `to_json`/`from_json` round-trips for every event type |
| C1.5 | `Config` is a frozen dataclass holding every parameter in `SPEC.md` section 3; YAML override works; `prior_scale` applies |
| C1.6 | Parameters missing from the spec are `None` and listed as "needs decision" (not invented) |
| C1.7 | Makefile has `test`, `lint`, `sim`, `eval` and they run |

### Prompt 2: simulator
| ID | Requirement |
|---|---|
| C2.1 | ~200 connectors, 60 sites, 4 operators, 5 hardware models, 3 firmware versions; Chennai bbox; labelled synthetic |
| C2.2 | Dead-end: P(start)=0.03 per SPEC, reports AVAILABLE ~90%; Degraded delivers 20-60% of rated; Offline mostly silent. Record the values the sim actually uses |
| C2.3 | Correlated faults exist and start at the right time: site outage, operator outage (~30% of that operator's connectors), firmware bug |
| C2.4 | Poisson arrivals with evening peak; queues/wait; travel times on a graph |
| C2.5 | Vehicle-side failure rate parametrised (3%, tested at 8% and 15%); 120 s failed-start cost |
| C2.6 | `Policy.choose(request, view) -> ranked connectors`; closed loop runs |
| C2.7 | JSONL writer and replayer; replay of a log reproduces the run; `acceleration` factor exists |
| C2.8 | 6 scenario presets: baseline, site_outage, operator_outage, firmware_bug, slow_degradation, vehicle_side_heavy |
| C2.9 | `scripts/calibrate.py` tunes ONLY misreport rates; header says the 71% target is an assumption; reports the achieved value |
| C2.10 | Tests: same seed gives identical logs; CRN across two policies; each fault changes the right connectors; policies cannot read hidden state |

### Prompt 3: belief, pooling, probing
| ID | Requirement |
|---|---|
| C3.1 | Beta-Bernoulli fallback exists with exponential forgetting toward the prior (half-life 3600 s from Config) |
| C3.2 | 4-state HMM forward filter, O(1) per event, includes a vehicle-side-failure term |
| C3.3 | Gamma-Poisson pooling over site/operator/firmware, clipped to [0.2, 5.0] |
| C3.4 | Probing: ~5% of requests, only vehicles with slack, prefers high entropy |
| C3.5 | Interface: `update`, `p_start`, `state_probs`, `uncertainty`, `probe_candidates` |
| C3.6 | Behaviour tests: probs sum to 1; p_start falls after consecutive failures and recovers; one failure does not mark Dead-end; forgetting moves toward prior; sibling failures raise suspicion; stable at `prior_scale` 0.7 and 1.3 |
| C3.7 | `docs/CALIBRATION.md` has Brier + reliability table and states where calibration is poor |

### Prompt 4: scan, router, tickets
| ID | Requirement |
|---|---|
| C4.1 | Scan groups: site, operator, firmware, operator x firmware; windows 15/30/60/120; evaluated every simulated minute |
| C4.2 | LLR matches `SCAN.md` formula; `c <= e` gives 0; `n == c` and `e == 0` handled without NaN/inf |
| C4.3 | Threshold from Monte Carlo null sized to the false-alarm budget, cached, method written down |
| C4.4 | Alert only after 2 consecutive exceedances; nested suppression works; alert has group_key, window, LLR, members |
| C4.5 | Router: `T = t + p(w+s) + (1-p)(t_fail + T_next)`, T_next = best of next 3 candidates; respects reserve SoC; low-evidence connectors shown as unknown, not healthy; each decision has a plain reason string |
| C4.6 | Tickets: priority `(1-p) x demand`; a cluster alert makes ONE grouped ticket; hint is labelled heuristic |
| C4.7 | Tests: site outage, operator outage, firmware bug each detected; 50 null runs within budget; nested suppression; router prefers farther healthy over near p=0.2; ticket order changes with demand |

### Prompt 5: baselines, harness
| ID | Requirement |
|---|---|
| C5.1 | Arms A (reported), B (failcount k=2), C (usagegap 2.5x), D (belief+router+scan); B and C docstrings say "simplified reimplementation" |
| C5.2 | All arms run on identical worlds across scenarios and seeds |
| C5.3 | Metrics: wasted-trip rate, wasted minutes, time-to-charged mean/p90, **failure-detection latency**, **cluster alert precision and recall**, Brier and reliability |
| C5.4 | **Matched false-alarm sweep**: each flagger's threshold swept, latency compared at the same false-flag rate |
| C5.5 | Paired bootstrap 95% CIs across seeds |
| C5.6 | **Ablations**: no vehicle outcomes, no pooling, no scan, no probing, prior_scale 0.7/1.3, vehicle failure 3/8/15%, split by traffic quantile |
| C5.7 | Tables and figures auto-generated into `docs/results/`; `losses.md` lists every metric where D does not beat the best baseline |
| C5.8 | Tests: identical request streams; sweep is monotone; harness deterministic |

## 5. Phase D: known suspects (investigate each; these came from reading the docs)
For every item: reproduce, give evidence, then rule on it.

| ID | What looks off | What to do |
|---|---|---|
| S1 | **Arm A and Arm C are identical** in `PROGRESS.md`: 28.80% wasted trips and 35.7 min for both. Arm C may never flag anything, or its flags never change routing | Log how many connectors Arm C flags per seed and when. If zero or irrelevant, mark MAJOR: Arm C is not a working baseline |
| S2 | **G1 passes inside the noise.** 70.70% = 111/157 attempts. Binomial SE at p=0.71, n=157 is about 3.6 points, larger than the 3-point gate, so a 0.30-point delta carries no information | Report the real N and a Wilson 95% CI for the achieved rate. State whether G1 is demonstrated or only point-estimate-met. Also check whether the calibration N (157) differs from the harness N and why |
| S3 | **Brier baseline is weak.** 0.1808 is compared to 0.250 (a constant 0.5 forecast). The base-rate forecast scores about p(1-p) = 0.205 at p ~= 0.71, so skill is roughly 12%, not "substantially better" | Compute the base-rate Brier from the same predictions and the Brier skill score. Also recheck the reliability table: bin successes add to 112 vs 111 implied by 70.70% (rounding or a bug?) |
| S4 | **G2 point estimate passes but the CI crosses zero**: -7.92 points, 95% CI [-17.38, +2.63]. Wording says "PASSED" with no caveat | Recompute per-seed paired differences: how many of 10 seeds favour D? Per-scenario breakdown? Rule: G2 is "met on point estimate, not statistically established". Propose wording |
| S5 | **Counts and units.** 28.80%, 28.08%, 20.88% are consistent with N=1250 requests (125 per seed), but calibration used 157 first-attempt predictions. "Wasted minutes 35.7" cannot be per request when mean time-to-charged is about 7.5 min | Read `metrics.py`: state N and the exact definition and unit of each metric (per request, per wasted trip, per seed?). Flag any metric whose unit is undocumented |
| S6 | **Prompt 5 deliverables missing from PROGRESS.** It reports only wasted trips, wasted minutes and time-to-charged. Nothing on detection latency, alert precision/recall, matched false-alarm sweep, ablations, per-scenario results. The primary claim depends on latency and the equal-false-alarm comparison | Check each in C5.3-C5.6. Mark MISSING where absent. This blocks the claim in AGENTS.md, which is stated at equal false-flag rate |
| S7 | **Scan null is idealised.** `SCAN.md` simulates independent failures at p0 = 0.22. The sim's real attempt failure rate under Arm A is about 29%, and dead-ends are concentrated in some connectors, so failures are overdispersed. Real false alarms may exceed the budget. Also, a 1-in-10,080 quantile needs on the order of 1e5 or more null draws to be stable | Report the number of null draws behind theta = 8.50. Run the scanner over `baseline` scenario logs with NO injected correlated fault (dev seeds 0-9) and count alerts per simulated week against the budget of 1. Report precision/recall per injected fault and detection delay |
| S8 | **Possible circularity.** SPEC priors (0.97/0.90/0.03/0.00; 0.95/0.95/0.90/0.15) look identical to the simulator's truth, so the estimator is tested under a perfectly specified model. Calibrated `p_avail_deadend = 0.92` is only slightly off | Diff the sim's true emission parameters against the estimator priors. Check whether any test misspecifies the SIMULATOR (not only `prior_scale`). If not, mark MAJOR as a limitation to disclose |
| S9 | **PREREG decision rule is weaker than the claim.** Rule only requires D to beat A on wasted trips. The claim says A, B and C, on wasted trips and detection latency, at equal false-alarm rate | Compare the two texts and list gaps. Do NOT edit `PREREG.md`. Recommend a dated, committed amendment BEFORE any eval seed runs |
| S10 | **Overclaiming language.** "Offline phase is 100% complete and fully verified" while S1-S9 are open. `CALIBRATION.md` says gaps "demonstrate why active probing and group pooling are critical", which is untested explanation | List every claim in docs not backed by a reproduced result |
| S11 | **Nested suppression can hide real faults.** A site alert inside an active operator alert is suppressed, and a firmware alert suppresses site alerts "running that firmware" though a site can mix firmware versions. Operator x firmware is not covered | Construct a case: operator outage plus an unrelated site outage at one site. Is the site outage ever surfaced? Document behaviour (MINOR unless it hides faults) |
| S12 | **Spec wording mismatch.** `SPEC.md` says dead-end "fails 97% of the time"; Prompt 2 says "never starts a session" | Record what the sim does (should be 3% start) |

## 6. Phase E: independent recomputation (no trust in the harness)
Write `scripts/verify/recompute.py`. It must NOT import `src/ct/eval`.
1. Run arms A and D on dev seeds 0-9 via the sim's own entry point, saving JSONL logs.
2. From the raw logs only, recompute wasted-trip rate and mean wasted minutes per arm, using the definitions you extracted in S5.
3. Compare with `docs/results/dev_seed_summary.md`. Tolerance: exact for rates on the same logs. Any mismatch is a BLOCKER.
4. Run twice and compare file hashes to confirm determinism.
5. Recompute the paired bootstrap CI (resample seeds, 10,000 draws, fixed numpy seed). Compare with the reported CI.

## 7. Phase F: mutation spot checks (does the test suite catch breakage?)
Work in a throwaway branch `verify/mutations`; never commit mutations; `git checkout -- .` after each.
| ID | Mutation | Test suite should |
|---|---|---|
| M1 | Add `policy_id` to the RNG key in the engine | fail the CRN test |
| M2 | Change pooling clip to [0.0, 100.0] | fail or at least flag |
| M3 | Remove persistence (alert on 1 exceedance) | fail the scan test |
| M4 | Make Arm D read a hidden-state field | fail the hidden-state test |
| M5 | Swap the router `p` and `1-p` terms | fail the router test |
If a mutation survives (all tests still pass), mark that area `PARTIAL: weak test`.

## 8. Report format
Write `docs/verification/report.md`:
1. **Verdict table** (one row per ID: Status | Severity | Evidence | Note).
2. **Gate status**: G1 and G2 re-ruled with evidence (see S2 and S4). State plainly: "met", "met on point estimate only", or "not met".
3. **Top 5 risks**, most damaging first.
4. **Proposed fixes** (do not apply).
5. **Not verified, and why.**

Verdict rules: any open BLOCKER means "offline phase NOT verified". Never write "fully verified". End the report with the date, the commit hash audited, and the exact commands run.

## 9. Later (add after Prompt 6 and onward)
Not part of this audit. When the pipeline exists, extend this spec with: transform wrappers match direct core calls on the same event sequence; key/partition correctness; late events logged not crashing (60 s); producer-kill decay; Gates G3 to G6.
