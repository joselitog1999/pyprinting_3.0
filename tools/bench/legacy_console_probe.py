# -*- coding: utf-8 -*-
"""
legacy_console_probe.py — Sonda de SOLO LECTURA para la consola del PySpectrum legado.

Se ejecuta DENTRO del proceso legado que ya tiene la cámara abierta (menú Console Widget),
con una sola línea:

    exec(open(r"C:\\Users\\josel\\Documents\\Obsidian_Vault\\printing3\\tools\\bench\\legacy_console_probe.py", encoding="utf-8").read())

(ajustá la ruta si el repositorio está en otra carpeta; ver tools/bench/INSTRUCCIONES.txt)

GARANTÍAS — esta sonda NO llama a nada que modifique el estado de la cámara:
  * La cámara, SÓLO con getters de pylablib sobre el objeto que el legado ya abrió (regla de
    R4-F/R4-L, 2026-09-30): nada de ctypes contra la DLL de Andor. Sin set_*, setup_*,
    start/stop/abort_acquisition, clear, close ni snap.
  * Cada consulta va en try/except: un nombre que no exista en tu versión de pylablib
    imprime "no disponible" y sigue, sin romper nada.
  * No toca obturadores, láseres, DAQmx ni platina. Del espectrógrafo sólo LEE (sección D):
    ningún Set*, ni movimiento de red, ranura, flipper u obturador.
  * No escribe archivos, salvo `guardar_info(ruta)`, que escribe un JSON sólo en la ruta que le des.

Qué responde:
  A. ¿Está tapado el método set_acquisition_mode por la asignación `= 'cont'/'single'`?
  B. Modo de adquisición según pylablib y estado actual de la cámara.
  C. Modelo, tamaño del sensor y PITCH DEL PÍXEL leídos del hardware (ítem 1).
  D. RESPALDO de la calibración del espectrógrafo Shamrock: offsets de cada red, offset del
     detector, cero de las ranuras, geometría configurada y coeficientes de calibración. Sólo
     funciones Get* del objeto `mySpectrometer` que el legado ya abrió. Guardá esa salida antes
     de ejecutar PySpectrum 3.0 contra el equipo (ver docs/evidence/PRUEBAS_BANCO_PENDIENTES.md).
     Corré la sonda con el legado en reposo (sin Step & Glue ni barridos en curso), para no
     consultar el espectrógrafo mientras otro hilo lo está moviendo.
  E. Lo que BANCO-55 compara con PySpectrum 3.0: versión de pylablib, ventilador, VS, amplificador,
     ganancia EM, modo de lectura, capacidades, tiempos y `get_full_info()`.

Opcional:
    guardar_info(r"C:\\ruta\\legado.json")   # el mismo contenido en JSON, para comparar con 3.0
    observar_live()                           # con el Live ENCENDIDO: contador de cuadros, 1 s
"""

_RESUMEN = []
_INFO = {}


def _r(tag, txt):
    print(f"  [{tag}] {txt}")
    _RESUMEN.append(f"{tag}: {txt}")


def _try(fn, default="no disponible"):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — sonda de diagnóstico, nunca debe romper la app
        return f"{default} ({type(e).__name__}: {e})"


def _jsonable(obj):
    if hasattr(obj, "_asdict"):
        return {k: _jsonable(v) for k, v in obj._asdict().items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    try:
        return obj.item()          # escalares de numpy
    except Exception:
        return str(obj)


def _buscar_camara():
    try:
        import __main__
        cam = getattr(__main__, "myAndor", None)
        if cam is not None:
            return cam, "__main__.myAndor"
    except Exception:
        pass
    import gc
    for o in gc.get_objects():
        try:
            if type(o).__name__ == "AndorSDK2Camera":
                return o, "gc (instancia AndorSDK2Camera en memoria)"
        except Exception:
            continue
    return None, None


def _buscar_espectrografo():
    try:
        import __main__
        sh = getattr(__main__, "mySpectrometer", None)
        if sh is not None:
            return sh, "__main__.mySpectrometer"
    except Exception:
        pass
    import gc
    for o in gc.get_objects():
        try:
            if type(o).__name__ == "Shamrock" and hasattr(o, "ShamrockGetGratingOffset"):
                return o, "gc (instancia Shamrock en memoria)"
        except Exception:
            continue
    return None, None


def _seccion_d_respaldo_shamrock():
    """Sólo lectura: cada llamada es un Get* del wrapper legado (Shamrock_ps.py), que devuelve
    (ret, valor...). 20202 = SHAMROCK_SUCCESS; cualquier otro código se informa tal cual."""
    print("\nD — Respaldo de la calibración del Shamrock (sólo lectura)")
    sh, origen = _buscar_espectrografo()
    if sh is None:
        _r("D", "no encontré el espectrógrafo (ni __main__.mySpectrometer ni una instancia Shamrock)")
        return
    dev = 0
    _r("D.origen", origen)
    _r("D.serie", _try(lambda: sh.ShamrockGetSerialNumber(dev)))
    n = _try(lambda: sh.ShamrockGetNumberGratings(dev))
    _r("D.num_redes", n)
    n_redes = n[1] if isinstance(n, tuple) and len(n) > 1 and isinstance(n[1], int) else 3
    for g in range(1, n_redes + 1):
        _r(f"D.red{g}.info(ret,lineas,blaze,home,offset)", _try(lambda g=g: sh.ShamrockGetGratingInfo(dev, g)))
        _r(f"D.red{g}.offset(ret,pasos)", _try(lambda g=g: sh.ShamrockGetGratingOffset(dev, g)))
    _r("D.detector_offset(ret,pasos)", _try(lambda: sh.ShamrockGetDetectorOffset(dev)))
    for idx in (1, 2, 3, 4):
        _r(f"D.ranura{idx}.cero(ret,pasos)", _try(lambda idx=idx: sh.ShamrockGetSlitZeroPosition(dev, idx)))
    _r("D.red_actual(ret,red)", _try(lambda: sh.ShamrockGetGrating(dev)))
    _r("D.lambda_central(ret,nm)", _try(lambda: sh.ShamrockGetWavelength(dev)))
    _r("D.pixel_width(ret,um)", _try(lambda: sh.ShamrockGetPixelWidth(dev)))
    _r("D.num_pixels(ret,n)", _try(lambda: sh.ShamrockGetNumberPixels(dev)))
    _r("D.coef_calibracion(ret,A,B,C,D)", _try(lambda: sh.ShamrockGetPixelCalibrationCoefficients(dev)))


# Lo que BANCO-55 compara con PySpectrum 3.0 (getters de pylablib 1.4.3, verificados en su fuente)
_BANCO55_GETTERS = (
    "get_fan_mode", "get_vsspeed", "get_all_vsspeeds", "get_amp_mode", "get_all_amp_modes", "get_EMCCD_gain",
    "get_read_mode", "get_acquisition_mode", "get_capabilities", "get_frame_timings", "get_cycle_timings",
    "get_readout_time", "get_shutter_parameters", "get_temperature_setpoint", "is_cooler_on",
    "get_temperature_status", "get_trigger_mode", "get_data_dimensions", "get_image_mode_parameters",
    "get_single_track_mode_parameters", "get_frames_status",
)


def _sonda():
    global _RESUMEN, _INFO
    _RESUMEN = []
    _INFO = {"origen": "legado"}
    print("=" * 72)
    print("SONDA DE SOLO LECTURA — PySpectrum legado (cámara por pylablib)")
    print("=" * 72)

    try:
        import pylablib
        _INFO["pylablib_version"] = getattr(pylablib, "__version__", "desconocida")
    except Exception as e:  # noqa: BLE001
        _INFO["pylablib_version"] = f"no disponible ({e})"
    _r("pylablib", _INFO["pylablib_version"])

    cam, origen = _buscar_camara()
    if cam is None:
        print("  No encontré la cámara (ni __main__.myAndor ni una AndorSDK2Camera en memoria).")
        return
    _r("cam", f"{type(cam).__module__}.{type(cam).__name__}  (encontrada vía {origen})")

    # ── A. ¿Método tapado por la asignación? (introspección pura, cero hardware) ──
    print("\nA — ¿set_acquisition_mode sigue siendo un método?")
    inst = vars(cam) if hasattr(cam, "__dict__") else {}
    if "set_acquisition_mode" in inst:
        _r("A", f"TAPADO: la instancia tiene set_acquisition_mode = {inst['set_acquisition_mode']!r} "
                f"(un {type(inst['set_acquisition_mode']).__name__}, no un método). La línea "
                f"`myAndor.set_acquisition_mode = '...'` NO llama al SDK.")
    else:
        _r("A", f"intacto en esta sesión: set_acquisition_mode es "
                f"{type(getattr(cam, 'set_acquisition_mode', None)).__name__}. Todavía no corrió "
                f"el camino de Live/adquisición que lo pisa — volvé a correr la sonda después de usar Live.")

    # ── B. Modo y estado ─────────────────────────────────────────────────────
    print("\nB — Modo de adquisición y estado")
    _r("B.modo_pylablib", _try(lambda: cam.get_acquisition_mode()))
    _r("B.estado", _try(lambda: cam.get_status()))
    _r("B.adquiriendo", _try(lambda: cam.acquisition_in_progress()))
    _r("B.exposicion_s", _try(lambda: cam.get_exposure()))
    _r("B.temperatura_C", _try(lambda: cam.get_temperature()))

    # ── C. Identidad y geometría ─────────────────────────────────────────────
    print("\nC — Identidad y geometría (pylablib)")
    _r("C.device_info", _try(lambda: cam.get_device_info()))
    _r("C.detector_size", _try(lambda: cam.get_detector_size()))
    ps = _try(lambda: cam.get_pixel_size())
    if isinstance(ps, (tuple, list)) and ps and isinstance(ps[0], (int, float)):
        um = [v * 1e6 if v < 1e-3 else v for v in ps]
        _r("C.pixel_size", f"crudo={tuple(ps)}  -> {um[0]:.2f} x {um[1]:.2f} um")
    else:
        _r("C.pixel_size", ps)

    # ── E. Lo que compara BANCO-55 ───────────────────────────────────────────
    print("\nE — Configuración para BANCO-55 (getters de pylablib)")
    settings = {}
    for name in _BANCO55_GETTERS:
        fn = getattr(cam, name, None)
        value = _try(fn) if callable(fn) else "no disponible en esta versión de pylablib"
        settings[name] = value
        _r(f"E.{name}", value)
    _INFO["settings"] = settings
    full = _try(lambda: cam.get_full_info())
    _INFO["camera_full_info"] = full
    _r("E.get_full_info", f"{len(full)} campos" if isinstance(full, dict) else full)

    _seccion_d_respaldo_shamrock()

    print("\n" + "=" * 72)
    print("RESUMEN — copiá y pegá este bloque:")
    print("=" * 72)
    for line in _RESUMEN:
        print(line)
    print("=" * 72)
    _INFO["resumen"] = list(_RESUMEN)
    print("Opcional: guardar_info(r\"C:\\ruta\\legado.json\")  y, con el Live ENCENDIDO, observar_live()")


def guardar_info(ruta):
    """Escribe lo leído por la sonda en un JSON, sólo en `ruta`. Para compararlo con la sonda de 3.0
    (BANCO-55). No toca el hardware: usa lo que ya se leyó."""
    import json
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(_jsonable(_INFO), f, ensure_ascii=False, indent=2)
    print(f"  guardado en {ruta}")


def observar_live(segundos=1.0):
    """Con el Live del legado ENCENDIDO: lee dos veces el contador de cuadros de pylablib
    (`get_frames_status`). Sólo lectura. Congela la GUI `segundos` (corre en su hilo); la cámara sigue
    adquiriendo en hardware, así que la medición es válida.

    También informa los cuadros SIN LEER: si el Live del legado nunca avanza el puntero de lectura
    (`read_oldest_image(self.shape)` pasa la forma como `peek`), ese número crece hasta llenar el búfer
    y el Live muestra un cuadro atrasado (hipótesis de BANCO-60, a verificar)."""
    import time
    cam, _origen = _buscar_camara()
    if cam is None:
        print("  No encontré la cámara.")
        return
    s1 = _try(lambda: cam.get_frames_status())
    time.sleep(segundos)
    s2 = _try(lambda: cam.get_frames_status())
    running = _try(lambda: cam.acquisition_in_progress())
    try:
        d = int(s2[0]) - int(s1[0])
        unread, skipped, size = int(s2[1]), int(s2[2]), int(s2[3])
    except Exception:
        print(f"  [live] no se pudo leer el contador: {s1} / {s2}")
        return
    if running is True and d > 1:
        v = "CONTINUO: el Live del legado realmente adquiere en flujo"
    elif d <= 1:
        v = "NO AVANZA: el Live del legado estaría mostrando un cuadro fijo"
    else:
        v = "ambiguo"
    print(f"  [live] cuadros en {segundos:.1f} s = {d}  adquiriendo={running}  -> {v}")
    print(f"  [live] sin leer = {unread} de un búfer de {size}, salteados = {skipped}"
          f"  (si 'sin leer' crece y queda cerca del búfer, el legado muestra un cuadro atrasado)")


_sonda()
