# -*- coding: utf-8 -*-
"""
exploration_analysis.py — Herramientas de la pestaña Exploración, sin Qt (paquete 2 de R4-M, DEC-040)

Contrato de las Rondas 2 y 3 (investigador, 2026-09-30):

- **Regla:** perfiles horizontal y vertical en px del sensor, promediados en una banda impar.
- **Eje del perfil horizontal:** λ del Shamrock (`ShamrockGetCalibration`, como las rutinas) sólo en
  primer orden. La corrección fina `c_sw` no mueve el eje: es metadato (R4-C-6). En especular o con el
  estado desconocido, px.
- **Ajuste gaussiano** de los dos perfiles con `estimate_line_center`, el estimador de la calibración de
  λ: los números de Exploración y los de la calibración salen del mismo cálculo.
- **Saturación** sobre el cuadro CRUDO: pico / 16383, siempre. El ADC recorta las cuentas crudas, bias
  incluido; con fondo restado o sin él, se mira el crudo.
- **Fondo:** vale sólo con las mismas condiciones de adquisición (exposición, ganancia EM, amplificador,
  preamplificador, HS, VS, modo de lectura, red, λc y forma del cuadro). El operador cierra el obturador
  por su cuenta; acá sólo se registra el estado leído.
- **Traza en el tiempo** de una fila propia o de la media del ROI vertical.
- **Guardado** en HDF5: el crudo y el fondo por separado, nunca sólo la resta.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from core.spectral_line_fit import FWHM_PER_SIGMA, LineCenterResult, estimate_line_center
from pyspectrum.drivers.andor_ccd_driver import ADC_MAX_COUNTS, DETECTOR_PIXEL_PITCH_UM

BAND_MAX_PX = 51
SAT_WARN_FRAC = 0.5            # H-21, ahora sobre el pico crudo
SAT_ALARM_FRAC = 0.8
BACKGROUND_FRAMES_DEFAULT = 10
TRACE_MAX_S = 600.0
TRACE_WINDOW_DEFAULT_S = 60.0
FIT_SEARCH_HALF_PX = 50
_FIRST_ORDER = "first_order"   # specular_interlock.FIRST_ORDER (sin importar el módulo del interlock)
_SHAMROCK_SUCCESS = 20202
_DRV_SUCCESS = 20002


# ── Perfiles ───────────────────────────────────────────────────────────────────────────────

def odd_band(band_px: int) -> int:
    """Ancho de banda impar entre 1 y BAND_MAX_PX (un par pasa al impar siguiente)."""
    b = max(1, int(band_px))
    if b % 2 == 0:
        b += 1
    return min(b, BAND_MAX_PX)


def _band(center: float, band_px: int, n: int) -> Tuple[int, int]:
    c = int(round(min(max(float(center), 0.0), n - 1)))
    half = odd_band(band_px) // 2
    return max(0, c - half), min(n, c + half + 1)


def _as_2d(frame) -> np.ndarray:
    arr = np.asarray(frame, dtype=np.float64)
    return arr[None, :] if arr.ndim == 1 else arr


def row_profile(frame, y_px: float, band_px: int = 1) -> np.ndarray:
    """Perfil horizontal: la media de las filas de la banda centrada en `y_px`."""
    arr = _as_2d(frame)
    lo, hi = _band(y_px, band_px, arr.shape[0])
    return arr[lo:hi].mean(axis=0)


def column_profile(frame, x_px: float, band_px: int = 1) -> np.ndarray:
    """Perfil vertical: la media de las columnas de la banda centrada en `x_px`."""
    arr = _as_2d(frame)
    lo, hi = _band(x_px, band_px, arr.shape[1])
    return arr[:, lo:hi].mean(axis=1)


# ── Eje del perfil horizontal ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProfileAxis:
    kind: str                  # "lambda" | "pixel"
    values: np.ndarray         # nm por píxel, o el índice de píxel
    reason: str = ""           # por qué no es λ (vacío si es λ)


def profile_axis(mode: str, wavelength_nm, width: int) -> ProfileAxis:
    pixels = np.arange(int(width), dtype=float)
    if mode != _FIRST_ORDER:
        why = "estado desconocido: cuenta como especular" if mode == "unknown" else "orden cero o especular"
        return ProfileAxis("pixel", pixels, why)
    if wavelength_nm is None:
        return ProfileAxis("pixel", pixels, "no hay eje del Shamrock")
    axis = np.asarray(wavelength_nm, dtype=float)
    if axis.ndim != 1 or axis.size != int(width):
        return ProfileAxis("pixel", pixels, f"el eje del Shamrock tiene {axis.size} valores y el cuadro {width} columnas")
    if not np.all(np.isfinite(axis)):
        return ProfileAxis("pixel", pixels, "el eje del Shamrock tiene valores no finitos")
    d = np.diff(axis)
    if not (np.all(d > 0) or np.all(d < 0)):
        return ProfileAxis("pixel", pixels, "el eje del Shamrock no es monótono")
    return ProfileAxis("lambda", wavelength_nm)


# ── Ajuste gaussiano ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProfileFit:
    result: LineCenterResult
    unit: str                  # "nm" (horizontal en primer orden) o "µm" (espacial: imagen 1:1)
    center: float              # en `unit` (en µm: desde el px 0 del sensor; para leer, center_px)
    u_center: float
    fwhm: float
    center_px: float
    fwhm_px: float


def fit_profile(profile, *, seed_px: float, axis: Optional[ProfileAxis] = None,
                search_half_px: int = FIT_SEARCH_HALF_PX, saturated: bool = False,
                pitch_um: float = DETECTOR_PIXEL_PITCH_UM) -> ProfileFit:
    """Gaussiana con fondo lineal alrededor de la regla. Con eje λ, centro y FWHM en nm con la dispersión
    local; sin eje λ (orden cero, o el perfil vertical), en µm con el pitch del detector (imagen 1:1)."""
    y = np.asarray(profile, dtype=float).ravel()
    n = y.size
    lo = max(0, int(math.floor(seed_px - search_half_px)))
    hi = min(n - 1, int(math.ceil(seed_px + search_half_px)))
    res = estimate_line_center(y, center_guess_px=float(seed_px), search_range_px=(lo, hi),
                               edge_trim_px=min(15, max(1, n // 20)), saturated=saturated,
                               seeded_by_operator=True)
    c_px, w_px, u_px = res.center_px, res.fwhm_px, res.u_center_px
    if axis is not None and axis.kind == "lambda":
        lam = np.asarray(axis.values, dtype=float)
        idx = np.arange(lam.size, dtype=float)
        if res.success:
            disp = abs(float(np.interp(c_px, idx, np.gradient(lam))))
            return ProfileFit(res, "nm", float(np.interp(c_px, idx, lam)), u_px * disp, w_px * disp, c_px, w_px)
        return ProfileFit(res, "nm", float("nan"), float("nan"), float("nan"), c_px, w_px)
    if res.success:
        return ProfileFit(res, "µm", c_px * pitch_um, u_px * pitch_um, w_px * pitch_um, c_px, w_px)
    return ProfileFit(res, "µm", float("nan"), float("nan"), float("nan"), c_px, w_px)


def fit_model_curve(fit: ProfileFit, n_points: int = 200) -> Tuple[np.ndarray, np.ndarray]:
    """El modelo ajustado (gaussiana + fondo lineal) sobre la ventana del ajuste, para dibujarlo."""
    r = fit.result
    if not r.success:
        return np.empty(0), np.empty(0)
    a, b = r.window_px
    x = np.linspace(a, b, n_points)
    sigma = r.fwhm_px / FWHM_PER_SIGMA
    y = (r.background_counts + r.background_slope_counts_per_px * (x - r.center_px)
         + r.amplitude_counts * np.exp(-0.5 * ((x - r.center_px) / sigma) ** 2))
    return x, y


# ── Saturación sobre el crudo ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RawSaturation:
    peak_counts: float
    frac: float
    n_clipped: int
    level: str                 # "ok" | "warn" | "alarm"


def raw_saturation(raw, adc_max: int = ADC_MAX_COUNTS) -> RawSaturation:
    arr = np.asarray(raw, dtype=float)
    if arr.size == 0:
        return RawSaturation(0.0, 0.0, 0, "ok")
    peak = float(np.max(arr))
    frac = peak / float(adc_max)
    level = "alarm" if frac >= SAT_ALARM_FRAC else ("warn" if frac >= SAT_WARN_FRAC else "ok")
    return RawSaturation(peak, frac, int(np.count_nonzero(arr >= adc_max)), level)


# ── Fondo ──────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CameraSettings:
    exposure_s: Optional[float]
    em_gain: Optional[int]
    output_amplifier: Optional[int]
    preamp_index: Optional[int]
    hs_index: Optional[int]
    vs_index: Optional[int]
    read_mode: Optional[int]
    grating: Optional[int]
    center_nm: Optional[float]
    shape: Optional[Tuple[int, ...]]


_SETTING_NAMES = {"exposure_s": "exposición", "em_gain": "ganancia EM", "output_amplifier": "amplificador",
                  "preamp_index": "preamplificador", "hs_index": "velocidad HS", "vs_index": "velocidad VS",
                  "read_mode": "modo de lectura", "grating": "red", "center_nm": "λc", "shape": "forma del cuadro"}


def _call(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


def _code_value(res, ok_code):
    """Lecturas que devuelven (código, valor): el valor sólo si el código es de éxito."""
    if isinstance(res, (tuple, list)) and len(res) >= 2:
        return res[1] if res[0] == ok_code else None
    return res


def snapshot_settings(camera, spectrometer, shape) -> CameraSettings:
    """Las condiciones de adquisición actuales. Una lectura que falla queda en None (y el fondo no vale)."""
    def cam(name, ok=_DRV_SUCCESS):
        fn = getattr(camera, name, None)
        return None if fn is None else _code_value(_call(fn), ok)

    def spec(name):
        fn = getattr(spectrometer, name, None) if spectrometer is not None else None
        return None if fn is None else _code_value(_call(fn, 0), _SHAMROCK_SUCCESS)

    exposure = cam("get_exposure_time_checked")
    gain = cam("get_emccd_gain")
    center = spec("ShamrockGetWavelength")
    return CameraSettings(
        exposure_s=float(exposure) if exposure is not None else None,
        em_gain=int(gain) if gain is not None else None,
        output_amplifier=_int_or_none(cam("get_output_amplifier")),
        preamp_index=_int_or_none(cam("get_preamp_gain_index")),
        hs_index=_int_or_none(cam("get_hs_speed_index")),
        vs_index=_int_or_none(cam("get_vs_speed_index")),
        read_mode=_int_or_none(cam("get_read_mode")),
        grating=_int_or_none(spec("ShamrockGetGrating")),
        center_nm=float(center) if center is not None else None,
        shape=tuple(int(s) for s in shape) if shape is not None else None)


def _int_or_none(v):
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def settings_differences(ref: CameraSettings, now: CameraSettings) -> list:
    """Qué condición cambió respecto de `ref`, en palabras ("exposición: 0.1 → 0.2 s")."""
    out = []
    for key, label in _SETTING_NAMES.items():
        a, b = getattr(ref, key), getattr(now, key)
        if b is None and a is not None:
            out.append(f"no se pudo leer {label}")
        elif a is None or b is None:
            if a != b:
                out.append(f"{label}: {a} → {b}")
        elif key == "exposure_s":
            if abs(a - b) > 1e-6 * max(abs(a), abs(b), 1e-9):
                out.append(f"{label}: {a:g} → {b:g} s")
        elif key == "center_nm":
            if abs(a - b) > 0.01:
                out.append(f"{label}: {a:.2f} → {b:.2f} nm")
        elif a != b:
            out.append(f"{label}: {a} → {b}")
    return out


@dataclass(frozen=True)
class Background:
    data: np.ndarray           # float32, la media de n_frames cuadros
    n_frames: int
    settings: CameraSettings
    first_index: int
    last_index: int
    t_host: float
    shutter_note: str          # estado del obturador leído al tomarlo (lo cierra el operador)


def background_status(bg: Optional[Background], settings_now: CameraSettings) -> Tuple[bool, str]:
    if bg is None:
        return False, "sin fondo"
    diffs = settings_differences(bg.settings, settings_now)
    return (not diffs), "; ".join(diffs)


class BackgroundAccumulator:
    """Promedia los próximos `n` cuadros distintos (por índice) de la misma forma."""

    def __init__(self, n_frames: int, settings: CameraSettings, shutter_note: str):
        self.n = max(1, int(n_frames))
        self.settings = settings
        self.shutter_note = shutter_note
        self._sum = None
        self._count = 0
        self._first = self._last = None

    @property
    def count(self) -> int:
        return self._count

    def add(self, frame, index: int, t_host: float = 0.0) -> Optional[Background]:
        arr = np.asarray(frame, dtype=np.float64)
        if self._last is not None and int(index) == self._last:
            return None
        if self._sum is None:
            self._sum, self._first = np.zeros_like(arr), int(index)
        elif arr.shape != self._sum.shape:
            raise ValueError(f"el cuadro cambió de forma durante el fondo: {self._sum.shape} → {arr.shape}")
        self._sum += arr
        self._count += 1
        self._last = int(index)
        if self._count < self.n:
            return None
        return Background((self._sum / self._count).astype(np.float32), self._count, self.settings,
                          self._first, self._last, float(t_host), self.shutter_note)


# ── Traza en el tiempo ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TraceSource:
    kind: str                  # "row": una fila (línea propia) | "roi": media del ROI vertical
    a: int
    b: int = 0


def trace_value(frame, source: TraceSource) -> float:
    arr = _as_2d(frame)
    n = arr.shape[0]
    if source.kind == "row":
        y = int(min(max(source.a, 0), n - 1))
        return float(arr[y].mean())
    lo = int(min(max(source.a, 0), n - 1))
    hi = int(min(max(source.b, lo + 1), n))
    return float(arr[lo:hi].mean())


class RoiTrace:
    """Puntos (t, índice, valor) de los últimos `max_s` segundos."""

    def __init__(self, max_s: float = TRACE_MAX_S):
        self.max_s = float(max_s)
        self._pts: deque = deque()

    def __len__(self) -> int:
        return len(self._pts)

    def append(self, t: float, index: int, value: float) -> None:
        self._pts.append((float(t), int(index), float(value)))
        while self._pts and self._pts[0][0] < t - self.max_s:
            self._pts.popleft()

    def points(self, window_s: float) -> Tuple[np.ndarray, np.ndarray]:
        if not self._pts:
            return np.empty(0), np.empty(0)
        t_last = self._pts[-1][0]
        sel = [(t, v) for t, _i, v in self._pts if t >= t_last - float(window_s)]
        arr = np.asarray(sel, dtype=float)
        return arr[:, 0], arr[:, 1]

    def clear(self) -> None:
        self._pts.clear()


# ── Niveles ────────────────────────────────────────────────────────────────────────────────

LEVEL_MODES = ("manual", "auto", "adc")


def display_levels(frame, mode: str) -> Optional[Tuple[float, float]]:
    if mode == "manual":
        return None
    if mode == "auto":
        from core.sif_processor import compute_robust_contrast_levels
        lo, hi = compute_robust_contrast_levels(np.asarray(frame, dtype=float))
        return float(lo), float(hi)
    if mode == "adc":
        return 0.0, float(ADC_MAX_COUNTS)
    raise ValueError(f"modo de niveles desconocido: {mode}")


# ── Guardado ───────────────────────────────────────────────────────────────────────────────

def _jsonable(obj: Any):
    if hasattr(obj, "_asdict"):
        return {k: _jsonable(v) for k, v in obj._asdict().items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist() if obj.size <= 4096 else f"<array {obj.shape} {obj.dtype}>"
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _attr_value(v: Any):
    if isinstance(v, (bool, int, float, str, np.generic)):
        return v
    if v is None:
        return "None"
    return json.dumps(_jsonable(v), ensure_ascii=False)


def default_save_path(data_dir, now: Optional[_dt.datetime] = None) -> Path:
    """`data_dir` es la carpeta de Exploración (work_dir/exploration, como las demás pestañas)."""
    now = now or _dt.datetime.now()
    return Path(data_dir) / f"exploration_{now:%Y%m%d_%H%M%S}.h5"


def save_exploration_h5(path, *, raw, background: Optional[Background], subtract: bool, axis: ProfileAxis,
                        cuts: Dict[str, np.ndarray], metadata: Dict[str, Any], full_info: Dict[str, Any]) -> Path:
    import h5py
    from pyspectrum.calibration.repository import _software_version
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    comp = dict(compression="gzip", compression_opts=4, shuffle=True)
    with h5py.File(path, "w") as f:
        f.create_dataset("frame/raw", data=np.asarray(raw), **comp)
        if background is not None:
            d = f.create_dataset("frame/background", data=background.data, **comp)
            d.attrs["n_frames"] = int(background.n_frames)
            d.attrs["first_index"] = int(background.first_index)
            d.attrs["last_index"] = int(background.last_index)
            d.attrs["shutter_note"] = background.shutter_note
            labelled = {_SETTING_NAMES[k]: v for k, v in asdict(background.settings).items()}
            d.attrs["settings_json"] = json.dumps(_jsonable(labelled), ensure_ascii=False)
        if axis.kind == "lambda":
            f.create_dataset("axis/wavelength_nm", data=np.asarray(axis.values, dtype=float))
        for name, cut in cuts.items():
            f.create_dataset(f"cuts/{name}", data=np.asarray(cut, dtype=float))
        f.attrs["axis_kind"] = axis.kind
        f.attrs["axis_reason"] = axis.reason
        f.attrs["subtract_background"] = bool(subtract and background is not None)
        f.attrs["camera_full_info_json"] = json.dumps(_jsonable(full_info), ensure_ascii=False)
        f.attrs["provenance"] = "EXPERIMENTAL"
        f.attrs["software_version"] = _software_version()
        f.attrs["c_sw_policy"] = "no aplicada al eje (R4-C-6)"
        for k, v in metadata.items():
            f.attrs[str(k)] = _attr_value(v)
    return path
