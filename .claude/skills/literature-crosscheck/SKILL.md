---
name: literature-crosscheck
description: Audits empirical numerical parameters, physical constants (Hamaker, dielectric permittivity, thermal conductivity, zeta-potential), and factual claims against primary literature via Zotero MCP and academic databases. Do NOT use for dimensional equation analysis (use physics-model-review) or macro-level methodology synthesis (use scientific-evaluation).
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

### Step 2: Search in the Researcher's Order of Sources
The order is fixed by the researcher (R1-8): the loaded bibliography, then the researcher, then the web.
1. **The bibliography in `docs/bibliografia/`** first: group theses and articles, datasheets, and topic folders (printing, thermometry, optical tweezers, static Debye-Waller). The keys and physical page numbers already verified are in `.claude/shared/lab-invariants.md` §9. The Zotero MCP, when connected, is a search aid over the same material. Note whether a source describes the CIBION microscope or the INS-UNSAM bench.
2. **The researcher**, when the loaded bibliography is silent or contradicts itself. An unpublished figure from the researcher is recorded as EXPERIMENTAL with its date, not as established.
3. **The web** last (Crossref, arXiv, Semantic Scholar), with every DOI checked against Crossref.
4. A CAT/SYS/MOD document, the manual, a ledger or a prompt of this repository is **never** a source: the 2026-09-27 audit found values copied between them under false attributions.

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

Also say which backing label the value earns in `lab-invariants` terms (RESPALDADO / DERIVADO / EXPERIMENTAL / SIN FUENTE). A method still in development, such as the Debye-Waller Monte Carlo, is EXPERIMENTAL however internally consistent it looks.

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
* **Status**: `SUPPORTED` / `OUTDATED` / `CONTROVERSIAL` / `UNFOUNDED` (backing label: ...)
* **Recommendation**: [Retain / Update parameter to ... / Add warning note]
```
