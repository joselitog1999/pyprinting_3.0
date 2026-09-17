# Template: Scientific Evidence Claim

```yaml
claim_id: "PHY-XXX"
statement: "Clear, unambiguous statement of the physical or mathematical principle."
status: "SUPPORTED | PROVISIONAL | FALSIFIED | REQUIRES_CALIBRATION"
domain: "nanophotonics | plasmonics | colloids | metrology | instrumentation"
assumptions:
  - "Assumption 1 (e.g., dipole approximation ka << 1)"
  - "Assumption 2 (e.g., constant solvent temperature T=298 K)"
  - "Assumption 3 (e.g., homogeneous dielectric medium)"
sources:
  literature:
    - doi: "10.xxxx/xxxxx"
      citation: "Author et al., Journal, Year"
      quote_or_formula: "Original formula or empirical constant"
  local_compendium:
    - doc_id: "CAT-XXX"
      section: "Section Title"
implementation:
  code_files:
    - path: "core/example.py"
      lines: "L120-L145"
      function: "calculate_force()"
validation:
  experiment_id: "EXP-XXX"
  simulation_script: "tests/test_physics_model.py"
  last_verified: "YYYY-MM-DD"
  verified_by: "physicist | metrologist"
notes: |
  Any edge case observations, known caveats, or planned refinements.
```
