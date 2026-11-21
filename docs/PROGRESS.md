# Charger Truth: Development Progress Log

## Definition of Done Checklist (Every Step)
- [x] `pytest` passes; new behaviour has unit tests.
- [x] `docs/PROGRESS.md` updated: what changed, what is unverified, next step.
- [ ] Short git commit.
- [ ] No TODOs left silently.

---

## Log Entry: 2026-11-22 (Prompt 1 Complete)

### What Changed:
1. Created repository layout following `AGENTS.md`:
   - `pyproject.toml` configured for Python 3.11+, pydantic v2, numpy, pandas, matplotlib, pyyaml, fastapi, websockets.
   - `Makefile` with targets `test`, `lint`, `sim`, `eval`.
   - Empty module packages created under `src/ct/sim/`, `src/ct/core/`, `src/ct/baselines/`, `src/ct/eval/`, and `src/ct/pipeline/`.
2. Created `src/ct/schemas.py`:
   - Pydantic v2 immutable event models for all 7 topics:
     - `charger.status` (`ChargerStatusEvent`)
     - `vehicle.session` (`VehicleSessionEvent`)
     - `vehicle.request` (`VehicleRequestEvent`)
     - `connector.belief` (`ConnectorBeliefEvent`)
     - `cluster.alert` (`ClusterAlertEvent`)
     - `route.decision` (`RouteDecisionEvent`)
     - `ops.ticket` (`OpsTicketEvent`)
   - Enums: `SessionOutcome` (STARTED, FAILED, TIMEOUT), `ReportedStatus`, `GroupType`, `TargetType`, `TicketStatus`.
   - Helper methods: `to_json()`, `from_json()`, and stable partition `.key` property on every event.
3. Created `src/ct/config.py`:
   - Frozen dataclass `Config` holding every parameter named in `docs/SPEC.md` and `AGENTS.md`.
   - YAML loading via `from_yaml` and immutable modification via `with_overrides`.
   - `prior_scale` scaling for misspecification robustness (+/- 30%).
4. Created unit tests:
   - `tests/test_schemas.py`: verified serialization roundtrip and stable key properties across all 7 topic events.
   - `tests/test_config.py`: verified config defaults, immutability, YAML override loading, and `prior_scale` clipping.

### Needs Decision / Parameter Values (from Spec):
- None missing for Prompt 1: All values explicitly enumerated in `AGENTS.md` and `docs/SPEC.md` were coded into `Config`.

### What is Unverified:
- Simulator dynamics and closed-loop policies (to be implemented in Prompt 2).

### Next Step:
- Execute **Prompt 2**: Build `src/ct/sim` (network, failures, demand, engine) and calibration script `scripts/calibrate.py` to hit the ~71% first-attempt success target under reported-status policy (Gate G1).
