---
name: experiment-design
description: Designs structured laboratory recipes, experimental protocols, control benchmarks, and falsification criteria for optical printing, spectroscopy, and metrology. Use when planning new physical experiments, parameter sweeps, or testing hypotheses on the bench.
---

# Experiment Design Skill

This skill guides the formal formulation and structuring of experimental workflows, parameter matrices, control groups, and falsification criteria in PyPrinting 3.0.

## Overview

A robust experimental design must define not only what to test, but what controls are required to rule out optical artifacts, thermal drift, or chemical contamination, and what specific quantitative criteria will falsify the hypothesis.

---

## Step-by-Step Execution Protocol

### Step 1: Scientific Hypothesis & Measurables
1. State the central physical hypothesis in unambiguous terms:
   * *Independent Variables*: Parameters to manipulate (e.g., laser power $P$, pulse duration $\Delta t$, colloidal concentration $C$, lattice pitch $a$).
   * *Dependent Variables*: Quantities to measure (e.g., printing success rate $\%$, localization variance $\sigma_r^2$, SERS intensity ratio $I_{\text{peak}}/I_{\text{bg}}$).
   * *Controlled Variables*: Fixed constants (ambient $T=298\ \text{K}$, ionic strength $I=0.75\ \text{mM}$, laser $\lambda=532\ \text{nm}$).

### Step 2: Essential Control Groups
Every nanophotonic printing or spectroscopic experiment must include four mandatory controls:
1. **Dark / Baseline Control**: Detector readout with laser shutters closed (measures dark counts and electronic bias).
2. **Substrate Blank Control**: Laser irradiation on silanized glass without colloidal nanoparticles (verifies absence of substrate autofluorescence or thermal melting).
3. **Solvent / Medium Control**: Irradiation of buffer solution without gold nanoparticles (verifies absence of solvent breakdown).
4. **Anchor Particle ($P_0$) Reference**: Periodic inspection of an anchor particle to measure and subtract optomechanical drift.

### Step 3: Parameter Space Sampling Strategy
1. Define the sweep geometry:
   * Linear vs logarithmic parameter progression.
   * Multi-pass printing grid recipe (e.g., $4 \times 3$ grid with stepped power levels).
2. Establish sample size $N$ ensuring statistical power ($N \ge 30$ printing events for meaningful yield estimation).

### Step 4: Falsification Criteria & Stopping Rules
1. Define explicit thresholds that will falsify the hypothesis:
   * If measured metric $M$ does not exceed $M_{\text{threshold}}$ at confidence $p < 0.01$, reject hypothesis.
2. Establish emergency abort criteria (e.g., photodiode voltage saturation, temperature excursion, stage limit switch trip).

---

## Deliverable Format

```markdown
# Experimental Protocol: [Experiment Title]

## 1. Scientific Objective & Hypothesis
* **Core Hypothesis**: ...
* **Theoretical Reference**: [[CAT-XXX]] / [[SYS-XXX]]

## 2. Experimental Parameters & Matrix
| Parameter | Symbol | Nominal Value | Range / Step | Justification |
| :--- | :--- | :--- | :--- | :--- |
| Laser Power | $P$ | $5.0\ \text{mW}$ | $2.0 - 10.0\ \text{mW}$ | Thermal threshold |
| Shutter Time | $\Delta t$ | $20\ \text{ms}$ | $10 - 50\ \text{ms}$ | Colloidal capture time |

## 3. Mandatory Controls
1. **Negative Control**: ...
2. **Blank Substrate**: ...
3. **Drift Monitor ($P_0$)**: ...

## 4. Execution Sequence (Step-by-Step SOP)
1. Laser warm-up (30 min stabilization)
2. Autofocus and $Z$-plane calibration
3. Anchor particle localization
4. Execution of grid recipe
5. Post-printing confocal verification scan

## 5. Falsification & Success Criteria
* **Success Metric**: ...
* **Falsification Threshold**: If ..., the hypothesis is rejected.
```
