---
name: scientific-evaluation
description: Executes macro-level tripartite evaluation (Local Knowledge vs External Literature vs Inferences) to assess scientific validity, identify hidden methodological gaps, and justify model choices. Coordinates physics-model-review, literature-crosscheck, and metrology-review.
---

# Scientific Evaluation Skill

This skill governs the end-to-end evaluation of scientific hypotheses, optical models, algorithms, and experimental methodologies in PyPrinting 3.0.

## Overview & The Tripartite Evaluation Model

Every scientific evaluation must explicitly decouple and contrast three distinct cognitive layers:
* **Layer A (Local Knowledge)**: Information already written in `docs/`, `reportes/cientificos/` (CAT), `reportes/sistema/` (SYS), or code comments. It is a set of claims to test, not a source: the 2026-09-27 audit found unsourced and false values copied between these documents, and code comments about wiring, filters or actuators that outlived the hardware they described. The machine-verified exception is the ✅ rows of `.claude/shared/lab-invariants.md`.
* **Layer B (External Literature)**: Peer-reviewed papers, textbook derivations, official standards, and manufacturer datasheets — searched in the researcher's order (R1-8): the bibliography in `docs/bibliografia/` first, then the researcher, then the web. For how the system behaves, the legacy programs worked and are the reference (R1-12). An unpublished figure from the researcher, or a method in development, is EXPERIMENTAL.
* **Layer C (Inference & Hypotheses)**: Logical deductions made by the agent, clearly labeled as non-empirical inferences.

---

## Step-by-Step Execution Protocol

### Step 1: Query Local Graph & Knowledge Base
1. Run Graphify to locate existing models and code connections:
   ```bash
   graphify query "<target concept or model>"
   ```
2. Read the specific `CAT-XXX` or `SYS-XXX` files linked to the topic.
3. Extract stated equations, empirical parameters, and documented limitations.

### Step 2: Gather External Evidence
1. Start with `docs/bibliografia/` (verified keys and pages in `lab-invariants` §9); use Zotero MCP (`zotero_search`, `get_item_metadata`) or other literature tools to reach further, following the order above.
2. Verify:
   * What are the accepted standard values for the relevant physical constants?
   * Under what boundary conditions does the theoretical approximation hold?
   * Are there competing or more recent formulations?

### Step 3: Tripartite Contrast & Gap Analysis
Compare Layer A and Layer B across five critical dimensions:
1. **Consistency**: Does our implementation match standard literature definitions?
2. **Discrepancies**: Are there divergent formulas, missing terms, or inconsistent signs?
3. **Implicit Assumptions**: What assumptions are baked into the code without being documented?
4. **Parameter Origins**: Are empirical numbers (e.g., laser power, threshold voltages) justified?
5. **Alternative Models**: Is there a more modern or computationally efficient formulation?

### Step 4: Multi-Agent Consultation (Optional / High-Impact)
For major architectural or physical changes, consult the specialized subagents:
* Summon `physicist` for mathematical rigor.
* Summon `experimentalist` for bench reality.
* Summon `devil-advocate` for hidden flaws.

---

## Deliverable Format

Structure the output as follows:

```markdown
# Scientific Evaluation: [Topic / Concept]

## 1. Local Baseline (Layer A)
- **Relevant Documents**: [[CAT-XXX]], [[SYS-XXX]]
- **Current Formulation**: $Equation$
- **Code Implementation**: `path/to/module.py:L100-L125`

## 2. External Evidence & Literature (Layer B)
- **Primary Sources**: [Author et al., Year, DOI]
- **Standard Convention**: $Literature Equation$
- **Validation Bounds**: Bounds on parameters $\lambda, T, P$.

## 3. Comparative Gap Analysis
| Dimension | Local Implementation | Literature Standard | Status |
| :--- | :--- | :--- | :--- |
| Equation Form | ... | ... | MATCH / DISCREPANCY |
| Validity Regime | ... | ... | ADEQUATE / OVEREXTENDED |
| Parameters | ... | ... | JUSTIFIED / UNVERIFIED |

## 4. Inferences & Open Questions (Layer C)
- *Inference 1*: ...
- *Untested Assumption*: ...

## 5. Synthesis & Recommendations
- [ ] Action item 1 (Update CAT-XXX)
- [ ] Action item 2 (Fix code discrepancy)
```
