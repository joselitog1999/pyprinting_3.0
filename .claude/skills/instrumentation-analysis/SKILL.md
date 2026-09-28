---
name: instrumentation-analysis
description: Audits hardware control routines, driver interfaces, timing budgets, buffer configurations, and safety fail-safes for NI-DAQmx, PI piezo controllers, lasers, and cameras. Use when modifying or debugging hardware control code or inspecting real-time acquisition loops.
---

# Instrumentation Analysis Skill

This skill governs the systematic inspection, timing analysis, and safety auditing of hardware drivers and Real-Time Hardware Abstraction Layers (HAL) in PyPrinting 3.0.

## Overview

Hardware control code interfaces with real, physical instruments. Software delays, buffer overruns, race conditions, or unhandled exceptions can result in physical actuator collisions, burnt lasers, or corrupted datasets.

---

## Step-by-Step Execution Protocol

### Step 1: Interface & Channel Mapping
1. Identify all physical channels used in the routine:
   * Digital I/O (e.g., `Dev1/port0/line8`–`line11` for the laser shutters, with 532 nm on `line11` active-LOW — `config.SHUTTER_CHANNELS` / `SHUTTER_POLARITY`).
   * Digital I/O, detection mirror: `Dev1/port0/line7` (*up* → confocal detector and Canon, *down* → spectrometer). The code calls it `flipper_notch532`, a legacy naming error; it is a toggle whose position the software does not know (C-08).
   * Analog Output (e.g., `Dev1/ao0` / `ao1` for the neutral-density filter flipper: *up* → low power, *down* → high power; `Dev1/ao2` for the 532 nm modulation).
   * Analog Input (e.g., `Dev1/ai0` for the 532 nm photodiode; full map in `config.PD_CHANNELS`, with `ai3` doubling as photodiode and Z trigger, C-44).
   * USB / serial (e.g., the PI E-517 connects over USB, `ConnectUSB` in `config.py`).
   * Values and backing: `.claude/shared/lab-invariants.md` §2.
2. Check for resource conflicts: Ensure no two tasks attempt to reserve the same physical channel simultaneously.
3. Treat code comments about wiring, filters or actuators as claims to verify, not facts: "Flipper Notch 532" survived from legacy 1.0 into the code although the line moves the detection mirror. For how the bench behaves, the legacy programs (PyPrinting in `Obsidian_Vault/printing2/`, PySpectrum in `scratch/pyspectrum-legacy/`) worked and are the reference (researcher, R1-12); re-check any finding that implies the legacy could not have worked.

### Step 2: Timing & Latency Budgeting
1. Quantify execution timing requirements:
   * Deterministic timing requirements (e.g., shutter opening duration), taken from a measurement or a datasheet, never from a monograph: the documented "< 1 ms" trace latencies were refuted (D-01).
   * Effective sampling cadence, measured, not the configured task rate. The print trace has no established cadence today: in `main` its continuous task overflows (C-01), and "10 kHz" was never an effective rate.
   * Buffer sizing: Verify circular ring buffer capacity is sufficient to withstand worst-case OS thread scheduling latency ($\ge 500\ \text{ms}$ buffer depth).
2. Inspect loop sleep statements: Replace non-deterministic `time.sleep()` with high-precision monotonic timing (`time.perf_counter()`) or hardware clock synchronization.

### Step 3: Safety Interlocks & Watchdog Auditing
1. Confirm fail-safe defaults:
   * In the event of an unhandled Python exception, is `core/safety_excepthook.py` installed in that entry point, so every shutter is written to its **closed** state at its own polarity? Never read "line at 0 V" as "closed": the 532 nm shutter (`line11`) is active-LOW, so 0 V means **open**, and an undriven line falls to 0 V through the PCIe-6353 pull-down (`BANCO-16`).
   * Is the `ShutterWatchdog` thread armed, and does every shutter-holding loop renew `heartbeat_shutter()` per iteration within the 30 s default deadline (`core/nidaq.py::_default_timeout_s`)? The call must carry no argument: an explicit `heartbeat_shutter(30.0)` overrides the operator's "Sin límite" setting (C-29).
   * Policy (researcher, R1-10, R2-8): the watchdog must never cut a healthy routine; the protection against a hung routine will be the routine's own liveness beat (design pending, never exempt). Flag any change to watchdog behavior as requiring Rounds 1-2.
2. Verify boundary checks on physical stages:
   * Are piezo axes clamped per axis, $0 \le X, Y \le 100\ \mu\text{m}$ and $0 \le Z \le 20\ \mu\text{m}$ (`config.PI_AXIS_RANGE_UM`, `clamp_axis_um()`)?
   * Does every on-target wait go through `config.wait_on_target()` and act on `False` (close shutters, abort or pause)? A stage communication failure trips an interlock and is never followed by an automatic reconnect (`DEC-036`).
   * Does the routine check controller status bits before initiating moves?

### Step 4: Driver Lifecycle & Resource Cleanup
1. Confirm that all DAQmx tasks use context managers (`with Task() as task:`) or explicit `try...finally` blocks with `task.stop()` and `task.close()`.
2. Verify that mock modes (`mock=True` / `SAFE_MODE=True`) execute cleanly in headless environments without calling native C DLLs.

---

## Deliverable Format

```markdown
# Instrumentation Audit: [Module / Routine Name]

## 1. Hardware Interface Summary
* **Subsystem**: [e.g., Photothermal Printing Shutter Engine]
* **DAQ Channels**: `Dev1/port0/line8` (TTL Digital Out, 637 nm shutter, active-HIGH — state each line's polarity; 532 nm on `line11` is active-LOW)
* **USB / Serial Interfaces**: [e.g., PI E-517 over USB]

## 2. Timing & Concurrency Verification
* **Required Timing**: [value, with its source: measurement or datasheet]
* **Jitter Margin**: [measured value]
* **Buffer Risk**: `LOW` / `BUFFER_OVERRUN_RISK`

## 3. Safety Interlock Checklist
- [x] Piezo coordinate bounding enforced per axis (X, Y: $0-100\ \mu\text{m}$; Z: $0-20\ \mu\text{m}$)
- [x] Every on-target wait bounded (`wait_on_target`), `False` handled; no automatic stage reconnect
- [x] Emergency stop disconnects all active tasks
- [x] Watchdog armed; heartbeat renewed per loop iteration (30 s default deadline)
- [x] Mock mode parity verified for offline development

## 4. Verdict & Actionable Fixes
* **Status**: `APPROVED_FOR_BENCH` / `HAZARD_DETECTED`
* **Recommendations**: [Specific driver adjustments]
```
