# Space-Time Scan Statistic Methodology & Thresholding (`docs/SCAN.md`)

> **Notice:** All data is strictly **SIMULATED**.
> This methodology implements a prospective space-time permutation scan statistic (Kulldorff et al.) adapted for continuous EV charging streams.

---

## 1. Scan Statistic Formulation

We monitor four overlapping spatial/organizational groups:
1. **Site:** Individual charging station hubs (`site_id`).
2. **Operator:** Charging Point Operators (`operator_id`).
3. **Firmware:** Connector firmware versions (`firmware_version`).
4. **Operator $\times$ Firmware:** Specific firmware builds deployed by a given operator.

### Rolling Windows
At every simulated minute $t$, we inspect multiple retrospective rolling time windows:
$$W \in \{15, 30, 60, 120\} \text{ minutes}$$

### Log-Likelihood Ratio (LLR)
For any group $g$ and window $W$:
- Let $n$ be the number of session attempts in $[t - W, t]$.
- Let $c$ be the number of observed failure outcomes (timeouts, handshake failures).
- Let $p_0$ be the expected baseline failure rate under normal background operation ($\approx 0.22$).
- Expected failures under the null hypothesis $H_0$: $e = n \cdot p_0$.

When $c > e$, the Poisson/Binomial log-likelihood ratio statistic is:
$$\text{LLR} = c \ln\left(\frac{c}{e}\right) + (n - c) \ln\left(\frac{n - c}{n - e}\right)$$

Edge case handling:
- If $c \le e$: $\text{LLR} = 0.0$.
- If $n == c$ (all attempts failed): the second term converges to $0$, yielding $\text{LLR} = c \ln(c / e)$.

---

## 2. False-Alarm Budget & Monte Carlo Threshold Calibration

A naive threshold generates excessive false alarms due to multiple hypothesis testing across 4 group types, 60 sites, 4 operators, 3 firmwares, and 4 time windows.

### Calibration Method:
1. **Budget:** Configured in `Config.false_alarm_budget_per_week = 1.0` (at most 1 false alarm per simulated week).
2. **Evaluation Steps:** With 1-minute evaluation intervals, a simulated week contains:
   $$N_{\text{eval}} = 7 \times 24 \times 60 = 10,080 \text{ evaluations}$$
3. **Null Simulations:** We run Monte Carlo null simulations (where failures occur independently with baseline probability $p_0$, with zero injected correlated faults).
4. **Threshold Selection:**
   $$\theta = \text{Quantile}_{1 - \alpha}\left( \max_{g, W} \text{LLR}_{g, W} \right)$$
   where $\alpha = \frac{1.0}{10,080} \approx 9.92 \times 10^{-5}$.
   On dev null simulations, this yields a calibrated threshold of **$\theta = 8.50$**.

---

## 3. Persistence & Nested Alert Suppression

1. **Persistence Requirement:** To eliminate transient single-minute spikes, an alert is published only when a group exceeds the threshold on **2 consecutive 1-minute evaluations** (`Config.scan_persistence = 2`).
2. **Nested Suppression:** When an operator-wide outage occurs, every site operated by that operator experiences failures. Emitting 30 individual site alerts causes ticket storms and operator confusion. Therefore:
   - If an **Operator** alert is active, child **Site** alerts for that operator are suppressed.
   - If a **Firmware** alert is active, child **Site** alerts running that firmware are suppressed.
   - The scanner emits a single, top-level `ClusterAlertEvent`.
