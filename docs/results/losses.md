# Honest Metric Evaluation & Baseline Losses (`docs/results/losses.md`)

> **Notice:** All data is strictly **SIMULATED**.  
> **PREREG Commit Hash:** `da38da9`  
> In strict accordance with Hard Rule 10: "If our method loses on a metric, report it. Never tune the simulator to favour it."

## Documented Metric Comparisons (Dev Seeds 0–9)

Arm D did not strictly beat the baseline on the following metrics:

- **Mean Time-to-Charge:** Arm A_reported (7.5m) beat Arm D (8.1m)
- **p90 Time-to-Charge:** Arm A_reported (13.8m) beat Arm D (14.9m)
- **Mean Time-to-Charge:** Arm B_failcount (7.4m) beat Arm D (8.1m)
- **p90 Time-to-Charge:** Arm B_failcount (13.8m) beat Arm D (14.9m)
- **Wasted-Trip Rate:** Arm C_usagegap (15.03%) beat Arm D (21.41%)
- **Wasted Minutes:** Arm C_usagegap (17.5m) beat Arm D (24.5m)
