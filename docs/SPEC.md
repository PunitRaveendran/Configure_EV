# Charger Truth: Specification & Architecture Reference

> **Notice:** All data in this project is strictly **SIMULATED** for the Configure 2026 hackathon (Condense x Bosch MPS). No actual proprietary charging network data is accessed or used.

---

## 1. Goal & Architecture
Charger Truth estimates, per EV charger connector, the hidden state \( S \in \{\text{Healthy}, \text{Degraded}, \text{Dead-end}, \text{Offline}\} \) from two event streams:
1. Unreliable charger-side telemetry (`charger.status`)
2. Vehicle-side session outcomes (`vehicle.session`)

It outputs real-time connector beliefs, cluster alerts for correlated hardware/firmware faults, expected-trip-time routing decisions, and demand-weighted maintenance tickets.

---

## 2. Event Topics Specification

All timestamps (`event_ts`, `ingest_ts`, `emit_ts`) are standard UTC unix epoch milliseconds (int64).
Every event supports deterministic serialization (`to_json` and `from_json`).

| Topic Name | Partition Key | Event Schema / Primary Fields | Description |
|---|---|---|---|
| `charger.status` | `connector_id` | `event_ts`, `connector_id`, `site_id`, `reported_status` (`AVAILABLE`, `CHARGING`, `FAULTED`, `OFFLINE`), `error_code` (optional str), `meter_reading_kwh` | Charger heartbeat telemetry. Frequently misreports dead-end or degraded connectors as available. |
| `vehicle.session` | `connector_id` | `event_ts`, `session_id`, `connector_id`, `vehicle_id`, `outcome` (`STARTED`, `FAILED`, `TIMEOUT`), `time_to_current_sec`, `delivered_kw`, `rated_kw`, `failure_reason` | Vehicle-side ground truth session attempt outcome. |
| `vehicle.request` | `vehicle_id` | `event_ts`, `request_id`, `vehicle_id`, `current_lat`, `current_lon`, `current_soc`, `battery_kwh`, `target_soc`, `reserve_soc`, `max_charge_rate_kw` | EV routing or charging request from an in-transit vehicle. |
| `connector.belief` | `connector_id` | `event_ts`, `connector_id`, `p_healthy`, `p_degraded`, `p_deadend`, `p_offline`, `p_start`, `uncertainty`, `evidence_count`, `last_evidence_ts` | Updated posterior probabilities and expected session start probability \( P(\text{start}) \). |
| `cluster.alert` | `group_key` | `event_ts`, `alert_id`, `group_type` (`site`, `operator`, `firmware`, `operator_x_firmware`), `group_key`, `window_min`, `llr`, `threshold`, `observed_failures`, `expected_failures`, `member_connector_ids` | Prospective Kulldorff space-time scan alert detecting correlated failure bursts. |
| `route.decision` | `vehicle_id` | `event_ts`, `request_id`, `vehicle_id`, `selected_connector_id`, `ranked_candidates` (list of connector, score, expected_time_min, p_start), `reason` | Success-weighted routing recommendation minimizing expected trip + charge time with 1-step lookahead. |
| `ops.ticket` | `ticket_id` | `event_ts`, `ticket_id`, `target_type` (`connector` or `cluster`), `target_id`, `priority`, `demand_rate`, `p_start`, `heuristic_hint`, `cluster_alert_id` | Maintenance repair queue entry ranked by \( (1 - P(\text{start})) \times \text{demand\_rate} \). |

---

## 3. Configuration & Parameter Reference

All tunables live in `src/ct/config.py`.

### 3.1 Network & Simulator Dimensions
- **Connectors**: ~200 connectors across ~60 sites
- **Operators**: 4 operators (e.g. OP_A, OP_B, OP_C, OP_D)
- **Hardware Models**: 5 hardware models (e.g. HW_1 to HW_5)
- **Firmware Versions**: 3 versions (e.g. FW_v1.0, FW_v1.1, FW_v2.0)
- **Spatial Bounding Box**: Synthetic Chennai coordinate bounds:
  - `lat_min`: 12.85, `lat_max`: 13.20
  - `lon_min`: 80.10, `lon_max`: 80.35
- **Baseline First-Attempt Success**: Target calibrated to ~0.71 (US EV charging benchmark assumption).

### 3.2 Hidden States & Transition Dynamics
Hidden states:
1. **Healthy**: Normal functioning.
2. **Degraded**: Slow onset; power delivered drops to 20%–60% of rated kW.
3. **Dead-end**: Appears "Available" ~90% of the time in heartbeats, but fails to deliver current 97% of the time.
4. **Offline**: Disconnected from network, mostly stops reporting.

### 3.3 Default Emission Priors (Priors table)
| Parameter | Healthy | Degraded | Dead-end | Offline |
|---|---|---|---|---|
| \( P(\text{start} \mid \text{state}) \) | 0.97 | 0.90 | 0.03 | 0.00 |
| \( P(\text{heartbeat reports available} \mid \text{state}) \) | 0.95 | 0.95 | 0.90 | 0.15 |
| Delivered / Rated Power Ratio | 0.90 – 1.00 | 0.20 – 0.60 | 0.00 | 0.00 |

### 3.4 Vehicle-Side Failure & Timeout
- **Unrelated vehicle-side failure rate**: Default `0.03` (evaluated also at `0.08` and `0.15`).
- **Failed start timeout cost**: `120` seconds (~2 minutes).

### 3.5 Belief Updating, Forgetting & Group Pooling
- **Forgetting Half-Life**: `3600` seconds (1 hour). Exponential decay towards baseline prior.
- **Group Pooling**: Gamma-Poisson hazard rate multiplier shared across `site`, `operator`, `firmware`.
- **Pooling Clip**: Bounds `[0.2, 5.0]`.
- **Probing Rate**: ~0.05 (5% of requests). Probes only vehicles with slack range/time on high-entropy connectors.
- **Prior Scale Factor**: Default `1.0` (evaluated at `0.7` and `1.3` for misspecification robustness).

### 3.6 Space-Time Scan Parameters
- **Windows**: `[15, 30, 60, 120]` minutes.
- **Evaluation Step**: Every 60 simulated seconds.
- **Statistic**: Log-Likelihood Ratio (LLR):
  \[
  \text{LLR} = c \ln\frac{c}{e} + (n-c) \ln\frac{n-c}{n-e} \quad (\text{for } c > e)
  \]
- **Persistence Requirement**: 2 consecutive evaluations above threshold before triggering an alert.
- **False-Alarm Budget**: 1 false alarm per simulated week under null Monte Carlo simulation.
- **Suppression**: Nested alerts suppressed (e.g. site alert suppressed if parent operator alert active).

### 3.7 Router Objective
Rank candidates by expected total trip duration \( T \):
\[
T = t_{\text{travel}} + p \cdot (w + s) + (1 - p) \cdot (t_{\text{fail}} + T_{\text{next}})
\]
where:
- \( t_{\text{travel}} \): travel time from vehicle location to connector site
- \( p = P(\text{start}) \): estimated probability session will start
- \( w \): estimated queue wait time
- \( s \): estimated charging duration to reach target SoC
- \( t_{\text{fail}} \): timeout penalty (~2 min)
- \( T_{\text{next}} \): best follow-up expected time among next 3 candidate connectors (1-step lookahead)

### 3.8 Random Seeds & Scenarios
- **Dev Seeds**: `0` through `9`
- **Evaluation Seeds**: `100` through `119` (frozen after `docs/PREREG.md`)
- **Scenarios**: `baseline`, `site_outage`, `operator_outage`, `firmware_bug`, `slow_degradation`, `vehicle_side_heavy`.
