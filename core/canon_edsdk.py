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
EdsVolumeRef        = ctypes.c_void_p
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

class EdsCapacity(ctypes.Structure):
    _fields_ = [
        ("numberOfFreeClusters", ctypes.c_int32),
        ("bytesPerSector", ctypes.c_int32),
        ("reset", ctypes.c_int32)
    ]

# Function Callbacks
EdsObjectEventHandler = ctypes.WINFUNCTYPE(
    EdsError, EdsUInt32, EdsDirectoryItemRef, ctypes.c_void_p)

# ── Firmas de Funciones DLL EDSDK (Compatibilidad 64-bit) ──────────────────────

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
    edsdk.EdsSendCommand.argtypes                   = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32]

    edsdk.EdsSendStatusCommand.restype              = EdsError
    edsdk.EdsSendStatusCommand.argtypes             = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32]

    edsdk.EdsCreateMemoryStream.restype             = EdsError
    edsdk.EdsCreateMemoryStreamFromPointer.restype = EdsError

    edsdk.EdsCreateFileStreamEx.restype             = EdsError
    edsdk.EdsCreateFileStreamEx.argtypes            = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]

    edsdk.EdsCreateEvfImageRef.restype             = EdsError
    edsdk.EdsDownloadEvfImage.restype              = EdsError
    edsdk.EdsGetPointer.restype                    = EdsError
    edsdk.EdsGetLength.restype                    = EdsError

    edsdk.EdsSetObjectEventHandler.restype         = EdsError
    edsdk.EdsSetObjectEventHandler.argtypes        = [ctypes.c_void_p, ctypes.c_uint32, EdsObjectEventHandler, ctypes.c_void_p]

    edsdk.EdsDownload.restype                      = EdsError
    edsdk.EdsDownload.argtypes                     = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]

    edsdk.EdsDownloadComplete.restype              = EdsError
    edsdk.EdsDownloadComplete.argtypes             = [ctypes.c_void_p]

    edsdk.EdsGetDirectoryItemInfo.restype          = EdsError
    edsdk.EdsGetDirectoryItemInfo.argtypes         = [ctypes.c_void_p, ctypes.c_void_p]

    if hasattr(edsdk, "EdsSetCapacity"):
        edsdk.EdsSetCapacity.restype               = EdsError
        edsdk.EdsSetCapacity.argtypes              = [ctypes.c_void_p, EdsCapacity]

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

            # Notificar capacidad de almacenamiento del Host PC a la cámara réflex
            try:
                cap = EdsCapacity()
                cap.numberOfFreeClusters = 0x7FFFFFFF
                cap.bytesPerSector = 512
                cap.reset = 1
                if hasattr(edsdk, "EdsSetCapacity"):
                    edsdk.EdsSetCapacity(self._camera_ref, cap)
                    self.log("Capacidad ilimitada de almacenamiento Host PC registrada en la réflex.")
            except Exception as _e:
                self.log(f"Advertencia al notificar EdsSetCapacity: {_e}")

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

    def set_zoom_center(self, cx: float, cy: float):
        """Configura el centro del ROI para navegación panorámica en el sensor FOV (0.0 a 1.0)."""
        self._zoom_center_x = max(0.0, min(1.0, cx))
        self._zoom_center_y = max(0.0, min(1.0, cy))

    def process_frame_zoom_and_orientation(self, frame_rgb: np.ndarray) -> np.ndarray:
        if frame_rgb is None: return frame_rgb

        # Rotación 90° sentido horario e inversión horizontal
        corrected = cv2.rotate(frame_rgb, cv2.ROTATE_90_CLOCKWISE)
        corrected = cv2.flip(corrected, 1)

        # Aplicar Zoom digital 2x/5x/10x por corte ROI con navegación panorámica FOV
        if self._active_zoom in (2, 5, 10):
            H, W, C = corrected.shape
            scale = float(self._active_zoom)
            crop_h = max(10, int(H / scale))
            crop_w = max(10, int(W / scale))

            cx = getattr(self, '_zoom_center_x', 0.5)
            cy = getattr(self, '_zoom_center_y', 0.5)

            center_y = int(cy * H)
            center_x = int(cx * W)

            y1 = max(0, min(H - crop_h, center_y - crop_h // 2))
            y2 = y1 + crop_h
            x1 = max(0, min(W - crop_w, center_x - crop_w // 2))
            x2 = x1 + crop_w

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
        if not self._is_session_open or edsdk is None: return False
        v = EdsUInt32(val)
        for attempt in range(5):
            with _edsdk_lock:
                try:
                    err = edsdk.EdsSetPropertyData(self._camera_ref, prop_id, 0, ctypes.sizeof(v), ctypes.byref(v))
                except Exception as _e:
                    err = -1
            if err == EDS_ERR_OK:
                self.log(f"Propiedad 0x{prop_id:04X} actualizada a 0x{val:02X}")
                return True
            time.sleep(0.06)
        self.log(f"⚠ Error al cambiar propiedad 0x{prop_id:04X} tras reintentos: {get_edsdk_error_msg(err)}")
        return False

    # ── Captura Inteligente con Pausa de Live View ────────────────────────────

    # ── Captura Inteligente con Pausa de Live View y Guardado Multi-Formato ───

    def take_photo(self, target_format: str = "jpg") -> Tuple[bool, Optional[str]]:
        """
        Pausa el Live View temporalmente para liberar el sensor réflex DIGIC 4,
        configura la capacidad de Host PC, ejecuta el disparo del obturador
        en resolución completa de 15.1 MP (4752x3168), descarga y convierte
        el archivo a la PC en el formato solicitado (.jpg, .png, .tiff, .bmp),
        y reactiva el Live View.
        """
        if not self._is_session_open or edsdk is None:
            self.log("⚠ No se puede tomar foto: Sesión USB no abierta.")
            return False, None

        self.log(f"📸 Pausando Live View para disparo en resolución completa de 15.1 MP (4752×3168)... Formato objetivo: .{target_format.upper()}")
        was_evf = self._evf_enabled
        if was_evf:
            self.disable_live_view()
            time.sleep(0.35) # Pausa necesaria para liberar sensor réflex DIGIC 4 antes de obturar

        save_dir = self._save_dir
        os.makedirs(save_dir, exist_ok=True)
        t_str = time.strftime("%Y%m%d_%H%M%S")
        ext = target_format.lower().strip(".")
        if ext not in ("jpg", "jpeg", "png", "tiff", "tif", "bmp"):
            ext = "jpg"

        desired_filename = f"CANON_EOS500D_{t_str}.{ext}"
        final_save_path = self.get_unique_save_path(save_dir, desired_filename)
        self._last_saved_photo = None

        with _edsdk_lock:
            # 1. Re-asegurar Host PC save destination
            save_to = EdsUInt32(kEdsSaveTo_Host)
            edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_SaveTo, 0, ctypes.sizeof(save_to), ctypes.byref(save_to))

            # 2. Re-notificar capacidad de almacenamiento del Host PC a la cámara réflex
            try:
                cap = EdsCapacity()
                cap.numberOfFreeClusters = 0x7FFFFFFF
                cap.bytesPerSector = 512
                cap.reset = 1
                if hasattr(edsdk, "EdsSetCapacity"):
                    edsdk.EdsSetCapacity(self._camera_ref, cap)
            except Exception: pass

            self.log(f"📸 Enviando orden de disparo del obturador (TakePicture / ShutterButton)...")
            err = edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_TakePicture, 0)
            
            # Si TakePicture retorna error de AF o BUSY, reintentar con obturación manual sin foco automático (NonAF)
            if err != EDS_ERR_OK:
                self.log(f"⚠ TakePicture retornó {get_edsdk_error_msg(err)}. Reintentando con PressShutterButton (modo NonAF directo)...")
                try:
                    edsdk.EdsSendStatusCommand(self._camera_ref, kEdsCameraStatusCommand_UIUnLock, 0)
                    time.sleep(0.05)
                except Exception: pass

                edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_PressShutterButton, kEdsCameraCommand_ShutterButton_Completely_NonAF)
                time.sleep(0.12)
                edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_PressShutterButton, kEdsCameraCommand_ShutterButton_OFF)
                
                try:
                    edsdk.EdsSendStatusCommand(self._camera_ref, kEdsCameraStatusCommand_UILock, 0)
                except Exception: pass

        # Esperar hasta 2.5s a que el evento de transferencia o la recuperacion de volumen entreguen el archivo
        downloaded_file = None
        for attempt in range(25):
            if hasattr(self, '_last_saved_photo') and self._last_saved_photo and os.path.exists(self._last_saved_photo):
                downloaded_file = self._last_saved_photo
                break
            if os.path.exists(final_save_path) and os.path.getsize(final_save_path) > 0:
                downloaded_file = final_save_path
                break
            for fname in os.listdir(save_dir):
                if fname.startswith("IMG_") or fname.startswith("CANON_"):
                    fpath = os.path.join(save_dir, fname)
                    if os.path.exists(fpath) and (time.time() - os.path.getmtime(fpath)) < 25:
                        downloaded_file = fpath
                        break
            if downloaded_file: break
            time.sleep(0.1)

        # Si aún no se detectó el archivo descargado, realizar exploración directa del volumen réflex
        if not downloaded_file:
            self._download_newest_photo_from_camera(save_dir)
            for fname in os.listdir(save_dir):
                if fname.startswith("IMG_") or fname.startswith("CANON_"):
                    fpath = os.path.join(save_dir, fname)
                    if os.path.exists(fpath) and (time.time() - os.path.getmtime(fpath)) < 25:
                        downloaded_file = fpath
                        break

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
                        self.log(f"✅ Conversión a formato .{ext.upper()} completada en 15.1 MP (4752×3168): {final_save_path}")
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
            self.log("⚠ No se detectó el archivo descargado por USB tras reintentos.")

        if was_evf:
            self.log("🎥 Reactivando Live View...")
            self.enable_live_view()

        return (saved_path is not None), saved_path

    def _download_directory_item_to_file(self, item_ref: ctypes.c_void_p, save_path: str, item_size: int) -> bool:
        """Descarga un objeto fotográfico de la cámara réflex a un archivo en la PC usando EdsCreateMemoryStream en RAM (inmune a errores de ruta 0x000000AB)."""
        if edsdk is None: return False
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        stream = EdsStreamRef()

        # 1. Probar descarga en memoria RAM (inmune a problemas de formato de ruta de la DLL C++)
        err = edsdk.EdsCreateMemoryStream(item_size, ctypes.byref(stream))
        if err != EDS_ERR_OK:
            err = edsdk.EdsCreateMemoryStream(0, ctypes.byref(stream))

        if err == EDS_ERR_OK and stream:
            try:
                err_dn = edsdk.EdsDownload(item_ref, item_size, stream)
                if err_dn == EDS_ERR_OK:
                    edsdk.EdsDownloadComplete(item_ref)
                    data_ptr = ctypes.c_void_p()
                    length = EdsUInt64(0)
                    edsdk.EdsGetPointer(stream, ctypes.byref(data_ptr))
                    edsdk.EdsGetLength(stream, ctypes.byref(length))

                    if data_ptr.value and length.value > 0:
                        raw_bytes = ctypes.string_at(data_ptr.value, length.value)
                        with open(save_path, "wb") as f:
                            f.write(raw_bytes)
                        self.log(f"✅ ¡FOTO DESCARGADA EXITOSAMENTE VÍA MEMORY STREAM!: {save_path}")
                        return True
                    else:
                        self.log("⚠ Memory Stream de descarga retornó 0 bytes.")
                else:
                    self.log(f"❌ Error durante EdsDownload: {get_edsdk_error_msg(err_dn)}")
            except Exception as _e:
                self.log(f"Excepción en descarga por memoria: {_e}")
            finally:
                edsdk.EdsRelease(stream)

        # 2. Fallback con EdsCreateFileStreamEx usando ruta UTF-8/ANSI
        try:
            stream_f = EdsStreamRef()
            err_f = edsdk.EdsCreateFileStreamEx(
                ctypes.c_char_p(save_path.encode("utf-8")),
                kEdsFileCreateDisposition_CreateAlways,
                kEdsAccess_ReadWrite,
                ctypes.byref(stream_f)
            )
            if err_f == EDS_ERR_OK and stream_f:
                try:
                    edsdk.EdsDownload(item_ref, item_size, stream_f)
                    edsdk.EdsDownloadComplete(item_ref)
                    self.log(f"✅ Descarga completada vía FileStream: {save_path}")
                    return True
                finally:
                    edsdk.EdsRelease(stream_f)
            else:
                self.log(f"❌ Error al crear stream de archivo (0x{err_f:08X}): {get_edsdk_error_msg(err_f)}")
        except Exception as _e:
            self.log(f"Excepción en descarga de archivo: {_e}")

        return False

    def _download_newest_photo_from_camera(self, save_dir: str):
        """Descarga la última foto disponible explorando directamente la tarjeta/volumen de la réflex."""
        if not self._is_session_open or edsdk is None: return
        with _edsdk_lock:
            try:
                vol_list_count = EdsUInt32(0)
                err = edsdk.EdsGetChildCount(self._camera_ref, ctypes.byref(vol_list_count))
                if err == EDS_ERR_OK and vol_list_count.value > 0:
                    vol_ref = ctypes.c_void_p()
                    err_v = edsdk.EdsGetChildAtIndex(self._camera_ref, 0, ctypes.byref(vol_ref))
                    if err_v == EDS_ERR_OK and vol_ref:
                        dir_count = EdsUInt32(0)
                        edsdk.EdsGetChildCount(vol_ref, ctypes.byref(dir_count))
                        for i in range(dir_count.value):
                            folder_ref = ctypes.c_void_p()
                            err_f = edsdk.EdsGetChildAtIndex(vol_ref, i, ctypes.byref(folder_ref))
                            if err_f == EDS_ERR_OK and folder_ref:
                                info = EdsDirectoryItemInfo()
                                edsdk.EdsGetDirectoryItemInfo(folder_ref, ctypes.byref(info))
                                fname_str = info.szFileName.decode("utf-8", errors="ignore")
                                if info.isFolder and fname_str.upper() in ("DCIM", "100CANON", "101CANON", "MISC"):
                                    item_count = EdsUInt32(0)
                                    edsdk.EdsGetChildCount(folder_ref, ctypes.byref(item_count))
                                    if item_count.value > 0:
                                        last_item = ctypes.c_void_p()
                                        err_l = edsdk.EdsGetChildAtIndex(folder_ref, item_count.value - 1, ctypes.byref(last_item))
                                        if err_l == EDS_ERR_OK and last_item:
                                            l_info = EdsDirectoryItemInfo()
                                            edsdk.EdsGetDirectoryItemInfo(last_item, ctypes.byref(l_info))
                                            out_name = l_info.szFileName.decode("utf-8", errors="ignore")
                                            target_p = os.path.join(save_dir, out_name)
                                            self._download_directory_item_to_file(last_item, target_p, l_info.size)
                                            edsdk.EdsRelease(last_item)
                                edsdk.EdsRelease(folder_ref)
                        edsdk.EdsRelease(vol_ref)
            except Exception as _e:
                self.log(f"Advertencia durante descarga manual de volumen: {_e}")

    def get_unique_save_path(self, base_dir: str, desired_filename: str) -> str:
        """Garantiza un nombre de archivo único agregando contadores numéricos para evitar sobreescrituras."""
        os.makedirs(base_dir, exist_ok=True)
        root, ext = os.path.splitext(desired_filename)
        save_path = os.path.join(base_dir, desired_filename)
        counter = 1
        while os.path.exists(save_path):
            save_path = os.path.join(base_dir, f"{root}_{counter:02d}{ext}")
            counter += 1
        return save_path

    def set_save_directory(self, path: str):
        self._save_dir = os.path.abspath(path)
        self.log(f"Directorio de guardado configurado en: {self._save_dir}")

    def _register_photo_handler(self):
        def _on_dir_item_created(event: int, item_ref: Any, context: ctypes.c_void_p) -> int:
            self.log("📸 Evento detectado: Nueva foto lista en la réflex. Iniciando transferencia a PC...")
            with _edsdk_lock:
                ref_ptr = ctypes.c_void_p(item_ref) if isinstance(item_ref, int) else item_ref
                info = EdsDirectoryItemInfo()
                err = edsdk.EdsGetDirectoryItemInfo(ref_ptr, ctypes.byref(info))
                if err == EDS_ERR_OK:
                    filename = info.szFileName.decode("utf-8", errors="ignore")
                    t_str = time.strftime("%Y%m%d_%H%M%S")
                    ext_str = os.path.splitext(filename)[1]
                    if not ext_str: ext_str = ".jpg"
                    desired = f"CANON_EOS500D_{t_str}{ext_str}"
                    save_path = self.get_unique_save_path(self._save_dir, desired)
                    ok_dn = self._download_directory_item_to_file(ref_ptr, save_path, info.size)
                    if ok_dn:
                        self._last_saved_photo = save_path
                else:
                    self.log(f"❌ Error leyendo información de foto: {get_edsdk_error_msg(err)}")
            return EDS_ERR_OK

        self._cb_keepalive = EdsObjectEventHandler(_on_dir_item_created)
        edsdk.EdsSetObjectEventHandler(self._camera_ref, kEdsObjectEvent_DirItemCreated, self._cb_keepalive, None)
        edsdk.EdsSetObjectEventHandler(self._camera_ref, kEdsObjectEvent_DirItemRequestTransfer, self._cb_keepalive, None)
