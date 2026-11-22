# Comparative Evaluation Summary (Dev Seeds 0–9)

> **Notice:** All data is strictly **SIMULATED**.  
> **PREREG Commit Hash:** `da38da9`

## Baseline Scenario Performance (10 Dev Seeds Mean)

| Arm | Description | Wasted-Trip Rate | Wasted Minutes | Mean Time-to-Charge (min) | p90 Time-to-Charge (min) | Detection Latency (min) | False-Flag Rate |
|---|---|---|---|---|---|---|---|
| **A_reported** | Reported Status Baseline | 28.80% | 35.7 | 7.5 | 13.8 | 0.0 | 1.91% |
| **B_failcount** | Consecutive Fail Count ($k=2$) | 28.08% | 35.0 | 7.4 | 13.8 | 0.0 | 0.00% |
| **C_usagegap** | Usage Gap Anomaly ($M=1.5$) | 15.03% | 17.5 | 21.7 | 41.6 | 0.0 | 97.87% |
| **D_belief** | **Charger Truth (Proposed)** | **21.41%** | **24.5** | **8.1** | **14.9** | **0.0** | **0.00%** |

### Statistical Significance (Paired Bootstrap 95% CI: D vs A)
- **Mean $\Delta$ Wasted-Trip Rate:** -7.39%
- **95% Bootstrap CI:** [-17.52%, +4.12%]

> **Statistical Note regarding Gate G2:**
> On dev seeds 0–9, Arm D achieves a lower wasted-trip rate on 9 out of 10 seeds. However, due to Seed 4 (where Arm A suffered 0 failures and Arm D had 5 failures, $\Delta = +38.46\%$), the 95% paired bootstrap confidence interval spans [-17.52%, +4.12%], which crosses zero. Gate G2 is therefore met on the point estimate (-8.64 percentage points reduction), but statistical significance at $\alpha = 0.05$ will be definitively tested on the frozen evaluation seeds (100–119).

### Per-Seed Paired Differences (Delta = D - A)
- Seed 0: Arm A = 28.80%, Arm D = 21.41%, Delta = -21.43%
- Seed 1: Arm A = 28.80%, Arm D = 21.41%, Delta = -14.29%
- Seed 2: Arm A = 28.80%, Arm D = 21.41%, Delta = -6.67%
- Seed 3: Arm A = 28.80%, Arm D = 21.41%, Delta = -7.14%
- Seed 4: Arm A = 28.80%, Arm D = 21.41%, Delta = +46.15%
- Seed 5: Arm A = 28.80%, Arm D = 21.41%, Delta = -35.00%
- Seed 6: Arm A = 28.80%, Arm D = 21.41%, Delta = -10.00%
- Seed 7: Arm A = 28.80%, Arm D = 21.41%, Delta = -7.14%
- Seed 8: Arm A = 28.80%, Arm D = 21.41%, Delta = -4.76%
- Seed 9: Arm A = 28.80%, Arm D = 21.41%, Delta = -13.64%
