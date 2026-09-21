---
name: deliberative-implementation
description: Governs the strict 4-round deliberation and implementation protocol for all non-trivial features, tools, modules, and experiments in PyPrinting 3.0. Enforces Round 1 (conceptual understanding & questions), Round 2 (technical engine & backend signatures), Round 3 (interactive GUI & ergonomics blueprint), and Round 4 (contract reconciliation table, atomic implementation & quality gates).
---

# Deliberative Multi-Round Implementation Protocol Skill

This skill enforces a structured, 4-round collaborative deliberation lifecycle before any non-trivial code or architectural change is executed in PyPrinting 3.0. It eliminates cognitive overload, prevents broken optical hardware, and ensures that mathematical contracts, GUI parameters, and physical safety are formally reconciled before modifying production code.

---

## 1. The Core Philosophy

Scientific software must never be developed through impulsive, unverified code dumps. Jumping straight to implementation leads to broken optical hardware, physical misinterpretations, brittle GUIs, and catastrophic refactor rollbacks (such as the Sept 14 Monolithic Trauma).

Furthermore, mixing backend mathematical engine design with frontend GUI widget ergonomics in a single discussion creates cognitive saturation and leads to subtle contract bugs (e.g. backend expecting 3 arguments while GUI provides 4, or unit mismatches like $\mu\text{m}$ vs $\text{nm}$).

Therefore, every implementation strictly follows the **4-Round Deliberation Lifecycle**:

```
[User Request]
       │
       ▼
[Round 1: Conceptual & Theoretical Exploration]
  • Deep conceptual understanding & paraphrase from first principles
  • Theoretical subagents panel (physics, chemistry, metrology, devil's advocate)
  • Non-obvious angles, risks & trade-offs
  • Probing questions & architectural options
       │
       ▼  [User Answers, Direction Validated & Approved]
[Round 2: Technical Architecture & Core Engine Blueprint]
  • Executive synthesis of physical & mathematical boundary conditions
  • Backend engine functions, signatures, types, defaults, and BLAS algorithms
  • Mandatory Dual-Track Architectural Flowchart (Mermaid)
  • Explicit Core Engine Parameter Inventory
       │
       ▼  [User Approves Technical Engine]
[Round 3: Interactive GUI & Ergonomics Blueprint] (Mandatory for UI/Visual tools)
  • Led by scientific-gui-designer & qa-ux-auditor
  • Parameter versatility & DoF automation ladder (Layers 0-3)
  • Direct plot manipulation, canvas clicks, table navigation & context menus
  • Sacred session state: unitary mutations without global invalidation
  • Scientific pedagogy: rich tooltips & deep-linked Wiki browser dialogs
       │
       ▼  [User Approves Interactive GUI Blueprint]
[Round 4: Contract Reconciliation, Atomic Implementation & Quality Gates]
  • MANDATORY: Parameter Interface Matrix (Contract Reconciliation Table)
  • Clean atomic code modifications adhering to Catppuccin & PyQt6 standards
  • Regression test execution (pytest tests/, SAFE_MODE = True)
  • Post-modification AST synchronization (graphify update .)
  • Documentation update (MANUAL_USUARIO.md, CAT/SYS monographs)
```

---

## 2. Dynamic Subagent Selection Matrix

The subagents summoned across rounds depend strictly on the **nature and scope of the task**:

| Task Archetype | Primary Examples | Round 1 Panel (Theoretical / Epistemic) | Round 2 Panel (Core Engine) | Round 3 Panel (Interactive GUI) |
| :--- | :--- | :--- | :--- | :--- |
| **Hardware Acquisition & HAL** | Line-scan, Shamrock/iXon3 series, autofocus, shutter timing | `experimentalist`, `physicist`, `instrumentation`, `devil-advocate` | `instrumentation`, `software-architect` | `scientific-gui-designer`, `qa-ux-auditor` |
| **Scientific Analysis & Curation** | SIF analyzer, lattice disorder, SMLM localization, deconvolution | `computational-physicist`, `metrology`, `physicist`, `devil-advocate` | `software-architect`, `computational-physicist`, `metrology` | `scientific-gui-designer`, `qa-ux-auditor` |
| **Photothermal & Colloidal Printing** | Printing recipes, APTES silanization, CTAC nanocavities | `colloidal-chemist`, `physicist`, `experimentalist`, `devil-advocate` | `instrumentation`, `software-architect` | `scientific-gui-designer`, `qa-ux-auditor` |
| **Architectural Refactor** | Decoupling God-nodes, QThread concurrency, memory leak cleanup | `software-architect`, `devil-advocate`, `metrology` | `software-architect` | `scientific-gui-designer`, `qa-ux-auditor` |
| **Visualization & Reporting** | FigureExportStudio, Wiki browser, interactive profile cutter | `metrology`, `devil-advocate` | `software-architect`, `metrology` | `scientific-gui-designer`, `qa-ux-auditor` |

---

## 3. Step-by-Step Round Execution Protocols

### 🔄 Round 1: Conceptual & Theoretical Exploration (The "Think First" Round)

**Objective**: Unpack the request with theoretical depth, establish mutual understanding, expose hidden assumptions, and solicit user decisions.

**Mandatory Deliverable Format**:
1. **User Request Understanding & Paraphrase**:
   * Explicitly state what was understood from the user's request from physical, mathematical, and metrological first principles.
2. **Targeted Conceptual Questions for the User**:
   * Concrete questions probing physical assumptions, parameter regimes, and user intent before making technical commitments.
3. **Specialized Theoretical Subagents Panel**:
   * Summaries of domain perspectives (`physicist`, `computational-physicist`, `colloidal-chemist`, `metrology`, `experimentalist`).
4. **Non-Obvious Angles & Critical Trade-offs**:
   * Latent edge cases (e.g. stage thermal drift, photothermal bubbling, state precedence conflicts, optical aberration).
5. **Devil's Advocate & Falsification Probe (`devil-advocate`)**:
   * What unstated assumptions are being made? Under what experimental conditions will this fail?

> [!CAUTION]
> **Round 1 Quality Gate:**
> Do NOT generate or modify production code. Stop and wait for the user to answer questions, choose options, and approve the conceptual direction.

---

### 📐 Round 2: Technical Architecture & Core Engine Blueprint (The "Engine" Round)

**Objective**: Lock down the mathematical and physical contracts in `core/` independently of the visual presentation.

**Mandatory Deliverable Format**:
1. **Executive Synthesis**:
   * Consolidated summary of agreed concepts, integrating user decisions and physical boundary conditions.
2. **Engineering Subagents Panel**:
   * `software-architect`: Data structures, class modularity, memory isolation, thread boundaries.
   * `computational-physicist` / `metrology`: Numerical algorithms, BLAS acceleration, covariance matrices, vectorization.
   * `instrumentation`: DAQmx lines, timing margins, watchdog heartbeat, piezo limits.
3. **Mandatory Dual-Track Architectural Flowchart (Mermaid)**:
   * Explicit side-by-side flow contrasting *User Journey Track* vs *Data/Hardware Pipeline Track*.
4. **Core Engine Parameter Inventory**:
   * Exhaustive catalog of function signatures, arguments, types, defaults, and return signatures in `core/`.
5. **Engine Verification & Testing Strategy**:
   * Concrete unit test scenarios (`pytest`), analytical benchmarks, and mock safety checks (`SAFE_MODE = True`).

> [!IMPORTANT]
> **Round 2 Quality Gate:**
> Await explicit user approval and agreement on the technical engine before proceeding to the GUI design.

---

### 🎨 Round 3: Interactive GUI & Cognitive Ergonomics Blueprint (The "Human-in-the-Loop" Round)

**Objective**: Design the visual controls, micro-interactions, canvas affordances, and cognitive ergonomics, grounded in the agreed engine.

**Mandatory Deliverable Format**:
1. **Interaction Subagents Panel**:
   * `scientific-gui-designer` (Lead): Information architecture, direct manipulation, visual metrology, and in-app documentation.
   * `qa-ux-auditor`: Ergonomic layout, defensive handling, accessibility, and manual testing checklists.
2. **Parameter Versatility & DoF Inventory**:
   * Breakdown into Fixed Invariants vs Layer 0 (Auto) vs Layer 1 (Visual) vs Layer 2 (Bounds/Locks) vs Layer 3 (Solvers).
   * Widget types (spinbox vs slider vs checkbox, step sizes, physical units).
   * Linked controls (coupling rules, nominal presets).
3. **Direct Plot Manipulation & Micro-Interactions**:
   * In-plot interactions (e.g. `pointPolygonTest` for contour selection, click-to-seed pins, draggable ROIs).
   * Table interactions (keyboard arrow navigation `currentCellChanged`, right-click custom context menus: Resolve, Merge, Discard).
   * Defensive bidirectional signal blocking: all widget updates from plot events wrapped strictly in `widget.blockSignals(True)`.
4. **State Resilience & Sacred Session State**:
   * Strict prohibition of global state invalidation upon local edits (never wipe user tables or reset inspection results after a single edit).
   * Work queue reordering: pending items remain at top; resolved items are marked green (`#a6e3a1`) and moved to the bottom.
5. **Scientific Pedagogy & Contextual Wiki Integration**:
   * Rich tooltips with physical equations and canonical reference values (e.g. $Z=4$ for square, $Z=6$ for hex, $Z=3$ for honeycomb).
   * Deep-linked `[📖 Help]` buttons connecting panels directly to `CAT-xxx` monographs in `ScientificWikiBrowserDialog`.

> [!IMPORTANT]
> **Round 3 Quality Gate:**
> Await explicit user review and approval of the interactive GUI design before proceeding to implementation.

---

### ⚙️ Round 4: Contract Reconciliation, Atomic Implementation & Quality Gates (The "Execution" Round)

**Objective**: Reconcile engine vs GUI contracts, execute atomic code changes, verify with zero regressions, and synchronize knowledge.

#### Step 1: Mandatory Contract Reconciliation
Before writing a single line of code, construct and verify the **Parameter Interface Matrix**:

| GUI Control / Widget | Widget Type | GUI Unit | Backend Function | Backend Parameter | Backend Unit | Conversion Factor | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `spin_pitch` | `QDoubleSpinBox` | $\text{nm}$ | `generate_ideal_lattice_template` | `a` | $\text{nm}$ | $1.0$ | `MATCH` |
| `spin_boundary_radius` | `QDoubleSpinBox` | $\mu\text{m}$ | `generate_ideal_lattice_template` | `boundary_size_nm` | $\text{nm}$ | $\times 1000.0$ | `RECONCILED` |

*Verification Checklist:*
- [ ] Argument count: Exact match between GUI-collected values and backend parameters.
- [ ] Argument names: Match keyword arguments exactly.
- [ ] Physical units: Dimensional scaling confirmed ($\mu\text{m} \to \text{nm}$, $\text{s} \to \text{ms}$, $\text{deg} \to \text{rad}$).
- [ ] Default values: Backend defaults mirror GUI widget initial values.

#### Step 2: Atomic Implementation
- Write modular, typed, and defensive code adhering strictly to PyQt6 standards and the Catppuccin palette.
- Preserve comments, existing signatures, and simulation fallback paths.

#### Step 3: Quality Gates & Automated Verification
- Execute test suites:
  ```bash
  pytest tests/
  ```
  Ensure 100% pass rate and 0 regressions.
- Verify simulation safety (`SAFE_MODE = True`).

#### Step 4: Closing the Loop
- Execute AST update:
  ```bash
  graphify update .
  ```
- Update user documentation (`docs/MANUAL_USUARIO.md`) and relevant scientific monographs (`reportes/cientificos/CAT-xxx.md`).
- Present a clear, verified walkthrough of all modifications.
