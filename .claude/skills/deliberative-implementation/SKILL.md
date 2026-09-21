---
name: deliberative-implementation
description: Governs the multi-round deliberation and implementation protocol for all non-trivial features, tools, modules, and experiments in PyPrinting 3.0. Enforces Round 1 (deep conceptual understanding, non-obvious angles, theoretical subagents panel, questions), Round 2 (engineering synthesis, dual-track flowchart, implementation subagents panel), optional Round 3 (hybrid clarifications), and Phase 4 (hard implementation).
---

# Deliberative Multi-Round Implementation Protocol Skill

This skill enforces a structured, multi-round collaborative deliberation process before any non-trivial code or architectural change is executed in PyPrinting 3.0. It ensures that theoretical rigor, physical safety, metrological validity, and software architecture are fully vetted before modifying production code.

---

## 1. The Core Philosophy

Scientific software must never be developed through impulsive, unverified code dumps. Jumping straight to implementation leads to broken optical hardware, physical misinterpretations, brittle GUIs, and catastrophic refactor rollbacks (such as the Sept 14 Monolithic Trauma).

Every implementation follows a phased deliberation lifecycle:
```
[User Request]
       │
       ▼
[Round 1: Conceptual & Theoretical Exploration]
  • Deep conceptual understanding from first principles
  • Theoretical subagents panel (physics, chemistry, metrology, devil's advocate)
  • Non-obvious angles, risks & trade-offs
  • Probing questions & architectural options
       │
       ▼  [User Answers & Direction Validated]
[Round 2: Technical Architecture & Engineering Blueprint]
  • Executive synthesis of accepted decisions
  • Engineering subagents panel (software architect, instrumentation, QA-UX)
  • Mandatory Dual-Track Architectural Flowchart (Mermaid)
  • DoF inventory & automation ladder (Layers 0-3)
       │
       ▼  [Optional Round 3: Hybrid Clarifications if needed]
[User Approval]
       │
       ▼
[Phase 4: Hard Implementation]
  • Atomic code changes, unit tests (pytest), Graphify update, documentation
```

---

## 2. Dynamic Subagent Selection Matrix

The specific subagents summoned for Round 1 and Round 2 depend strictly on the **nature and scope of the task**:

| Task Archetype | Primary Examples | Round 1 Panel (Theoretical / Epistemic) | Round 2 Panel (Engineering / Applied) |
| :--- | :--- | :--- | :--- |
| **Hardware Acquisition Experiment** | New stage line-scan, Shamrock/iXon3 extinction series, camera autofocus, shutter sequencing | `experimentalist`, `physicist`, `instrumentation`, `devil-advocate` | `instrumentation`, `software-architect`, `qa-ux-auditor` |
| **Scientific Analysis & Curation Module** | SIF analyzer, lattice disorder, SMLM localization, deconvolution, peak fitting | `computational-physicist`, `metrology`, `physicist`, `devil-advocate` | `software-architect`, `qa-ux-auditor`, `interactive-tool-design` |
| **Photothermal / Colloidal Synthesis & Printing** | Plasmonic printing recipe, APTES silanization, CTAC nanocavities, thermal dissipation | `colloidal-chemist`, `physicist`, `experimentalist`, `devil-advocate` | `instrumentation`, `software-architect`, `qa-ux-auditor` |
| **Architectural Refactor & God-Node Decoupling** | Modularizing `LatticeDisorderWindow`, QThread concurrency fixes, memory leak resolution | `software-architect`, `devil-advocate`, `metrology` | `software-architect`, `qa-ux-auditor` |
| **Secondary Utility / Visualization Tool** | Interactive plot exporter, profile cutter, colormap selector, metadata inspector | `metrology`, `devil-advocate` | `software-architect`, `qa-ux-auditor`, `interactive-tool-design` |

---

## 3. Step-by-Step Round Execution Protocols

### 🔄 Round 1: Conceptual & Theoretical Exploration (The "Think First" Round)

**Objective**: Unpack the request with theoretical depth, expose hidden assumptions, identify risks, and solicit user decisions.

**Mandatory Deliverable Format**:
1. **Deep Conceptual Understanding**:
   * What was understood from the user's request from physical, mathematical, and metrological first principles.
   * Why this feature is scientifically necessary and what phenomena it investigates/controls.
2. **Specialized Theoretical Subagents Panel**:
   * Summaries of domain reviews from the assigned Round 1 subagents (e.g., `physicist` on forces, `colloidal-chemist` on surface reactions, `computational-physicist` on solver stability, `metrology` on CRLB/uncertainty).
3. **Non-Obvious Angles & Critical Trade-offs**:
   * Latent edge cases (e.g., photothermal bubbling, astigmatism, stage thermal drift, state precedence conflicts).
4. **Devil's Advocate & Falsification Probe (`devil-advocate`)**:
   * What unstated assumptions are we making? Under what experimental conditions will this fail?
5. **Proactive Suggestions & Key Questions for the User**:
   * Concrete options (e.g., Option A [High-Throughput] vs Option B [High-Precision]).
   * Specific questions clarifying degrees of freedom and user preferences.

> [!CAUTION]
> **Round 1 Quality Gate:**
> Do NOT generate or modify production code. Stop and wait for the user to answer questions, select suggestions, and approve the conceptual direction.

---

### 📐 Round 2: Technical Architecture & Engineering Blueprint (The "Design" Round)

**Objective**: Synthesize user feedback into a rock-solid technical blueprint and verify concurrency, hardware safety, and UI ergonomics.

**Mandatory Deliverable Format**:
1. **Executive Synthesis**:
   * Clear summary of *what* will be built, explicitly incorporating the user's accepted suggestions, answered questions, and locked invariants.
2. **Engineering Subagents Panel**:
   * `software-architect`: Signal/slot routing, `moveToThread` topology, Graphify AST impact, class structure.
   * `instrumentation`: DAQmx lines, timing margins, watchdog heartbeat, piezo limits.
   * `qa-ux-auditor`: Ergonomic layout, 4-rule ROIs with `blockSignals(True)`, FigureExportStudio hook, Click-to-Seed modes.
3. **Mandatory Dual-Track Architectural Flowchart (Mermaid)**:
   * Explicit side-by-side flow contrasting *User Journey Track* vs *Data/Hardware Pipeline Track*.
4. **DoF Inventory & Automation Ladder**:
   * Breakdown of Fixed Invariants vs Layer 0 (Auto) vs Layer 1 (Visual) vs Layer 2 (Bounds) vs Layer 3 (Solvers) via `interactive-tool-design`.
5. **Concrete Verification Plan**:
   * Automated unit tests (`pytest`), mock safety checks (`SAFE_MODE = True`), and rollback safeguards.

> [!IMPORTANT]
> **Round 2 Quality Gate:**
> Present the blueprint for user validation. If substantial ambiguities or design divergences remain, enter a brief **Round 3 (Hybrid Clarification)**. Once the user signs off, proceed to **Phase 4**.

---

### ⚙️ Phase 4: Hard Implementation (The "Execution" Phase)

**Objective**: Execute the agreed blueprint with atomic precision.

**Execution Protocol**:
1. Apply code changes strictly following clean architecture (`SYS-001`) and non-destructive refactoring rules.
2. Write comprehensive unit tests in `tests/` (`pytest tests/`).
3. Execute `graphify update .` to keep the AST knowledge graph in sync.
4. Update corresponding module documentation in `docs/modulos/MOD-XX.md` and user manual in `docs/MANUAL_USUARIO.md`.
5. Provide a clear, verified walkthrough of changes.
