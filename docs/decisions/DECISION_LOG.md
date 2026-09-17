# Architecture & Experimental Decision Log — PyPrinting 3.0

**Location**: `docs/decisions/DECISION_LOG.md`  
**Purpose**: Chronological log of major architectural, experimental, and calibration choices made in PyPrinting 3.0.

---

## Decisions Index

| Decision ID | Date | Title | Status | Deciders | Linked Docs |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `DEC-001` | 2026-08-10 | Decoupling Power Flipper from Shutter Safety Lines | `ACCEPTED` | Instrumentation, QA | `SYS-202` |
| `DEC-002` | 2026-08-20 | Dedicated 500 ms Autonomous Watchdog Heartbeat | `ACCEPTED` | Software Architect, HAL | `SYS-201` |
| `DEC-003` | 2026-09-01 | Adoption of HDF5 Container with Shuffle+Gzip | `ACCEPTED` | Metrology, Data Scientist | `CAT-401` |
| `DEC-004` | 2026-09-16 | Migration to Claude Lab OS (Agents + Skills Ecosystem) | `ACCEPTED` | Lead Dev, Meta-Architect | `CLAUDE.md` |
| `DEC-005` | 2026-09-16 | Event Isolation via `_results_stale` Flag in Lattice Disorder Analyzer (Bloque 5/6/Fourier) | `ACCEPTED` | Software Architect, QA/UX, Metrology | `SW-001`, `analysis/lattice_disorder_gui.py` |
| `DEC-006` | 2026-09-16 | Real `QThread` (`moveToThread`) for LineScanSpectroscopyWorker — First Exception to the QTimer-on-GUI-Thread Convention in PySpectrum | `ACCEPTED` | Software Architect, Instrumentation | `pyspectrum/modules/routines/linescan_spectroscopy.py` |
| `DEC-007` | 2026-09-16 | Formal ADR: Dedicated `QThread` Worker for LineScan Spectroscopy (Considered Options & Traceability) | `ACCEPTED` | Software Architect, Instrumentation | `SYS-101`, `SYS-102`, `SYS-104`, complements `DEC-006` |
| `DEC-008` | 2026-09-16 | Metrological Traceability of Transmittance/Extinction Datasets in LineScan Spectroscopy HDF5 (Raw vs. `_physical`) | `ACCEPTED` *(minor follow-ups open)* | Scientific Reviewer, Metrology | `SYS-104`, `CAT-401`, `core/sif_processor.py` |

---

## Summary of Key Historic Decisions

### DEC-001: Decoupling Power Flipper from Shutter Safety Lines
* **Context**: Previously, moving the neutral density (ND) optical flipper relied on shared digital lines, causing race conditions when emergency shutters triggered.
* **Decision**: Actuate the flipper strictly via analog voltage steps (+5V) on `Dev1/ao0` and `Dev1/ao1`, completely isolated from digital lines `port0/line0:3`.
* **Outcome**: Shutter panic close is unconditionally preserved regardless of flipper motion state.

### DEC-006: Real `QThread` for LineScanSpectroscopyWorker
* **Context**: Every existing PySpectrum routine (`growth_kinetics.py`, `hyperspectral_confocal.py`, `dimers.py`, `luminescence.py`) runs its `Backend(QObject)` on the GUI thread, driven by a `QTimer` whose steps are short (~20ms) and non-blocking. The new linescan routine's steps can legitimately block from hundreds of ms (single-window mode) to several seconds/minutes per spatial point (Step & Glue mode: multiple grating moves, each gated by `wait_until_ready()`, plus exposure time). A software-architect + instrumentation review of the blueprint found that running this in the GUI thread would risk the shutter heartbeat and the emergency-abort button going unresponsive during a blocking `time.sleep()`/polling call.
* **Decision**: `LineScanSpectroscopyWorker(QObject)` is moved to a dedicated `QThread` via `moveToThread()` (see `create_linescan_routine()` in `pyspectrum/modules/routines/linescan_spectroscopy.py`). The worker never relies on `hardware_session.emergencyStopSignal` to interrupt an in-progress blocking wait (a Qt signal is only delivered when the receiving thread returns to its event loop); instead it polls the thread-safe `hardware_session.is_emergency_stopped` property between every blocking sub-step, mirroring the `_abort_requested` pattern already used in `step_and_glue.py`. `heartbeat_shutter(30.0)` is called on every tick of any blocking wait (piezo settle polling, grating settle polling, exposure wait), not just once per step, since a single Step & Glue point can exceed the watchdog's 30s timeout.
* **Outcome**: First routine in PySpectrum 3.0 to use a real `QThread`. GUI remains responsive and the local/global abort paths remain effective during arbitrarily long acquisitions. Verified via `tests/test_linescan_h5.py` (9/9 passing) and the full `pytest tests/` suite (176 passed, no regressions).

### DEC-007: Formal ADR — Dedicated `QThread` Worker for the Linear Scan Spectroscopy Routine

* **Decision ID**: `DEC-007`
* **Title**: Dedicated `QThread` (`moveToThread`) Worker for the Linear Scan Spectroscopy Routine — First Departure from PySpectrum's QTimer-on-GUI-Thread Convention
* **Date**: 2026-09-16
* **Status**: `ACCEPTED`
* **Deciders**: Software Architect, Instrumentation

**1. Context & Problem Statement**
PySpectrum 3.0 has five acquisition routines. Four of them — `growth_kinetics.py`, `hyperspectral_confocal.py`, `dimers.py`, `luminescence.py` — run a `Backend(QObject)` on the GUI thread, driven by a `QTimer` whose steps are short (~20 ms) and non-blocking. The new Linear Scan Spectroscopy routine (`linescan_spectroscopy.py`) breaks that assumption: a single spatial point can block for hundreds of ms (Single-Window mode) to several seconds or minutes (Step & Glue mode), stacking piezo settle waits, one or more grating moves gated by `spectrometer.is_moving()`, and camera exposure time. Running this on the GUI thread would starve the Qt event loop during each blocking call: neither the shutter watchdog heartbeat nor the emergency-abort button could be serviced, since `pyqtSignal` delivery — including `hardware_session.emergencyStopSignal` — only happens once the receiving thread returns to its event loop.

**2. Decision Drivers**
* Shutter watchdog heartbeat and emergency-abort must stay serviceable through acquisitions that can exceed the watchdog's 30 s heartbeat timeout by orders of magnitude.
* GUI responsiveness (`SYS-101`) must hold under sustained blocking hardware polling.
* Reuse already-validated abort and HDF5 patterns over new abstractions.
* Preserve Liskov substitution on the HDF5 container schema.

**3. Considered Options**
* **Option A — Keep the `QTimer`-on-GUI-thread convention**: consistent with the other four routines; rejected because a single blocking sub-step (grating settle, exposure) can exceed the heartbeat cadence by orders of magnitude, leaving shutters and abort unresponsive.
* **Option B — `AcquisitionStrategy` class hierarchy** for the two acquisition modes: rejected as over-engineering; `step_and_glue.py` already resolves the same two-mode dilemma with sibling methods and no base class.
* **Option C (chosen) — `LineScanSpectroscopyWorker(QObject)` on a dedicated `QThread`** via `moveToThread()`, polling `hardware_session.is_emergency_stopped` between every blocking sub-step instead of trusting signal delivery mid-wait, mirroring the `_abort_requested` pattern already used in `step_and_glue.py`.

**4. Decision Outcome**
Chosen option: **Option C**, the only one that keeps the watchdog and abort paths responsive through arbitrarily long blocking waits without adding unneeded abstractions. `create_linescan_routine()` builds `LineScanSpectroscopyWidget` + `LineScanSpectroscopyWorker`, calls `worker.moveToThread(thread)`, wires widget→worker request signals and worker→widget result signals, then starts the thread. `_should_abort()` (`_cancel_requested or hardware_session.is_emergency_stopped`) gates `_sleep_with_heartbeat()`, `_move_and_settle()` (piezo, `pi.qONT()` polling, 5 s timeout) and `_settle_wavelength()` (grating, `spectrometer.is_moving()`, 6 s timeout); each re-issues `heartbeat_shutter(30.0)` per tick, not just once per step. Exposure wait adds `ACQUISITION_READOUT_MARGIN_S` (0.05 s, a documented placeholder — no real EMCCD readout model exists yet). Persistence uses the standalone `write_linescan_spectroscopy_hdf5()`, not a `BatchHDF5Container` subclass, reusing only its `shuffle+gzip(4)` compression under an independent hierarchical schema.

*Positive Consequences*: first PySpectrum routine with a verified-responsive abort/watchdog path across arbitrarily long acquisitions; no blind `time.sleep()` — every settle wait is hardware-polled with an explicit timeout and post-settle verification (`pi.qPOS` vs. `PIEZO_POSITION_TOLERANCE_UM`); zero LSP violation on the HDF5 layer.

*Negative Consequences / Trade-offs*: introduces PySpectrum's first real `moveToThread()` lifecycle, requiring explicit teardown (`_cleanup()` in `create_linescan_routine()`, plus `PySpectrumWindow.closeEvent()`) that the `QTimer` routines never needed; `ACQUISITION_READOUT_MARGIN_S = 0.05 s` remains an undocumented-physics placeholder pending a real EMCCD readout model; the two acquisition modes diverge structurally (sibling methods, no shared interface) — the same shape already used in `step_and_glue.py`.

**5. Physical / Code Traceability**
* **Affected Modules**: `pyspectrum/modules/routines/linescan_spectroscopy.py` (`LineScanSpectroscopyWorker`, `LineScanSpectroscopyWidget`, `create_linescan_routine`), `core/hdf5_container.py` (`write_linescan_spectroscopy_hdf5`), `tests/test_linescan_h5.py`.
* **Linked Compendiums**: `SYS-101`, `SYS-102`, `SYS-104`; complements `DEC-006`.

### DEC-008: Metrological Traceability of Transmittance/Extinction Datasets in LineScan Spectroscopy
* **Context**: Peer review of `linescan_spectroscopy.py`'s T/E pipeline and its HDF5 serialization (`core/hdf5_container.py::write_linescan_spectroscopy_hdf5`), specifically whether reusing `sif_processor.py`'s shared functions and storing an unclamped raw dataset alongside a derived `_physical` one is metrologically defensible.
* **Decision / Review Verdict**: Reusing `compute_transmittance_with_errors()`/`compute_extinction()` (shared with `sif_analyzer.py`) is the correct traceability choice — both modules derive T/E from the same audited implementation rather than parallel reimplementations. The raw-vs-physical split is metrologically sound: clamping raw T would bias a symmetric dark-noise residual (a GUM violation), so an unclamped raw dataset plus a derived `transmission_*_physical` copy is consistent practice, and the NaN gate (weak reference) is properly decoupled from the positivity clamp (signal sign) — two orthogonal guards, not conflated.
  Two non-blocking gaps found during review: (1) `transmission_*_physical = clip(T, 0, None)` floors at exactly `0.0`, not the `1e-6` epsilon `compute_extinction()` uses internally — a non-Python consumer computing `-log10()` directly on `_physical`, as its own `rationale` attribute invites, would hit `-inf` rather than `NaN`. Note that `extinction_1d/2d` in this pipeline are actually computed from the raw `T`, not from `_physical` — the derived dataset is written for external/downstream consumers but is not itself consumed anywhere in this pipeline, so its own `rationale` ("positividad fisica... no correccion metrologica") slightly overstates its current role. (2) The noise multiplier and per-row `noise_threshold_2d` are not persisted to HDF5, only inferable from `noise_threshold_1d`/`sigma_dark_1d`.
* **Outcome**: Core design **ACCEPTED**; the two gaps above are logged as non-blocking follow-up items (candidates: clamp `_physical` at `1e-6` instead of `0.0`, and persist `noise_threshold_2d`/the multiplier explicitly). Verified against `tests/test_linescan_h5.py` (9/9 passing).

### DEC-002: Dedicated 500 ms Autonomous Watchdog Heartbeat
* **Context**: A Python crash during high-power laser irradiation could leave physical shutters open, destroying samples and objectives.
* **Decision**: Implement an autonomous background thread issuing 500 ms heartbeats to the DAQmx digital line. If the heartbeat expires without renewal, hardware auto-trips to closed state.
* **Outcome**: Zero sample damage even during unhandled Python runtime terminations.

### DEC-005: Event Isolation via `_results_stale` Flag in Lattice Disorder Analyzer
* **Context**: An internal audit (computational-physicist, metrology, qa-ux-auditor) found that `_update_real_space_analysis()` in `analysis/lattice_disorder_gui.py` silently cascaded Bloque 5 (cluster detection), Bloque 6 (grid/vacancy fit) and Fourier reciprocal-space recalculation from 12+ unrelated call sites (particle deletion, undo/revert curation, ROI apply, image invert, and — most critically — `_on_load_image()`, which could recompute clusters/grid/g(r) against a newly loaded image while still holding `locs_df` positions from the previous image). This violated the GUM traceability principle that every reported quantity must be attributable to a single, frozen input state, and contradicted the explicitly requested strict sequential flow (each block fires only from its own button).
* **Decision**: Replace the silent cascade with a `self._results_stale: bool` flag plus a non-blocking amber badge (`lbl_stale_badge`) shown in Pestaña 1. Any mutation of `locs_df` (curation, ROI, image reload) now only re-renders the particle scatter and marks results stale — it never recomputes Bloque 5/6/Fourier automatically. `_on_recalc_grid()` and `_on_recalculate_reciprocal()` remain the sole entry points for those computations and clear the flag on execution. `_on_load_image()` additionally hard-resets `locs_df`/`locs_df_raw`/`cluster_results`/`kdtree_results`/`rdf_results`/`reciprocal_results` to structurally prevent cross-image computation. A companion `unmarked_indices` set + red-square (🟥) scatter layer + "Desenmarcar" button was added so multi-Gaussian-resolved particles remain visually flagged for review until the user explicitly dismisses them.
* **Outcome**: Bloque 5, Bloque 6 and Fourier are now strictly confined to their own buttons; every reported metrological quantity is traceable to an explicit, user-triggered recompute. Verified via `pytest tests/` (33/33 lattice_disorder/export tests passing, no regressions in unrelated pre-existing failures).
