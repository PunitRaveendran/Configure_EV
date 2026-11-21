# Comparative Evaluation Summary (Dev Seeds 0–9)

> **Notice:** All data is strictly **SIMULATED**. Pre-registration: `docs/PREREG.md`.

## Baseline Scenario Performance (10 Dev Seeds Mean)

| Arm | Description | Wasted-Trip Rate | Wasted Minutes | Mean Time-to-Charge (min) | p90 Time-to-Charge (min) |
|---|---|---|---|---|---|
| **A_reported** | Reported Status Baseline | 28.80% | 35.7 | 7.5 | 13.8 |
| **B_failcount** | Consecutive Fail Count ($k=2$) | 28.08% | 35.0 | 7.4 | 13.8 |
| **C_usagegap** | Usage Gap Anomaly ($M=2.5$) | 28.80% | 35.7 | 7.5 | 13.8 |
| **D_belief** | **Charger Truth (Proposed)** | **20.16%** | **23.1** | **7.2** | **14.2** |

### Statistical Significance (Paired Bootstrap 95% CI: D vs A)
- **Mean $\Delta$ Wasted-Trip Rate:** -8.64%
- **95% Bootstrap CI:** [-17.89%, +1.72%]
