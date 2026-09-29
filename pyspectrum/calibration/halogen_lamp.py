# -*- coding: utf-8 -*-
"""
halogen_lamp.py — Calibración de Lámpara Halógena y Algoritmo de Cosido (Step & Glue)
PySpectrum 3.0 — UNSAM Nanofotónica

Fase 4 del Rework Arquitectónico (docs/decisions/DECISION_LOG.md#DEC-018): además de
glue_steps() (blending sigmoideo logístico preexistente, usado sin cambios por
linescan_spectroscopy.py y sus tests), agrega un segundo algoritmo de cosido con la
ponderación raised-cosine (cos²/sin²) exacta especificada en la Fase 4, con solapamiento
determinado directamente por la intersección real de los ejes de longitud de onda de pasos
consecutivos (no por un ancho de píxeles fijo), más el cálculo de centros espectrales según la
dispersión real de la red activa y la exportación HDF5 estructurada del cosido.
"""
from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from pyspectrum.drivers.shamrock_driver import GRATING_150_LINES, nominal_window_nm

try:
    import h5py
    H5PY_AVAILABLE = True
except ImportError:
    H5PY_AVAILABLE = False


class HalogenLampCalibration:
    """Gestiona el perfil de referencia de la lámpara halógena para normalización espectral."""

    def __init__(self, data_path: Optional[str] = None):
        self.wave_lamp = np.linspace(450, 950, 1004)
        self.spec_lamp = np.ones_like(self.wave_lamp)
        self.is_loaded = False
        self.source_path: Optional[Path] = None      # None = perfil sintético: no sirve para normalizar (G-18)
        self._load_reference_data(data_path)

    def _load_reference_data(self, data_path: Optional[str] = None):
        if not data_path:
            base = Path(__file__).resolve().parent / "data" / "lamparaIR_450-950_overlap0.2"
            data_path = str(base / "lamparaIR_grade_2.txt")

        p = Path(data_path)
        if p.exists():
            try:
                data = np.loadtxt(str(p), comments="#")
                self.wave_lamp = data[:, 0]
                self.spec_lamp = data[:, 1]
                self.is_loaded = True
                self.source_path = p
                print(f"[Lamp Calibration] Perfil halógeno cargado ({len(self.wave_lamp)} puntos) desde {p.name}")
            except Exception as e:
                print(f"[Lamp Calibration] Error al leer {p} ({e}). Generando perfil sintético.")
                self._generate_synthetic_profile()
        else:
            print(f"[Lamp Calibration] Archivo {p} no encontrado. Generando perfil sintético de cuerpo negro.")
            self._generate_synthetic_profile()

    def _generate_synthetic_profile(self):
        """Genera una curva de lámpara halógena de 3000 K (cuerpo negro)."""
        self.wave_lamp = np.linspace(450, 950, 1004)
        # Ley de Planck aproximada en el rango visible/NIR
        wl_m = self.wave_lamp * 1e-9
        T = 3000.0  # Kelvin
        h = 6.626e-34; c = 3.0e8; k = 1.38e-23
        intensity = (2.0 * h * c**2) / (wl_m**5 * (np.exp((h * c) / (wl_m * k * T)) - 1.0))
        self.spec_lamp = intensity / np.max(intensity) * 50000.0
        self.is_loaded = True
        self.source_path = None

    def get_lamp_profile(self) -> Tuple[np.ndarray, np.ndarray]:
        return self.wave_lamp, self.spec_lamp

    def normalize_spectrum(self, wave: np.ndarray, spec: np.ndarray) -> np.ndarray:
        """Interpola la lámpara a la cuadrícula de longitud de onda del espectro y normaliza."""
        lamp_interp = np.interp(wave, self.wave_lamp, self.spec_lamp)
        # Evitar división por cero
        lamp_interp = np.where(lamp_interp <= 0, 1.0, lamp_interp)
        return spec / lamp_interp


# ── Algoritmo Step and Glue ───────────────────────────────────────────────────

def glue_steps(wave_py: np.ndarray, spec_py: np.ndarray, number_pixel: int = 1004, grade: float = 2.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Une múltiples espectros discretos obtenidos por Step & Glue con solapamiento ponderado suave.
    """
    if len(spec_py) == 0 or len(wave_py) == 0:
        return np.array([]), np.array([])

    L = int(len(spec_py) / number_pixel)
    if L <= 1:
        return wave_py, spec_py

    n_skip_points = 30
    n = int(n_skip_points / 2)
    valid_pixels = number_pixel - n_skip_points

    spec_steps = np.zeros((valid_pixels, L))
    wave_steps = np.zeros((valid_pixels, L))
    spec_steps_glue = np.zeros((valid_pixels, L))
    wave_steps_glue = np.zeros((valid_pixels, L))

    list_of_inf = np.zeros(L)

    for i in range(L):
        spec = spec_py[i * number_pixel:(i + 1) * number_pixel]
        wave = wave_py[i * number_pixel:(i + 1) * number_pixel]
        spec_steps[:, i] = spec[n:-n]
        wave_steps[:, i] = wave[n:-n]
        spec_steps_glue[:, i] = spec[n:-n]
        wave_steps_glue[:, i] = wave[n:-n]
        list_of_inf[i] = wave_steps[0, i]

    for j in range(L - 1):
        inf = list_of_inf[j + 1]
        wave_tail = wave_steps[:, j]
        desired_range_tail = np.where(wave_tail >= inf)[0]
        m = int(len(desired_range_tail))

        if m > 0:
            # Ponderación sigmoidea suave de transición continua: w(x) = 1 / (1 + exp(-x))
            x_norm = np.linspace(-3.5, 3.5, m)
            weight_h = 1.0 / (1.0 + np.exp(-x_norm))
            weight_t = 1.0 - weight_h

            idx_tail = range(valid_pixels - m, valid_pixels)
            idx_head = range(0, m)

            spec_tail = spec_steps[idx_tail, j]
            wave_t_seg = wave_steps[idx_tail, j]

            spec_head = spec_steps[idx_head, j + 1]
            wave_h_seg = wave_steps[idx_head, j + 1]

            spec_weight = weight_h * spec_head + weight_t * spec_tail

            spec_steps_glue[idx_tail, j] = spec_weight
            wave_steps_glue[idx_tail, j] = wave_t_seg

            spec_steps_glue[idx_head, j + 1] = spec_weight
            wave_steps_glue[idx_head, j + 1] = wave_h_seg

    wave_final = wave_steps_glue.flatten()
    spectrum_final = spec_steps_glue.flatten()

    sort_idx = np.argsort(wave_final)
    wave_sorted = wave_final[sort_idx]
    spec_sorted = spectrum_final[sort_idx]

    # Eliminar duplicados en el área de cosido promediando bins
    unique_waves, inverse_indices = np.unique(np.round(wave_sorted, 4), return_inverse=True)
    counts = np.bincount(inverse_indices)
    spec_unique = np.bincount(inverse_indices, weights=spec_sorted) / counts

    return unique_waves, spec_unique


# ── Fase 4: Cosido Raised-Cosine (cos²/sin²) y Utilidades de Barrido ──────────


def raised_cosine_weights(wavelengths: np.ndarray, lambda_a: float, lambda_b: float) -> Tuple[np.ndarray, np.ndarray]:
    """Pesos raised-cosine w1(λ)=cos²(θ), w2(λ)=sin²(θ) con θ=(π/2)·(λ-λa)/(λb-λa), clampeado
    a [0,1] fuera de [λa,λb]. w1+w2=1 exactamente en todo punto por identidad trigonométrica."""
    span = float(lambda_b) - float(lambda_a)
    if span <= 0:
        t = np.zeros_like(np.asarray(wavelengths, dtype=np.float64))
    else:
        t = np.clip((np.asarray(wavelengths, dtype=np.float64) - lambda_a) / span, 0.0, 1.0)
    theta = (np.pi / 2.0) * t
    w1 = np.cos(theta) ** 2
    w2 = np.sin(theta) ** 2
    return w1, w2


def glue_pair_sigmoidal(
    wave1: np.ndarray, spec1: np.ndarray, wave2: np.ndarray, spec2: np.ndarray,
    edge_crop_pixels: int = 15,
) -> Tuple[np.ndarray, np.ndarray]:
    """Cose dos espectros 1D consecutivos con blending raised-cosine en la región de
    solapamiento real [λa,λb] = intersección de los rangos de wave1/wave2. Fuera de la
    intersección, cada espectro conserva sus valores originales sin modificar.

    edge_crop_pixels: recorta N píxeles de AMBOS extremos de cada paso individual antes de
    calcular la intersección, para evitar la aberración de coma del detector Andor en los
    bordes del CCD. Default 15 = fidelidad exacta con StepandGlue_ps.py/Lampara_ps.py
    (`n_skip_points=30` -> `n=15` por lado, código legado de Luciana/CIBION)."""
    wave1 = np.asarray(wave1, dtype=np.float64)
    spec1 = np.asarray(spec1, dtype=np.float64)
    wave2 = np.asarray(wave2, dtype=np.float64)
    spec2 = np.asarray(spec2, dtype=np.float64)

    n = max(0, int(edge_crop_pixels))
    if n > 0:
        if len(wave1) > 2 * n:
            wave1, spec1 = wave1[n:-n], spec1[n:-n]
        if len(wave2) > 2 * n:
            wave2, spec2 = wave2[n:-n], spec2[n:-n]

    if len(wave1) == 0:
        return wave2, spec2
    if len(wave2) == 0:
        return wave1, spec1

    lambda_a = max(float(wave1.min()), float(wave2.min()))
    lambda_b = min(float(wave1.max()), float(wave2.max()))

    if lambda_b <= lambda_a:
        # Sin solapamiento real entre los dos pasos: concatenar y ordenar sin blending.
        wave_out = np.concatenate([wave1, wave2])
        spec_out = np.concatenate([spec1, spec2])
        order = np.argsort(wave_out)
        return wave_out[order], spec_out[order]

    only1_mask = wave1 < lambda_a
    only2_mask = wave2 > lambda_b
    ov1_mask = (wave1 >= lambda_a) & (wave1 <= lambda_b)
    ov2_mask = (wave2 >= lambda_a) & (wave2 <= lambda_b)

    overlap_wave = np.unique(np.concatenate([wave1[ov1_mask], wave2[ov2_mask]]))
    spec1_interp = np.interp(overlap_wave, wave1, spec1)
    spec2_interp = np.interp(overlap_wave, wave2, spec2)

    w1_weight, w2_weight = raised_cosine_weights(overlap_wave, lambda_a, lambda_b)
    overlap_spec = w1_weight * spec1_interp + w2_weight * spec2_interp

    wave_out = np.concatenate([wave1[only1_mask], overlap_wave, wave2[only2_mask]])
    spec_out = np.concatenate([spec1[only1_mask], overlap_spec, spec2[only2_mask]])
    order = np.argsort(wave_out)
    return wave_out[order], spec_out[order]


def sigmoidal_step_and_glue(wave_steps: List[np.ndarray], spec_steps: List[np.ndarray], edge_crop_pixels: int = 15) -> Tuple[np.ndarray, np.ndarray]:
    """Cose N espectros 1D consecutivos encadenando glue_pair_sigmoidal() secuencialmente
    (cada paso nuevo se funde contra el resultado acumulado). Resiliente a cancelación
    anticipada: basta con pasar una lista parcial de pasos ya adquiridos."""
    if not wave_steps:
        return np.array([]), np.array([])
    wave_acc, spec_acc = wave_steps[0], spec_steps[0]
    for w, s in zip(wave_steps[1:], spec_steps[1:]):
        wave_acc, spec_acc = glue_pair_sigmoidal(wave_acc, spec_acc, w, s, edge_crop_pixels=edge_crop_pixels)
    return wave_acc, spec_acc


def sigmoidal_step_and_glue_2d(wave_steps: List[np.ndarray], frame_steps: List[np.ndarray], edge_crop_pixels: int = 15) -> Tuple[np.ndarray, np.ndarray]:
    """Cose N cuadros 2D (H, W_i) consecutivos fila por fila, reutilizando
    glue_pair_sigmoidal() por cada fila del ROI vertical. Todos los cuadros deben compartir
    la misma altura H (mismo ROI/modo de lectura durante todo el barrido)."""
    if not wave_steps:
        return np.array([]), np.zeros((0, 0))
    if len(wave_steps) == 1:
        return wave_steps[0], frame_steps[0]

    h = frame_steps[0].shape[0]
    wave_acc, row0_acc = wave_steps[0], frame_steps[0][0, :]
    for w, f in zip(wave_steps[1:], frame_steps[1:]):
        wave_acc, row0_acc = glue_pair_sigmoidal(wave_acc, row0_acc, w, f[0, :], edge_crop_pixels=edge_crop_pixels)

    result = np.zeros((h, len(wave_acc)), dtype=np.float64)
    result[0, :] = row0_acc
    for row_idx in range(1, h):
        wave_row, spec_row = wave_steps[0], frame_steps[0][row_idx, :]
        for w, f in zip(wave_steps[1:], frame_steps[1:]):
            wave_row, spec_row = glue_pair_sigmoidal(wave_row, spec_row, w, f[row_idx, :], edge_crop_pixels=edge_crop_pixels)
        result[row_idx, :] = spec_row

    return wave_acc, result


# Ventana por red que el legado usó en el banco (StepandGlue_ps.py:576 y 1065-1069, código de
# Luciana/CIBION), rotulada allí "estimativa". DEC-033 mostró que no es un núcleo conservador
# sino la ventana completa real: la dispersión nominal del SR-500i por el detector de 8 µm da
# 103.05 / 11.57 nm. Se conserva como elección explícita del operador ("Zona Óptica Central").
OPTICAL_CORE_WINDOW_NM = {1: 103.0, 2: 12.0}


def resolve_step_window_nm(
    grating: int, num_pixels: int = 1004, use_optical_core: bool = False,
    window_nm: Optional[float] = None,
) -> Tuple[float, str]:
    """Ancho de ventana con que se planifica el Step & Glue, y de dónde salió.

    Precedencia (DEC-033): la elección explícita del operador (`optical_core`) > la ventana
    medida con la calibración del espectrógrafo (`measured`) > la nominal de la hoja de datos
    (`nominal`). Una medición no finita o no positiva se descarta. El espejo no dispersa, así
    que su nominal cae a la de 150 l/mm para que el planificador siempre termine.
    """
    if use_optical_core:
        return float(OPTICAL_CORE_WINDOW_NM.get(int(grating), OPTICAL_CORE_WINDOW_NM[1])), "optical_core"
    if window_nm is not None and np.isfinite(window_nm) and window_nm > 0.0:
        return float(window_nm), "measured"
    span = nominal_window_nm(grating, num_pixels)
    if not span > 0.0:
        span = nominal_window_nm(GRATING_150_LINES, num_pixels)
    return float(span), "nominal"


def compute_step_centers(
    start_wl: float, end_wl: float, overlap_pct: float, grating: int = 1, num_pixels: int = 1004,
    use_optical_core: bool = False, window_nm: Optional[float] = None,
) -> List[float]:
    """Calcula las longitudes de onda centrales necesarias para cubrir [start_wl, end_wl] con el
    % de solapamiento pedido. El ancho de ventana lo decide `resolve_step_window_nm`.

    Cada extremo del rango recibe el mismo margen que cada lado de un solapamiento interno (la
    mitad del solapamiento): la ventana real no es simétrica respecto de su centro (curvatura
    de la dispersión, exactitud de posicionamiento de la red) y el cosido recorta píxeles de
    borde, así que sin margen el comienzo y el final del rango quedarían sin medir — verificado
    con el eje cúbico del mock, que dejaba 0.4 nm afuera. Se agregan ventanas sólo mientras la
    cobertura no alcance el final: ninguna ventana queda casi entera fuera del rango."""
    full_span, _ = resolve_step_window_nm(grating, num_pixels, use_optical_core, window_nm)
    overlap_pct = max(0.0, min(0.9, float(overlap_pct)))
    step_span = full_span * (1.0 - overlap_pct)
    margin = 0.5 * overlap_pct * full_span

    if end_wl < start_wl:
        return [0.5 * (start_wl + end_wl)]

    c = start_wl - margin + full_span / 2.0
    centers: List[float] = [c]
    while c + full_span / 2.0 < end_wl + margin:
        c += step_span
        centers.append(c)
    return centers


def coverage_gaps_nm(
    wave_steps: List[np.ndarray], start_wl: Optional[float] = None, end_wl: Optional[float] = None,
) -> List[Tuple[float, float]]:
    """Tramos de [start_wl, end_wl] que ninguna ventana adquirida cubre, según sus ejes REALES.

    Es la verificación posterior de la planificación (DEC-014 aplicado a la cobertura): si el
    ancho supuesto al planificar no coincide con el físico, aparecen huecos entre ventanas y
    acá se ven, en lugar de quedar escondidos por el cosido."""
    intervals = sorted(
        (float(np.nanmin(w)), float(np.nanmax(w)))
        for w in wave_steps
        if w is not None and np.size(w) > 1 and np.isfinite(np.asarray(w, dtype=np.float64)).any()
    )
    if not intervals:
        return [(float(start_wl), float(end_wl))] if start_wl is not None and end_wl is not None else []

    gaps: List[Tuple[float, float]] = []
    cursor = float(start_wl) if start_wl is not None else intervals[0][0]
    for lo, hi in intervals:
        if lo > cursor:
            gaps.append((cursor, lo))
        cursor = max(cursor, hi)
    if end_wl is not None and cursor < float(end_wl):
        gaps.append((cursor, float(end_wl)))
    return gaps


def export_step_and_glue_to_hdf5(
    filepath: str, glued_wave: np.ndarray, glued_spec: np.ndarray,
    raw_wave_steps: List[np.ndarray], raw_spec_steps: List[np.ndarray],
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Exporta el cosido Step & Glue a HDF5 estructurado: /glued_spectrum, /wavelengths y un
    grupo /raw_steps/step_NN por cada paso crudo adquirido, con metadatos de red, ranura,
    número de pasos y timestamp como atributos. Degradación segura si h5py no está disponible
    (mismo patrón que core/sif_processor.py::export_sif_session_to_hdf5): no escribe nada y
    retorna la ruta solicitada sin crear el archivo."""
    if not H5PY_AVAILABLE:
        print("[Step & Glue HDF5 Warning] h5py no está disponible. No se generará el archivo.")
        return filepath

    os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
    comp = dict(compression="gzip", compression_opts=4, shuffle=True)

    with h5py.File(filepath, "w") as f:
        f.attrs["NX_class"] = "NXentry"
        f.attrs["n_steps"] = len(raw_wave_steps)
        f.attrs["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        for k, v in (metadata or {}).items():
            if v is not None:
                f.attrs[k] = v

        f.create_dataset("wavelengths", data=np.asarray(glued_wave, dtype=np.float64), **comp)
        f.create_dataset("glued_spectrum", data=np.asarray(glued_spec, dtype=np.float64), **comp)

        raw_group = f.create_group("raw_steps")
        for i, (w, s) in enumerate(zip(raw_wave_steps, raw_spec_steps)):
            step_grp = raw_group.create_group(f"step_{i:02d}")
            step_grp.create_dataset("wavelength", data=np.asarray(w, dtype=np.float64), **comp)
            step_grp.create_dataset("intensity", data=np.asarray(s, dtype=np.float64), **comp)

    return filepath
