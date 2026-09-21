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
   * Digital I/O (e.g., `Dev1/port0/line0:3` for Uniblitz shutters).
   * Analog Output (e.g., `Dev1/ao0`, `ao1` for flippers).
   * Analog Input (e.g., `Dev1/ai0` for photodiode capture).
   * Serial / COM ports (e.g., PI E-517 controller, laser diode SCPI).
2. Check for resource conflicts: Ensure no two tasks attempt to reserve the same physical channel simultaneously.

### Step 2: Timing & Latency Budgeting
1. Quantify execution timing requirements:
   * Deterministic microsecond requirements (e.g., laser shutter opening duration $\Delta t \sim 5-50\ \text{ms}$).
   * Sampling rates (e.g., $10\ \text{kHz}$ on DAQmx analog input).
   * Buffer sizing: Verify circular ring buffer capacity is sufficient to withstand worst-case OS thread scheduling latency ($\ge 500\ \text{ms}$ buffer depth).
2. Inspect loop sleep statements: Replace non-deterministic `time.sleep()` with high-precision monotonic timing (`time.perf_counter()`) or hardware clock synchronization.

### Step 3: Safety Interlocks & Watchdog Auditing
1. Confirm fail-safe defaults:
   * In the event of an unhandled Python exception, do digital lines drop to 0V (shutter closed)?
   * Is the autonomous 500 ms heartbeat watchdog active?
2. Verify boundary checks on physical stages:
   * Are piezo axes clamped to $0.0 \le X,Y,Z \le 100.0\ \mu\text{m}$?
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
* **DAQ Channels**: `Dev1/port0/line0` (TTL Digital Out)
* **Serial Interfaces**: COM3 (PI E-517, 115200 baud)

## 2. Timing & Concurrency Verification
* **Required Timing**: Deterministic $10\ \text{ms}$ pulse.
* **Jitter Margin**: $\pm 0.2\ \text{ms}$.
* **Buffer Risk**: `LOW` / `BUFFER_OVERRUN_RISK`

## 3. Safety Interlock Checklist
- [x] Piezo coordinate bounding enforced ($0-100\ \mu\text{m}$)
- [x] Emergency stop disconnects all active tasks
- [x] Watchdog heartbeat active (500 ms timeout)
- [x] Mock mode parity verified for offline development

## 4. Verdict & Actionable Fixes
* **Status**: `APPROVED_FOR_BENCH` / `HAZARD_DETECTED`
* **Recommendations**: [Specific driver adjustments]
```
