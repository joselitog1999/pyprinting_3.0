---
name: metrology-review
description: Evaluates measurement uncertainty, statistical rigor, calibration protocols, and error propagation according to ISO/GUM standards. Use when reviewing localization precision, peak fitting, uncertainty budgets, or calibration curves.
---

# Metrology Review Skill

This skill governs the quantitative metrological auditing of experimental measurements, calibration routines, and statistical estimation algorithms in PyPrinting 3.0.

## Overview

In accordance with the Guide to the Expression of Uncertainty in Measurement (ISO/GUM) and modern nanometrology principles, a reported value without a traceable uncertainty statement is scientifically incomplete.

---

## Step-by-Step Execution Protocol

### Step 1: Measurement Equation Formulation
1. Formulate the functional relationship between the measurand $Y$ and input quantities $X_i$:
   $$Y = f(X_1, X_2, \dots, X_N)$$
2. Identify all input quantities, separating them into:
   * **Type A**: Evaluated by statistical analysis of series of observations (mean $\bar{x}$, standard deviation $s$).
   * **Type B**: Evaluated by scientific judgment, datasheets, calibration certificates, or physical limits.

### Step 2: Standard Uncertainty Quantification
1. For each input $X_i$, compute the standard uncertainty $u(x_i)$:
   * Normal distribution (from certificate with $k=2$): $u = U / 2$.
   * Rectangular / Uniform distribution (digital display resolution $\delta$): $u = \delta / \sqrt{3}$ or $\delta / (2\sqrt{3})$.
   * Triangular distribution: $u = \delta / \sqrt{6}$.

### Step 3: Sensitivity Coefficients & Error Propagation
1. Compute analytical partial derivatives (sensitivity coefficients):
   $$c_i = \frac{\partial f}{\partial X_i}$$
2. Calculate the combined standard uncertainty $u_c(y)$:
   $$u_c^2(y) = \sum_{i=1}^N c_i^2 u^2(x_i) + 2 \sum_{i=1}^{N-1}\sum_{j=i+1}^N c_i c_j u(x_i, x_j)$$
3. Compute effective degrees of freedom $\nu_{\text{eff}}$ using the Welch-Satterthwaite equation.
4. Apply coverage factor $k$ (typically $k=2$ for $95.45\%$ coverage) to obtain expanded uncertainty $U = k \cdot u_c(y)$.

### Step 4: Physical Limits & Lower Bounds
1. In optical localization, verify that reported positioning precision does not violate the Cramér-Rao Lower Bound (CRLB) given the measured photon count $N$ and background noise $b$:
   $$\sigma_{\text{CRLB}} = \sqrt{\frac{\sigma_{\text{PSF}}^2}{N} \left(1 + \frac{4\tau}{1 + \sqrt{2\tau}}\right)}$$
2. In spectral calibration, check residual root-mean-square error (RMSE) against the spectrometer slit resolution limit.

---

## Deliverable Format

```markdown
# Metrological Uncertainty Budget: [Measurand Name]

## 1. Functional Measurement Equation
$$ Y = f(X_1, X_2, \dots, X_N) $$

## 2. Uncertainty Budget Table (ISO/GUM)
| Quantity $X_i$ | Estimate $x_i$ | Standard Uncertainty $u(x_i)$ | Distribution | Sensitivity $c_i$ | Uncertainty Contribution $u_i(y)$ |
| :--- | :--- | :--- | :--- | :--- | :--- |
| $X_1$ | ... | ... | Normal ($k=1$) | ... | ... |
| $X_2$ | ... | ... | Rectangular | ... | ... |

## 3. Combined & Expanded Uncertainty
* **Combined Standard Uncertainty $u_c(y)$**: $...$ [units]
* **Effective Degrees of Freedom $\nu_{\text{eff}}$**: $...$
* **Expanded Uncertainty $U$ ($k=2, 95.45\%$)**: $...$ [units]

## 4. Final Metrological Statement
$$ Y = (\bar{y} \pm U)\ [\text{units}],\quad k=2 $$

## 5. Physical Limit Audit
* **Theoretical Limit (e.g., CRLB)**: $...$
* **Compliance**: `COMPLIANT_WITH_PHYSICAL_LIMITS` / `UNREALISTIC_PRECISION_CLAIM`
```
