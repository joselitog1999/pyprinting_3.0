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
3. Give every input a backing label (RESPALDADO / DERIVADO / EXPERIMENTAL / SIN FUENTE, `.claude/shared/lab-invariants.md` §0) and take hardware values from that table. An input without data gets no number: write "no value — measure by …", and it blocks the expanded uncertainty. `CAT-203` filled such a row with 1.50 nm, and the invented figure travelled into the lab tables.

### Step 2: Standard Uncertainty Quantification
1. For each input $X_i$, compute the standard uncertainty $u(x_i)$:
   * Normal distribution (from certificate with $k=2$): $u = U / 2$.
   * Rectangular / Uniform distribution: $u = a/\sqrt{3}$ for a **half-width** $a$ (a bound written $\pm a$), and $u = \delta/(2\sqrt{3}) = \delta/\sqrt{12}$ for a **full width** $\delta$ (e.g. a display resolution). Reading $\pm 1\ \mu\text{m}$ as a full width halves the uncertainty; that exact error sat in the `CAT-203` pinhole term.
   * Triangular distribution: $u = \delta / \sqrt{6}$.

### Step 3: Sensitivity Coefficients & Error Propagation
1. Compute analytical partial derivatives (sensitivity coefficients):
   $$c_i = \frac{\partial f}{\partial X_i}$$
2. Calculate the combined standard uncertainty $u_c(y)$:
   $$u_c^2(y) = \sum_{i=1}^N c_i^2 u^2(x_i) + 2 \sum_{i=1}^{N-1}\sum_{j=i+1}^N c_i c_j u(x_i, x_j)$$
3. Compute effective degrees of freedom $\nu_{\text{eff}}$ using the Welch-Satterthwaite equation.
4. Apply coverage factor $k$ to obtain expanded uncertainty $U = k \cdot u_c(y)$. $k=2$ gives $\approx 95\%$ only when the output is approximately normal and $\nu_{\text{eff}}$ is large (JCGM 100:2008 §6.3, Annex G); otherwise take $k$ from $\nu_{\text{eff}}$.

### Step 4: Physical Limits & Lower Bounds
1. In optical localization, verify that reported positioning precision does not violate the Cramér-Rao Lower Bound (CRLB) given the measured photon count $N$ and background $b$ (photons per pixel), per Rieger & Stallinga (2014), Eq. 7 (doi:10.1002/cphc.201300711):
   $$\sigma_{\text{CRLB}} \approx \sqrt{\frac{\sigma_a^2}{N} \left(1 + 4\tau + \sqrt{\frac{2\tau}{1 + 4\tau}}\right)}, \qquad \sigma_a^2 = \sigma_{\text{PSF}}^2 + \frac{a^2}{12}, \qquad \tau = \frac{2\pi b\, \sigma_a^2}{N a^2}$$
   with $a$ the pixel size. For EMCCD data (iXon3) multiply the variance by $F^2 = 2$, unless $N$ came from a mean–variance gain calibration, which already absorbs that factor (Rieger & Stallinga 2014 §2.1).
   * Pixelation enters **once**, as $a^2/12$ inside $\sigma_a^2$. Never add $\Delta x/\sqrt{12}$ as a separate budget term for a sub-pixel fit: it counts the same effect twice with ~100× the weight, and in `CAT-203` it became the false dominant term.
   * The formula assumes photon counting. For a photodiode channel (the confocal scan), $N$ has to be converted from the signal with the responsivity and gain, and electronic noise adds on top, so the bound is an optimistic floor. It is still the right test for rejecting a claimed precision.
   * Worked case: `.claude/agents/exemplars/metrology_uncertainty_budget_gold.md`.
2. In spectral calibration, check residual root-mean-square error (RMSE) against the spectrometer slit resolution limit.

---

## Deliverable Format

```markdown
# Metrological Uncertainty Budget: [Measurand Name]

## 1. Functional Measurement Equation
$$ Y = f(X_1, X_2, \dots, X_N) $$

## 2. Uncertainty Budget Table (ISO/GUM)
| Quantity $X_i$ | Type | Estimate $x_i$ | Standard Uncertainty $u(x_i)$ | Distribution | Sensitivity $c_i$ | Uncertainty Contribution $u_i(y)$ | Backing |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| $X_1$ | A | ... | ... | Normal ($k=1$) | ... | ... | RESPALDADO / DERIVADO / EXPERIMENTAL |
| $X_2$ | B | ... | no value — measure by ... | Rectangular | ... | — | SIN FUENTE |

## 3. Combined & Expanded Uncertainty
* **Combined Standard Uncertainty $u_c(y)$**: $...$ [units] (or: not reportable — rows without value: ...)
* **Effective Degrees of Freedom $\nu_{\text{eff}}$**: $...$
* **Expanded Uncertainty $U$ ($k$ = ..., from $\nu_{\text{eff}}$)**: $...$ [units]
* **Dominant term and lever**: ... (checked not to be an artifact of the model)

## 4. Final Metrological Statement
$$ Y = (\bar{y} \pm U)\ [\text{units}],\quad k = \dots,\ \text{coverage} \approx \dots\% $$

## 5. Physical Limit Audit
* **Theoretical Limit (e.g., CRLB)**: $...$
* **Compliance**: `COMPLIANT_WITH_PHYSICAL_LIMITS` / `UNREALISTIC_PRECISION_CLAIM`
```
