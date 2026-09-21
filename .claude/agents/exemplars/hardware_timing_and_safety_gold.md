# Gold Exemplar: Canonical Safe Hardware Scan-Loop Pattern

Referenced by `instrumentation.md`, `software-architect.md`. Match this structure whenever writing or reviewing a stepped hardware acquisition loop (piezo scan, spectrometer sweep, camera stream).

## The Canonical Cycle
```
MOVE → SETTLE (bounded poll) → ACQUIRE → DECIMATE-EMIT → (row end: FLYBACK-MOVE → DAMPING PAUSE) → repeat
```
Each stage exists because skipping it reproduces a real post-mortem in this lab (`DEC-002`, `DEC-003`, `DEC-013`, `DEC-014`).

## Reference Implementation (schematic)
```python
def _scan_axis(self, positions, timeout_s=5.0):
    for i, target in enumerate(positions):
        # 1. MOVE — never skip clamping, even for "small" relative steps
        pi.MOV(axis, clamp(target, 0.0, PI_STAGE_RANGE_UM))

        # 2. SETTLE — bounded poll, never `while True`, never a blind sleep
        t0 = time.monotonic()
        while not pi.qONT(axis):
            if time.monotonic() - t0 > timeout_s:
                raise TimeoutError(f"Axis {axis} did not settle within {timeout_s}s")
            heartbeat_shutter()          # renew watchdog EVERY iteration, not once per node
            time.sleep(0.003)             # >=3ms physical settle floor

        # 3. ACQUIRE
        sample = read_photodiode()

        # 4. DECIMATE-EMIT — never emit a heavy payload every tick
        self._row_buffer.append(sample)
        if i % DECIMATE_N == 0:
            self.dataSignal.emit(self._row_buffer.copy())   # throttled, not per-pixel

    # 5. FLYBACK — move FIRST, damping pause AFTER (not before)
    pi.MOV(axis, row_start)
    heartbeat_shutter()
    time.sleep(0.035)                     # >=35ms flyback damping, applied to the NEW position
```

## Why Each Line Is There (map to post-mortems)
| Line | Failure it prevents | Source |
|---|---|---|
| `clamp(target, 0, 100)` inside `MOV` | Roundoff/tilt-compensation drift pushes the controller past physical limits | `instrumentation.md` §3.1 |
| Bounded `qONT()` poll with `timeout_s` | Unbounded poll hangs the whole worker forever on a stalled servo | `DEC-013` (`ANOM-FOCUS-03`), `DEC-014` |
| `heartbeat_shutter()` **inside** the settle loop | A single call per node is not enough — a slow settle or long exposure alone can exceed the 30s watchdog deadline | `DEC-002`, `DEC-013` |
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
