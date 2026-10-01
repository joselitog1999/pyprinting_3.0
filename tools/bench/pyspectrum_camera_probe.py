# -*- coding: utf-8 -*-
"""
pyspectrum_camera_probe.py — Sonda de la cámara como la abre PySpectrum 3.0 (R4-N 2b; P5; BANCO-55)

Se corre desde una terminal, con el PySpectrum legado, Solis y PySpectrum 3.0 CERRADOS (la cámara admite un
solo programa):

    .venv\\Scripts\\python.exe tools\\bench\\pyspectrum_camera_probe.py --salida C:\\ruta\\3.0.json
    .venv\\Scripts\\python.exe tools\\bench\\pyspectrum_camera_probe.py --salida C:\\ruta\\3.0.json --comparar C:\\ruta\\legado.json
    .venv\\Scripts\\python.exe tools\\bench\\pyspectrum_camera_probe.py --estado-base --salida C:\\ruta\\3.0_base.json

Qué hace:
  1. **Conecta exactamente como 3.0** (`PylablibAndorCCD`, `CONNECT_KWARGS`). Esto NO es sólo lectura: al
     conectar, pylablib fija su configuración por defecto (ventilador en bajo, setpoint de −60 °C, obturador
     cerrado, ROI completo, ganancia EM 0), lo mismo que pasa al abrir 3.0.
  2. **Lee** con getters de pylablib los mismos datos que la sección E de la sonda del legado
     (`legacy_console_probe.py`), más `get_full_info`, identidad, geometría, exposición y temperatura.
  3. **Con `--estado-base`** (opcional, P5) aplica el estado base de 3.0 (`apply_camera_baseline`, el mismo
     del arranque) y vuelve a leer. Sin la opción, después de conectar no escribe nada en la cámara.
  4. **Con `--salida`** escribe un JSON con el formato de `guardar_info` del legado, más cada lectura con su
     resultado y el informe del estado base. Sin `--salida` no escribe ningún archivo.
  5. **Con `--comparar legado.json`** muestra en qué difiere de lo que leyó la sonda del legado.
  6. **Cierra la cámara**, pase lo que pase. El enfriador queda como lo deje el SDK al cerrar (R4-L; BANCO-57).

No adquiere, no abre obturadores (ni el de la cámara ni el del espectrómetro), no toca láseres, DAQmx,
platina ni espectrógrafo.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Los mismos getters que la sección E de la sonda del legado (BANCO-55), y los de identidad.
BANCO55_GETTERS = (
    "get_fan_mode", "get_vsspeed", "get_all_vsspeeds", "get_amp_mode", "get_all_amp_modes", "get_EMCCD_gain",
    "get_read_mode", "get_acquisition_mode", "get_capabilities", "get_frame_timings", "get_cycle_timings",
    "get_readout_time", "get_shutter_parameters", "get_temperature_setpoint", "is_cooler_on",
    "get_temperature_status", "get_trigger_mode", "get_data_dimensions", "get_image_mode_parameters",
    "get_single_track_mode_parameters", "get_frames_status",
)
IDENTITY_GETTERS = ("get_device_info", "get_detector_size", "get_pixel_size", "get_exposure", "get_temperature",
                    "get_status", "acquisition_in_progress")


def _jsonable(obj):
    """Como la sonda del legado: namedtuples a dict, numpy a escalares, lo demás a str."""
    if hasattr(obj, "_asdict"):
        return {k: _jsonable(v) for k, v in obj._asdict().items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    try:
        return obj.item()
    except Exception:
        return str(obj)


class _Reader:
    """Llama getters del objeto de pylablib y registra cada llamada con su resultado."""

    def __init__(self, cam, calls: List[Dict[str, Any]]):
        self.cam, self.calls = cam, calls

    def read(self, name: str, stage: str):
        fn = getattr(self.cam, name, None)
        if not callable(fn):
            self.calls.append({"stage": stage, "call": name, "ok": False, "detail": "no disponible en esta versión"})
            return "no disponible en esta versión de pylablib"
        try:
            value = fn()
        except Exception as e:  # noqa: BLE001 — sonda de diagnóstico
            self.calls.append({"stage": stage, "call": name, "ok": False, "detail": f"{type(e).__name__}: {e}"})
            return f"no disponible ({type(e).__name__}: {e})"
        self.calls.append({"stage": stage, "call": name, "ok": True})
        return value


def read_camera(cam, calls: List[Dict[str, Any]], stage: str) -> Dict[str, Any]:
    """Todo lo que lee la sonda, sólo con getters."""
    r = _Reader(cam, calls)
    out = {"identidad": {n: r.read(n, stage) for n in IDENTITY_GETTERS},
           "settings": {n: r.read(n, stage) for n in BANCO55_GETTERS},
           "camera_full_info": r.read("get_full_info", stage)}
    return _jsonable(out)


def _flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(d, list) and d and all(isinstance(v, dict) for v in d):
        for i, v in enumerate(d):
            out.update(_flatten(v, f"{prefix}{i}."))
    else:
        out[prefix[:-1]] = d
    return out


def compare(legacy: Dict[str, Any], ours: Dict[str, Any]) -> List[str]:
    """Diferencias entre la sonda del legado y la de 3.0, en `settings` y `camera_full_info`."""
    lines = []
    for section in ("settings", "camera_full_info"):
        a, b = _flatten(legacy.get(section) or {}), _flatten(ours.get(section) or {})
        for key in sorted(set(a) | set(b)):
            if key not in b:
                lines.append(f"{section}.{key}: legado {a[key]!r} · 3.0 sin dato")
            elif key not in a:
                lines.append(f"{section}.{key}: legado sin dato · 3.0 {b[key]!r}")
            elif a[key] != b[key]:
                lines.append(f"{section}.{key}: legado {a[key]!r} · 3.0 {b[key]!r}")
    return lines


def run(argv: Optional[List[str]] = None, *, camera_factory: Optional[Callable[[], Any]] = None,
        baseline_fn: Optional[Callable[[Any], Any]] = None, out: Callable[[str], None] = print) -> int:
    """La sonda. Devuelve el código de salida: 0 bien, 2 sin cámara, 3 si algo falló al leer o al guardar."""
    p = argparse.ArgumentParser(description="Sonda de la cámara como la abre PySpectrum 3.0 (BANCO-55).")
    p.add_argument("--estado-base", action="store_true",
                   help="aplica el estado base de 3.0 (escribe en la cámara lo mismo que 3.0 al arrancar)")
    p.add_argument("--salida", type=Path, help="JSON donde guardar lo leído (sin esto no escribe archivos)")
    p.add_argument("--comparar", type=Path, help="JSON de la sonda del legado (guardar_info) para comparar")
    args = p.parse_args(argv)

    from pyspectrum.drivers.andor_pylablib import CONNECT_KWARGS, PylablibAndorCCD
    drv = PylablibAndorCCD(camera_factory) if camera_factory is not None else PylablibAndorCCD()
    calls: List[Dict[str, Any]] = []
    info: Dict[str, Any] = {"origen": "pyspectrum3", "conexion": dict(CONNECT_KWARGS),
                            "estado_base_aplicado": bool(args.estado_base)}
    try:
        import pylablib
        info["pylablib_version"] = getattr(pylablib, "__version__", "desconocida")
    except Exception as e:  # noqa: BLE001
        info["pylablib_version"] = f"no disponible ({e})"
    out("=" * 72)
    out("SONDA DE LA CÁMARA — como la abre PySpectrum 3.0 (pylablib)")
    out("=" * 72)
    out(f"  pylablib {info['pylablib_version']} · conexión {CONNECT_KWARGS}")

    if not drv.initialize():
        out(f"  No se pudo abrir la cámara: {drv.unavailable_reason}")
        return 2
    code = 0
    try:
        cam = drv._cam
        info.update(read_camera(cam, calls, "al conectar"))
        _print_section(out, "Al conectar", info)
        if args.estado_base:
            from pyspectrum.modules.camera_baseline import apply_camera_baseline
            report = (baseline_fn or apply_camera_baseline)(drv)
            items = [_jsonable(asdict(i) if is_dataclass(i) else i) for i in getattr(report, "items", [])]
            info["estado_base"] = {"items": items, "resumen": getattr(report, "summary", lambda: "")()}
            out(f"\nEstado base aplicado: {info['estado_base']['resumen']}")
            info["despues_estado_base"] = read_camera(cam, calls, "después del estado base")
            _print_section(out, "Después del estado base", info["despues_estado_base"])
        info["llamadas"] = calls
        failed = [c for c in calls if not c["ok"]]
        if failed:
            out(f"\n  {len(failed)} lecturas no disponibles: " + ", ".join(c["call"] for c in failed))
        if args.comparar is not None:
            try:
                legacy = json.loads(Path(args.comparar).read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                out(f"\n  No se pudo leer {args.comparar}: {e}")
                code = 3
            else:
                ours = info.get("despues_estado_base", info) if args.estado_base else info
                diffs = compare(legacy, ours)
                info["diferencias_con_legado"] = diffs
                out(f"\nDiferencias con el legado ({args.comparar.name}): {len(diffs)}")
                for line in diffs:
                    out(f"  {line}")
        if args.salida is not None:
            try:
                args.salida.parent.mkdir(parents=True, exist_ok=True)
                args.salida.write_text(json.dumps(_jsonable(info), ensure_ascii=False, indent=2), encoding="utf-8")
                out(f"\n  guardado en {args.salida}")
            except Exception as e:  # noqa: BLE001
                out(f"\n  No se pudo guardar {args.salida}: {e}")
                code = 3
    finally:
        drv.close()
        out("  cámara cerrada")
    return code


def _print_section(out, title: str, data: Dict[str, Any]) -> None:
    out(f"\n{title}:")
    for group in ("identidad", "settings"):
        for k, v in (data.get(group) or {}).items():
            out(f"  [{k}] {v}")
    full = data.get("camera_full_info")
    out(f"  [get_full_info] {len(full)} campos" if isinstance(full, dict) else f"  [get_full_info] {full}")


if __name__ == "__main__":
    sys.exit(run())
