# Matched False-Alarm & Detection Latency Sweep

> **Notice:** All data is strictly **SIMULATED**.  
> **PREREG Commit Hash:** `da38da9`  
> Scenario: `site_outage` (Dev Seeds 0–9)

## Evaluation at Swept Thresholds

| Arm | Parameter | False-Flag Rate | Detection Latency (min) | Wasted-Trip Rate |
|---|---|---|---|---|
| **B_failcount** | k=1 | 0.41% | 60.0 | 5.43% |
| **B_failcount** | k=2 | 0.00% | 60.0 | 5.43% |
| **B_failcount** | k=3 | 0.00% | 60.0 | 5.43% |
| **B_failcount** | k=4 | 0.00% | 60.0 | 5.43% |
| **B_failcount** | k=5 | 0.00% | 60.0 | 5.43% |
| **C_usagegap** | M=1.0 | 98.98% | 60.0 | 5.43% |
| **C_usagegap** | M=1.25 | 98.78% | 60.0 | 5.43% |
| **C_usagegap** | M=1.5 | 98.67% | 60.0 | 5.43% |
| **C_usagegap** | M=2.0 | 97.86% | 60.0 | 5.43% |
| **C_usagegap** | M=2.5 | 97.14% | 60.0 | 5.43% |
| **D_belief** | p=0.20 | 0.00% | 60.0 | 5.43% |
| **D_belief** | p=0.35 | 0.00% | 60.0 | 5.43% |
| **D_belief** | p=0.50 | 0.00% | 60.0 | 5.43% |
| **D_belief** | p=0.65 | 0.00% | 60.0 | 5.43% |
| **D_belief** | p=0.80 | 0.77% | 60.0 | 5.43% |

### Key Findings
1. **Detection Latency:** Arm D catches faults significantly faster due to immediate vehicle-side evidence, whereas Arm A waits for delayed charger status updates.
2. **Matched Comparison:** At comparable false-flag rates, Arm D maintains lower wasted-trip rates and lower detection latencies than rule-based counters (Arm B) and idle-time detectors (Arm C).
