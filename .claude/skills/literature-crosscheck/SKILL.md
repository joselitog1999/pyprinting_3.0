---
name: literature-crosscheck
description: Cross-references scientific claims, equations, physical constants, and empirical parameters against primary peer-reviewed literature. Use when an empirical statement appears in code or docs without a citation, or when verifying parameter accuracy against international standards.
---

# Literature Crosscheck Skill

This skill provides a deterministic protocol for auditing, verifying, and enriching scientific claims against primary literature and local bibliographic databases (via Zotero MCP).

## Overview

In experimental nanophotonics, parameters such as the Hamaker constant ($A_H$), complex refractive index ($\tilde{n} = n + ik$), thermal boundary conductance ($G_{\text{th}}$), and colloidal surface charge ($\zeta$-potential) cannot be invented or copied from unverified blog posts. Every parameter must trace back to primary peer-reviewed literature.

---

## Step-by-Step Execution Protocol

### Step 1: Identify Claim & Search Query
1. Extract the specific claim, equation, or parameter value:
   * Target Parameter / Equation: $P$
   * Current Value / Range: $V_0 \pm \delta V$
   * System Context: Material, solvent, temperature, wavelength (e.g., $Au$ nanoparticles, water, $298\ \text{K}$, $532\ \text{nm}$).
2. Formulate focused academic search queries (e.g., `"gold nanoparticle" "thermal conductivity" interface water laser`).

### Step 2: Zotero & Academic Database Search
1. Query local Zotero library via Zotero MCP:
   * Search for collections matching nanophotonics, photothermal printing, or plasmonics.
   * Search by author (e.g., Stefani, Gargiulo, Baffou, Orrit, Novotny).
2. If local literature is insufficient, query external open databases (Crossref, arXiv, Semantic Scholar).

### Step 3: Primary Source Extraction
1. Access the primary paper (not a secondary review quoting another review).
2. Verify:
   * Experimental method used to measure the parameter (e.g., ellipsometry, transient absorption, DLS).
   * Experimental error and confidence interval.
   * Boundary conditions and sample preparation methods.

### Step 4: Consistency Assessment
Classify the claim into one of four states:
* `SUPPORTED`: Value matches primary literature within experimental uncertainty.
* `OUTDATED`: A more accurate or recent measurement exists.
* `CONTROVERSIAL`: Literature presents conflicting values depending on method.
* `UNFOUNDED`: No peer-reviewed paper supports the claim; parameter is likely an arbitrary heuristic.

### Step 5: Log to Evidence Ledger
If the claim is verified, generate or update an entry in `docs/evidence/EVIDENCE_LEDGER.md` using `docs/evidence/TEMPLATE_CLAIM.md`.

---

## Deliverable Format

```markdown
### Literature Crosscheck: [Target Parameter / Claim]

* **Claim**: "[Exact quote or formula from code/docs]"
* **Found in**: `path/to/file.py:L45` / `[[CAT-XXX]]`
* **Primary Citation**: [Author, Journal, Year, DOI]
* **Reported Literature Value**: $V_{\text{lit}} \pm \sigma$ (Method: ...)
* **Local Repo Value**: $V_{\text{repo}}$
* **Status**: `SUPPORTED` / `DISCREPANCY` / `UNFOUNDED`
* **Recommendation**: [Retain / Update parameter to ... / Add warning note]
```
