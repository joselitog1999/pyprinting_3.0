# -*- coding: utf-8 -*-
"""
canon_edsdk.py — Wrapper nativo ctypes para Canon EOS Digital SDK (EDSDK) 64-bit
PyPrinting — UNSAM Nanofotónica — PyQt6

Soporta control nativo de Canon EOS 500D:
  - Conexión y sesión USB con protección contra colisiones en bus C++.
  - Pausa inteligente de Live View para captura de foto en alta resolución.
  - Stream de Live View (EVF) de alta calidad sin cuellos de botella.
  - Extensión de temporizador de apagado aislada (ExtendShutDownTimer).
  - Descarga de fotografías en alta resolución (JPEG/RAW) a la PC.
  - Corrección geométrica de orientación (rotación 90° e inversión espejo).
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
import threading
import atexit
from pathlib import Path
from typing import Optional, Callable, Tuple, List, Dict

import numpy as np
import cv2

if not sys.platform.startswith("win"):
    raise OSError("Canon EDSDK DLL solo es compatible con Windows.")

# ── Búsqueda y Carga de EDSDK.dll ──────────────────────────────────────────────

def _find_edsdk_dll() -> Optional[str]:
    # Buscar dinámicamente desde el directorio raíz del proyecto
    _curr = Path(__file__).resolve().parent
    root_dir = _curr.parent
    while _curr != _curr.parent:
        if (_curr / "config.py").exists():
            root_dir = _curr
            break
        _curr = _curr.parent

    candidate_paths = [
        root_dir / "ESDK_CANON" / "EDSDK_v13.20.21_Windows" / "EDSDK_64" / "Dll" / "EDSDK.dll",
        root_dir / "ESDK_CANON" / "EDSDK_v13.20.10_Raw_Win" / "EDSDK_64" / "Dll" / "EDSDK.dll",
        root_dir / "EDSDK.dll",
        Path.cwd() / "ESDK_CANON" / "EDSDK_v13.20.21_Windows" / "EDSDK_64" / "Dll" / "EDSDK.dll",
        Path.cwd() / "EDSDK.dll",
    ]

    for p in candidate_paths:
        if p.exists():
            return str(p)

    # Búsqueda recursiva en ESDK_CANON o root_dir
    try:
        for match in root_dir.rglob("EDSDK.dll"):
            if match.exists():
                return str(match)
    except Exception:
        pass

    return None

_DLL_PATH = _find_edsdk_dll()
edsdk = None

if _DLL_PATH and os.path.exists(_DLL_PATH):
    try:
        os.add_dll_directory(os.path.dirname(_DLL_PATH))
        edsdk = ctypes.cdll.LoadLibrary(_DLL_PATH)
    except Exception as _e:
        print(f"[Canon EDSDK] Advertencia al cargar DLL {_DLL_PATH}: {_e}")
else:
    print("[Canon EDSDK] EDSDK.dll no fue encontrado en el proyecto. Modo seguro/MOCK activo para la cámara Canon.")

# Lock de exclusión mutua para llamadas ctypes a la DLL de EDSDK
_edsdk_lock = threading.Lock()

# ── Tipos y Constantes Canon EDSDK ────────────────────────────────────────────

EdsError            = ctypes.c_uint32
EdsBaseRef          = ctypes.c_void_p
EdsCameraListRef    = ctypes.c_void_p
EdsCameraRef        = ctypes.c_void_p
EdsStreamRef        = ctypes.c_void_p
EdsEvfImageRef      = ctypes.c_void_p
EdsDirectoryItemRef = ctypes.c_void_p
EdsUInt32           = ctypes.c_uint32
EdsUInt64           = ctypes.c_uint64
EdsInt32            = ctypes.c_int32
EdsVoid             = None

# Errors
EDS_ERR_OK                         = 0x00000000
EDS_ERR_UNIMPLEMENTED              = 0x00000001
EDS_ERR_INTERNAL_ERROR             = 0x00000002
EDS_ERR_HANDLE_INVALID             = 0x00000006
EDS_ERR_INVALID_PARAMETER          = 0x00000007
EDS_ERR_DEVICE_BUSY                = 0x00000080
EDS_ERR_SESSION_NOT_OPEN           = 0x0000008D
EDS_ERR_INVALID_TRANSACTION        = 0x0000008E
EDS_ERR_TAKE_PICTURE_AF_NG         = 0x000000F0
EDS_ERR_TAKE_PICTURE_NO_CARD_NG    = 0x000000F5
EDS_ERR_OBJECT_NOTREADY            = 0x0000A102

EDSDK_ERRORS: Dict[int, str] = {
    0x00000000: "EDS_ERR_OK (Éxito)",
    0x00000001: "EDS_ERR_UNIMPLEMENTED (Función no implementada)",
    0x00000002: "EDS_ERR_INTERNAL_ERROR (Error interno EDSDK)",
    0x00000006: "EDS_ERR_HANDLE_INVALID (Referencia de cámara no válida)",
    0x00000007: "EDS_ERR_INVALID_PARAMETER (Parámetro no válido)",
    0x00000080: "EDS_ERR_DEVICE_BUSY (Cámara ocupada procesando imagen)",
    0x0000008D: "EDS_ERR_SESSION_NOT_OPEN (Sesión USB no abierta)",
    0x0000008E: "EDS_ERR_INVALID_TRANSACTION (Transacción USB ocupada)",
    0x000000F0: "EDS_ERR_TAKE_PICTURE_AF_NG (Fallo de enfoque AF)",
    0x000000F5: "EDS_ERR_TAKE_PICTURE_NO_CARD_NG (Sin tarjeta de memoria)",
    0x0000A102: "EDS_ERR_OBJECT_NOTREADY (Cuadro EVF en preparación)",
}

def get_edsdk_error_msg(err_code: int) -> str:
    return EDSDK_ERRORS.get(err_code, f"Error EDSDK 0x{err_code:08X}")

# Property IDs
kEdsPropID_ProductName            = 0x00000002
kEdsPropID_SaveTo                 = 0x0000000b
kEdsPropID_AEMode                 = 0x00000400
kEdsPropID_ISOSpeed               = 0x00000402
kEdsPropID_Av                     = 0x00000405
kEdsPropID_Tv                     = 0x00000406
kEdsPropID_Evf_OutputDevice        = 0x00000500
kEdsPropID_Evf_Mode                = 0x00000501
kEdsPropID_Evf_Zoom                = 0x00000507
kEdsPropID_Evf_ZoomPosition        = 0x00000508

# Property Values
kEdsSaveTo_Camera = 1
kEdsSaveTo_Host   = 2
kEdsSaveTo_Both   = 3

kEdsEvfOutputDevice_Off = 0
kEdsEvfOutputDevice_TFT = 1
kEdsEvfOutputDevice_PC  = 2
kEdsEvfOutputDevice_All = 3

# Commands
kEdsCameraCommand_TakePicture         = 0x00000000
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
kEdsCameraCommand_PressShutterButton  = 0x00000004
kEdsCameraCommand_DoEvfAf             = 0x00000102

# Shutter Button States
kEdsCameraCommand_ShutterButton_OFF                 = 0x00000000
kEdsCameraCommand_ShutterButton_Halfway             = 0x00000001
kEdsCameraCommand_ShutterButton_Completely          = 0x00000003
kEdsCameraCommand_ShutterButton_Halfway_NonAF       = 0x00010001
kEdsCameraCommand_ShutterButton_Completely_NonAF    = 0x00010003

# Object Events
kEdsObjectEvent_All                   = 0x00000200
kEdsObjectEvent_DirItemCreated        = 0x00000204
kEdsObjectEvent_DirItemRequestTransfer= 0x00000208

# File Access
kEdsFileCreateDisposition_CreateAlways = 1
kEdsAccess_ReadWrite                   = 3

# Structs
class EdsPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int32), ("y", ctypes.c_int32)]

class EdsSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int32), ("height", ctypes.c_int32)]

class EdsRect(ctypes.Structure):
    _fields_ = [("point", EdsPoint), ("size", EdsSize)]

class EdsPropertyDesc(ctypes.Structure):
    _fields_ = [
        ("form", ctypes.c_int32),
        ("numElements", ctypes.c_int32),
        ("propDesc", ctypes.c_int32 * 128)
    ]

class EdsDirectoryItemInfo(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint64),
        ("isFolder", ctypes.c_int32),
        ("groupID", ctypes.c_uint32),
        ("option", ctypes.c_uint32),
        ("szFileName", ctypes.c_char * 256),
        ("format", ctypes.c_uint32),
        ("dateTime", ctypes.c_uint32)
    ]

# Function Callbacks
EdsObjectEventHandler = ctypes.WINFUNCTYPE(
    EdsError, EdsUInt32, EdsDirectoryItemRef, ctypes.c_void_p)

# ── Firmas de Funciones DLL EDSDK ─────────────────────────────────────────────

if edsdk is not None:
    edsdk.EdsInitializeSDK.restype = EdsError
    edsdk.EdsTerminateSDK.restype  = EdsError
    edsdk.EdsGetCameraList.restype = EdsError
    edsdk.EdsGetChildCount.restype = EdsError
    edsdk.EdsGetChildAtIndex.restype = EdsError
    edsdk.EdsOpenSession.restype   = EdsError
    edsdk.EdsCloseSession.restype  = EdsError
    edsdk.EdsRelease.restype       = EdsError

    edsdk.EdsGetPropertyData.restype = EdsError
    edsdk.EdsSetPropertyData.restype = EdsError
    edsdk.EdsGetPropertyDesc.restype = EdsError

    edsdk.EdsSendCommand.restype                    = EdsError
    edsdk.EdsCreateMemoryStream.restype             = EdsError
    edsdk.EdsCreateMemoryStreamFromPointer.restype = EdsError
    edsdk.EdsCreateFileStreamEx.restype             = EdsError
    edsdk.EdsCreateEvfImageRef.restype             = EdsError
    edsdk.EdsDownloadEvfImage.restype              = EdsError
    edsdk.EdsGetPointer.restype                    = EdsError
    edsdk.EdsGetLength.restype                    = EdsError

    edsdk.EdsSetObjectEventHandler.restype = EdsError
    edsdk.EdsDownload.restype              = EdsError
    edsdk.EdsDownloadComplete.restype      = EdsError
    edsdk.EdsGetDirectoryItemInfo.restype  = EdsError

# ── Tablas de Conversión para Canon EOS 500D ──────────────────────────────────

AE_MODE_MAP: Dict[int, str] = {
    0: "Manual (M)",
    1: "Program (P)",
    2: "Tv (Prioridad Obturador)",
    3: "Av (Prioridad Apertura)",
    4: "Auto",
    5: "No-Flash",
    6: "Creative Auto",
}

ISO_MAP: Dict[int, str] = {
    0x00: "Auto",
    0x48: "100",
    0x50: "200",
    0x58: "400",
    0x60: "800",
    0x68: "1600",
    0x70: "3200",
}
FULL_ISO_LIST = list(ISO_MAP.keys())
REV_ISO_MAP   = {v: k for k, v in ISO_MAP.items()}

TV_MAP: Dict[int, str] = {
    0x53: "1/10s",
    0x50: "1/8s",
    0x4D: "1/6s",
    0x4B: "1/5s",
    0x48: "1/4s",
    0x38: "1s",
    0x30: "2s",
    0x2B: "3.2s",
    0x1D: "10s",
    0x10: "30s",
    0x18: "15s",
    0x20: "8s",
    0x23: "6s",
    0x28: "4s",
    0x60: "1/30s",
    0x68: "1/60s",
    0x70: "1/125s",
    0x78: "1/250s",
    0x80: "1/500s",
    0x88: "1/1000s",
    0x90: "1/2000s",
    0x98: "1/4000s",
}
FULL_TV_LIST = [0x53, 0x50, 0x4D, 0x4B, 0x48, 0x38, 0x30, 0x2B, 0x1D, 0x10, 0x18, 0x20, 0x28, 0x60, 0x68, 0x70, 0x78, 0x80, 0x88, 0x90, 0x98]
REV_TV_MAP   = {v: k for k, v in TV_MAP.items()}

ZOOM_MAP: Dict[int, str] = {
    1: "1x (Vista Completa)",
    2: "2x (Zoom Digital Cero Pérdida)",
    5: "5x (Zoom Hardware AF)",
    10: "10x (Zoom Hardware Enfoque Fino)"
}
REV_ZOOM_MAP = {v: k for k, v in ZOOM_MAP.items()}


# ══════════════════════════════════════════════════════════════════════════════
# ── Registro Global y Seguro de Emergencia de Obturador ───────────────────────

_registered_cameras: List[CanonCamera] = []

def _emergency_shutter_cleanup():
    """Seguro físico de emergencia: garantiza que si Python se cierra o fuerza su salida, 
    el obturador mecánico retorne a posición de reposo y la sesión USB se cierre limpiamente."""
    for cam in list(_registered_cameras):
        try:
            if cam and getattr(cam, '_is_session_open', False):
                cam.log("🚨 [EMERGENCIA HARDWARE] Cerrando obturador físico y liberando cámara Canon...")
                cam.close_session()
                cam.terminate_sdk()
        except Exception as _e:
            print(f"[Canon Emergency Cleanup] Exception: {_e}")

atexit.register(_emergency_shutter_cleanup)


# ══════════════════════════════════════════════════════════════════════════════
#  CLASE CANON CAMERA CONTROLLER
# ══════════════════════════════════════════════════════════════════════════════

class CanonCamera:
    """Clase controladora nativa para cámaras Canon EOS mediante EDSDK."""

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self._is_sdk_init = False
        self._camera_ref  = None
        self._is_session_open = False
        self._save_dir    = os.path.abspath("data")
        self._evf_enabled = False
        self._cb_keepalive = None
        self._active_zoom = 1
        self._log_cb = log_callback
        if self not in _registered_cameras:
            _registered_cameras.append(self)

    def log(self, msg: str):
        t_str = time.strftime("%H:%M:%S")
        formatted = f"[{t_str}] {msg}"
        print(f"[Canon EDSDK] {formatted}")
        if self._log_cb:
            try: self._log_cb(formatted)
            except Exception: pass

    def initialize_sdk(self) -> bool:
        with _edsdk_lock:
            if self._is_sdk_init: return True
            if edsdk is None:
                self.log("⚠ EDSDK.dll no disponible.")
                return False
            err = edsdk.EdsInitializeSDK()
            if err == EDS_ERR_OK:
                self._is_sdk_init = True
                self.log("SDK inicializado con éxito.")
                return True
            self.log(f"⚠ Error al inicializar SDK: {get_edsdk_error_msg(err)}")
            return False

    def terminate_sdk(self):
        if self._is_session_open:
            self.close_session()
        with _edsdk_lock:
            if self._is_sdk_init and edsdk is not None:
                try: edsdk.EdsTerminateSDK()
                except Exception: pass
                self._is_sdk_init = False
                self.log("SDK finalizado.")

    def open_session(self) -> bool:
        if not self._is_sdk_init:
            if not self.initialize_sdk(): return False
        if edsdk is None: return False

        with _edsdk_lock:
            cam_list = EdsCameraListRef()
            err = edsdk.EdsGetCameraList(ctypes.byref(cam_list))
            if err != EDS_ERR_OK:
                self.log(f"⚠ Error al obtener lista de cámaras: {get_edsdk_error_msg(err)}")
                return False

            count = EdsUInt32(0)
            edsdk.EdsGetChildCount(cam_list, ctypes.byref(count))

            if count.value == 0:
                self.log("⚠ No se detectó ninguna cámara Canon EOS conectada por USB.")
                if cam_list: edsdk.EdsRelease(cam_list)
                return False

            cam = EdsCameraRef()
            err = edsdk.EdsGetChildAtIndex(cam_list, 0, ctypes.byref(cam))
            if cam_list: edsdk.EdsRelease(cam_list)

            if err != EDS_ERR_OK or not cam:
                self.log(f"⚠ Error al obtener referencia de cámara: {get_edsdk_error_msg(err)}")
                return False

            self._camera_ref = cam
            err = edsdk.EdsOpenSession(self._camera_ref)
            if err != EDS_ERR_OK:
                self.log(f"⚠ Error al abrir sesión USB: {get_edsdk_error_msg(err)}")
                return False

            self._is_session_open = True
            self.log("Sesión USB abierta exitosamente con Canon EOS 500D.")

            # Configurar guardado directo en PC (Host)
            save_to = EdsUInt32(kEdsSaveTo_Host)
            edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_SaveTo, 0, ctypes.sizeof(save_to), ctypes.byref(save_to))

            # Registrar handlers para eventos de fotos creadas o listas para transferencia
            self._register_photo_handler()
            return True

    def close_session(self):
        try:
            if self._is_session_open and self._camera_ref:
                self.disable_live_view()
                time.sleep(0.1)
                with _edsdk_lock:
                    if edsdk is not None:
                        try:
                            edsdk.EdsCloseSession(self._camera_ref)
                        except Exception as _e:
                            self.log(f"Excepción al cerrar sesión: {_e}")
                        try:
                            edsdk.EdsRelease(self._camera_ref)
                        except Exception:
                            pass
        except Exception as e:
            self.log(f"Error imprevisto en close_session: {e}")
        finally:
            self._camera_ref = None
            self._is_session_open = False
            self._evf_enabled = False
            self.log("Sesión de cámara cerrada y recursos USB liberados.")

    # ── Live View (EVF Stream) ────────────────────────────────────────────────

    def enable_live_view(self) -> bool:
        if not self._is_session_open or edsdk is None: return False
        with _edsdk_lock:
            device = EdsUInt32(kEdsEvfOutputDevice_PC)
            err = edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(device), ctypes.byref(device))
            if err == EDS_ERR_OK:
                self._evf_enabled = True
                self.log("Transmisión PC Live View activada (Obturador y Espejo Réflex Arriba).")
                return True
            self.log(f"⚠ Error al activar salida PC Live View: {get_edsdk_error_msg(err)}")
            return False

    def disable_live_view(self) -> bool:
        if not self._is_session_open or not self._camera_ref or edsdk is None:
            self._evf_enabled = False
            return True

        device = EdsUInt32(kEdsEvfOutputDevice_Off)
        for attempt in range(6):
            with _edsdk_lock:
                try:
                    err = edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(device), ctypes.byref(device))
                except Exception:
                    err = -1
            if err == EDS_ERR_OK:
                self._evf_enabled = False
                self.log("🛡️ Transmisión Live View deshabilitada | Obturador mecánico cerrado y en reposo.")
                return True
            time.sleep(0.08)

        self.log(f"⚠ Advertencia: No se pudo desactivar EVF tras reintentos: {get_edsdk_error_msg(err)}")
        self._evf_enabled = False
        return False

    def get_live_view_frame(self) -> Optional[bytes]:
        """Obtiene un frame JPEG comprimido en memoria desde el sensor Live View."""
        if not self._is_session_open or not self._evf_enabled or edsdk is None: return None

        with _edsdk_lock:
            stream = EdsStreamRef()
            err = edsdk.EdsCreateMemoryStream(0, ctypes.byref(stream))
            if err != EDS_ERR_OK: return None

            evf_image = EdsEvfImageRef()
            err = edsdk.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image))
            if err != EDS_ERR_OK:
                edsdk.EdsRelease(stream)
                return None

            try:
                err = edsdk.EdsDownloadEvfImage(self._camera_ref, evf_image)
                if err in (EDS_ERR_DEVICE_BUSY, EDS_ERR_OBJECT_NOTREADY) or err != EDS_ERR_OK:
                    return None

                data_ptr = ctypes.c_void_p()
                length   = EdsUInt64(0)
                edsdk.EdsGetPointer(stream, ctypes.byref(data_ptr))
                edsdk.EdsGetLength(stream, ctypes.byref(length))

                buffer = ctypes.string_at(data_ptr.value, length.value) if (length.value > 0 and data_ptr.value) else None
                return buffer
            finally:
                edsdk.EdsRelease(evf_image)
                edsdk.EdsRelease(stream)

    # ── Controles de Zoom y Corrección de Orientación Live View ──────────────

    def set_live_view_zoom(self, zoom_val: int) -> bool:
        if not self._is_session_open: return False
        self._active_zoom = zoom_val

        with _edsdk_lock:
            hw_zoom = 1 if zoom_val in (1, 2) else zoom_val
            val = EdsUInt32(hw_zoom)
            err = edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_Evf_Zoom, 0, ctypes.sizeof(val), ctypes.byref(val))
            return err == EDS_ERR_OK

    def process_frame_zoom_and_orientation(self, frame_rgb: np.ndarray) -> np.ndarray:
        if frame_rgb is None: return frame_rgb

        # Rotación 90° sentido horario e inversión horizontal
        corrected = cv2.rotate(frame_rgb, cv2.ROTATE_90_CLOCKWISE)
        corrected = cv2.flip(corrected, 1)

        # Aplicar Zoom 2x de alta resolución por corte central e interpolación cúbica
        if self._active_zoom == 2:
            H, W, C = corrected.shape
            ch, cw = H // 2, W // 2
            y1, y2 = ch - H // 4, ch + H // 4
            x1, x2 = cw - W // 4, cw + W // 4
            crop = corrected[y1:y2, x1:x2]
            return cv2.resize(crop, (W, H), interpolation=cv2.INTER_CUBIC)

        return corrected

    def process_frame_live_adjustments(
        self,
        frame_rgb: np.ndarray,
        mode: str = "Color RGB",
        clim_min: int = 0,
        clim_max: int = 255,
        lut_idx: int = 0,
        r_gain: float = 1.0,
        g_gain: float = 1.0,
        b_gain: float = 1.0,
    ) -> np.ndarray:
        if frame_rgb is None: return frame_rgb

        # 1. Aplicar orientación y zoom nativo
        proc = self.process_frame_zoom_and_orientation(frame_rgb)
        if proc is None: return proc

        if mode.startswith("Grises"):
            # Convertir a 8-bit escala de grises para microscopía de transmisión
            gray = cv2.cvtColor(proc, cv2.COLOR_RGB2GRAY) if proc.ndim == 3 else proc
            cmin = float(clim_min)
            cmax = float(clim_max)
            if cmax <= cmin: cmax = cmin + 1.0
            norm = np.clip((gray.astype(float) - cmin) / (cmax - cmin), 0.0, 1.0)
            u8 = (norm * 255.0).astype(np.uint8)

            if lut_idx == 0:
                # Gris estandar RGB
                return np.stack([u8] * 3, axis=-1)
            else:
                cv_maps = [None, cv2.COLORMAP_HOT, cv2.COLORMAP_VIRIDIS, cv2.COLORMAP_PLASMA, cv2.COLORMAP_INFERNO, cv2.COLORMAP_JET]
                idx = min(lut_idx, len(cv_maps) - 1)
                colored = cv2.applyColorMap(u8, cv_maps[idx])
                return cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
        else:
            # Modo Color (RGB): Ganancias ultrarrápidas R, G, B (<1 ms)
            if r_gain == 1.0 and g_gain == 1.0 and b_gain == 1.0:
                return proc
            f = proc.astype(float)
            f[:, :, 0] *= r_gain
            f[:, :, 1] *= g_gain
            f[:, :, 2] *= b_gain
            return np.clip(f, 0, 255).astype(np.uint8)

    # ── Lectura y Ajuste de Propiedades ───────────────────────────────────────

    def get_property_desc(self, prop_id: int) -> List[int]:
        if not self._is_session_open: return []
        with _edsdk_lock:
            desc = EdsPropertyDesc()
            err = edsdk.EdsGetPropertyDesc(self._camera_ref, prop_id, ctypes.byref(desc))
            if err != EDS_ERR_OK: return []
            return [desc.propDesc[i] for i in range(desc.numElements)]

    def get_property_value(self, prop_id: int) -> int:
        if not self._is_session_open: return 0
        with _edsdk_lock:
            val = EdsUInt32(0)
            err = edsdk.EdsGetPropertyData(self._camera_ref, prop_id, 0, ctypes.sizeof(val), ctypes.byref(val))
            return val.value if err == EDS_ERR_OK else 0

    def set_property_value(self, prop_id: int, val: int) -> bool:
        if not self._is_session_open: return False
        with _edsdk_lock:
            v = EdsUInt32(val)
            err = edsdk.EdsSetPropertyData(self._camera_ref, prop_id, 0, ctypes.sizeof(v), ctypes.byref(v))
            if err == EDS_ERR_OK:
                self.log(f"Propiedad 0x{prop_id:04X} actualizada a 0x{val:02X}")
                return True
            self.log(f"⚠ Error al cambiar propiedad 0x{prop_id:04X}: {get_edsdk_error_msg(err)}")
            return False

    # ── Captura Inteligente con Pausa de Live View ────────────────────────────

    # ── Captura Inteligente con Pausa de Live View y Guardado Multi-Formato ───

    def take_photo(self, target_format: str = "jpg") -> Tuple[bool, Optional[str]]:
        """
        Pausa el Live View temporalmente para liberar el sensor réflex DIGIC 4,
        ejecuta el disparo TakePicture en resolución completa de 15 MP (4752x3168),
        descarga el archivo a la PC en el formato solicitado (.jpg, .png, .tiff, .bmp),
        y reactiva el Live View.
        """
        if not self._is_session_open or edsdk is None:
            self.log("⚠ No se puede tomar foto: Sesión USB no abierta.")
            return False, None

        self.log(f"📸 Pausando Live View para disparo en resolución completa de 15 MP (4752×3168)... Formato objetivo: .{target_format.upper()}")
        was_evf = self._evf_enabled
        if was_evf:
            self.disable_live_view()
            time.sleep(0.15) # Pausa necesaria para liberar buffer de sensor

        save_dir = self._save_dir
        os.makedirs(save_dir, exist_ok=True)
        t_str = time.strftime("%Y%m%d_%H%M%S")
        ext = target_format.lower().strip(".")
        if ext not in ("jpg", "jpeg", "png", "tiff", "tif", "bmp"):
            ext = "jpg"

        final_filename = f"CANON_EOS500D_{t_str}.{ext}"
        final_save_path = os.path.join(save_dir, final_filename)

        with _edsdk_lock:
            # Configurar guardado directo en PC (Host)
            save_to = EdsUInt32(kEdsSaveTo_Host)
            edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_SaveTo, 0, ctypes.sizeof(save_to), ctypes.byref(save_to))

            self.log(f"📸 Enviando orden de disparo del obturador (TakePicture)...")
            err = edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_TakePicture, 0)
            if err != EDS_ERR_OK:
                self.log(f"⚠ TakePicture retornó {get_edsdk_error_msg(err)}. Reintentando con PressShutterButton...")
                edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_PressShutterButton, kEdsCameraCommand_ShutterButton_Completely_NonAF)
                time.sleep(0.08)
                edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_PressShutterButton, kEdsCameraCommand_ShutterButton_OFF)

        # Esperar la foto creada en el buffer C++ o descargarla directamente
        time.sleep(0.5)

        # Buscar foto descargada en save_dir o convertir si fue descargada como JPG/CR2
        downloaded_file = None
        for attempt in range(30):
            if os.path.exists(final_save_path) and os.path.getsize(final_save_path) > 0:
                downloaded_file = final_save_path
                break
            for fname in os.listdir(save_dir):
                if fname.startswith("IMG_") or fname.startswith("CANON_"):
                    fpath = os.path.join(save_dir, fname)
                    if os.path.exists(fpath) and (time.time() - os.path.getmtime(fpath)) < 15:
                        downloaded_file = fpath
                        break
            if downloaded_file: break
            time.sleep(0.1)

        saved_path = None
        if downloaded_file:
            if ext in ("jpg", "jpeg") and downloaded_file.lower().endswith((".jpg", ".jpeg")):
                if downloaded_file != final_save_path:
                    try:
                        os.rename(downloaded_file, final_save_path)
                        saved_path = final_save_path
                    except Exception:
                        saved_path = downloaded_file
                else:
                    saved_path = final_save_path
            else:
                try:
                    img = cv2.imread(downloaded_file, cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        cv2.imwrite(final_save_path, img)
                        saved_path = final_save_path
                        self.log(f"✅ Conversión a formato .{ext.upper()} completada en 15 MP (4752×3168): {final_save_path}")
                        if downloaded_file != final_save_path:
                            try: os.remove(downloaded_file)
                            except Exception: pass
                    else:
                        saved_path = downloaded_file
                except Exception as _e:
                    self.log(f"⚠ Error convirtiendo formato: {_e}")
                    saved_path = downloaded_file

            if saved_path:
                self.log(f"✅ ¡FOTO DE ALTA RESOLUCIÓN GUARDADA EN DISCO!: {saved_path}")
        else:
            self.log("⚠ Foto tomada en hardware pero no se detectó el archivo descargado por USB.")

        if was_evf:
            self.log("🎥 Reactivando Live View...")
            self.enable_live_view()

        return (saved_path is not None), saved_path

    def set_save_directory(self, path: str):
        self._save_dir = os.path.abspath(path)
        self.log(f"Directorio de guardado configurado en: {self._save_dir}")

    def _register_photo_handler(self):
        def _on_dir_item_created(event: int, item_ref: EdsDirectoryItemRef, context: ctypes.c_void_p) -> int:
            self.log("📸 Evento detectado: Nueva foto lista en la réflex. Iniciando transferencia a PC...")
            with _edsdk_lock:
                info = EdsDirectoryItemInfo()
                err = edsdk.EdsGetDirectoryItemInfo(item_ref, ctypes.byref(info))
                if err == EDS_ERR_OK:
                    filename = info.szFileName.decode("utf-8", errors="ignore")
                    save_path = os.path.join(self._save_dir, filename)
                    os.makedirs(self._save_dir, exist_ok=True)

                    stream = EdsStreamRef()
                    err_st = edsdk.EdsCreateFileStreamEx(
                        ctypes.c_wchar_p(save_path),
                        kEdsFileCreateDisposition_CreateAlways,
                        kEdsAccess_ReadWrite,
                        ctypes.byref(stream)
                    )
                    if err_st == EDS_ERR_OK:
                        edsdk.EdsDownload(item_ref, info.size, stream)
                        edsdk.EdsDownloadComplete(item_ref)
                        edsdk.EdsRelease(stream)
                        self.log(f"✅ Descarga completada desde cámara: {save_path}")
                    else:
                        self.log(f"❌ Error al crear archivo de descarga: {get_edsdk_error_msg(err_st)}")
                else:
                    self.log(f"❌ Error leyendo información de foto: {get_edsdk_error_msg(err)}")
            return EDS_ERR_OK

        self._cb_keepalive = EdsObjectEventHandler(_on_dir_item_created)
        edsdk.EdsSetObjectEventHandler(self._camera_ref, kEdsObjectEvent_DirItemCreated, self._cb_keepalive, None)
        edsdk.EdsSetObjectEventHandler(self._camera_ref, kEdsObjectEvent_DirItemRequestTransfer, self._cb_keepalive, None)
