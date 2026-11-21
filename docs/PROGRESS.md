# Charger Truth: Development Progress Log

## Definition of Done Checklist (Every Step)
- [x] `pytest` passes; new behaviour has unit tests.
- [x] `docs/PROGRESS.md` updated: what changed, what is unverified, next step.
- [x] Short git commit.
- [x] No TODOs left silently.

---

## Log Entry: 2026-11-22 (Prompt 4 Complete)

### What Changed:
1. **Prospective Space-Time Cluster Scanner (`src/ct/core/scan.py`)**:
   - Implemented `KulldorffClusterScanner` monitoring rolling retrospective windows (15, 30, 60, 120 min) across `site`, `operator`, `firmware`, and `operator_x_firmware`.
   - Computes exact Log-Likelihood Ratio:
     $$\text{LLR} = c \ln(c/e) + (n-c) \ln((n-c)/(n-e))$$
     with edge-case protection ($c \le e$, $n = c$, $e = 0$).
   - Enforces persistence requirement (alert triggered only after exceeding threshold for 2 consecutive 1-minute evaluations).
   - Suppresses nested alerts (site alerts suppressed when parent operator or firmware alert is active; fleet alerts require failure spread across $\ge 2$ distinct sites).
   - Calibrated null threshold ($\theta = 8.50$) sized to 1 false alarm per simulated week. Documented methodology in `docs/SCAN.md`.
2. **Expected Trip-Time Router (`src/ct/core/router.py`)**:
   - Implemented `ExpectedTimeRouter(Policy)` ranking connectors by:
     $$T = t + p(w + s) + (1 - p)(t_{\text{fail}} + T_{\text{next}})$$
   - Features 1-step lookahead recursion evaluating $T_{\text{next}}$ across next candidate connectors.
   - Respects vehicle battery range with reserve SoC (rejects connectors beyond safe energy reach).
   - Produces structured `RouteDecisionEvent` with plain human-readable reasoning strings and penalizes connectors with active cluster alerts.
3. **Demand-Weighted Repair Queue (`src/ct/core/tickets.py`)**:
   - Implemented `TicketManager` ranking repair priority by:
     $$\text{priority} = (1 - p) \times \text{local\_demand\_rate}$$
   - Grouped ticketing: produces **ONE** grouped `OpsTicketEvent` upon a `ClusterAlertEvent` with heuristic first-check hints (labeled explicitly as heuristics).
4. **Verification & Tests (`tests/test_scan_router_tickets.py`)**:
   - Verified cluster detection for injected site outage, operator backend outage, and firmware bug.
   - Verified nested alert suppression (site alert suppressed inside operator alert).
   - Verified null false-alarm budget on 50 evaluations.
   - Verified router selects a slightly farther healthy connector over a near failing connector ($p=0.20$).
   - Verified repair ticket ranking changes with demand rate (high-demand site prioritized over low-demand site).
   - Total test suite: 32 passed.

### Needs Decision / Parameter Values:
- None.

### What is Unverified:
- Baselines A/B/C/D comparison across seeds and matched false-alarm sweeps (Prompt 5).

### Next Step:
- Execute **Prompt 5**: Implement `src/ct/baselines/failcount.py` (Arm B), `src/ct/baselines/usagegap.py` (Arm C), evaluation harness `src/ct/eval/harness.py`, metrics, paired bootstrap confidence intervals, and pre-registration document `docs/PREREG.md` (Gate G2).
