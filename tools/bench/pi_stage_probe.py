# -*- coding: utf-8 -*-
"""
pi_stage_probe.py — Sonda de SÓLO LECTURA de la platina PI (controlador E-517).

Responde qué platina tiene conectada el controlador y cuál es su recorrido real por eje, para
confirmar el límite de Z que adoptó DEC-036 (20 µm, hoja de datos de la P-517.3CD) y el de
X/Y (100 µm). Prueba BANCO-17 de docs/evidence/PRUEBAS_BANCO_PENDIENTES.md.

GARANTÍAS — esta sonda NO mueve nada:
  * Sin MOV, MVR, SVO, VCO, ATZ, INI, WGO ni ningún comando que cambie el estado del
    controlador. Sólo consultas q* (IDN, SAI, CST, TMN, TMX, SVO, POS, ONT, ERR).
  * No es la conexión de PyPrinting: `config.pi.connect()` activa el servo y manda la platina
    a home; esta sonda usa pipython directamente y sólo abre y cierra la conexión USB.
  * Cada consulta va en try/except: una que el controlador no soporte imprime "no disponible".
  * Única excepción, documentada: qERR devuelve el último código de error del controlador y,
    como en todo controlador GCS, al leerlo lo borra. No mueve nada ni cambia el servo.

REQUISITOS: cerrar PyPrinting, el software legado y PIMikroMove (el controlador admite una
sola conexión USB a la vez). Python 3 con pipython instalado.

USO (desde la raíz del repositorio):
    python tools\\bench\\pi_stage_probe.py                 (usa el número de serie de config.py)
    python tools\\bench\\pi_stage_probe.py 0119048050      (número de serie explícito)
"""
import sys

DEFAULT_SERIAL = "0119048050"  # config.PI_SERIAL
AXES = ["1", "2", "3"]

SUMMARY = []


def report(tag, value):
    print(f"  [{tag}] {value}")
    SUMMARY.append(f"{tag}: {value}")


def ask(tag, fn):
    try:
        report(tag, fn())
    except Exception as e:  # noqa: BLE001 — sonda de diagnóstico
        report(tag, f"no disponible ({type(e).__name__}: {e})")


def main():
    serial = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SERIAL
    try:
        from pipython import GCSDevice
    except ImportError as e:
        print(f"pipython no está instalado en este Python: {e}")
        return 1

    dev = GCSDevice()
    try:
        try:
            found = dev.EnumerateUSB()
        except Exception as e:  # noqa: BLE001
            found = []
            print(f"Aviso al enumerar USB: {e}")
        print(f"Controladores PI por USB: {found}")
        target = next((d for d in found if serial in str(d)), found[0] if found else serial)
        print(f"Conectando (sólo USB, sin servo ni movimiento) a: {target}")
        dev.ConnectUSB(target)

        print("\nIdentidad")
        ask("idn", lambda: dev.qIDN().strip())
        ask("ejes", lambda: dev.qSAI())
        print("\nPlatina conectada por eje (qCST)")
        ask("tipo_platina", lambda: dev.qCST(AXES))
        print("\nRecorrido por eje, µm (qTMN / qTMX)")
        ask("recorrido_min", lambda: dev.qTMN(AXES))
        ask("recorrido_max", lambda: dev.qTMX(AXES))
        print("\nEstado actual (no se modifica)")
        ask("servo", lambda: dev.qSVO(AXES))
        ask("posicion", lambda: dev.qPOS(AXES))
        ask("on_target", lambda: dev.qONT(AXES))
        ask("error_pendiente", lambda: dev.qERR())
        return 0
    finally:
        try:
            dev.CloseConnection()
            print("\nConexión USB cerrada (la platina no se movió).")
        except Exception:
            pass
        if SUMMARY:
            print("\n" + "=" * 70)
            print("RESUMEN — copiá y pegá este bloque:")
            print("=" * 70)
            for line in SUMMARY:
                print(line)
            print("=" * 70)
            print("Esperado para una P-517.3CD: recorrido_max ~ {'1': 100, '2': 100, '3': 20}.")


if __name__ == "__main__":
    sys.exit(main())
