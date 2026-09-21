# CLAUDE.md — PyPrinting 3.0 / UNSAM Nanophotonics
> Operating Constitution for Claude Code and Autonomous Scientific Agents.
> Version: 3.0 (Claude Lab OS Architecture)

---

## 1. Identity, Purpose & Foundational Directive

**PyPrinting 3.0** is an experimental nanophotonics software and instrumentation platform developed at the Nanophotonics Lab (INS-UNSAM / CONICET). It orchestrates real-time hardware, confocal spectroscopy (Andor Shamrock 500i / iXon3), computer vision, counter-propagating microscopy, and light-assisted photothermal nanolithography of colloidal Au/Ag nanoparticles and sub-100 nm plasmonic dimers.

### Foundational Directive: Code is Physical Instrumentation
Treat this repository not as generic software, but as a **physical metrological instrument**. A software exception or unvalidated parameter is an actual laboratory event that can damage optical hardware, photobleach samples, or invalidate scientific measurements.

---

## 2. Epistemic Architecture & Separation of Concerns

To preserve context window efficiency and prevent instruction dilution:
* **`CLAUDE.md` (Constitution)**: Meta-rules, workflow orchestration, safety gates, and dispatch logic.
* **Graphify (`graphify-out/`)**: Semantic, AST, and structural codebase topology.
* **Subagents (`.claude/agents/`)**: Specialized domain perspectives and multi-agent peer review.
* **Skills (`.claude/skills/`)**: Deterministic, step-by-step scientific and engineering workflows.
* **Zotero & Literature MCP**: Primary peer-reviewed sources and empirical references.
* **Ledgers (`docs/evidence/`, `docs/decisions/`)**: Explicit epistemic claims and architectural decisions.
* **Compendiums (`reportes/cientificos/` [CAT], `reportes/sistema/` [SYS], `docs/modulos/` [MOD])**: Consolidated laboratory knowledge.

---

## 3. Structural Codebase Navigation: Graphify-First Protocol

Blind recursive text searches (`grep -r` across 200 files) are strictly prohibited. Always inspect the graph before reading source code:

1. **Query Relationships**:
   ```bash
   graphify query "<concept or target functionality>"
   graphify path "<Component_A>" "<Component_B>"
   graphify explain "<module or class>"
   graphify affected "<modified_component>"
   ```
2. **Context Budgeting**: Read only the subgraphs and target files identified by Graphify.
3. **Mandatory Post-Modification Hook**:
   Every time Python source files (`.py`) are modified, execute:
   ```bash
   graphify update .
   ```
   *Zero API cost ($0.00)*. Ensures the AST graph remains synchronized with reality.

---

## 4. Hardware Safety Gates & Interlocks

> [!CAUTION]
> **Strict Hardware Protection Mandate:**
> Never execute raw commands targeting physical instrumentation without explicit human approval and pre-validation in simulation.

* **Nanopositioning (PI E-517)**: Travel limits are strictly restricted to $0 \le X, Y, Z \le 100\ \mu\text{m}$. Never bypass closed-loop sensor checks.
* **Laser Shutters & Flippers**: Digital lines (`Dev1/port0/line0:3`) require the autonomous 500 ms heartbeat watchdog. Power flippers on analog outputs (`Dev1/ao0`, `ao1`) must remain decoupled from safety shutters.
* **Safe Development**: Default to `SAFE_MODE = True` in mock configurations for all testing and automated verification.

---

## 5. Multi-Round Deliberative Implementation Protocol

For any non-trivial implementation, new tool, module, experiment, or architectural modification, NEVER jump directly into coding. Strictly follow the phased deliberation lifecycle:

### 🔄 Round 1: Conceptual & Theoretical Exploration (The "Think First" Round)
1. **Deep Conceptual Understanding**: Paraphrase and analyze the request from first principles (physics, metrology, chemistry). Explain *why* it matters and what physical/data mechanisms are involved.
2. **Theoretical Subagents Panel**: Dynamically convene domain agents based on task archetype (`physicist`, `computational-physicist`, `colloidal-chemist`, `metrology`, `experimentalist`).
3. **Non-Obvious Angles & Critical Trade-Offs**: Identify latent physical edge cases, thermal drift, optical noise, or parameter precedence conflicts.
4. **Devil's Advocate & Falsification Probe (`devil-advocate`)**: Probe unstated assumptions and design failure modes.
5. **Proactive Suggestions & Key Questions**: Offer concrete architectural options (Option A vs B) and solicit user feedback.
*⛔ STOP & WAIT: Await explicit user answers, selection of suggestions, and conceptual approval.*

### 📐 Round 2: Technical Architecture & Engineering Blueprint (The "Design" Round)
1. **Executive Synthesis**: Comprehensive summary of the agreed concept, integrating user decisions and accepted suggestions.
2. **Engineering Subagents Panel**:
   - `software-architect`: Thread topology (`QThread`), signal routing, AST impact (Graphify), and **Mandatory Dual-Track Flowchart (Mermaid)** contrasting *User Journey* vs *Data/Hardware Pipeline*.
   - `instrumentation`: DAQmx lines, timing margins, watchdog heartbeat, piezo travel limits, driver collision prevention.
   - `qa-ux-auditor`: Ergonomic layout, 4-rule ROIs (`blockSignals`), `FigureExportStudioDialog`, Click-to-Seed modes.
   - `interactive-tool-design` skill: DoF Inventory & Automation Ladder (Layers 0-3).
3. **Verification & Testing Strategy**: Unit tests (`pytest`), simulation validation (`SAFE_MODE = True`), and rollback safeguards.
*⛔ STOP & WAIT (or Optional Round 3): Await user review. If ambiguities remain, execute a brief Hybrid Round 3.*

### ⚙️ Phase 4: Hard Implementation (The "Execution" Phase)
Once approved, execute changes with atomic precision: write clean code, add tests, verify 0 regressions, execute `graphify update .`, and update user manuals.

---

## 6. Subagent Dispatch Matrix

When facing complex tasks, delegate to the specialized subagents in `.claude/agents/`:

| Subagent | Role & Focus | Primary Triggers |
| :--- | :--- | :--- |
| **`physicist`** | Theoretical nanophotonics & plasmonics | Equations, asymptotic limits, forces, DLVO, Debye-Waller |
| **`computational-physicist`** | Numerical FDTD, Monte Carlo & GPU/BLAS | Meshes, CFL stability, PML boundaries, near-field hot-spots, DDA |
| **`experimentalist`** | Lab reality & optical alignment | Noise, thermal drift ($\sim 1\ \text{nm/min}$), photobleaching, colloids |
| **`instrumentation`** | Real-time HAL & DAQmx | Drivers, timing, buffer overruns, watchdog, TTL polarities |
| **`metrology`** | Measurement validity & statistics | ISO/GUM, Cramér-Rao lower bound, NUFFT, Hosemann paracrystal |
| **`software-architect`** | PyQt6 & clean architecture | `QThread`, `pyqtSignal`, DAQmx error `-200088` prevention, Pytest |
| **`qa-ux-auditor`** | Laboratory UX, ergonomics & manual QA | Usability, presets, physical units, panic controls, MANUAL_USUARIO |
| **`scientific-reviewer`** | Methodological peer review | Scientific defensibility, validity regimes, citation verification |
| **`devil-advocate`** | Anti-sycophancy & falsification | Unstated assumptions, confirmation bias, experimental edge cases |
| **`colloidal-chemist`** | Surface chemistry & nanofabrication | APTES silanization, CTAC/KCl nanocavities, DLVO, EBL vs printing |
| **`agent-trainer`** | Continuous alignment & prompt evolution | Failure trace post-mortems, prompt patching, golden exemplars, topology |

---

## 7. Procedural Skills Directory

Execute procedural routines defined in `.claude/skills/*/SKILL.md`:
* **`scientific-evaluation`**: Tripartite analysis (Local Knowledge $\leftrightarrow$ Literature $\leftrightarrow$ Inferences).
* **`literature-crosscheck`**: Cross-referencing claims against primary sources via Zotero/Crossref.
* **`physics-model-review`**: Analytical derivation, dimensional consistency, and energy conservation.
* **`instrumentation-analysis`**: Real-time signal timings, hardware hazards, and isolation.
* **`metrology-review`**: Quantitative uncertainty propagation and confidence limits ($k=2$).
* **`experiment-design`**: Generating testable recipes, controls, and falsification criteria.
* **`knowledge-integrator`**: Atomic updates across `CAT`, `SYS`, Ledgers, and Graphify.
* **`scientific-documentation`**: Automated generation of SOPs, manuals, and technical reports.
* **`interactive-tool-design`**: DoF inventories, customization ladders (Layers 0-3), and dual-track user/pipeline flowcharts.
* **`deliberative-implementation`**: Multi-round deliberation protocol, dynamic agent panels, and engineering blueprints.

---

## 8. Epistemic Ledgers: Evidence & Decisions

* **Evidence Ledger (`docs/evidence/EVIDENCE_LEDGER.md`)**: Whenever introducing or auditing a scientific claim, log its ID, statement, status, assumptions, source DOI/CAT, and source code lines.
* **Decision Ledger (`docs/decisions/DECISION_LOG.md`)**: Record all architectural, experimental, and calibration choices following the standard ADR template.

---

## 9. Quality Gates & Commit Protocol

All modifications must pass two quality gates:
1. **Pre-Commit Verification**: Run unit tests (`pytest tests/`) and ensure 0 regressions.
2. **Conventional Commits**: Format commits with clear semantic prefixes (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `phys:`).
