# Charger Truth: agent context

## Goal
Build Charger Truth for the Configure 2026 mobility hackathon (Condense x Bosch MPS).
It estimates, per EV charger connector, the hidden state (Healthy / Degraded / Dead-end / Offline) from two streams:
(1) charger status heartbeats (often wrong), and
(2) vehicle-side session outcomes (attempt, started/failed/timeout, time-to-current, delivered vs rated power).

Output: P(next session starts) per connector, success-weighted routing, a ranked repair queue, and a space-time scan for correlated failures by site / operator / firmware.

## The claim we test (do not overclaim)
At an equal false-flag rate, belief-based routing has a lower wasted-trip rate and shorter failure-detection latency than:
A) routing on reported status,
B) a failure-count rule,
C) a usage-gap detector.

All data is SIMULATED. Say so everywhere. The problem itself has prior art; we claim only: streaming, vehicle-side evidence independent of charger firmware, group pooling + cluster scan, closed loop into routing, honest baselines.

## Schedule

| When | What |
|---|---|
| Sun 22 to Wed 25 Nov | Prompts 1 to 5 offline (schemas, simulator, estimator, scan and router, baselines and harness) |
| Thu 26 Nov | Team leader registers; open the Condense workspace, run the sample pipeline, then Prompt 0 |
| Fri 27 Nov, 9:30 PM IST | Kickoff; re-read the rules for anything that changes Gate 4 |
| Sat 28 Nov 12:00 AM to Sun 29 Nov 11:59 PM IST | Prompts 6, 7, 8; submit via the leader's Google Form |

## Hard rules
1. Ingestion, processing, transformation and routing stages must run on Condense. Frontend, dashboards and any AI may use any stack.
2. Core logic is pure Python in `src/ct/core` with NO Kafka or Condense imports. Condense adapters live only in `src/ct/pipeline`.
3. The simulator (`src/ct/sim`) is independent: it never imports `src/ct/core`. It exposes only observable events to policies, never hidden state.
4. Common random numbers: per-attempt RNG keyed by `(seed, vehicle_id, attempt_no)` so every arm faces identical worlds.
5. Synthetic data only. Pseudonymous IDs. No secrets or keys in the repo.
6. Every tunable lives in `src/ct/config.py`. No magic numbers elsewhere.
7. Dev seeds 0-9. Evaluation seeds 100-119, frozen after `docs/PREREG.md` is committed.
8. Never invent numbers, citations or results. If unknown, write "unknown".
9. Never invent Condense APIs. Read `CONDENSE_NOTES.md`; if it does not answer, stop and ask the user.
10. If our method loses on a metric, report it. Never tune the simulator to favour it.

## Stack
- Python 3.11+, numpy, pydantic v2, pytest, pandas, matplotlib, pyyaml.
- Backend: FastAPI + WebSocket.
- Frontend: React + Vite + MapLibre GL.

## Layout
```
charger-truth/
  AGENTS.md CONDENSE_NOTES.md pyproject.toml Makefile
  src/ct/schemas.py config.py
  src/ct/sim/{network,failures,demand,engine}.py
  src/ct/core/{belief,pooling,scan,router,tickets}.py
  src/ct/baselines/{reported,failcount,usagegap}.py
  src/ct/eval/{harness,metrics,report}.py
  src/ct/pipeline/{producers,transforms,consumers}.py
  web/ tests/ docs/
```

## Definition of done (every task)
- pytest passes; new behaviour has tests.
- `docs/PROGRESS.md` updated: what changed, what is unverified, next step.
- Short git commit.
- No TODOs left silently; list them in `PROGRESS.md`.


## Verification mode (applies when the task says "verify" or "audit")
Read `docs/VERIFY_SPEC.md` first and follow it exactly. In this mode:
- You are an auditor, not a builder. `src/` and `tests/` are READ-ONLY. Do not fix; report and propose.
- Writes are allowed only in `docs/verification/` and `scripts/verify/`. Commit only those.
- Never run evaluation seeds 100-119. Never tune the simulator or any parameter to change a result; label any such run EXPLORATORY.
- PASS requires evidence you produced (command + output, or file:line). A doc statement is not evidence.
- If a number or fact is unknown, write "unknown". Never write "fully verified" while any BLOCKER is open.
- Work one phase at a time; after each, update `docs/verification/report.md` and `docs/verification/state.md`.
- Where this section conflicts with "Definition of done" (e.g. new tests, PROGRESS.md updates), this section wins for verification tasks.

---

# Build Prompts & Instructions

## How to use these prompts
Run Prompts 1 to 5 now, because they are pure Python and need no Condense access; Prompts 0 and 6 wait for the Condense workspace; 7 and 8 happen inside the build window. These prompts are untested, and nothing here knows Condense's real transform API yet, so Prompt 0 exists to find that out before any adapter code is written.

1. Save the Master context as `AGENTS.md` (or `CLAUDE.md`) in the repo root so every session reads it.
2. Export the spec doc to `docs/SPEC.md` so the agent can read the topics, parameters and evaluation plan.
3. One prompt per agent session. Paste it, let the agent work, review the diff, run the tests yourself.
4. End every session with tests passing, `docs/PROGRESS.md` updated, and a git commit. If a session cannot do that, stop and fix before the next prompt.
5. Never let the agent tune the simulator to make your method win. If your method loses, that is a result to report.

**Assumption to confirm**: Organizer allowance for pre-built simulator and estimator code. Save organizer reply in `docs/ORGANIZER_REPLY.md`, disclose pre-existing work in `README.md`, and build Condense pipeline, adapters and UI inside the window.

---

### Prompt 0: Condense recon (after registration)
Run this once the workspace exists and the starter-kit sample pipeline has run. It turns unknowns into a written list before any adapter is built. If the agent cannot reach Condense docs, paste the relevant pages to it.

```text
Read AGENTS.md. Task: produce CONDENSE_NOTES.md. Write code only if I ask.

Answer each question below from Condense documentation or from the sample pipeline I give you. Cite the doc page or file for every answer. If you cannot find it, write "unknown". Do not guess.

1. Which languages or tools can a Condense transform use?
2. Can a transform keep per-key state (keyed by connector_id)? How is it stored, and does it survive redeploys?
3. How are topics created, and how are partitions and message keys set?
4. How do external programs produce to and consume from Condense topics? Which auth is used? Where do credentials come from?
5. Throughput or rate limits on the shared cluster.
6. Windowing and event-time support. How is late data handled?
7. Can one transform read two topics and join them?
8. How is a pipeline deployed and redeployed? How are logs and metrics viewed?
9. Formats and fields of the starter-kit sample telemetry.

Then write:
- the 3 riskiest assumptions in our design, ranked, with how to test each in under 30 minutes;
- a proposed adapter interface (function signatures only) that lets src/ct/core be called from a Condense transform;
- which rung of this fallback ladder we must use:
  (a) stateful per-key transform reading both streams,
  (b) compacted topic as the state store,
  (c) both streams merged into one topic ct.events keyed by connector_id with a `kind` field, so one stateful transform sees everything,
  (d) sidecar state outside Condense (weakest; must be disclosed).

Stop after writing CONDENSE_NOTES.md and wait for me.
```

---

### Prompt 1: repo, schemas, config (start here)
Gives every later prompt a shared vocabulary. Export the spec doc to `docs/SPEC.md` before running it.

```text
Read AGENTS.md and docs/SPEC.md. Task: scaffold the repo.

1. Create the layout from AGENTS.md with empty modules and a pyproject.toml (Python 3.11+, numpy, pydantic>=2, pytest, pandas, matplotlib, pyyaml).
2. src/ct/schemas.py: pydantic v2 models for every event in the spec's topics table, with topic-name constants:
   charger.status, vehicle.session, vehicle.request, connector.belief, cluster.alert, route.decision, ops.ticket.
   Every event has event_ts (UTC, ms) and a stable key. Session outcome is an enum: STARTED, FAILED, TIMEOUT. Include delivered_kw and rated_kw on completed sessions. Add to_json / from_json helpers.
3. src/ct/config.py: a frozen dataclass Config holding EVERY parameter named in the spec (emission table, forgetting half-life, pooling clip, probe rate, scan windows 15/30/60/120 min, false-alarm budget, persistence = 2, simulator size and failure rates, target first-attempt success, seeds).
   Support YAML override and a prior_scale multiplier for misspecification tests.
   If the spec does not give a value, set it to None and list it in docs/PROGRESS.md as "needs decision". Do not invent one.
4. Makefile targets: test, lint, sim, eval.
5. Tests: schema round-trip, config YAML override, prior_scale applies.

Done = definition of done in AGENTS.md. Then stop.
```

---

### Prompt 2: the simulator
The simulator is the weakest point a judge will attack, so it is built independently of the estimator and calibrated to a stated target, not to your method's benefit.

```text
Read AGENTS.md and docs/SPEC.md. Task: build src/ct/sim.
It must NOT import src/ct/core.

World (all values from Config):
- ~200 connectors, 60 sites, 4 operators, 5 hardware models, 3 firmware versions.
  Place sites on a synthetic road graph inside a Chennai bounding box for map display only; label it synthetic.
- Hidden connector state: Healthy, Degraded (slow onset, delivers 20-60% of rated), Dead-end (reports Available ~90% of the time, never starts a session), Offline (mostly stops reporting).
- Correlated faults: site outage; operator backend outage hitting ~30% of that operator's connectors; firmware bug starting at a set time.
- Status reports can be wrong (misreport model per hidden state).
- Vehicles: Poisson arrivals with an evening peak, SoC and range with reserve, queues and wait times, travel times on the graph.
- ~3% of attempts fail for unrelated vehicle-side reasons (parametrised; also test 8% and 15%). A failed start costs ~2 min timeout.

Interface:
- class Policy: choose(request, view) -> ranked connectors. `view` contains only observable events (status heartbeats, past session outcomes, map), never hidden state.
- engine runs closed loop: policy decision -> attempt outcome -> new events.
- Common random numbers: each attempt's randomness is keyed by (seed, vehicle_id, attempt_no), so all policies face identical worlds.
- JSONL event log writer and replayer; an `acceleration` factor for live runs.
- Scenario presets: baseline, site_outage, operator_outage, firmware_bug, slow_degradation, vehicle_side_heavy.

Calibration script `scripts/calibrate.py`: with a reported-status policy, tune ONLY the misreport rates until first-attempt success is about 71% (the target comes from a US figure in the spec; it is an assumption, say so in the script header). Report the achieved value.

Tests: same seed gives identical logs; common random numbers hold across two different policies; each correlated fault actually changes the affected connectors at the right time; policies cannot read hidden state.

Done = definition of done. Then stop.
```

---

### Prompt 3: belief estimator, pooling, probing
The starting emission numbers are priors from the spec, not measurements. The agent builds the simple version first so you always have a working fallback.

```text
Read AGENTS.md and docs/SPEC.md. Task: build src/ct/core/belief.py and src/ct/core/pooling.py. Pure Python + numpy, no Kafka imports.

Step A (ship first): Beta-Bernoulli belief per connector for "session starts", with exponential forgetting toward the prior (half-life from Config, ~1 hour).
Step B: 4-state HMM online forward filter per connector, O(1) per event.
States: Healthy, Degraded, Dead-end, Offline.
Emissions (starting values, in Config, not measurements):
  P(start | state) = 0.97 / 0.90 / 0.03 / 0.00
  P(status heartbeat reports available | state) = 0.95 / 0.95 / 0.90 / 0.15
  delivered/rated power ratio: 0.9-1.0 for Healthy, 0.2-0.6 for Degraded
Include a vehicle-side-failure term so a few unrelated failures do not condemn a connector.
Forgetting: the belief decays toward the prior with the configured half-life.
Step C: group pooling. A Gamma-Poisson multiplier on hazard rates shared by site / operator / firmware groups, clipped to Config bounds, so a connector with little data borrows strength from its group without being swamped by it.
Step D: probing. Return a list of connectors worth probing: about 5% of requests, only for vehicles with slack range/time, preferring high-entropy connectors.

Interface (one class, shared by both steps):
  update(event) -> None
  p_start(connector_id, now) -> float
  state_probs(connector_id, now) -> dict
  uncertainty(connector_id, now) -> float # entropy
  probe_candidates(request, now) -> list
Support Config.prior_scale (+/-30% misspecification).

Tests: probabilities sum to 1; p_start falls after consecutive failures and recovers after successes; one failure alone does not mark Dead-end; forgetting moves a stale belief toward the prior; pooling raises suspicion for a connector when its siblings fail; behaviour is stable with prior_scale 0.7 and 1.3.

Calibration check on dev seeds 0-9 using sim logs: Brier score and a reliability table for p_start. Write results to docs/CALIBRATION.md, including where it is poorly calibrated. Do not tune the simulator.

Done = definition of done. Then stop.
```

---

### Prompt 4: cluster scan, router, repair queue
The scan threshold comes from a null simulation, so the false-alarm rate is a stated budget rather than a guess.

```text
Read AGENTS.md and docs/SPEC.md. Task: build src/ct/core/scan.py, router.py, tickets.py. Pure Python, no Kafka imports.

1. scan.py: prospective Kulldorff-style space-time scan.
   - Groups: site, operator, firmware, operator x firmware.
   - Windows: 15, 30, 60, 120 minutes. Evaluate every simulated minute.
   - For a group with n attempts in the window and c failures, expected e under the baseline failure rate, when c > e:
     LLR = c*ln(c/e) + (n-c)*ln((n-c)/(n-e))
     handle n == c and e == 0 safely.
   - Threshold: Monte Carlo of the max LLR under the null (no correlated fault) sized to a false-alarm budget in Config (default 1 per simulated week). Cache the threshold; write the method to docs/SCAN.md.
   - Alert only after the group exceeds the threshold on 2 consecutive evaluations. Suppress nested alerts (a site alert inside an operator alert).
   - Output a cluster.alert event with group_key, window, LLR, and the member connectors.
2. router.py: given a request and beliefs, rank connectors by expected time
   T = t + p*(w + s) + (1-p)*(t_fail + T_next)
   where t = travel, w = wait, s = charge time, p = P(start), t_fail = timeout cost, T_next = best follow-up among the next 3 candidates (one-step lookahead). Respect range with reserve SoC. Connectors with too little evidence show as unknown, not healthy. Each decision carries a plain reason string, for example "p=0.31 after 4 failures in 40 min; site alert active".
3. tickets.py: repair priority = (1 - p) * local demand rate. A cluster alert produces ONE grouped ticket with a heuristic first-check hint (for example "firmware X on operator Y: check backend/auth"). Label hints as heuristics.

Tests: an injected site outage, operator outage and firmware bug are each detected; on 50 null runs the false-alarm count stays within the budget; nested suppression works; router prefers a slightly farther healthy connector over a near connector with p=0.2; ticket order changes with demand.

Done = definition of done. Then stop.
```

---

### Prompt 5: baselines and evaluation harness
This is the prompt that decides whether the project has a result. Baselines B and C are simplified reimplementations of published-style ideas, and the README must say so.

```text
Read AGENTS.md and docs/SPEC.md. Task: build src/ct/baselines and src/ct/eval.

Arms (each is a Policy plus a failure flagger):
  A reported: rank by reported status, travel time only.
  B failcount: flag a connector after k consecutive failed sessions; route around flagged.
  C usagegap: flag a connector idle longer than a threshold relative to its expected usage; route around flagged.
  D belief: src/ct/core belief + router + scan.
B and C are simplified reimplementations, not the published systems. Document each in its module docstring.

Harness:
- Run every arm on identical worlds (common random numbers), across scenarios and seeds, in parallel. Dev seeds 0-9 now; evaluation seeds 100-119 only after docs/PREREG.md is committed.
- Metrics: wasted-trip rate, wasted minutes, time-to-charged mean and p90, failure-detection latency, cluster alert precision and recall, Brier and reliability for belief, pipeline latency is added later.
- Matched false-alarm comparison: sweep each flagger's threshold, then compare detection latency at the SAME false-flag rate.
- Paired bootstrap 95% confidence intervals across seeds.
- Ablations: no vehicle outcomes, no pooling, no scan, no probing, prior_scale 0.7 and 1.3, vehicle-side failure 3/8/15%, results split by connector traffic quantile.
- Auto-generate tables and figures into docs/results/, plus docs/results/losses.md listing every metric where D does not beat the best baseline.
- docs/PREREG.md: before the evaluation seeds are run, write the primary metrics, arms, scenarios, and the decision rule. Record its git commit hash in every results file.

Tests: arms receive identical request streams; matched-false-alarm sweep is monotone; harness is deterministic for a fixed seed.

Done = definition of done. Then stop and report the dev-seed results honestly, including any metric where D loses.
```

---

### Prompt V: verify the offline phase (run after Prompt 5, before Prompt 6)
Independent audit of Prompts 1 to 5. Use a fresh agent session. It must not fix anything.

```text
Read AGENTS.md (including "Verification mode") and docs/VERIFY_SPEC.md. Task: audit the offline phase.

1. Run Phase A to F in order. Do one phase at a time.
2. After each phase, append your results to docs/verification/report.md and update docs/verification/state.md.
3. Investigate every suspect S1 to S12 and give evidence for each.
4. Recompute the headline results from raw logs without importing src/ct/eval (Phase E).
5. Do not edit src/ or tests/. Do not run seeds 100-119. Do not tune anything.
6. Finish with the report format in section 8: verdict table, G1 and G2 re-ruled, top 5 risks, proposed fixes, not verified.

Stop after writing the report and wait for me. Do not apply fixes.
```

---

### Prompt 6: Condense pipeline adapters
Run this after Prompt 0 has produced `CONDENSE_NOTES.md`. It is the part the rules actually judge, so it is built inside the build window.

```text
Read AGENTS.md, CONDENSE_NOTES.md and docs/SPEC.md. Task: build src/ct/pipeline.
Use only Condense APIs documented in CONDENSE_NOTES.md. If something needed is "unknown", STOP and ask me. Do not invent an API.

1. producers.py: replay a simulator JSONL log (or run the simulator live with an acceleration factor) into charger.status, vehicle.session, vehicle.request. Keys: connector_id (vehicle_id for vehicle.request). Stamp ingest_ts.
2. transforms.py: thin wrappers that call src/ct/core and nothing else:
   - belief transform: events -> connector.belief (state per connector_id, using the fallback-ladder rung chosen in CONDENSE_NOTES.md);
   - repartition by group key -> scan -> cluster.alert;
   - route.decision from vehicle.request + beliefs;
   - ops.ticket from beliefs + alerts.
   Stamp emit_ts on every output. Allow ~60 s lateness; log, do not crash, on events later than that.
3. consumers.py: read outputs for the backend and compute pipeline latency (emit_ts - ingest_ts) p50 / p95.
4. scripts/kill_producer.sh: stop the producer mid-run and show that beliefs decay toward the prior rather than freezing or crashing.
5. Local Redpanda/Kafka via docker compose for development and CI only. Mark it in the README as not the submission pipeline.
6. docs/DEPLOY.md written from what actually worked, step by step.

Tests: transform wrappers produce the same beliefs as calling core directly on the same event sequence; late-event handling; key/partition correctness.

Done = definition of done. Then stop and report which fallback-ladder rung is in use.
```

---

### Prompt 7: backend and map UI
The demo's job is to let a judge see reported status and belief disagree, then watch the system catch a fault.

```text
Read AGENTS.md and docs/SPEC.md. Task: build the backend and web/ UI.

Backend (FastAPI + WebSocket):
- Consume connector.belief, cluster.alert, route.decision, ops.ticket and the latency metrics from Condense topics; push to the browser over WebSocket.
- Control endpoints: pick a scenario, inject a fault (site outage, operator outage, firmware bug), set acceleration, reset.
- A/B worlds: run arm A (reported) and arm D (belief) on IDENTICAL seeds side by side so the browser shows the same vehicles getting different outcomes.

Frontend (React + Vite + MapLibre GL):
- Map of connectors with TWO rings per site: outer = reported status, inner = belief. Never rely on colour alone; add shape or pattern.
- Counters: wasted trips and wasted minutes, A versus D, live.
- Alert feed for cluster alerts with the grouped ticket and the heuristic hint.
- Repair queue ranked by priority.
- Pipeline latency gauge (p50 / p95 from real timestamps).
- Connector detail: evidence timeline (heartbeats vs session outcomes) and the route-decision reason string.
- A permanent banner: "Simulated data".
- A development-only REPLAY mode, clearly labelled, for working when Condense is unavailable. It must never be shown during judging as if it were live.

Tests: websocket message schema; A/B worlds share the same request stream; the UI renders with an empty state and with a recorded fixture.

Done = definition of done. Then stop, with screenshots of the map in healthy, outage and recovered states.
```

---

### Prompt 8: hardening, demo and submission
Submission requirements such as repo visibility and video length were not readable from the rules PDF, so the checklist below marks them to confirm at kickoff.

```text
Read AGENTS.md, docs/SPEC.md, docs/PROGRESS.md and docs/results/. Task: harden and package.

1. Load test: raise event rate in steps and record the highest rate at which p95 latency stays under the target in Config. README may claim ONLY this measured number, with the date and setup.
2. Producer-kill test (scripts/kill_producer.sh): record the outcome.
3. README.md with: problem; the claim; architecture diagram; run steps; results tables embedded automatically from docs/results/; a Limitations section (simulated data, simplified baselines B and C, assumed 71% target, priors not measured); prior art (Caltrans/UC Davis silent-failure detection, a failed-charge scoring patent, TUM/BMW work, ChargerHelp taxonomy) stated plainly; a pre-existing-work disclosure that points to docs/ORGANIZER_REPLY.md; licences.
4. docs/DEMO.md: a 3-minute script: problem, show reported vs belief disagreeing, inject a firmware bug, watch the cluster alert and grouped ticket, show the A vs D counters, show the measured results and the losses, state the limits.
5. Fresh-clone smoke test: clone to a new directory, follow the README only, confirm it runs. Fix the README, not your memory.
6. docs/SUBMISSION.md checklist (items marked CONFIRM are unknown until the rules are re-read at kickoff):
   - Google Form submitted by the team leader
   - repo link and visibility (CONFIRM)
   - demo video and length limit (CONFIRM)
   - what artifacts the form requires (CONFIRM)
   - team members and roles listed
7. A short post draft for the event Discord/social channel. No claims beyond what the results support.

Done = definition of done. Then stop and list anything unverified.
```

---

## Gates and Cut Order
Stop and rethink at any gate that fails; do not push on and hope.

| Gate | Pass condition | If it fails |
|---|---|---|
| **G1** | Simulator calibrated within 3 points of the target and the harness runs end to end | Fix the simulator or harness before touching the estimator |
| **G2** | Arm D beats arm A on wasted-trip rate on dev seeds | Debug the estimator; never tune the simulator to favour D. If it still loses, report that honestly and reframe |
| **G3** | Condense recon (Prompt 0) answers per-key state and multi-stream reads | Use the next rung of the fallback ladder and disclose it |
| **G4** | Rules re-read at kickoff show no conflict with pre-built code, public repo, video length | Adjust the disclosure and plan; ask organizers |
| **G5** | Events flow end to end through a Condense transform by about build hour 12 | Drop UI polish; fix the pipeline first |
| **G6** | Live demo flow works by about build hour 32 | Switch effort to README, results and demo script |

### Cut order if time runs out:
1. Probing first
2. Then ablations
3. Then cluster scan
4. Then HMM down to Beta-Bernoulli
*Never cut the baselines or the A/B comparison, because they are the evidence.*
