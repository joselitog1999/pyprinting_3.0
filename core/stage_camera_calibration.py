# -*- coding: utf-8 -*-
"""
core/stage_camera_calibration.py — Orquestación de la calibración de
StageCameraTransform (Fase B): asistente de paso físico con confirmación visual humana
obligatoria, y corroboración independiente por fiducial de dímeros impresos.
PyPrinting 3.0 — UNSAM Nanofotónica

Decisiones de diseño:

1. **El asistente de paso corre exclusivamente a zoom 1x.** A 1x, la fracción de
   pantalla (0..1) mapea directamente a coordenada de sensor completo sin tener que
   componer además la ventana de recorte del zoom (posición/tamaño dependientes del
   nivel de zoom, ver core/canon_edsdk.py::_apply_zoom_position_from_center()) — evita
   una fuente de error geométrico adicional en la propia calibración. La matriz
   resultante sigue siendo válida a cualquier zoom (StageCameraTransform trabaja en
   píxeles de sensor completo, invariante al zoom, por diseño — ver Fase A).
2. **Nunca decide sola.** Ninguna función de este módulo escribe en un
   StageCameraTransform — devuelven un resultado con toda la evidencia (posiciones
   detectadas, desvío estándar entre frames, cantidad de partículas candidatas, ratio de
   prominencia) para que el operador (o el diálogo de la Fase B en modules/camera.py)
   decida explícitamente aceptar, reintentar o descartar. Esto implementa el requisito
   explícito del usuario: confirmación visual humana obligatoria, con el agregado
   recomendado por el panel de metrología de exigir varios frames por medición (no un
   solo frame ruidoso) y una guarda de ambigüedad (dos partículas de prominencia
   similar en el campo de visión).
3. **La corroboración por fiducial (dímeros impresos) es una validación cruzada, no una
   segunda calibración independiente.** Un solo par de dímeros da una sola ecuación
   (una dirección dx,dy) — insuficiente para derivar una matriz 2x2 completa por sí
   sola. Se usa para comparar lo que la calibración del asistente de paso PREDICE contra
   (a) la separación nominal impresa y (b) la separación medida independientemente por
   un escaneo confocal (referencia metrológica separada, no depende de esta
   calibración) — "una calibración más real" en el sentido de que corrobora contra
   física real, no en el sentido de reemplazar el método de paso.
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from core.stage_camera_transform import SENSOR_WIDTH_PX, SENSOR_HEIGHT_PX

try:
    import trackpy as tp
    _TRACKPY_AVAILABLE = True
except Exception:
    _TRACKPY_AVAILABLE = False


def display_fraction_to_sensor_px(fx: float, fy: float) -> tuple[float, float]:
    """Convierte una fracción de pantalla (0..1, vista a ZOOM 1x SIN recorte) a
    coordenada de sensor completo. Misma transposición ya usada y verificada en
    core/canon_edsdk.py::_apply_zoom_position_from_center() (rotate 90° CW + flip
    horizontal aplicados en el pipeline de video, camera.py): Display X -> Sensor Y,
    Display Y -> Sensor X. Solo válida a 1x — ver nota de diseño #1 arriba."""
    sensor_x = fy * SENSOR_WIDTH_PX
    sensor_y = fx * SENSOR_HEIGHT_PX
    return sensor_x, sensor_y


def sensor_px_to_display_fraction(u_px: float, v_px: float, zoom_level: int,
                                    zoom_center_frac: tuple[float, float]) -> Optional[tuple[float, float]]:
    """Inversa de display_fraction_to_sensor_px, generalizada a cualquier nivel de zoom
    de hardware (1x/5x/10x) — usada por la Fase D (overlays Confocal/Impresión -> Cámara,
    que deben seguir siendo correctos mientras el operador navega con el zoom óptico, a
    diferencia del asistente de calibración/ROI->Confocal de las Fases B/C, que
    deliberadamente se restringen a 1x). Dado un punto en píxeles de sensor completo,
    devuelve su fracción DENTRO DEL FRAME ACTUALMENTE TRANSMITIDO por CanonWorker (ya
    recortado por hardware si zoom>1x), o None si el punto cae fuera de ese recorte.

    Replica — sin refactorizarla, para no arriesgar código EDSDK ya verificado — la
    misma geometría de ventana de recorte que
    core/canon_edsdk.py::_apply_zoom_position_from_center()/set_live_view_zoom_position()
    (mismo z_factor, mismo clamping). Se verifica por separado, con su propio test,
    contra la transposición pixel-exacta ya validada en
    tests/test_zoom_and_movement.py::test_02.

    La fracción devuelta es relativa al FRAME RECIBIDO, no a la pantalla final:
    OverlayWidget.frac_to_screen() ya compone automáticamente cualquier zoom de
    VISUALIZACIÓN por software (pan/zoom del viewport de pyqtgraph, independiente del
    zoom de hardware) a partir de esa fracción — igual que ya hace con
    _ref_frac/_roi_rect/_particles. No hay que componerlo acá de nuevo."""
    cx, cy = zoom_center_frac
    if zoom_level <= 1:
        clamped_x, clamped_y = 0.0, 0.0
        win_w, win_h = float(SENSOR_WIDTH_PX), float(SENSOR_HEIGHT_PX)
    else:
        z_factor = 10.0 if zoom_level >= 10 else 5.0
        win_w = SENSOR_WIDTH_PX / z_factor
        win_h = SENSOR_HEIGHT_PX / z_factor
        center_sensor_x = cy * SENSOR_WIDTH_PX
        center_sensor_y = cx * SENSOR_HEIGHT_PX
        ul_x = center_sensor_x - win_w / 2.0
        ul_y = center_sensor_y - win_h / 2.0
        clamped_x = max(0.0, min(SENSOR_WIDTH_PX - win_w, ul_x))
        clamped_y = max(0.0, min(SENSOR_HEIGHT_PX - win_h, ul_y))

    fy = (u_px - clamped_x) / win_w
    fx = (v_px - clamped_y) / win_h
    if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
        return None
    return fx, fy


def detect_dominant_feature(frame: np.ndarray, diameter: int = 11, separation: int = 8,
                              min_mass_ratio: float = 1.5) -> dict:
    """Detecta la partícula dominante (mayor "mass" = brillo integrado) en un frame de
    cámara, con guardas explícitas contra los modos de fallo silenciosos señalados en la
    Ronda 1 (panel de metrología): sin trackpy, sin ninguna partícula, o dos partículas
    de prominencia similar (ambigüedad real sobre cuál es "la" partícula de referencia)
    -> ok=False con una razón explícita, nunca un valor adivinado.

    Devuelve dict: {ok, reason, x_px, y_px, mass, n_candidates, mass_ratio}
    (x_px, y_px en coordenadas de PÍXEL DEL FRAME recibido — el llamador es responsable
    de convertir a fracción de pantalla dividiendo por el ancho/alto del frame)."""
    if not _TRACKPY_AVAILABLE:
        return {"ok": False, "reason": "trackpy no disponible en este entorno.", "n_candidates": 0}
    if frame is None or frame.size == 0:
        return {"ok": False, "reason": "Frame vacío o nulo.", "n_candidates": 0}

    gray = np.mean(frame, axis=2).astype(float) if frame.ndim == 3 else frame.astype(float)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = tp.locate(gray, diameter=diameter, separation=separation)
    except Exception as e:
        return {"ok": False, "reason": f"Excepción en detección: {e}", "n_candidates": 0}

    if df is None or len(df) == 0:
        return {"ok": False, "reason": "No se detectó ninguna partícula en el frame.", "n_candidates": 0}

    df_sorted = df.sort_values("mass", ascending=False)
    top = df_sorted.iloc[0]
    n_candidates = len(df_sorted)
    mass_ratio = float("inf")
    if n_candidates >= 2:
        second = df_sorted.iloc[1]
        mass_ratio = float(top["mass"]) / max(1e-9, float(second["mass"]))
        if mass_ratio < min_mass_ratio:
            return {
                "ok": False,
                "reason": (
                    f"Ambigüedad: {n_candidates} partículas detectadas, la más brillante "
                    f"supera a la segunda por solo {mass_ratio:.2f}x (mínimo requerido "
                    f"{min_mass_ratio}x). Aislá una única partícula de referencia en el campo."
                ),
                "n_candidates": n_candidates,
                "mass_ratio": mass_ratio,
            }

    return {
        "ok": True,
        "reason": "",
        "x_px": float(top["x"]),
        "y_px": float(top["y"]),
        "mass": float(top["mass"]),
        "n_candidates": n_candidates,
        "mass_ratio": mass_ratio,
    }


@dataclass
class StepCalibrationSession:
    """Orquesta la calibración de UN eje físico (1 o 2): acumula varios frames 'antes' y
    'después' de un paso conocido, detecta la partícula dominante en cada uno, promedia
    y calcula desvío estándar como control de calidad. No mueve la platina ni aplica
    nada a un StageCameraTransform por sí sola — ver notas de diseño del módulo."""
    axis: int
    step_um: float
    frame_width_px: int
    frame_height_px: int
    before_frames: list = field(default_factory=list)
    after_frames: list = field(default_factory=list)

    def __post_init__(self):
        if self.axis not in (1, 2):
            raise ValueError(f"Eje físico inválido: {self.axis} (debe ser 1 o 2)")
        if abs(self.step_um) < 1e-9:
            raise ValueError("step_um no puede ser ~0")

    def add_before_frame(self, frame: np.ndarray) -> None:
        self.before_frames.append(frame)

    def add_after_frame(self, frame: np.ndarray) -> None:
        self.after_frames.append(frame)

    def _aggregate(self, frames: list, min_mass_ratio: float) -> dict:
        if not frames:
            return {"ok": False, "reason": "No se capturó ningún frame."}
        xs, ys = [], []
        n_candidates_list = []
        for fr in frames:
            det = detect_dominant_feature(fr, min_mass_ratio=min_mass_ratio)
            if not det["ok"]:
                return {"ok": False, "reason": f"Frame descartado: {det['reason']}"}
            xs.append(det["x_px"]); ys.append(det["y_px"])
            n_candidates_list.append(det["n_candidates"])
        return {
            "ok": True,
            "x_px": float(np.mean(xs)),
            "y_px": float(np.mean(ys)),
            "std_x_px": float(np.std(xs)),
            "std_y_px": float(np.std(ys)),
            "n_frames": len(frames),
            "n_candidates_max": max(n_candidates_list),
        }

    def compute_result(self, min_mass_ratio: float = 1.5, max_std_px: float = 2.0) -> dict:
        """Calcula el desplazamiento de sensor completo observado entre 'antes' y
        'después'. Rechaza (ok=False) si cualquiera de los dos lados no pudo detectar
        una partícula inequívoca, o si la dispersión entre frames supera max_std_px
        (posición inestable / partícula mal localizada) — nunca devuelve un resultado
        parcial o de baja confianza como si fuera válido."""
        before = self._aggregate(self.before_frames, min_mass_ratio)
        if not before["ok"]:
            return {"ok": False, "reason": f"[Antes] {before['reason']}"}
        after = self._aggregate(self.after_frames, min_mass_ratio)
        if not after["ok"]:
            return {"ok": False, "reason": f"[Después] {after['reason']}"}

        if before["std_x_px"] > max_std_px or before["std_y_px"] > max_std_px:
            return {"ok": False, "reason": (
                f"[Antes] Posición inestable entre frames (std x={before['std_x_px']:.2f}px, "
                f"y={before['std_y_px']:.2f}px, máximo {max_std_px}px).")}
        if after["std_x_px"] > max_std_px or after["std_y_px"] > max_std_px:
            return {"ok": False, "reason": (
                f"[Después] Posición inestable entre frames (std x={after['std_x_px']:.2f}px, "
                f"y={after['std_y_px']:.2f}px, máximo {max_std_px}px).")}

        before_fx = before["x_px"] / self.frame_width_px
        before_fy = before["y_px"] / self.frame_height_px
        after_fx = after["x_px"] / self.frame_width_px
        after_fy = after["y_px"] / self.frame_height_px

        u1, v1 = display_fraction_to_sensor_px(before_fx, before_fy)
        u2, v2 = display_fraction_to_sensor_px(after_fx, after_fy)

        return {
            "ok": True,
            "axis": self.axis,
            "step_um": self.step_um,
            "delta_u_sensor_px": u2 - u1,
            "delta_v_sensor_px": v2 - v1,
            "before_px": (before["x_px"], before["y_px"]),
            "after_px": (after["x_px"], after["y_px"]),
            "before_std_px": (before["std_x_px"], before["std_y_px"]),
            "after_std_px": (after["std_x_px"], after["std_y_px"]),
        }


def compare_fiducial_calibration(transform, printed_dx_um: float, printed_dy_um: float,
                                   camera_pt1_frac: tuple[float, float],
                                   camera_pt2_frac: tuple[float, float],
                                   confocal_measured_dx_um: Optional[float] = None,
                                   confocal_measured_dy_um: Optional[float] = None) -> dict:
    """Corrobora la calibración actual de `transform` (un StageCameraTransform ya
    calibrado por el asistente de paso) contra un par de dímeros impresos a una
    separación físicamente conocida (printed_dx_um/dy_um, del modo dímeros de
    modules/measurements.py), marcados por el operador en dos puntos de cámara (fracción
    de pantalla, a 1x), y opcionalmente contra una medición independiente por escaneo
    confocal. No modifica `transform` — devuelve las discrepancias para que el operador
    decida. Ver nota de diseño #3 del módulo: esto es corroboración, no una segunda
    calibración independiente completa (un solo par de puntos da una sola dirección,
    insuficiente para derivar una matriz 2x2 por sí solo)."""
    u1, v1 = display_fraction_to_sensor_px(*camera_pt1_frac)
    u2, v2 = display_fraction_to_sensor_px(*camera_pt2_frac)
    delta_u_px = u2 - u1
    delta_v_px = v2 - v1

    predicted_axis1_um, predicted_axis2_um = transform.sensor_px_delta_to_stage_um(delta_u_px, delta_v_px)

    # printed_dx_um/dy_um están en la convención de ejes físicos de la platina (mismo
    # dx/dy que ya usa modules/measurements.py para posicionar el segundo NP del dímero).
    printed_mag = float(np.hypot(printed_dx_um, printed_dy_um))
    predicted_mag = float(np.hypot(predicted_axis1_um, predicted_axis2_um))
    discrepancy_vs_printed_pct = (
        100.0 * abs(predicted_mag - printed_mag) / printed_mag if printed_mag > 1e-9 else float("nan")
    )

    result = {
        "delta_u_sensor_px": delta_u_px,
        "delta_v_sensor_px": delta_v_px,
        "predicted_axis1_um": predicted_axis1_um,
        "predicted_axis2_um": predicted_axis2_um,
        "predicted_magnitude_um": predicted_mag,
        "printed_magnitude_um": printed_mag,
        "discrepancy_vs_printed_pct": discrepancy_vs_printed_pct,
    }

    if confocal_measured_dx_um is not None and confocal_measured_dy_um is not None:
        confocal_mag = float(np.hypot(confocal_measured_dx_um, confocal_measured_dy_um))
        result["confocal_magnitude_um"] = confocal_mag
        result["discrepancy_vs_confocal_pct"] = (
            100.0 * abs(predicted_mag - confocal_mag) / confocal_mag if confocal_mag > 1e-9 else float("nan")
        )

    return result
