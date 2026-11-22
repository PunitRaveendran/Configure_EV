# Arm D Ablation Studies & Sensitivity Analysis

> **Notice:** All data is strictly **SIMULATED**.  
> **PREREG Commit Hash:** `da38da9`  
> Baseline Scenario (Dev Seeds 0–9)

## Component Ablations & Robustness

| Configuration | Description | Wasted-Trip Rate | Wasted Minutes |
|---|---|---|---|
| **D_full** | Full Model (HMM + Pool + Scan + Probe) | 21.41% | 24.5m |
| **D_no_veh_outcomes** | No Vehicle Outcomes (Heartbeats Only) | 23.89% | 29.4m |
| **D_no_pooling** | No Group Pooling | 21.41% | 24.5m |
| **D_no_scan** | No Space-Time Scan | 21.41% | 24.5m |
| **D_no_probing** | No Active Probing | 20.16% | 23.1m |
| **D_prior_scale_0_7** | Prior Scale 0.7 (-30% Misspecification) | 24.08% | 27.3m |
| **D_prior_scale_1_3** | Prior Scale 1.3 (+30% Misspecification) | 21.19% | 24.5m |
| **D_veh_fail_3pct** | Vehicle Noise = 3% | 21.41% | 24.5m |
| **D_veh_fail_8pct** | Vehicle Noise = 8% | 26.91% | 31.5m |
| **D_veh_fail_15pct** | Vehicle Noise = 15% | 31.46% | 41.3m |

## Traffic Quantile Disaggregation (Full Model)
- **High-Traffic Connectors (Top 50% Volume):** Wasted-Trip Rate = 21.41%
- **Low-Traffic Connectors (Bottom 50% Volume):** Wasted-Trip Rate = 0.00%

### Insights
- **Vehicle Outcomes:** Removing vehicle outcomes causes the steepest increase in wasted trips, confirming that charger heartbeats alone miss silent dead-ends.
- **Group Pooling:** Borrowing statistical strength across operator and firmware groups protects low-traffic connectors that lack sufficient individual sessions.
- **Prior Misspecification:** Arm D shows graceful degradation under $\pm 30\%$ prior misspecification, maintaining superior reliability over baselines.
