---
name: scientific-documentation
description: Generates standardized scientific reports, technical specifications, module manuals, and Standard Operating Procedures (SOPs). Use when authoring new documentation or updating existing CAT, SYS, or MOD compendiums in PyPrinting 3.0.
---

# Scientific Documentation Skill

This skill governs the production of publication-grade technical and scientific documentation in PyPrinting 3.0, ensuring uniform structure, notation, and formatting across all institutional records.

## Overview

All laboratory documents must follow strict formatting standards: explicit metadata headers, clear visual diagrams (Mermaid), formal LaTeX mathematical formulations, and bidirectional cross-links.

---

## Step-by-Step Execution Protocol

### Step 1: Select Document Archetype
Identify the correct document type:
* **CAT (Compendio Analítico Teórico)**: Pure physics, mathematical derivations, electrodynamics, crystallography.
* **SYS (Especificación de Sistema e Instrumentación)**: Hardware topology, timing diagrams, DAQmx signals, concurrency architectures.
* **MOD (Manual Operativo de Módulo)**: User-facing interface guide, parameter descriptions, error troubleshooting.
* **SOP (Standard Operating Procedure)**: Step-by-step laboratory bench recipe.

### Step 2: Structure & Metadata Standard
Every generated markdown file must begin with standard metadata:
```markdown
# [ID] — [Descriptive Title in Spanish/English]

**Laboratory**: Nanophotonics Lab — Instituto de Nanosistemas (INS-UNSAM / CONICET)  
**Author**: [Author / Specialist Role]  
**Location**: `path/to/document.md`  
**Linked Modules**: [[MOD-XX]], [[SYS-XX]], [[CAT-XX]]  
**Last Updated**: [YYYY-MM-DD]  
```

### Step 3: Mathematical Notation & Visuals
1. **Equations**: All formulas must be formatted in LaTeX display mode (`$$...$$`) with numbered labels where referenced in text.
2. **Architecture Diagrams**: Complex state transitions or data flows must include Mermaid diagrams (`mermaid`).
3. **Traceability Links**: Hyperlink code files with exact line numbers (e.g., `[`core/nidaq.py:L45-L60`](file:///...)`).

### Step 4: Quality Gate & Hyperlink Verification
1. Ensure no broken links or orphaned references.
2. Run link validator script if available (`scratch/validate_links.py`).

---

## Deliverable Format

Produces a complete, ready-to-merge markdown document adhering to the chosen archetype, validated against existing documentation standards in `reportes/`.
