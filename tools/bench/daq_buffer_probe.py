# -*- coding: utf-8 -*-
"""
daq_buffer_probe.py — BANCO-26: tamaño real del buffer de una tarea continua a 10 kS/s

SÓLO ENTRADAS ANALÓGICAS. No crea tareas de salida, no toca obturadores, láseres, filtro de
densidad, espejo ni platina. No arranca ninguna adquisición: configura la tarea, la "confirma"
(commit, que es cuando NI-DAQmx asigna el buffer), lee el tamaño y la cierra.

Qué resuelve (docs/evidence/PRUEBAS_BANCO_PENDIENTES.md, BANCO-26): la regla de NI para el buffer
automático de una tarea continua es ambigua justo en 10 kS/s (10 000 o 100 000 muestras por canal).
Eso decide si el defecto de C-01 desbordaba a ≈ 1 s o a ≈ 10 s, y si la opción E puede fijar el
buffer explícitamente.

Reproduce la tarea que tenía la traza cuando usaba la tarea continua (C-01, antes de DEC-037):
  canales  Dev1/ai0, ai1, ai2, ai3, ai6   (config.PD_CHANS_LIST)
  tasa     10 000 S/s por canal          (config.RATE_MULTICHANNEL / 100)
  muestras samps_per_chan = 1000         (max(N·10, 1000) con N = 10)

Cómo se corre (con PyPrinting, el PySpectrum legado y Solis CERRADOS, o al menos sin la traza ni
ninguna lectura de fotodiodos en curso: si otro programa tiene las entradas, NI-DAQmx da -50103):
    python tools\\bench\\daq_buffer_probe.py
Copiá el bloque RESUMEN en BANCO-26.
"""
from __future__ import annotations

import sys

DEVICE = "Dev1"
CHANNELS = [0, 1, 2, 3, 6]
RATE = 10_000.0
SAMPS_PER_CHAN = 1000
EXPLICIT_BUFFER = 100_000


def _task(nidaqmx, AcquisitionType, TaskMode, explicit_buffer=None):
    task = nidaqmx.Task()
    for ch in CHANNELS:
        task.ai_channels.add_ai_voltage_chan(physical_channel=f"{DEVICE}/ai{ch}",
                                             name_to_assign_to_channel=f"chan_PD{ch}")
    task.timing.cfg_samp_clk_timing(rate=RATE, sample_mode=AcquisitionType.CONTINUOUS,
                                    samps_per_chan=SAMPS_PER_CHAN)
    before = task.in_stream.input_buf_size
    if explicit_buffer is not None:
        task.in_stream.input_buf_size = int(explicit_buffer)
    task.control(TaskMode.TASK_COMMIT)   # NI-DAQmx asigna el buffer al confirmar; no adquiere
    after = task.in_stream.input_buf_size
    return task, before, after


def main() -> int:
    try:
        import nidaqmx
        from nidaqmx.constants import AcquisitionType, TaskMode
    except Exception as e:
        print(f"No se pudo importar nidaqmx: {e}")
        return 2

    summary = {}
    try:
        system = nidaqmx.system.System.local()
        dv = system.driver_version
        summary["driver_nidaqmx"] = f"{dv.major_version}.{dv.minor_version}.{dv.update_version}"
        summary["nidaqmx_python"] = getattr(nidaqmx, "__version__", "?")
        dev = nidaqmx.system.Device(DEVICE)
        summary["placa"] = f"{dev.product_type} (serie {dev.dev_serial_num})"
    except Exception as e:
        summary["sistema"] = f"no se pudo leer: {e}"

    for label, explicit in (("automatico", None), (f"explicito_{EXPLICIT_BUFFER}", EXPLICIT_BUFFER)):
        task = None
        try:
            task, before, after = _task(nidaqmx, AcquisitionType, TaskMode, explicit)
            summary[f"buffer_{label}_antes_commit"] = before
            summary[f"buffer_{label}_despues_commit"] = after
            summary[f"buffer_{label}_segundos"] = round(after / RATE, 3)
        except Exception as e:
            summary[f"buffer_{label}"] = f"ERROR: {e}"
        finally:
            if task is not None:
                try:
                    task.close()
                except Exception as e:
                    summary[f"cierre_{label}"] = f"ERROR al cerrar: {e}"

    print("\n=== RESUMEN BANCO-26 ===")
    print(f"canales={','.join(f'ai{c}' for c in CHANNELS)} tasa={RATE:.0f} S/s/canal samps_per_chan={SAMPS_PER_CHAN}")
    for k, v in summary.items():
        print(f"{k}: {v}")
    print("Interpretación: buffer automático = 10000 -> el defecto de C-01 desbordaba a ≈ 1 s; "
          "= 100000 -> a ≈ 10 s. El explícito tiene que quedar en 100000 para la opción E.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
