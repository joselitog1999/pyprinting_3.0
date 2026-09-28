# -*- coding: utf-8 -*-
"""
andor_acquisition_mode_probe.py — Sonda de diagnóstico del protocolo de adquisición Andor.

Habla DIRECTAMENTE con la DLL del SDK de Andor (atmcd64d.dll) por ctypes, sin importar nada
de PySpectrum ni del código legado: responde preguntas sobre la CÁMARA, no sobre un wrapper.
Sólo necesita Python 3 en Windows y la DLL.

Qué responde (ver DEC-032 y la Ronda 1 sobre el protocolo de adquisición):
  T0  Modelo del detector, tamaño del sensor y PITCH DEL PÍXEL leídos del hardware.
      -> resuelve el conflicto 13 µm vs 8 µm de .claude/shared/lab-invariants.md §3.
  T1  Modo de adquisición POR DEFECTO tras Initialize (nadie en PySpectrum lo fija).
  T2  ¿La exposición empieza en StartAcquisition(), o recién al leer el primer cuadro?
  T3  ¿GetMostRecentImage() devuelve otra vez el mismo cuadro viejo, o NO_NEW_DATA?
  T4  ¿Funcionan en esta instalación los dos modos explícitos (Run Till Abort / Single +
      WaitForAcquisition)? Es la base de cualquier rediseño.

SEGURIDAD — qué hace y qué NO hace:
  * NO enciende el enfriador, NO acciona ningún obturador, NO toca láseres, DAQmx, la
    platina PI ni el espectrógrafo Shamrock. Sólo exposiciones cortas de la cámara.
  * La luz de la sala es irrelevante: se analizan estados y contadores, no el contenido.
  * Toda espera está acotada por timeout, y AbortAcquisition + ShutDown van en `finally`.

REQUISITOS antes de correrlo:
  1. Cerrar Andor Solis, el software legado y PySpectrum: la cámara sólo admite UN proceso.
  2. Cámara a temperatura ambiente (enfriador apagado). Por prudencia, el script se niega a
     continuar si lee una temperatura por debajo de -20 °C.

USO:
    python andor_acquisition_mode_probe.py                      (busca la DLL sola)
    python andor_acquisition_mode_probe.py "C:\\ruta\\atmcd64d.dll"
    python andor_acquisition_mode_probe.py --ini-dir            (pasa la carpeta de la DLL a Initialize)

Initialize se llama con una cadena vacía, como pylablib (la referencia probada en el banco) y el
driver de PySpectrum 3.0. Antes se le pasaba la carpeta de la DLL, y en el banco devolvió 0, que no
es un código del SDK (2026-09-28).

Al final imprime un bloque RESUMEN para copiar y pegar.
"""
import os
import sys
import time
from ctypes import (byref, c_char_p, c_float, c_int, c_long, c_ulong,
                    create_string_buffer, windll)

# ── Códigos del SDK de Andor (SDK2) ─────────────────────────────────────────
DRV_SUCCESS = 20002
DRV_NO_NEW_DATA = 20024
DRV_ACQUIRING = 20072
DRV_IDLE = 20073
CODE_NAMES = {DRV_SUCCESS: "DRV_SUCCESS", DRV_NO_NEW_DATA: "DRV_NO_NEW_DATA",
              DRV_ACQUIRING: "DRV_ACQUIRING", DRV_IDLE: "DRV_IDLE",
              # Tabla del legado (scratch/pyspectrum-legacy/ccd_ps.py), probada en el banco.
              20003: "DRV_VXDNOTINSTALLED", 20006: "DRV_ERROR_FILELOAD", 20013: "DRV_ERROR_ACK (no se comunica)",
              20070: "DRV_INIERROR", 20071: "DRV_COFERROR", 20075: "DRV_NOT_INITIALIZED",
              20089: "DRV_USBERROR", 20990: "DRV_ERROR_NOCAMERA", 20992: "DRV_NOT_AVAILABLE (otro programa la tiene)"}

ACQ_SINGLE, ACQ_RUN_TILL_ABORT = 1, 5
READ_FVB = 0
TRIGGER_INTERNAL = 0

SUMMARY = []
_DLL_DIR_HANDLES = []  # mantener vivos los directorios agregados con add_dll_directory


def name(code):
    return f"{code} ({CODE_NAMES.get(code, '?')})"


def report(tag, text):
    print(f"  [{tag}] {text}")
    SUMMARY.append(f"{tag}: {text}")


def load_dll():
    candidates = []
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        candidates.append(args[0])
    here = os.path.dirname(os.path.abspath(__file__))
    # Mismo orden que pylablib 1.4.3 (atmcd32d_lib.initlib), la referencia que funciona en el banco:
    # primero la variante _legacy y primero la carpeta de Solis. En el banco el legado carga
    # C:\Program Files\Andor SOLIS\atmcd64d_legacy.dll (2026-09-28); con atmcd64d.dll el SDK veía 0 cámaras.
    for folder in (r"C:\Program Files\Andor SOLIS", r"C:\Program Files\Andor SDK"):
        for name in ("atmcd64d_legacy.dll", "atmcd64d.dll"):
            candidates.append(os.path.join(folder, name))
    candidates.append(os.path.join(here, "..", "..", "pyspectrum", "drivers", "libs", "atmcd64d.dll"))
    for path in candidates:
        path = os.path.abspath(path)
        if os.path.exists(path):
            folder = os.path.dirname(path)
            os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
            # Desde Python 3.8, ctypes no busca en PATH las dependencias de la DLL: hace falta esto.
            if hasattr(os, "add_dll_directory"):
                _DLL_DIR_HANDLES.append(os.add_dll_directory(folder))
            print(f"DLL: {path}")
            return windll.LoadLibrary(path), folder
    print("DLL: buscando atmcd64d.dll en el PATH del sistema...")
    return windll.LoadLibrary("atmcd64d.dll"), ""


def status(dll):
    s = c_int()
    dll.GetStatus(byref(s))
    return s.value


def frames_acquired(dll):
    n = c_long()
    dll.GetTotalNumberImagesAcquired(byref(n))
    return n.value


def wait_idle(dll, timeout_s):
    """Espera acotada a que la cámara vuelva a IDLE, SIN leer ningún dato."""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        if status(dll) == DRV_IDLE:
            return time.perf_counter() - t0
        time.sleep(0.02)
    return None


def main():
    import platform
    import struct
    print(f"Python {platform.python_version()} de {struct.calcsize('P') * 8} bits ({sys.executable})")
    dll, sdk_dir = load_dll()
    # Diagnóstico previo, válido antes de Initialize: ¿el SDK ve alguna cámara?
    n_cams = c_long(-1)
    try:
        ret_n = dll.GetAvailableCameras(byref(n_cams))
        report("PRE", f"GetAvailableCameras -> {name(ret_n)}, cámaras = {n_cams.value}")
    except Exception as e:
        report("PRE", f"GetAvailableCameras no disponible: {e}")
    ini_dir = sdk_dir if "--ini-dir" in sys.argv else ""
    ret = dll.Initialize(c_char_p(ini_dir.encode("ascii")))
    if ret != DRV_SUCCESS:
        print(f"\nInitialize({ini_dir!r}) falló: {name(ret)}.")
        if ret == 0 or ret not in CODE_NAMES:
            print("  Ese valor no es un código del SDK (todos empiezan en 20001). Pegá también la línea 'DLL:'")
            print("  y la de GetAvailableCameras de arriba.")
        else:
            print("  ¿Quedó abierto Solis, el legado u otro proceso? (tasklist | findstr /i \"andor solis python\")")
        print("\n=== RESUMEN ===")
        for line in SUMMARY:
            print(line)
        print(f"INIT: Initialize({ini_dir!r}) -> {name(ret)}")
        return 1
    try:
        # ── T0: identidad y geometría leídas del hardware ─────────────────────
        print("\nT0 — Identidad y geometría del detector")
        model = create_string_buffer(256)
        dll.GetHeadModel(model)
        xp, yp = c_int(), c_int()
        dll.GetDetector(byref(xp), byref(yp))
        px, py = c_float(), c_float()
        ret_px = dll.GetPixelSize(byref(px), byref(py))
        temp = c_int()
        dll.GetTemperature(byref(temp))
        report("T0", f"modelo={model.value.decode(errors='replace')}  sensor={xp.value}x{yp.value} px  "
                     f"pitch={px.value:.2f} x {py.value:.2f} um (ret {name(ret_px)})  temp={temp.value} C")
        if temp.value < -20:
            print("\n  La cámara está fría (< -20 °C), probablemente enfriada por otro programa.")
            print("  Dejala volver a temperatura ambiente y reintentá. Se corta aquí por prudencia.")
            return 2

        width = xp.value
        dll.SetReadMode(c_int(READ_FVB))
        dll.SetTriggerMode(c_int(TRIGGER_INTERNAL))

        # ── T1: modo por defecto (NO se llama a SetAcquisitionMode) ───────────
        print("\nT1 — Modo de adquisición por defecto (sin SetAcquisitionMode)")
        dll.SetExposureTime(c_float(0.1))
        r = dll.StartAcquisition()
        time.sleep(2.0)
        st, n = status(dll), frames_acquired(dll)
        dll.AbortAcquisition()
        wait_idle(dll, 5.0)
        if st == DRV_ACQUIRING and n > 3:
            verdict = "CONTINUO (tipo Run Till Abort): el Live actual funcionaría"
        elif st == DRV_IDLE and n <= 1:
            verdict = "SINGLE SCAN: tomó 1 cuadro y paró -> el Live actual quedaría CONGELADO"
        else:
            verdict = "AMBIGUO: pegame el resultado"
        report("T1", f"start={name(r)}  estado a los 2 s={name(st)}  cuadros={n}  -> {verdict}")

        # ── T2: ¿la exposición empieza en StartAcquisition? ───────────────────
        print("\nT2 — ¿La exposición arranca en StartAcquisition()? (exposición 2 s, sin leer)")
        dll.SetAcquisitionMode(c_int(ACQ_SINGLE))
        dll.SetExposureTime(c_float(2.0))
        eff = c_float(); acc = c_float(); kin = c_float()
        dll.GetAcquisitionTimings(byref(eff), byref(acc), byref(kin))
        dll.StartAcquisition()
        elapsed = wait_idle(dll, 10.0)
        if elapsed is None:
            dll.AbortAcquisition()
            wait_idle(dll, 5.0)
            verdict = "NO terminó sin leer -> la integración esperaría a la lectura (respalda tu B)"
        else:
            verdict = (f"terminó sola en {elapsed:.2f} s SIN leer nada -> la exposición arranca en "
                       f"StartAcquisition() (contradice B)")
        report("T2", f"exposición efectiva={eff.value:.3f} s  -> {verdict}")

        # ── T3: ¿GetMostRecentImage devuelve otra vez el cuadro viejo? ────────
        print("\nT3 — Relectura del mismo buffer después de terminar")
        a = (c_long * width)()
        b = (c_long * width)()
        r1 = dll.GetMostRecentImage(a, c_ulong(width))
        r2 = dll.GetMostRecentImage(b, c_ulong(width))
        same = bytes(a) == bytes(b)
        if r1 == DRV_SUCCESS and r2 == DRV_SUCCESS and same:
            verdict = "devuelve el MISMO cuadro viejo cada vez -> riesgo de datos viejos con aspecto válido"
        elif r2 == DRV_NO_NEW_DATA:
            verdict = "la segunda lectura da NO_NEW_DATA -> el driver actual la convertiría en ceros"
        else:
            verdict = "comportamiento distinto: pegame el resultado"
        report("T3", f"lectura1={name(r1)}  lectura2={name(r2)}  idénticas={same}  -> {verdict}")

        # ── T4: ¿funcionan los modos explícitos? ──────────────────────────────
        print("\nT4 — Modos explícitos")
        dll.SetAcquisitionMode(c_int(ACQ_RUN_TILL_ABORT))
        dll.SetExposureTime(c_float(0.1))
        dll.StartAcquisition()
        time.sleep(1.0)
        st_rta, n_rta = status(dll), frames_acquired(dll)
        dll.AbortAcquisition()
        wait_idle(dll, 5.0)
        report("T4a", f"Run Till Abort 1 s: estado={name(st_rta)}  cuadros={n_rta}  "
                      f"-> {'OK, avanza' if st_rta == DRV_ACQUIRING and n_rta > 3 else 'NO avanza'}")

        dll.SetAcquisitionMode(c_int(ACQ_SINGLE))
        dll.SetExposureTime(c_float(0.1))
        dll.StartAcquisition()
        rw = dll.WaitForAcquisitionTimeOut(c_int(5000))
        report("T4b", f"Single + WaitForAcquisitionTimeOut(5 s): {name(rw)}  "
                      f"-> {'OK, el diseño por medición es viable' if rw == DRV_SUCCESS else 'FALLÓ'}")
        return 0
    finally:
        try:
            dll.AbortAcquisition()
        except Exception:
            pass
        dll.ShutDown()
        print("\nCámara liberada (AbortAcquisition + ShutDown).")
        if SUMMARY:
            print("\n" + "=" * 70)
            print("RESUMEN — copiá y pegá este bloque:")
            print("=" * 70)
            for line in SUMMARY:
                print(line)
            print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
