# -*- coding: utf-8 -*-
"""
slit_center.py — Centro de la ranura en orden cero (R4-N 1a; respuestas P1 a P4 del 2026-09-30; DEC-040)

Sin Qt. La ranura es vertical: en orden cero (condición especular) su imagen es una línea brillante a lo largo
de las filas.

- **Método (P1):** una gaussiana con fondo lineal en cada fila del ROI vertical (`estimate_line_center`, el
  estimador de la calibración de λ y de Exploración) y el promedio de las posiciones del máximo. Esa columna,
  cruzada con el ROI de filas, es la zona de trabajo.
- **Estadística (P2):** sale de las filas. Las filas se ajustan a una recta (centro contra fila): su pendiente es
  la inclinación de la ranura sobre el sensor y la dispersión se mide respecto de esa recta. Una fila que se
  aparta (un rayo cósmico) se descarta. u del centro: Tipo A, s / √n, o la del ajuste si es mayor.
- **Con varios cuadros,** cada píxel es la mediana en el tiempo (los rayos se rechazan entre cuadros).
- **Saturación, por fila:** una fila con el crudo al 80 % del ADC no se usa (un rayo cósmico satura una o dos
  filas); si satura más del 10 % de las filas, satura la imagen de la ranura y la medición se rechaza.
- **Se rechaza:** fuera de orden cero, sin un ROI de al menos 5 filas, con la imagen saturada, sin línea o con
  menos de la mitad de las filas útiles. Una medición rechazada no da centro (NaN) y no se guarda.
- **Unidades:** píxeles del sensor contados desde 0, sin el volteo de la pantalla; FWHM también en µm
  (× 8 µm por píxel).
- **Resultado EXPERIMENTAL:** el método no está validado en el banco (BANCO-63).
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Tuple

import numpy as np

from core.spectral_line_fit import FWHM_PER_SIGMA, estimate_line_center

SESSION_NAME = "Calibración de ranura"
DEFAULT_EXPOSURE_S = 0.05
DEFAULT_FRAMES = 1
MIN_ROWS = 5
MIN_USED_FRACTION = 0.5
TILT_FLAG_PX = 1.0                 # corrimiento del centro de punta a punta del ROI que levanta TILT
OUTLIER_MAD = 5.0
OUTLIER_FLOOR_PX = 0.2
SEARCH_HALF_PX = 25
MAX_SATURATED_ROW_FRACTION = 0.10
DETECTOR_ROWS = 1002
DETECTOR_COLS = 1004
_DRV_SUCCESS = 20002


class SlitCalibrationRefused(RuntimeError):
    """La medición no se puede hacer (orden cero, ROI, cámara); el motivo va en el mensaje."""


@dataclass(frozen=True)
class SlitCenterResult:
    ok: bool
    reason: str                        # vacío si salió bien
    center_px: float                   # NaN si no salió bien
    u_center_px: float
    fwhm_px: float
    fwhm_um: float
    scatter_px: float                  # desviación de los centros por fila respecto de la recta
    tilt_px_per_row: float
    rows: Tuple[int, int]              # filas del sensor [r0, r1)
    rows_used: Tuple[int, ...]
    row_centers: Tuple[float, ...]
    n_frames: int
    saturation_frac: float
    flags: Tuple[str, ...]
    profile: Optional[np.ndarray] = None      # promedio de las filas usadas, para mostrar
    fit_x: Optional[np.ndarray] = None
    fit_y: Optional[np.ndarray] = None
    frames_file: Optional[str] = None

    def summary(self) -> str:
        if not self.ok:
            flags = f" ({', '.join(self.flags)})" if self.flags else ""
            return f"No se calibró: {self.reason}{flags}"
        extra = f" · banderas: {', '.join(self.flags)}" if self.flags else ""
        return (f"Centro {self.center_px:.2f} ± {self.u_center_px:.2f} px · FWHM {self.fwhm_px:.2f} px "
                f"({self.fwhm_um:.1f} µm) · dispersión {self.scatter_px:.2f} px · inclinación "
                f"{self.tilt_px_per_row * 1000:.1f} mpx/fila · {len(self.rows_used)}/{self.rows[1] - self.rows[0]} "
                f"filas{extra}")

    def values(self) -> Dict:
        """Lo que va al archivo de calibraciones (sin los arreglos)."""
        return {"center_px": float(self.center_px), "u_center_px": float(self.u_center_px),
                "fwhm_px": float(self.fwhm_px), "fwhm_um": float(self.fwhm_um), "scatter_px": float(self.scatter_px),
                "tilt_px_per_row": float(self.tilt_px_per_row), "rows": [int(self.rows[0]), int(self.rows[1])],
                "n_rows_used": len(self.rows_used), "n_frames": int(self.n_frames),
                "saturation_frac": float(self.saturation_frac), "flags": list(self.flags),
                "frames_file": self.frames_file, "provenance": "EXPERIMENTAL"}


def failed_result(reason: str, rows, n_frames: int, sat: float, flags) -> SlitCenterResult:
    nan = float("nan")
    return SlitCenterResult(False, reason, nan, nan, nan, nan, nan, nan, (int(rows[0]), int(rows[1])), (), (),
                            int(n_frames), float(sat), tuple(flags))


def _row_saturation(frames: np.ndarray) -> np.ndarray:
    """Por fila, el mayor (pico − bias) / ADC entre los cuadros crudos (la escala de `saturation_level`)."""
    from pyspectrum.modules.zero_order_service import ZeroOrderService
    return np.array([max(ZeroOrderService.saturation_level(f[i])[0] for f in frames)
                     for i in range(frames.shape[1])])


def analyze_slit_frames(frames, rows: Sequence[int], *, pixel_um: float = 8.0) -> SlitCenterResult:
    """Centro de la ranura a partir de cuadros crudos de las filas `rows` = (r0, r1). Puro."""
    from pyspectrum.modules.zero_order_service import SATURATION_ALARM_FRAC, SATURATION_WARN_FRAC
    arr = np.asarray(frames, dtype=np.float64)
    if arr.ndim == 2:
        arr = arr[None]
    r0, r1 = int(rows[0]), int(rows[1])
    k = arr.shape[0] if arr.ndim == 3 else 0
    if arr.ndim != 3 or arr.shape[1] != r1 - r0 or arr.shape[1] < MIN_ROWS:
        return failed_result(f"los cuadros no tienen las filas del ROI ({arr.shape} para {r1 - r0} filas)", rows, k,
                       0.0, ["NO_LINE"])
    row_sat = _row_saturation(arr)
    saturated = row_sat >= SATURATION_ALARM_FRAC
    n_rows = arr.shape[1]
    if saturated.sum() > MAX_SATURATED_ROW_FRACTION * n_rows:
        return failed_result(f"el crudo satura en {int(saturated.sum())} de {n_rows} filas ({float(row_sat.max()):.0%} "
                       f"del ADC): bajá la exposición o la luz", rows, k, float(row_sat.max()), ["SATURATED"])
    sat = float(row_sat[~saturated].max())
    image = np.median(arr, axis=0) if k >= 3 else arr.mean(axis=0)

    seed = estimate_line_center(image.mean(axis=0))
    if not seed.success:
        return failed_result("no se ve la imagen de la ranura en el promedio de las filas", rows, k, sat,
                       ["NO_LINE"] + [f for f in seed.flags if f != "NO_LINE"])
    half = int(max(SEARCH_HALF_PX, 3 * seed.fwhm_px))
    search = (int(seed.center_px) - half, int(seed.center_px) + half)

    idx, centers, us, fwhms, row_flags = [], [], [], [], []
    for i in range(n_rows):
        if saturated[i]:
            continue
        r = estimate_line_center(image[i], center_guess_px=seed.center_px, search_range_px=search)
        if r.success and "EDGE" not in r.flags:
            idx.append(i)
            centers.append(r.center_px)
            us.append(r.u_center_px)
            fwhms.append(r.fwhm_px)
            row_flags.append(r.flags)
    need = max(MIN_ROWS, int(math.ceil(MIN_USED_FRACTION * n_rows)))
    if len(idx) < need:
        return failed_result(f"sólo {len(idx)} de {n_rows} filas muestran la línea (hacen falta {need}): ajustá el ROI "
                       f"vertical a la imagen de la ranura", rows, k, sat, ["FEW_ROWS"])

    idx_a, c_a, u_a, w_a = (np.asarray(v, dtype=np.float64) for v in (idx, centers, us, fwhms))
    keep = np.ones(idx_a.size, dtype=bool)
    for _ in range(2):                                 # recta robusta: se ajusta, se descartan filas, se reajusta
        slope, icpt = np.polyfit(idx_a[keep], c_a[keep], 1)
        resid = c_a - (slope * idx_a + icpt)
        mad = 1.4826 * float(np.median(np.abs(resid[keep] - np.median(resid[keep]))))
        keep = np.abs(resid) <= max(OUTLIER_MAD * mad, OUTLIER_FLOOR_PX)
    if int(keep.sum()) < need:
        return failed_result(f"las filas no coinciden entre sí: sólo {int(keep.sum())} de {n_rows} quedan cerca de la "
                       f"recta", rows, k, sat, ["SCATTERED"])
    slope, icpt = np.polyfit(idx_a[keep], c_a[keep], 1)
    resid = c_a[keep] - (slope * idx_a[keep] + icpt)
    n = int(keep.sum())
    scatter = float(np.sqrt(np.sum(resid ** 2) / max(1, n - 2)))
    center = float(np.mean(c_a[keep]))
    u_center = max(scatter / math.sqrt(n), float(np.sqrt(np.mean(u_a[keep] ** 2)) / math.sqrt(n)))
    fwhm = float(np.median(w_a[keep]))

    flags = []
    if abs(slope) * (n_rows - 1) > TILT_FLAG_PX:
        flags.append("TILT")
    if n < idx_a.size or idx_a.size < n_rows:
        flags.append("ROWS_REJECTED")
    if sat >= SATURATION_WARN_FRAC:
        flags.append("SATURATION_WARN")
    if saturated.any():
        flags.append("ROWS_SATURATED")
    kept_flags = [f for f, ok in zip(row_flags, keep) if ok]
    for name in ("LOW_SNR", "ASYMMETRIC"):
        if sum(name in f for f in kept_flags) > n / 2:
            flags.append(name)

    used = idx_a[keep].astype(int)
    profile = image[used].mean(axis=0)
    disp = estimate_line_center(profile, center_guess_px=center, search_range_px=search)
    fit_x = fit_y = None
    if disp.success:
        a, b = disp.window_px
        fit_x = np.arange(a, b + 1, dtype=np.float64)
        sigma = disp.fwhm_px / FWHM_PER_SIGMA
        fit_y = (disp.amplitude_counts * np.exp(-0.5 * ((fit_x - disp.center_px) / sigma) ** 2)
                 + disp.background_counts + disp.background_slope_counts_per_px * (fit_x - disp.center_px))
    return SlitCenterResult(True, "", center, u_center, fwhm, fwhm * float(pixel_um), scatter, float(slope),
                            (r0, r1), tuple(int(r0 + i) for i in used), tuple(float(c) for c in c_a[keep]), k,
                            float(sat), tuple(flags), profile, fit_x, fit_y)


# ── Contra la cámara ────────────────────────────────────────────────────────────────────────

def zero_order_mode(camera, spectrometer) -> str:
    """La condición leída del Shamrock ahora (sólo lectura): SPECULAR, FIRST_ORDER o UNKNOWN."""
    from pyspectrum.modules.zero_order_service import get_zero_order_service
    return get_zero_order_service(camera, spectrometer).refresh_state()


def check_rows(rows) -> Tuple[int, int]:
    try:
        r0, r1 = int(rows[0]), int(rows[1])
    except (TypeError, ValueError, IndexError):
        raise SlitCalibrationRefused("Definí el ROI vertical (Exploración) sobre la imagen de la ranura.")
    if r0 < 0 or r1 > DETECTOR_ROWS or r1 - r0 < MIN_ROWS:
        raise SlitCalibrationRefused(f"El ROI vertical [{r0}, {r1}) no sirve: tiene que tener al menos {MIN_ROWS} "
                                     f"filas dentro del sensor. Definilo en Exploración sobre la imagen de la ranura.")
    return r0, r1


def check_zero_order(mode: str) -> None:
    from pyspectrum.drivers import specular_interlock as si
    if mode != si.SPECULAR:
        raise SlitCalibrationRefused(f"El espectrógrafo no está en orden cero (se leyó: {mode}). Pasá a orden "
                                     f"cero y volvé a intentar.")


def _snapshot(camera):
    from pyspectrum.drivers.andor_ccd_driver import READ_MODE_IMAGE, READ_MODE_SINGLE_TRACK
    mode = camera.get_read_mode()
    extra = None
    if mode == READ_MODE_SINGLE_TRACK and hasattr(camera, "get_single_track"):
        extra = tuple(camera.get_single_track())
    elif mode == READ_MODE_IMAGE and hasattr(camera, "get_image_params"):
        extra = camera.get_image_params()
    return mode, extra


def _restore(camera, snap) -> None:
    from pyspectrum.drivers.andor_ccd_driver import READ_MODE_IMAGE, READ_MODE_SINGLE_TRACK
    mode, extra = snap
    if mode == READ_MODE_IMAGE:
        if extra:
            hs, he, vs, ve, hb, vb = (int(v) for v in extra)
            camera.set_image(hb, vb, hs + 1, he, vs + 1, ve)
        else:
            camera.set_image()
        return
    camera.set_read_mode(mode)
    if mode == READ_MODE_SINGLE_TRACK and extra:
        camera.set_single_track(int(extra[0]), int(extra[1]))


def measure_slit_center(camera, expose: Callable[[Tuple[int, int], float], np.ndarray], *, exposure_s: float,
                        rows, n_frames: int, mode_fn: Callable[[], str]) -> SlitCenterResult:
    """Toma `n_frames` cuadros nuevos de las filas del ROI con `expose` y los analiza. Exige orden cero.

    No abre ni cierra obturadores (lo hace la sesión que llama) y deja la cámara en el modo de lectura que tenía,
    también si la exposición falla. Lanza SlitCalibrationRefused antes de tocar la cámara."""
    check_zero_order(mode_fn())
    r0, r1 = check_rows(rows)
    snap = _snapshot(camera)
    try:
        ret = camera.set_image(1, 1, 1, DETECTOR_COLS, r0 + 1, r1)
        if ret != _DRV_SUCCESS:
            raise SlitCalibrationRefused(f"La cámara no aceptó el modo imagen sobre el ROI (código {ret}).")
        frames = [np.asarray(expose((r1 - r0, DETECTOR_COLS), float(exposure_s)), dtype=np.float64)
                  for _ in range(max(1, int(n_frames)))]
    finally:
        _restore(camera, snap)
    return analyze_slit_frames(np.stack(frames), (r0, r1))


def save_slit_frames(directory, frames, result: SlitCenterResult, meta: Optional[Dict] = None) -> Path:
    """Los cuadros crudos de una medición buena, aparte (`slit_center_<fecha>.h5`)."""
    import h5py
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"slit_center_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.h5"
    with h5py.File(path, "w") as f:
        f.create_dataset("frames", data=np.asarray(frames, dtype=np.float32), compression="gzip", shuffle=True)
        f.attrs["rows"] = list(result.rows)
        f.attrs["result_json"] = json.dumps(result.values(), ensure_ascii=False)
        f.attrs["meta_json"] = json.dumps(meta or {}, ensure_ascii=False)
    return path


def with_frames_file(result: SlitCenterResult, path) -> SlitCenterResult:
    return replace(result, frames_file=str(path))
