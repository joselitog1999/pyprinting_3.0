# -*- coding: utf-8 -*-
"""
legacy_console_probe.py — Sonda de SOLO LECTURA para la consola del PySpectrum legado.

Se ejecuta DENTRO del proceso legado que ya tiene la cámara abierta (menú Console Widget),
con una sola línea:

    exec(open(r"C:\\Users\\josel\\Documents\\Obsidian_Vault\\printing3\\tools\\bench\\legacy_console_probe.py", encoding="utf-8").read())

(ajustá la ruta si el repositorio está en otra carpeta; ver tools/bench/INSTRUCCIONES.txt)

GARANTÍAS — esta sonda NO llama a nada que modifique el estado de la cámara:
  * Sin Initialize, ShutDown, start/stop/abort_acquisition, set_*, setup_*, close ni snap.
  * Sólo getters de pylablib y funciones Get* del SDK de Andor sobre la sesión YA abierta.
  * Cada consulta va en try/except: un nombre que no exista en tu versión de pylablib
    imprime "no disponible" y sigue, sin romper nada.
  * No toca obturadores, láseres, DAQmx ni platina. Del espectrógrafo sólo LEE (sección D):
    ningún Set*, ni movimiento de red, ranura, flipper u obturador.

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

Opcional, con el Live View del legado ENCENDIDO:
    observar_live()      # mira 1 s el contador de cuadros (sólo lectura)
"""
import ctypes
from ctypes import byref, c_float, c_int, c_long, create_string_buffer

_RESUMEN = []


def _r(tag, txt):
    print(f"  [{tag}] {txt}")
    _RESUMEN.append(f"{tag}: {txt}")


def _try(fn, default="no disponible"):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — sonda de diagnóstico, nunca debe romper la app
        return f"{default} ({type(e).__name__}: {e})"


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


# El legado del banco carga atmcd64d_legacy.dll (Solis), el primer candidato de pylablib 1.4.3
# (hallazgo del 2026-09-28). Se prueban los dos nombres.
_SDK_NAMES = ("atmcd64d_legacy.dll", "atmcd64d.dll")


def _sdk():
    """La DLL que el proceso legado YA tiene cargada, para consultar la MISMA sesión inicializada.
    Sólo se usa un módulo ya cargado (GetModuleHandleW): nunca se carga una copia nueva, que no
    estaría inicializada y devolvería DRV_NOT_INITIALIZED."""
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetModuleHandleW.restype = ctypes.c_void_p
        k32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        for name in _SDK_NAMES:
            handle = k32.GetModuleHandleW(name)
            if handle:
                return ctypes.WinDLL(name, handle=handle)
    except Exception:
        pass
    return None


def _sonda():
    global _RESUMEN
    _RESUMEN = []
    print("=" * 72)
    print("SONDA DE SOLO LECTURA — PySpectrum legado")
    print("=" * 72)

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

    print("\nC — Contraste directo con el SDK (misma sesión, sólo funciones Get*)")
    dll = _sdk()
    if dll is None:
        _r("C.sdk", f"el proceso no tiene cargada ninguna de {_SDK_NAMES}")
    else:
        px, py = c_float(), c_float()
        rp = _try(lambda: dll.GetPixelSize(byref(px), byref(py)))
        xp, yp = c_int(), c_int()
        rd = _try(lambda: dll.GetDetector(byref(xp), byref(yp)))
        model = create_string_buffer(256)
        rm = _try(lambda: dll.GetHeadModel(model))
        st = c_int()
        rs = _try(lambda: dll.GetStatus(byref(st)))
        _r("C.sdk", f"GetHeadModel={model.value.decode(errors='replace')!r} (ret {rm})  "
                    f"GetDetector={xp.value}x{yp.value} (ret {rd})  "
                    f"GetPixelSize={px.value:.2f}x{py.value:.2f} um (ret {rp})  "
                    f"GetStatus={st.value} (ret {rs}; 20072=adquiriendo, 20073=idle)")

    _seccion_d_respaldo_shamrock()

    print("\n" + "=" * 72)
    print("RESUMEN — copiá y pegá este bloque:")
    print("=" * 72)
    for line in _RESUMEN:
        print(line)
    print("=" * 72)
    print("Opcional: con el Live View del legado ENCENDIDO, corré  observar_live()")


def observar_live(segundos=1.0):
    """Con el Live del legado ENCENDIDO: lee dos veces el contador de cuadros del SDK.
    Sólo lectura. Congela la GUI `segundos` (corre en su hilo); la cámara sigue adquiriendo
    en hardware, así que la medición es válida."""
    import time
    dll = _sdk()
    if dll is None:
        print(f"  el proceso no tiene cargada ninguna de {_SDK_NAMES}")
        return
    n1, n2, st = c_long(), c_long(), c_int()
    dll.GetTotalNumberImagesAcquired(byref(n1))
    time.sleep(segundos)
    dll.GetTotalNumberImagesAcquired(byref(n2))
    dll.GetStatus(byref(st))
    d = n2.value - n1.value
    if st.value == 20072 and d > 1:
        v = "CONTINUO: el Live del legado realmente adquiere en flujo"
    elif d <= 1:
        v = "NO AVANZA: el Live del legado estaría mostrando un cuadro fijo"
    else:
        v = "ambiguo"
    print(f"  [live] cuadros en {segundos:.1f} s = {d}  estado={st.value}  -> {v}")


_sonda()
