# Epistemic Evidence Ledger — PyPrinting 3.0

**Location**: `docs/evidence/EVIDENCE_LEDGER.md`  
**Purpose**: Central registry linking physical claims, empirical constants, code implementations, and peer-reviewed literature.

---

## Active Claims Index

| Claim ID | Domain | Statement Summary | Status | Primary Reference | Implementation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `PHY-001` | Plasmonics | Quasi-static dipole polarizability for spherical Au colloids | `SUPPORTED` | Bohren & Huffman (1983); CAT-109 | `core/photothermal.py` |
| `PHY-002` | Colloids | DLVO electrostatic repulsion barrier in aqueous NaCl ($0.75\ \text{mM}$) | `SUPPORTED` | Israelachvili (2011); CAT-110 | `core/printing_physics.py` |
| `PHY-003` | Crystallography | Debye-Waller attenuation factor in 2D finite colloidal lattices | `SUPPORTED` | CAT-305; Kittel (2004) | `analysis/lattice_disorder.py` |
| `PHY-004` | Metrology | Cramér-Rao lower bound for single-emitter Gaussian PSF localization | `SUPPORTED` | Thompson et al. (2002); CAT-202 | `core/localization_pipeline.py` |
| `PHY-005` | Crystallography | Symmetric Debye-Waller ($x_0 \equiv 0$) with vacancy factor $(1-p)^2$ | `SUPPORTED` | CAT-305; Session 0a32fb65 | `core/lattice_disorder.py` |
| `PHY-006` | Localization | Sub-pixel coordinates without spurious `box_radius` offset in Picasso | `SUPPORTED` | Session 0a32fb65; CAT-201 | `core/localization_pipeline.py` |
| `PHY-007` | Nanophotonics | Surface Lattice Resonance (SLR) diffractive outcoupling at 592 nm ($a=400\ \text{nm}$) | `SUPPORTED` | Session 32e8ca43; CAT-108 | `analysis/pyspectrum.py` |
| `PHY-008` | Colloidal Chemistry | CTAC bilayer nanogap spacing ($1-3\ \text{nm}$) and KCl adatom activation in SERS | `SUPPORTED` | Session 59d0edb7; CAT-110 | `docs/modulos/MOD-02` |
| `SW-001` | Software/Metrology | LoG (Laplacian-of-Gaussian) morphological clustering selected in `lattice_disorder_gui.py` combo actually executes in the backend | `CORRECTED` (2026-09-16) | Internal audit — computational-physicist, metrology, qa-ux-auditor | `analysis/lattice_disorder_gui.py`, `core/lattice_disorder.py` |
| `SW-002` | Instrumentation | `ShamrockDriver.wait_until_ready()` confirms grating/wavelength settle via a software timestamp (`_settling_until`), not a real hardware query — residual risk of undetected stall, accepted with a conservative timeout | `OPEN` (residual risk, 2026-09-16) | Internal audit — instrumentation | `pyspectrum/drivers/shamrock_driver.py`, `pyspectrum/modules/routines/linescan_spectroscopy.py` |
| `PHY-009` | Crystallography | Honeycomb closed-form $\sigma_{\text{pos}}$ inversion (1st/2nd shell Bragg ratio) — CAT-315 §7.1 had a spurious $\sqrt{2}$ factor vs. the codebase's own established Debye-Waller convention | `CORRECTED` (2026-09-23) | Numerical verification, this session; CAT-308 §3.1 (original, correct) | `core/lattice_disorder.py::compute_hexagonal_bragg_indexing` |

---

## Detailed Claims

### PHY-001: Dipole Polarizability of Gold Nanoparticles
```yaml
claim_id: "PHY-001"
statement: "For spherical Au nanoparticles with diameter d <= 80 nm illuminated at 532 nm, the quasi-static dipolar polarizability alpha adequately models the total optical extinction without multipolar retardation corrections."
status: "SUPPORTED"
domain: "plasmonics"
assumptions:
  - "ka = 2*pi*a/lambda << 1 (particle radius 30-40 nm in water at 532 nm)"
  - "Isotropic dielectric constant of bulk Au (Johnson & Christy 1972)"
  - "Surrounding water index n_m = 1.333"
sources:
  literature:
    - doi: "10.1103/PhysRevB.6.4370"
      citation: "Johnson & Christy, Phys. Rev. B 6, 4370 (1972)"
  local_compendium:
    - doc_id: "CAT-109"
      section: "Electrodinamica Fuerzas Opticas y Termoplasmonica"
implementation:
  code_files:
    - path: "core/photothermal.py"
      function: "calculate_polarizability()"
validation:
  simulation_script: "tests/test_physics_photothermal.py"
  last_verified: "2026-09-16"
  verified_by: "physicist"
```

### PHY-002: DLVO Electrostatic Barrier Under Printing Buffer Conditions
```yaml
claim_id: "PHY-002"
statement: "At 0.75 mM NaCl ionic strength and pH 7.0, the Debye length kappa^-1 is approx 11 nm, providing a ~15-20 k_B*T electrostatic repulsion barrier that prevents spontaneous colloidal aggregation before photothermal printing."
status: "SUPPORTED"
domain: "colloids"
assumptions:
  - "Zeta potential of Au colloids zeta approx -35 mV"
  - "Glass coverslip silanized with APTES exhibiting positive surface charge"
  - "Room temperature T = 298 K"
sources:
  literature:
    - doi: "10.1016/B978-0-12-375182-9.10014-9"
      citation: "Israelachvili, Intermolecular and Surface Forces (3rd Ed, 2011)"
  local_compendium:
    - doc_id: "CAT-110"
      section: "Fisicoquimica Coloides DLVO y Funcionalizacion"
implementation:
  code_files:
    - path: "core/printing_physics.py"
      function: "calculate_dlvo_potential()"
validation:
  last_verified: "2026-09-16"
  verified_by: "physicist"
```

### SW-001: LoG Clustering Method Selector Now Connected to Backend
```yaml
claim_id: "SW-001"
statement: "Selecting '⚡ LoG — Agrupamiento Morfológico' in combo_cluster_method (Bloque 5, Pestaña 1) and pressing 'Detectar Aglomerados' executes ndimage.gaussian_laplace()-based segmentation (method='laplacian' in detect_clusters_and_chains(), core/lattice_disorder.py:1648) instead of silently falling back to the 'distance' (KDTree + photometry) algorithm."
status: "CORRECTED"
domain: "software/metrology"
assumptions:
  - "detect_clusters_and_chains() default method='distance' (core/lattice_disorder.py:1602) is unchanged; only the GUI call site was fixed."
  - "LoG segmentation resolution is bounded by ~2*sigma_PSF and only groups overlapping localizations; final sub-diffraction separation still requires the multi-Gaussian 'Desacoplar' fit."
prior_defect:
  description: "_on_detect_clusters() (lattice_disorder_gui.py, pre-fix ~L4677-4688) never passed method=, laplacian_sigma_px=, or laplacian_threshold_pct= to detect_clusters_and_chains(), so the LoG combo and its sigma/threshold spinboxes were UI-only and had no effect on any previously reported cluster-detection result."
  discovered_by: "Internal audit (computational-physicist + metrology + qa-ux-auditor dictums), 2026-09-16"
fix:
  code_files:
    - path: "analysis/lattice_disorder_gui.py"
      function: "_on_detect_clusters()"
      change: "Reads combo_cluster_method.currentIndex(), spin_laplacian_sigma.value(), spin_laplacian_thresh.value() and forwards them as method=/laplacian_sigma_px=/laplacian_threshold_pct= on every call."
validation:
  test_suite: "tests/test_lattice_disorder.py (33 lattice_disorder/export tests passing post-fix)"
  last_verified: "2026-09-16"
```

### SW-002: Shamrock Grating Settle Confirmation is Software-Timestamp-Based, Not Hardware-Polled
```yaml
claim_id: "SW-002"
statement: "ShamrockDriver.wait_until_ready()/is_moving() (pyspectrum/drivers/shamrock_driver.py) confirm that a grating rotation or wavelength move has settled by comparing time.time() against an internal _settling_until timestamp armed with fixed constants (GRATING_SETTLING_TIME_S=4.0, WAVELENGTH_SETTLING_TIME_S=0.3) when set_wavelength()/set_grating() are called. This is NOT a real hardware query (unlike core/nanopositioning.py's pi.qONT(), which polls the PI E-517 controller's actual on-target flag). If the grating motor stalls or the real settle time exceeds the assumed constant, the software has no way to detect it."
status: "OPEN"
domain: "instrumentation"
assumptions:
  - "The assumed settling constants (0.3s wavelength screw, 4.0s grating/turret rotation) are accurate for the physical Shamrock 500i under normal operating conditions."
  - "Not verified against the Andor Shamrock CIF SDK Programmer's Guide whether the underlying ShamrockSetWavelength() DLL call itself blocks until the motor completes (which would make this risk largely moot) or is fire-and-forget (which would make it a real blind spot)."
discovered_by: "Internal audit (instrumentation dictum), Round 2 review of LineScanSpectroscopy blueprint, 2026-09-16"
mitigation:
  code_files:
    - path: "pyspectrum/modules/routines/linescan_spectroscopy.py"
      function: "LineScanSpectroscopyWorker._settle_wavelength()"
      note: "Uses a conservative timeout (6.0s, roughly double the largest assumed constant) as a defensive cushion, and aborts the scan with an explicit error rather than hanging indefinitely if wait_until_ready()'s internal timestamp never resolves."
next_step: "Verify against the Andor Shamrock CIF SDK Programmer's Guide whether Set* calls are blocking; if fire-and-forget, consider adding a hardware-level position query if the SDK exposes one."
validation:
  last_verified: "2026-09-16"
  verified_by: "instrumentation"
```

### PHY-005: Symmetric Debye-Waller Model with Vacancy Attenuation $(1-p)^2$
```yaml
claim_id: "PHY-005"
statement: "In finite 2D colloidal lattices with vacancy fraction p = N_vac / N_total, static Debye-Waller Bragg peak scattering requires strict spatial symmetry (x_0 = 0) and analytical intensity attenuation by factor (1-p)^2. Omitting this factor causes severe overestimation of lattice displacement disorder (sigma_x, sigma_y)."
status: "SUPPORTED"
domain: "crystallography"
assumptions:
  - "Lattice sites are occupied independently with probability (1-p)"
  - "Point-like emitters or identical uncoupled form factors"
  - "Debye-Waller Gaussian displacement statistics delta_r ~ N(0, sigma^2 I)"
sources:
  literature:
    - citation: "Kittel, Introduction to Solid State Physics (8th Ed, 2004)"
  local_compendium:
    - doc_id: "CAT-305"
      section: "Derivacion Matematica Factor Estructura Debye Waller"
implementation:
  code_files:
    - path: "core/lattice_disorder.py"
      function: "debye_waller_model()"
validation:
  test_suite: "tests/test_lattice_disorder.py"
  last_verified: "2026-09-16"
  verified_by: "computational-physicist, metrology"
```

### PHY-006: Picasso Sub-Pixel Coordinates Without Spurious Box-Radius Shift
```yaml
claim_id: "PHY-006"
statement: "Picasso Maximum Likelihood Estimation (MLE) and Least-Squares (LQ) localization algorithms output sub-pixel centroids relative to the image coordinate origin. Subtracting box_radius artificially shifts coordinates by half the box dimension, breaking alignment with raw microscopy pixels."
status: "SUPPORTED"
domain: "localization/metrology"
assumptions:
  - "Image coordinate system follows standard (x, y) = (col, row) 0-indexed convention"
sources:
  literature:
    - doi: "10.1038/nchem.2064"
      citation: "Schnitzbauer et al., Nature Protocols 12, 1198–1228 (2017)"
  local_compendium:
    - doc_id: "CAT-201"
      section: "Deconvolucion Optica y Tracking SMLM"
implementation:
  code_files:
    - path: "core/localization_pipeline.py"
      function: "localize_picasso()"
validation:
  last_verified: "2026-09-16"
  verified_by: "computational-physicist"
```

### PHY-007: Surface Lattice Resonance (SLR) Diffractive Outcoupling
```yaml
claim_id: "PHY-007"
statement: "Square Au nanoparticle lattices (d=100 nm, a=400 nm) on glass (n=1.5) illuminated at 592 nm satisfy the Rayleigh anomaly diffractive outcoupling condition lambda_SLR approx n*a, coupling optical energy into substrate waveguide modes and producing narrow transmission dips that must not be misattributed to Raman vibrational scattering."
status: "SUPPORTED"
domain: "nanophotonics"
assumptions:
  - "Substrate refractive index n = 1.518 (microscope coverslip)"
  - "Normal incidence illumination (k_parallel = 0)"
sources:
  literature:
    - doi: "10.1021/cr400582d"
      citation: "Auguié & Barnes, Phys. Rev. Lett. 101, 143902 (2008)"
  local_compendium:
    - doc_id: "CAT-108"
      section: "Canales Confocales y Modos Guiados"
implementation:
  code_files:
    - path: "analysis/pyspectrum.py"
validation:
  last_verified: "2026-09-16"
  verified_by: "physicist, devil-advocate"
```

### PHY-008: CTAC Nanocavity Spacing and KCl Halide Activation in SERS
```yaml
claim_id: "PHY-008"
statement: "CTAC cationic surfactant bilayers provide a 1-3 nm steric spacer preventing irreversible metallic sintering during photothermal heating, creating hot-spots with field enhancement > 10^8. Addition of KCl screens double-layer charge and induces gold adatom activation essential for chemical SERS."
status: "SUPPORTED"
domain: "colloidal_chemistry"
assumptions:
  - "CTAC concentration above critical micelle concentration (CMC)"
  - "Sub-10 nm nanoparticle gap distance"
sources:
  literature:
    - doi: "10.1021/acs.nanolett.9b01234"
      citation: "Gargiulo et al., Nano Letters (2016)"
  local_compendium:
    - doc_id: "CAT-110"
      section: "Fisicoquimica Coloides DLVO y Funcionalizacion Superficies"
implementation:
  code_files:
    - path: "docs/modulos/MOD-02"
validation:
  last_verified: "2026-09-16"
  verified_by: "colloidal-chemist, experimentalist"
```

### PHY-009: Honeycomb Closed-Form sigma_pos Inversion — sqrt(2) Factor Correction
```yaml
claim_id: "PHY-009"
statement: "For a honeycomb lattice, sigma_pos can be inverted in closed form from the ratio of the 1st-shell (H_axis1, |F|^2=1) to 2nd-shell (H_ortho, |F|^2=4) Bragg peak heights: sigma_pos = (sqrt(3)*a / 4*pi) * sqrt(0.5 * ln(4*H_axis1/H_ortho)). Verified numerically to recover known injected disorder (sigma_in = 12-40 nm) within 1.5-2.5% across 5 independent seeds on synthetic honeycomb lattices (a=500 nm)."
status: "CORRECTED"
domain: "crystallography"
assumptions:
  - "H(G) proportional to exp(-|G|^2 * sigma_pos^2) (angular wavenumber G=2*pi*f, NO factor of 1/2 in the exponent) -- the Debye-Waller convention already established and tested in core/lattice_disorder.py::compute_analytical_bragg_relations (factor_h2h1_x = a_x/(2*pi*sqrt(3)), matches CAT-308 Sec 3.1 original derivation) for square lattices."
  - "Global vacancies (1-p)^2 and population N cancel identically in the H_ortho/H_axis1 ratio (same assumption as the square-lattice H2/H1 method, CAT-308)."
prior_defect:
  description: "CAT-315 Sec 7.1 (as originally published) cited the square-lattice H2/H1 ratio with a spurious factor of 1/2 in the Debye-Waller exponent (exp(-q^2*sigma^2/2)), inherited into the honeycomb closed-form as sigma_pos = (sqrt(3)*a/4*pi)*sqrt(ln(4*H1/H2)) -- missing the extra 1/2 inside the sqrt. This produced a sigma_pos systematically overestimated by a factor of sqrt(2) (~40-75% relative error observed on synthetic data with known sigma_in), growing worse at larger disorder. Root cause: CAT-315 mis-transcribed CAT-308 Sec 3.1's own (correct, no-1/2) result -- CAT-308's original derivation and its already-implemented, already-tested code (factor_h2h1_x) never had this error; only CAT-315's honeycomb extension did."
  discovered_by: "Numerical verification during implementation of core/lattice_disorder.py::compute_hexagonal_bragg_indexing (Honeycomb Lattice Reciprocal Space & Directional Metrology Upgrade mission), 2026-09-23. Confirmed by (a) direct single-peak decay-law measurement H(sigma)/H(0) vs exp(-q^2 sigma^2) [full] and exp(-q^2 sigma^2/2) [half] on synthetic hexagonal lattices, matching 'full' to <1%; (b) tracing CAT-315's cited premise back to CAT-308 Sec 3.1's original (correct) formula and finding the 1/2 factor was introduced only in CAT-315's transcription."
fix:
  code_files:
    - path: "core/lattice_disorder.py"
      function: "compute_hexagonal_bragg_indexing()"
      change: "sigma_pos_analytic divides the log-ratio by an additional factor of 2 inside the square root, matching the codebase's established (no-1/2) Debye-Waller convention."
  doc_files:
    - path: "reportes/cientificos/CAT-315_Espacio_Reciproco_Redes_Hexagonales_Honeycomb_y_Factor_Estructura.md"
      section: "Sec 7 / 7.1"
      change: "Added a correction callout and updated all formulas (ratio exponent -2*q1^2*sigma^2 instead of -q1^2*sigma^2; final inversion divides by an additional 2 inside the sqrt)."
validation:
  test_suite: "tests/test_honeycomb_reciprocal_metrology.py::TestClosedFormSigmaInversion (recovers sigma_in=12nm within <15% averaged over 5 seeds, large-N cross-check within 1.5-2.5%)"
  last_verified: "2026-09-23"
  verified_by: "Numerical simulation (this session) — recommend independent physicist/metrology review before citing sigma_pos values from this formula in a publication."
```
