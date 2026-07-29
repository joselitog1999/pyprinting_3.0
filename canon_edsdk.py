# -*- coding: utf-8 -*-
"""
canon_edsdk.py — Wrapper nativo ctypes para Canon EOS Digital SDK (EDSDK) 64-bit
PyPrinting — UNSAM Nanofotónica — PyQt6

Soporta control nativo de Canon EOS 500D (y otras réflex Canon EOS):
  - Conexión y sesión USB.
  - Stream de Live View (EVF) de alta calidad.
  - Zoom Live View (1x, 2x Digital Fino, 5x Hardware AF, 10x Hardware Manual).
  - Control de Enfoque Remoto por Software/Motor (Near 1/2/3, Far 1/2/3, AF Trigger).
  - Ajuste dinámico de ISO, Apertura (Av), Velocidad de Obturación (Tv) y Modo AE.
  - Captura y descarga automática de fotos en alta resolución al PC.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from typing import Optional, Callable, Tuple, List, Dict

import numpy as np
import cv2

if not sys.platform.startswith("win"):
    raise OSError("Canon EDSDK DLL solo es compatible con Windows.")

# ── Búsqueda y Carga de EDSDK.dll ──────────────────────────────────────────────

def _find_edsdk_dll() -> str:
    possible_paths = [
        os.path.abspath("ESDK_CANON/EDSDK_v13.20.21_Windows/EDSDK_64/Dll/EDSDK.dll"),
        os.path.abspath("ESDK_CANON/EDSDK_v13.20.10_Raw_Win/EDSDK_64/Dll/EDSDK.dll"),
        os.path.abspath("EDSDK.dll"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("No se encontró EDSDK.dll en las rutas del proyecto.")

_DLL_PATH = _find_edsdk_dll()
os.add_dll_directory(os.path.dirname(_DLL_PATH))
edsdk = ctypes.cdll.LoadLibrary(_DLL_PATH)

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
EDS_ERR_OK = 0x00000000

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
kEdsEvfOutputDevice_All = 3 # TFT | PC (Mapeado por EOS Utility)

# Commands
kEdsCameraCommand_TakePicture         = 0x00000000
kEdsCameraCommand_ExtendShutDownTimer = 0x00000001
kEdsCameraCommand_PressShutterButton  = 0x00000004
kEdsCameraCommand_DoEvfAf             = 0x00000102
kEdsCameraCommand_DriveLensEvf        = 0x00000103

# Lens Drive constants
EvfDriveLens_Near1 = 0x00000001
EvfDriveLens_Near2 = 0x00000002
EvfDriveLens_Near3 = 0x00000003
EvfDriveLens_Far1  = 0x00008001
EvfDriveLens_Far2  = 0x00008002
EvfDriveLens_Far3  = 0x00008003

# Object Events
kEdsObjectEvent_All                   = 0x00000200
kEdsObjectEvent_DirItemCreated        = 0x00000204

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
    0x78: "6400",
    0x80: "12800 (H)",
}
REV_ISO_MAP = {v: k for k, v in ISO_MAP.items()}

AV_MAP: Dict[int, str] = {
    0x08: "f/1.4",
    0x0B: "f/1.8",
    0x0D: "f/2.0",
    0x10: "f/2.5",
    0x13: "f/2.8",
    0x15: "f/3.2",
    0x18: "f/3.5",
    0x1B: "f/4.0",
    0x1D: "f/4.5",
    0x20: "f/5.0",
    0x23: "f/5.6",
    0x25: "f/6.3",
    0x28: "f/7.1",
    0x2B: "f/8.0",
    0x2D: "f/9.0",
    0x30: "f/10",
    0x33: "f/11",
    0x35: "f/13",
    0x38: "f/14",
    0x3B: "f/16",
    0x3D: "f/18",
    0x40: "f/20",
    0x43: "f/22",
    0x45: "f/25",
    0x48: "f/29",
    0x4B: "f/32",
}
REV_AV_MAP = {v: k for k, v in AV_MAP.items()}

TV_MAP: Dict[int, str] = {
    0x0C: "Bulb",
    0x10: "30\"",
    0x13: "25\"",
    0x15: "20\"",
    0x18: "15\"",
    0x1B: "13\"",
    0x1D: "10\"",
    0x20: "8\"",
    0x23: "6\"",
    0x25: "5\"",
    0x28: "4\"",
    0x2B: "3.2\"",
    0x2D: "2.5\"",
    0x30: "2\"",
    0x33: "1.6\"",
    0x35: "1.3\"",
    0x38: "1\"",
    0x3B: "0.8\"",
    0x3D: "0.6\"",
    0x40: "0.5\"",
    0x43: "0.4\"",
    0x45: "0.3\"",
    0x48: "1/4s",
    0x50: "1/8s",
    0x58: "1/15s",
    0x60: "1/30s",
    0x68: "1/60s",
    0x70: "1/125s",
    0x78: "1/250s",
    0x80: "1/500s",
    0x88: "1/1000s",
    0x90: "1/2000s",
    0x98: "1/4000s",
}
REV_TV_MAP = {v: k for k, v in TV_MAP.items()}

ZOOM_MAP: Dict[int, str] = {
    1: "1x (Vista Completa)",
    2: "2x (Zoom Digital Cero Pérdida)",
    5: "5x (Zoom Hardware AF)",
    10: "10x (Zoom Hardware Enfoque Fino)"
}
REV_ZOOM_MAP = {v: k for k, v in ZOOM_MAP.items()}


# ══════════════════════════════════════════════════════════════════════════════
#  CLASE CANON CAMERA CONTROLLER
# ══════════════════════════════════════════════════════════════════════════════

class CanonCamera:
    """Clase controladora nativa para cámaras Canon EOS mediante EDSDK."""

    def __init__(self):
        self._is_sdk_init = False
        self._camera_ref  = None
        self._is_session_open = False
        self._save_dir    = os.path.abspath("data")
        self._evf_enabled = False
        self._cb_keepalive = None
        self._active_zoom = 1

    def initialize_sdk(self) -> bool:
        if self._is_sdk_init: return True
        err = edsdk.EdsInitializeSDK()
        if err == EDS_ERR_OK:
            self._is_sdk_init = True
            print("[Canon EDSDK] SDK inicializado con éxito.")
            return True
        print(f"[Canon EDSDK] Error al inicializar SDK: {hex(err)}")
        return False

    def terminate_sdk(self):
        if self._is_session_open:
            self.close_session()
        if self._is_sdk_init:
            edsdk.EdsTerminateSDK()
            self._is_sdk_init = False
            print("[Canon EDSDK] SDK finalizado.")

    def open_session(self) -> bool:
        if not self._is_sdk_init:
            if not self.initialize_sdk(): return False

        cam_list = EdsCameraListRef()
        err = edsdk.EdsGetCameraList(ctypes.byref(cam_list))
        if err != EDS_ERR_OK:
            print(f"[Canon EDSDK] Error al obtener lista de cámaras: {hex(err)}")
            return False

        count = EdsUInt32(0)
        edsdk.EdsGetChildCount(cam_list, ctypes.byref(count))

        if count.value == 0:
            print("[Canon EDSDK] No hay ninguna cámara Canon EOS conectada por USB.")
            if cam_list: edsdk.EdsRelease(cam_list)
            return False

        cam = EdsCameraRef()
        err = edsdk.EdsGetChildAtIndex(cam_list, 0, ctypes.byref(cam))
        if cam_list: edsdk.EdsRelease(cam_list)

        if err != EDS_ERR_OK or not cam:
            print(f"[Canon EDSDK] Error obteniendo referencia de cámara: {hex(err)}")
            return False

        self._camera_ref = cam
        err = edsdk.EdsOpenSession(self._camera_ref)
        if err != EDS_ERR_OK:
            print(f"[Canon EDSDK] Error al abrir sesión USB: {hex(err)}")
            return False

        self._is_session_open = True
        print("[Canon EDSDK] Sesión USB abierta con la cámara Canon EOS 500D.")

        # Configurar guardado directo en PC
        save_to = EdsUInt32(kEdsSaveTo_Host)
        edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_SaveTo, 0, ctypes.sizeof(save_to), ctypes.byref(save_to))

        # Registrar handler de descarga de fotos
        self._register_photo_handler()
        return True

    def close_session(self):
        if self._is_session_open and self._camera_ref:
            if self._evf_enabled:
                self.disable_live_view()
            edsdk.EdsCloseSession(self._camera_ref)
            edsdk.EdsRelease(self._camera_ref)
            self._camera_ref = None
            self._is_session_open = False
            print("[Canon EDSDK] Sesión de cámara cerrada.")

    # ── Live View (EVF Stream) ────────────────────────────────────────────────

    def enable_live_view(self) -> bool:
        if not self._is_session_open: return False
        # Activar ambos TFT y PC (igual que Canon EOS Utility) para máxima calidad del sensor
        device = EdsUInt32(kEdsEvfOutputDevice_All)
        err = edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(device), ctypes.byref(device))
        if err == EDS_ERR_OK:
            self._evf_enabled = True
            print("[Canon Live View] Transmisión de alta calidad TFT+PC activada.")
            return True
        print(f"[Canon Live View] Error al activar EVF Output: {hex(err)}")
        return False

    def disable_live_view(self):
        if not self._is_session_open: return
        device = EdsUInt32(kEdsEvfOutputDevice_Off)
        edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_Evf_OutputDevice, 0, ctypes.sizeof(device), ctypes.byref(device))
        self._evf_enabled = False
        print("[Canon Live View] Transmisión desactivada.")

    def get_live_view_frame(self) -> Optional[bytes]:
        """Obtiene un frame JPEG comprimido en memoria desde el sensor Live View."""
        if not self._is_session_open or not self._evf_enabled: return None

        stream = EdsStreamRef()
        err = edsdk.EdsCreateMemoryStream(0, ctypes.byref(stream))
        if err != EDS_ERR_OK: return None

        evf_image = EdsEvfImageRef()
        err = edsdk.EdsCreateEvfImageRef(stream, ctypes.byref(evf_image))
        if err != EDS_ERR_OK:
            edsdk.EdsRelease(stream)
            return None

        err = edsdk.EdsDownloadEvfImage(self._camera_ref, evf_image)
        if err != EDS_ERR_OK:
            edsdk.EdsRelease(evf_image)
            edsdk.EdsRelease(stream)
            return None

        data_ptr = ctypes.c_void_p()
        length   = EdsUInt64(0)
        edsdk.EdsGetPointer(stream, ctypes.byref(data_ptr))
        edsdk.EdsGetLength(stream, ctypes.byref(length))

        if length.value > 0 and data_ptr.value:
            buffer = ctypes.string_at(data_ptr.value, length.value)
        else:
            buffer = None

        edsdk.EdsRelease(evf_image)
        edsdk.EdsRelease(stream)
        return buffer

    # ── Controles de Zoom Live View (1x, 2x, 5x, 10x) ─────────────────────────

    def set_live_view_zoom(self, zoom_val: int) -> bool:
        """
        Ajusta el zoom de Live View:
          - 1: 1x (Hardware Normal)
          - 2: 2x (Corte Central 50% de Alta Calidad por Software)
          - 5: 5x (Hardware AF)
          - 10: 10x (Hardware Enfoque Fino)
        """
        if not self._is_session_open: return False
        self._active_zoom = zoom_val

        # Si el zoom es 2x, la cámara física permanece en 1x y aplicamos recoche fino en cliente
        hw_zoom = 1 if zoom_val in (1, 2) else zoom_val
        val = EdsUInt32(hw_zoom)
        err = edsdk.EdsSetPropertyData(self._camera_ref, kEdsPropID_Evf_Zoom, 0, ctypes.sizeof(val), ctypes.byref(val))
        return err == EDS_ERR_OK

    def process_frame_zoom(self, frame_rgb: np.ndarray) -> np.ndarray:
        """Aplica procesamiento de interpolación de alta calidad según el nivel de Zoom activo."""
        if self._active_zoom == 2 and frame_rgb is not None:
            H, W, C = frame_rgb.shape
            ch, cw = H // 2, W // 2
            y1, y2 = ch - H // 4, ch + H // 4
            x1, x2 = cw - W // 4, cw + W // 4
            crop = frame_rgb[y1:y2, x1:x2]
            # Interpolación cúbica de máxima nitidez
            return cv2.resize(crop, (W, H), interpolation=cv2.INTER_CUBIC)
        return frame_rgb

    # ── Control Remoto de Enfoque (DriveLens / AF) ────────────────────────────

    def drive_lens(self, command_code: int) -> bool:
        """Envía comando de movimiento de lente motorizado de enfoque."""
        if not self._is_session_open: return False
        err = edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_DriveLensEvf, command_code)
        return err == EDS_ERR_OK

    def trigger_autofocus(self) -> bool:
        """Dispara el enfoque automático EVF."""
        if not self._is_session_open: return False
        err = edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_DoEvfAf, 1)
        return err == EDS_ERR_OK

    # ── Lectura y Ajuste de ISO, Av, Tv, AE Mode ──────────────────────────────

    def get_property_desc(self, prop_id: int) -> List[int]:
        """Obtiene la lista de valores de propiedad soportados por la cámara."""
        if not self._is_session_open: return []
        desc = EdsPropertyDesc()
        err = edsdk.EdsGetPropertyDesc(self._camera_ref, prop_id, ctypes.byref(desc))
        if err != EDS_ERR_OK: return []
        return [desc.propDesc[i] for i in range(desc.numElements)]

    def get_property_value(self, prop_id: int) -> int:
        if not self._is_session_open: return 0
        val = EdsUInt32(0)
        err = edsdk.EdsGetPropertyData(self._camera_ref, prop_id, 0, ctypes.sizeof(val), ctypes.byref(val))
        return val.value if err == EDS_ERR_OK else 0

    def set_property_value(self, prop_id: int, val: int) -> bool:
        if not self._is_session_open: return False
        v = EdsUInt32(val)
        err = edsdk.EdsSetPropertyData(self._camera_ref, prop_id, 0, ctypes.sizeof(v), ctypes.byref(v))
        return err == EDS_ERR_OK

    # ── Captura y Descarga de Fotos ───────────────────────────────────────────

    def take_photo(self) -> bool:
        if not self._is_session_open: return False
        err = edsdk.EdsSendCommand(self._camera_ref, kEdsCameraCommand_TakePicture, 0)
        return err == EDS_ERR_OK

    def set_save_directory(self, path: str):
        self._save_dir = os.path.abspath(path)

    def _register_photo_handler(self):
        def _on_dir_item_created(event: int, item_ref: EdsDirectoryItemRef, context: ctypes.c_void_p) -> int:
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
                    print(f"[Canon Photo] Foto descargada exitosamente en: {save_path}")
            return EDS_ERR_OK

        self._cb_keepalive = EdsObjectEventHandler(_on_dir_item_created)
        edsdk.EdsSetObjectEventHandler(self._camera_ref, kEdsObjectEvent_DirItemCreated, self._cb_keepalive, None)
