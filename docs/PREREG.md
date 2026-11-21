# Charger Truth: Pre-Registration Plan (`docs/PREREG.md`)

> **Notice:** All data is strictly **SIMULATED**.
> This pre-registration commits the experimental protocol, arms, scenarios, hypothesis, and decision rules before any evaluation seed (seeds 100–119) is run.

---

## 1. Experimental Arms
- **Arm A (`reported`):** Baseline policy routing to the nearest connector reporting `AVAILABLE` status via firmware heartbeats.
- **Arm B (`failcount`):** Baseline heuristic flagging a connector after $k=2$ consecutive session failures; routes around flagged units.
- **Arm C (`usagegap`):** Baseline heuristic flagging a connector idle $> 2.5 \times$ expected inter-arrival interval; routes around flagged units.
- **Arm D (`belief`):** Proposed system — Online 4-state HMM forward filter + Gamma-Poisson group pooling + prospective Kulldorff space-time scan + expected trip-time router.

---

## 2. Benchmark Scenarios
1. **`baseline`:** Background steady-state failures (~22% dead-ends, ~10% degraded) with status misreporting.
2. **`site_outage`:** Complete substation / electrical blackout across all connectors at a major hub.
3. **`operator_outage`:** Cloud backend outage hitting ~30% of an operator's network.
4. **`firmware_bug`:** Protocol handshake crash affecting all units running a specific firmware build.
5. **`slow_degradation`:** Power delivery degradation (dropping to 20%–60% of rated kW) across aging hardware.
6. **`vehicle_side_heavy`:** Elevated vehicle-side failure rate (8% and 15%) testing filter robustness against false positives.

---

## 3. Seed Partitioning
- **Development Seeds:** `0` through `9` (Used exclusively for tuning, testing, and debugging).
- **Evaluation Seeds:** `100` through `119` (**Frozen** until development code and pre-registration are committed).

---

## 4. Primary Claim & Decision Rule (Gate G2)
### Primary Claim:
At an equal false-alarm rate, belief-based routing (Arm D) achieves a **lower wasted-trip rate** and **shorter failure-detection latency** than:
- Arm A (Reported Status)
- Arm B (Failure Counter)
- Arm C (Usage Gap Detector)

### Decision Rule (Gate G2 Pass Condition):
Arm D must beat Arm A on wasted-trip rate across the dev seeds (and evaluation seeds). If Arm D fails to beat any baseline on any metric, the loss must be documented honestly in `docs/results/losses.md` without tuning the simulator to favor Arm D.
