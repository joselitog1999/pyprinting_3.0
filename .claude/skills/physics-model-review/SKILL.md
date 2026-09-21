---
name: physics-model-review
description: Audits physical equations, analytical approximations, and mathematical models for dimensional correctness, asymptotic limits, conservation laws, and physical validity regimes. Use when auditing physical derivations or translating mathematical equations into code.
---

# Physics Model Review Skill

This skill governs the rigorous validation of physical formulas, electrodynamic equations, and statistical models prior to algorithmic coding or documentation in `reportes/cientificos/` (CAT).

## Overview

A mathematical formula in computational physics cannot simply be accepted because it "looks plausible." It must be stress-tested against the fundamental laws of physics: dimensional consistency, boundary limits, and conservation theorems.

---

## Step-by-Step Execution Protocol

### Step 1: Formal Mathematical Extraction
1. Extract the equation in symbolic form:
   $$y = f(x_1, x_2, \dots, x_n; p_1, p_2, \dots, p_k)$$
2. Identify all fundamental dimensions (Length $[L]$, Mass $[M]$, Time $[T]$, Current $[I]$, Temperature $[\Theta]$) for all variables and constants.

### Step 2: Dimensional Homogeneity Check
1. Calculate the dimensional formula for the Left-Hand Side (LHS).
2. Calculate the dimensional formula for each additive term on the Right-Hand Side (RHS).
3. Confirm that $[LHS] \equiv [RHS]$.
4. Verify that arguments of transcendental functions ($\exp, \ln, \sin, \cos, \text{erf}$) are strictly dimensionless ($[1]$).

### Step 3: Asymptotic Boundary Analysis
Test the equation at the extreme frontiers of its parameter space:
1. **Zero Limit**: As spatial distance $r \to 0$, wavevector $q \to 0$, or time $t \to 0$. Does it diverge physically or smoothly approach a known boundary value?
2. **Infinity Limit**: As $r \to \infty$, $q \to \infty$, or $t \to \infty$. Does it recover the homogeneous, undisturbed, or steady-state background?
3. **Quasistatic / Wave Limit**: Does an electrodynamic formula reduce to electrostatics when $\omega \to 0$ or $c \to \infty$? Does it recover Rayleigh scattering when particle radius $a \ll \lambda$?

### Step 4: Conservation Laws & Physical Bounds
1. **Energy / Power**: Does the model conserve energy? E.g., is the extinction cross-section equal to absorption plus scattering ($\sigma_{\text{ext}} = \sigma_{\text{abs}} + \sigma_{\text{scat}}$)?
2. **Positivity**: Must the quantity be positive-definite (e.g., temperature $T \ge 0\ \text{K}$, probability density $P \ge 0$, radial distribution $g(r) \ge 0$)? Does the formula guarantee this?
3. **Thermodynamic Consistency**: Does heat always flow from hot to cold ($\nabla T \cdot \mathbf{J}_q \le 0$)?

### Step 5: Discretization & Implementation Guidance
1. Identify numerical singularity risks (e.g., division by zero at $r=0$).
2. Propose stable numerical schemes (e.g., adding a regularization parameter $\varepsilon$ or using an analytical Taylor expansion near zero).

---

## Deliverable Format

```markdown
# Physics Model Review: [Model / Equation Name]

## 1. Mathematical Formulation
$$ [LaTeX Equation] $$

## 2. Dimensional Homogeneity Audit
* $[LHS] = [M^a L^b T^c \dots]$
* $[RHS] = [M^a L^b T^c \dots]$
* **Verdict**: `HOMOGENEOUS` / `DIMENSIONAL_MISMATCH`

## 3. Asymptotic Limit Verification
| Parameter | Limit Tested | Expected Behavior | Model Prediction | Status |
| :--- | :--- | :--- | :--- | :--- |
| $r$ | $r \to 0$ | ... | ... | PASS / DIVERGENCE |
| $r$ | $r \to \infty$ | ... | ... | PASS / FAIL |
| $ka$ | $ka \ll 1$ | Rayleigh limit | ... | PASS / FAIL |

## 4. Physical Assumptions & Validity Regime
* **Required Conditions**: [e.g., Dilute suspension, linear optics, thermal equilibrium]
* **Breakdown Boundary**: [Where the model fails, e.g., $I > 10\ \text{MW/cm}^2$]

## 5. Implementation Recommendations
* Code translation cautions (numerical stability, vectorization hints).
```
