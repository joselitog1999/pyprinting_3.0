# -*- coding: utf-8 -*-
"""
core/stage_camera_transform.py — Transformación afín 2D entre la platina PI E-517
(ejes físicos 1 y 2, µm) y el plano de píxeles de sensor completo de la cámara Canon
(u, v, en píxeles de sensor 4752×3168, independiente del zoom de hardware).
PyPrinting 3.0 — UNSAM Nanofotónica

Decisiones de diseño (Fase A de la misión "Suite de Cámara Réflex Canon, Cinemática de
Ejes y Sincronización Espacial Bidireccional"):

1. **Deliberadamente NO depende del régimen de coordenadas activo**
   (core.nanopositioning.Frontend.DIRECTION_MAP). SYS-103 establece, y
   tests/test_coordinate_nomenclature_sync.py confirma, que el régimen es una
   re-etiquetación de UI que nunca cambia la cinemática real de los actuadores — los
   tres regímenes ya fueron verificados (a mano, derivándolos desde REGIME_LEGACY) como
   matemáticamente consistentes entre sí. Construir esta clase sobre los DOS EJES
   FÍSICOS de la platina (los mismos "1"/"2" que ya usan pi.MOV()/pi.qPOS() de forma
   nativa, sin importar qué régimen esté mostrando la UI) la hace correcta bajo los 3
   regímenes automáticamente, sin necesidad de calibrar ni almacenar una matriz
   separada por régimen — evita además una fuente de inconsistencia entre matrices que
   "deberían" ser la misma físico pero se calibrarían por separado.

2. **Trabaja en píxeles de SENSOR COMPLETO (4752×3168), no en fracción de pantalla
   dependiente del zoom activo.** El sensor físico siempre representa la misma distancia
   real independientemente de qué recorte 1x/5x/10x esté mostrando el Live View — el
   nivel de zoom solo cambia qué subconjunto de píxeles de sensor se está viendo, no su
   significado físico. Esto evita necesitar una matriz recalibrada por cada nivel de
   zoom (el gap que encontró el panel de metrología en la Ronda 1): el llamador
   convierte su clic en pantalla (fracción, dependiente del zoom) a la coordenada de
   sensor completo equivalente usando la MISMA matemática de transposición ya usada y
   ya verificada en core/canon_edsdk.py::_apply_zoom_position_from_center() /
   set_live_view_zoom_position() — no se reinventa acá.

3. **Es específica por RIG físico** ("microscopio derecho" vs. "contrapropagante" montan
   la cámara con óptica/relay-lens propios — confirmado que son procesos independientes
   que nunca corren simultáneamente, DEC-013) y se persiste en un archivo separado por
   rig. No es específica por régimen (ver punto 1).

4. **No asume una matriz fija.** El patrón de signos conocido (derivado a mano de
   REGIME_LEGACY + la convención física verificada por el operador: platina arriba ->
   láser a la derecha en cámara, platina derecha -> láser abajo en cámara) se guarda
   solo como KNOWN_SIGN_PATTERN, usado para un chequeo de sanidad post-calibración
   (matches_known_sign_pattern()) — nunca para mover la platina sin calibración real.
   Sin calibrar, todo método que devuelve un desplazamiento de platina lanza
   RuntimeError explícito en vez de devolver un valor por defecto silencioso.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np

# Dimensiones del sensor CMOS de la Canon EOS 500D — mismas constantes que
# core/canon_edsdk.py::_apply_zoom_position_from_center()/set_live_view_zoom_position().
SENSOR_WIDTH_PX  = 4752
SENSOR_HEIGHT_PX = 3168

# Patrón de signos conocido (px_sensor -> eje_físico_µm), derivado a mano de
# REGIME_LEGACY (core/nanopositioning.py: right->(eje1,+1), up->(eje2,+1)) combinado con
# la convención física verificada por el operador (arriba de platina -> láser a la
# derecha en cámara [+u]; derecha de platina -> láser abajo en cámara [+v]):
#   Δu_sensor = s2 · Δeje2   ;   Δv_sensor = s1 · Δeje1      (s1, s2 > 0)
# Invertido (lo que esta clase necesita, px->µm):
#   Δeje1 = (1/s1) · Δv_sensor   ;   Δeje2 = (1/s2) · Δu_sensor
# Patrón de signos puro (sin magnitud) de esa inversa, fila=eje físico, columna=(u,v):
KNOWN_SIGN_PATTERN = np.array([
    [0.0, 1.0],   # Δeje1 responde solo a Δv_sensor, con signo positivo
    [1.0, 0.0],   # Δeje2 responde solo a Δu_sensor, con signo positivo
])


class StageCameraTransform:
    """Matriz de calibración afín platina<->cámara para UN rig físico.

    M_forward: eje_físico(1,2) [µm] -> sensor_px(u,v) [px], calibrada columna por
    columna (una columna por cada paso de prueba en un eje físico — ver
    calibrate_axis_from_step()). Es la fuente de verdad; la inversa (sensor_px -> eje
    físico, lo que necesita ROI->Confocal) se deriva y cachea bajo demanda.
    """

    def __init__(self, rig_id: str, base_dir: Optional[Path] = None):
        self.rig_id = rig_id
        self._base_dir = Path(base_dir) if base_dir is not None else self._default_base_dir()
        self.M_forward: Optional[np.ndarray] = None   # shape (2,2)
        self.calibration_method: Optional[str] = None  # "step_wizard" | "fiducial_dimer" | "step_wizard+fiducial_dimer"
        self.calibrated_at: Optional[str] = None
        self.last_fiducial_validation: Optional[dict] = None
        self._M_inverse_cache: Optional[np.ndarray] = None
        self._pending_columns: dict[int, np.ndarray] = {}  # columnas parciales durante calibración por pasos
        self.load()

    @staticmethod
    def _default_base_dir() -> Path:
        from config import DEFAULT_DATA_PATH
        return Path(DEFAULT_DATA_PATH)

    def _calibration_path(self) -> Path:
        safe_rig = "".join(c if c.isalnum() else "_" for c in self.rig_id)
        return self._base_dir / f"stage_camera_calibration_{safe_rig}.json"

    # ── Persistencia ─────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Carga la calibración persistida para este rig, si existe. Devuelve True si se
        cargó una matriz completa y utilizable."""
        path = self._calibration_path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            m = data.get("M_forward")
            if m is None or len(m) != 2 or len(m[0]) != 2 or len(m[1]) != 2:
                return False
            self.M_forward = np.array(m, dtype=float)
            self.calibration_method = data.get("calibration_method")
            self.calibrated_at = data.get("calibrated_at")
            self.last_fiducial_validation = data.get("last_fiducial_validation")
            self._M_inverse_cache = None
            self._pending_columns = {}
            return True
        except Exception as e:
            print(f"[StageCameraTransform] No se pudo cargar calibración de '{self.rig_id}': {e}")
            return False

    def save(self) -> None:
        if self.M_forward is None:
            raise RuntimeError(
                "No hay matriz calibrada para guardar — corré la calibración antes de save().")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        path = self._calibration_path()
        data = {
            "rig_id": self.rig_id,
            "M_forward": self.M_forward.tolist(),
            "calibration_method": self.calibration_method,
            "calibrated_at": self.calibrated_at,
            "determinant": float(np.linalg.det(self.M_forward)),
            "matches_known_sign_pattern": self.matches_known_sign_pattern(),
            "last_fiducial_validation": self.last_fiducial_validation,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_fiducial_validation(self, validation_result: dict) -> None:
        """Adjunta el resultado de una corroboración por fiducial de dímeros
        (core.stage_camera_calibration.compare_fiducial_calibration) al registro de esta
        calibración — no modifica M_forward (ver nota de diseño #3 del módulo de
        calibración: es una validación cruzada, no una segunda calibración). Solo queda
        persistido en disco tras llamar save()."""
        self._require_calibrated()
        record = dict(validation_result)
        record["recorded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.last_fiducial_validation = record

    # ── Calibración ──────────────────────────────────────────────────────────

    def calibrate_axis_from_step(self, axis: int, physical_step_um: float,
                                   measured_delta_u_px: float, measured_delta_v_px: float) -> None:
        """Registra UNA columna de M_forward a partir de un paso de prueba conocido en
        un eje físico (1 o 2) y el desplazamiento de sensor completo medido. Necesita
        que ambos ejes se calibren (dos llamadas) antes de que la matriz quede completa
        y utilizable — ver is_calibrated()."""
        if axis not in (1, 2):
            raise ValueError(f"Eje físico inválido: {axis} (debe ser 1 o 2)")
        if abs(physical_step_um) < 1e-9:
            raise ValueError("physical_step_um no puede ser ~0 — división por cero al derivar la escala")
        column = np.array([measured_delta_u_px, measured_delta_v_px], dtype=float) / physical_step_um
        self._pending_columns[axis] = column
        if 1 in self._pending_columns and 2 in self._pending_columns:
            self.M_forward = np.column_stack([self._pending_columns[1], self._pending_columns[2]])
            self.calibration_method = "step_wizard"
            self.calibrated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self._M_inverse_cache = None

    def set_calibrated_matrix(self, M_forward: np.ndarray, method: str) -> None:
        """Fija la matriz completa directamente (p.ej. resultado ya promediado/validado
        del asistente de calibración, o de la validación por fiducial de dímeros)."""
        M_forward = np.asarray(M_forward, dtype=float)
        if M_forward.shape != (2, 2):
            raise ValueError(f"M_forward debe ser 2x2, recibido {M_forward.shape}")
        self.M_forward = M_forward
        self.calibration_method = method
        self.calibrated_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._M_inverse_cache = None
        self._pending_columns = {}

    def reset_calibration(self) -> None:
        self.M_forward = None
        self.calibration_method = None
        self.calibrated_at = None
        self.last_fiducial_validation = None
        self._M_inverse_cache = None
        self._pending_columns = {}

    def is_calibrated(self) -> bool:
        return self.M_forward is not None

    # ── Chequeo de sanidad ───────────────────────────────────────────────────

    def determinant(self) -> float:
        self._require_calibrated()
        return float(np.linalg.det(self.M_forward))

    def matches_known_sign_pattern(self, tolerance_deg: float = 30.0) -> Optional[bool]:
        """Compara la ORIENTACIÓN de M_forward (normalizada, sin magnitud) contra
        KNOWN_SIGN_PATTERN — señala si el signo/paridad medido coincide con la
        convención física ya verificada por el operador, en vez de asumirlo. Devuelve
        None si todavía no hay calibración. Recomendación de metrología (Ronda 1):
        cualquier corrida de calibración debe computar y registrar esto, no asumir
        'rotación pura' ni ningún signo de antemano."""
        if self.M_forward is None:
            return None
        det_known = np.linalg.det(KNOWN_SIGN_PATTERN)
        det_measured = np.linalg.det(self.M_forward)
        if det_known == 0 or det_measured == 0:
            return False
        if (det_known > 0) != (det_measured > 0):
            return False  # paridad opuesta (rotación vs. reflexión) — desacuerdo real, no solo de tolerancia
        # Ángulo entre cada columna medida y su contraparte del patrón conocido.
        for col in (0, 1):
            v_known = KNOWN_SIGN_PATTERN[:, col]
            v_meas = self.M_forward[:, col]
            n_known = np.linalg.norm(v_known)
            n_meas = np.linalg.norm(v_meas)
            if n_known < 1e-12 or n_meas < 1e-12:
                return False
            cos_angle = float(np.dot(v_known, v_meas) / (n_known * n_meas))
            cos_angle = max(-1.0, min(1.0, cos_angle))
            angle_deg = np.degrees(np.arccos(cos_angle))
            if angle_deg > tolerance_deg:
                return False
        return True

    # ── Aplicación ───────────────────────────────────────────────────────────

    def _require_calibrated(self) -> None:
        if self.M_forward is None:
            raise RuntimeError(
                f"StageCameraTransform('{self.rig_id}') no está calibrada — "
                f"no se puede convertir ninguna coordenada todavía.")

    def sensor_px_delta_to_stage_um(self, delta_u_px: float, delta_v_px: float) -> tuple[float, float]:
        """Desplazamiento en píxeles de sensor completo -> desplazamiento en ejes
        físicos de platina (µm). Uso principal: Cámara -> Confocal (ROI arrastrado)."""
        self._require_calibrated()
        if self._M_inverse_cache is None:
            self._M_inverse_cache = np.linalg.inv(self.M_forward)
        d = self._M_inverse_cache @ np.array([delta_u_px, delta_v_px], dtype=float)
        return float(d[0]), float(d[1])

    def stage_um_delta_to_sensor_px(self, delta_axis1_um: float, delta_axis2_um: float) -> tuple[float, float]:
        """Desplazamiento en ejes físicos de platina (µm) -> desplazamiento en píxeles
        de sensor completo. Uso principal: Confocal/Impresión -> Cámara (cajas
        proyectadas, grilla de impresión)."""
        self._require_calibrated()
        d = self.M_forward @ np.array([delta_axis1_um, delta_axis2_um], dtype=float)
        return float(d[0]), float(d[1])
