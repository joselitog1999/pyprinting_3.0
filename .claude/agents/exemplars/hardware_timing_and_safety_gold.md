# Gold Exemplar: Canonical Safe Hardware Scan-Loop Pattern

Referenced by `instrumentation.md`, `software-architect.md`. Match this structure whenever writing or reviewing a stepped hardware acquisition loop (piezo scan, spectrometer sweep, camera stream).

## The Canonical Cycle
```
MOVE → SETTLE (bounded poll) → ACQUIRE → DECIMATE-EMIT → (row end: FLYBACK-MOVE → DAMPING PAUSE) → repeat
```
Each stage exists because skipping it reproduces a real post-mortem in this lab (`DEC-010`, `DEC-011`, `DEC-013`, `DEC-014`, `DEC-036`).

## Reference Implementation (schematic)
```python
from config import pi, clamp_axis_um, wait_on_target
from core.nidaq import heartbeat_shutter, close_all_shutters

def _scan_axis(self, axis, positions, timeout_s=5.0):
    for i, target in enumerate(positions):
        # 1. MOVE — never skip clamping, even for "small" relative steps (per axis: Z is 20 µm)
        pi.MOV(axis, clamp_axis_um(axis, target))

        # 2. SETTLE — bounded, confirmed by the closed loop; heartbeat on EVERY poll
        if not wait_on_target(axis, timeout_s=timeout_s, poll_s=0.003, on_tick=heartbeat_shutter):
            close_all_shutters()          # no confirmed arrival: never acquire, never continue
            self._abort(f"Axis {axis} did not confirm on-target within {timeout_s}s")
            return

        # 3. ACQUIRE
        sample = read_photodiode()

        # 4. DECIMATE-EMIT — never emit a heavy payload every tick
        self._row_buffer.append(sample)
        if i % DECIMATE_N == 0:
            self.dataSignal.emit(self._row_buffer.copy())   # throttled, not per-pixel

    # 5. FLYBACK — move FIRST, damping pause AFTER (not before)
    pi.MOV(axis, clamp_axis_um(axis, row_start))
    heartbeat_shutter()
    time.sleep(0.035)                     # >=35ms flyback damping, applied to the NEW position
```

## Why Each Line Is There (map to post-mortems)
| Line | Failure it prevents | Source |
|---|---|---|
| `clamp_axis_um(axis, target)` (also inside `MOV`) | Roundoff/tilt-compensation drift pushes the controller past physical limits; Z travel is 20 µm, not 100 µm | `instrumentation.md` §3.1, `DEC-036` |
| `wait_on_target(...)` instead of a hand-written `qONT()` loop | Unbounded poll hangs the whole worker forever on a stalled servo; `pi.qONT()` returns a **dict**, so `while not pi.qONT(axis)` never waits at all; a read failure used to be reported as on-target | `DEC-013` (`ANOM-FOCUS-03`), `DEC-014`, `DEC-036` |
| On `False`: close shutters and abort, never re-home or reconnect | Continuing after an unconfirmed arrival acquires at the wrong place with the laser open; an automatic reconnect homes the stage mid-routine | `DEC-036` |
| `heartbeat_shutter()` **inside** the settle loop, with no argument | A single call per node is not enough — a slow settle or long exposure alone can exceed the 30s watchdog deadline. No argument so the operator's policy governs: `heartbeat_shutter(30.0)` re-arms a fixed cut even in "Sin límite" mode (C-29) | `DEC-010`, `DEC-013` |
| Decimated `emit()` | Emitting a full frame/row every tick floods the Qt event queue and produces GC-pressure stutter, read by users as "the program hangs" | `DEC-013` |
| Flyback `MOV` **before** the damping `sleep` | A pause placed before the flyback move settles the *previous* pixel, not the flyback destination — the next trigger then fires mid-flight | `DEC-013` |
| `heartbeat_shutter()` before the flyback sleep too | Flyback pauses are exactly the kind of "in-between" wait that gets forgotten and silently drains the watchdog budget | `DEC-013` |

## Shutter State: Confirm, Don't Assume
```python
# WRONG — optimistic state update
self._shutter_open = True
nidaq.write_line(SHUTTER_LINE, True)     # if this raises, state already lied

# RIGHT — state follows confirmed hardware result
ok = nidaq.write_line(SHUTTER_LINE, True)
if not ok:
    raise HardwareWriteError("shutter line write failed — NOT marking open")
self._shutter_open = True
```
A state flag set before hardware confirmation is a **metrological claim with no evidence** — the watchdog and any downstream safety logic will trust it.

## Concurrency Placement
* The loop above runs on a `QObject` worker moved to a real `QThread` (`moveToThread`) — never inline in the GUI thread for anything that blocks $>$ a few ms per iteration.
* The mode/parameter combo that selects which axis-dispatch function runs must be `setEnabled(False)` for the full duration of the scan — see `qa-ux-auditor.md` §5 for why a mid-scan combo change orphans the Stop button's timer reference.

## Falsification Checklist Before Accepting This Pattern As Implemented
Ask (`devil-advocate.md` §6): where exactly is the flyback sleep relative to the flyback `MOV`? What happens if the shutter write throws? What happens if Stop is pressed after the combo changed mid-scan?
