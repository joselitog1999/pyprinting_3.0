---
name: knowledge-integrator
description: Consolidates new scientific findings, architectural decisions, or driver updates into persistent institutional memory. Automates updates across CAT/SYS/MOD compendiums, Evidence Ledgers, Decision Logs, and triggers Graphify AST synchronization. Use when concluding an investigation or closing a development cycle.
---

# Knowledge Integrator Skill

This skill governs the persistent consolidation of validated knowledge into PyPrinting 3.0's institutional memory, preventing knowledge loss across AI sessions.

## Overview

In accordance with Foundational Directive #1 (Absolute Knowledge Preservation), insights generated during an AI session must never evaporate into conversational history. This skill orchestrates the atomic synchronization of documents, ledgers, and the structural knowledge graph.

---

## Step-by-Step Execution Protocol

### Step 1: Knowledge Classification
Categorize the new finding or implementation into its proper institutional container:
* **Scientific / Theoretical**: Belongs in `reportes/cientificos/CAT-XXX.md`.
* **System / Architecture / Hardware**: Belongs in `reportes/sistema/SYS-XXX.md`.
* **Module Manual**: Belongs in `docs/modulos/MOD-XXX.md`.
* **Epistemic Claim**: Belongs in `docs/evidence/EVIDENCE_LEDGER.md`.
* **Architectural / Calibration Choice**: Belongs in `docs/decisions/DECISION_LOG.md`.

### Step 2: Check for Prior Existence & Update
1. Query Graphify to check if a document or node already exists for this concept:
   ```bash
   graphify query "<concept_name>"
   ```
2. If it exists: Append or revise the existing document with explicit version history and diff rationale.
3. If it does not exist: Create a new document following the standard numbering conventions (`CAT-XXX`, `SYS-XXX`, `DEC-XXX`).

### Step 3: Epistemic & Decision Ledger Logging
1. If a scientific claim or physical equation was established or verified:
   * Add a structured entry in `docs/evidence/EVIDENCE_LEDGER.md` referencing code lines and source DOI.
2. If an architectural tradeoff or calibration parameter was chosen:
   * Create a new record in `docs/decisions/` using `docs/decisions/TEMPLATE_DECISION.md`.

### Step 4: Graphify Graph Synchronization
Execute the mandatory post-modification AST update:
```bash
graphify update .
```
Verify that new symbols, classes, or markdown links are parsed without syntax errors.

---

## Deliverable Format

```markdown
# Knowledge Integration Summary

## 1. Modified & Created Artifacts
* **Compendium**: Updated `reportes/cientificos/CAT-XXX.md` (Section 3.2 added)
* **Evidence Ledger**: Added entry `PHY-045` in `docs/evidence/EVIDENCE_LEDGER.md`
* **Decision Log**: Logged `DEC-014` in `docs/decisions/DEC-014_Piezo_Filter_Cutoff.md`

## 2. Graphify AST Synchronization
* Command: `graphify update .`
* Result: Nodes added, dependencies updated, zero AST errors.

## 3. Preservation Check
- [x] Code references contain exact file paths and line ranges
- [x] LaTeX equations rendered properly
- [x] Zero dangling wiki links
```
