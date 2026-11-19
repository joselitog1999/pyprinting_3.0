# -*- coding: utf-8 -*-
"""Luminiscencia en grilla con la secuencia completa del legado (`Luminescence_ps.py`; DEC-054).

Por nodo, como el legado:
  1. moverse al nodo (con confirmación on-target), corrido por la referencia si se refresca;
  2. autofoco cada N nodos con el lock del operador (el del satélite), con un corrimiento opcional;
  3. centrado con el fotodiodo del láser (el confocal del satélite), guardando el trío de TIFF NPscan crudos;
  4. ir al centro de masa, bajar el espejo de detección;
  5. mini-mapa hiperespectral nx × ny alrededor del centro: una exposición por píxel, leída en Single-Track sobre
     las filas de la fibra, con una muestra del BS por píxel. El valor del mapa es la suma del espectro dentro de la
     banda λ (`Confocal_Spectrum_ps.py:687-696`);
  6. cerrar el láser, centro de masa del mapa (umbral 0.7 sobre el mapa normalizado, `:806-826`), subir el espejo;
  7. si se pide, refrescar la referencia: el resto de la grilla se corre por (centro del mapa − nodo nominal).

Los archivos salen en los dos formatos (`legacy_files` y un `.h5` por corrida). Nada guardado lleva el fondo
restado. Sin Qt: el hilo lo pone la rutina, y el foco y el confocal llegan por `SatelliteOptics`.

`runner` es siempre el `GridRunner` que entrega `RoutineThread` (el backend de `luminescence.py`): la rutina está
registrada en el watchdog de rutinas mientras dura (DEC-052), y el láser se abre y se cierra sólo por el runner.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from pyspectrum.modules.routines.grid_runner import FiberROI, GridAbort, GridSafetyPause, NodeFailed
from pyspectrum.services import legacy_files as lf
from pyspectrum.services.satellite_optics import CenterScanSpec, OpticsUnavailable


@dataclass
class MiniMapSpec:
    """El mini-mapa, como "HyperSpectral Confocal" del legado (`Confocal_Spectrum_ps.py:184-194, 428-441`)."""
    enabled: bool = True
    range_um: float = 1.0
    nx: int = 20
    ny: int = 20
    exposure_s: float = 2.0
    band_nm: Tuple[float, float] = (540.0, 580.0)
    cm_threshold: float = 0.7
    laser_off: bool = False               # modo scattering del legado: no se abre ningún láser

    def __post_init__(self):
        if self.enabled:
            if int(self.nx) < 1 or int(self.ny) < 1:
                raise ValueError("El mini-mapa necesita al menos 1×1 píxeles")
            if not (0.0 < float(self.range_um) <= 20.0):
                raise ValueError(f"Rango del mini-mapa {self.range_um} µm fuera de (0, 20] µm")
        lo, hi = (float(v) for v in self.band_nm)
        if not lo < hi:
            raise ValueError(f"Banda λ inválida: {lo}–{hi} nm")
        if not (0.0 <= float(self.cm_threshold) < 1.0):
            raise ValueError("El umbral del centro de masa del mapa va de 0 a 1")
        if not float(self.exposure_s) > 0:
            raise ValueError("La exposición tiene que ser positiva")


@dataclass
class LuminescenceGridParams:
    laser: str
    autofocus_every: int = 2                       # 0 = nunca
    af_shift_um: Tuple[float, float] = (0.0, 0.0)
    center_enabled: bool = True
    center: CenterScanSpec = field(default_factory=CenterScanSpec)
    minimap: MiniMapSpec = field(default_factory=MiniMapSpec)
    roi: FiberROI = field(default_factory=FiberROI)
    refresh_reference: bool = False
    grid_name: str = "Load_grid"
    group_size: int = 1000                         # nodos por "columna" del legado (para Col_%03d)

    @property
    def needs_optics(self) -> bool:
        return self.center_enabled or int(self.autofocus_every) > 0

    def summary(self) -> dict:
        d = asdict(self)
        d["roi"] = {"center_row": self.roi.center_row, "height": self.roi.height, "rows": list(self.roi.rows)}
        return d


# ── cálculos del legado ─────────────────────────────────────────────────────────

def band_value(wave, spec, band_nm: Sequence[float]) -> float:
    """Suma del espectro donde lower ≤ λ ≤ upper, como `option_step_profile` del legado (sin dλ)."""
    w = np.asarray(wave, dtype=np.float64)
    s = np.asarray(spec, dtype=np.float64)
    lo, hi = float(band_nm[0]), float(band_nm[1])
    return float(np.sum(np.where((w >= lo) & (w <= hi), s, 0.0)))


def minimap_positions(cx: float, cy: float, range_um: float, nx: int, ny: int) -> Tuple[np.ndarray, np.ndarray]:
    """Posiciones del legado: x_i = cx − rango/2 + i·rango/nx (y igual), i = 0..nx−1 (`:616-621`)."""
    dx, dy = float(range_um) / int(nx), float(range_um) / int(ny)
    xs = float(cx) - float(range_um) / 2.0 + np.arange(int(nx)) * dx
    ys = float(cy) - float(range_um) / 2.0 + np.arange(int(ny)) * dy
    return xs, ys


def map_center_of_mass(image, cx: float, cy: float, range_um: float, threshold: float = 0.7):
    """Centro de masa del mapa como el legado: normaliza mín–máx, anula lo menor al umbral y toma el centro de masa
    (`image[j, i]`, j = y). Devuelve (x_µm, y_µm, xcm_px, ycm_px), o None si el mapa es plano o no finito."""
    from scipy import ndimage
    Z = np.asarray(image, dtype=np.float64)
    if Z.size == 0 or not np.all(np.isfinite(Z)):
        return None
    zmin, zmax = float(Z.min()), float(Z.max())
    if zmax - zmin <= 0:
        return None
    Zn = (Z - zmin) / (zmax - zmin)
    Zn[Zn < float(threshold)] = 0.0
    ycm, xcm = ndimage.center_of_mass(Zn)
    ny, nx = Z.shape
    x = round(float(cx) - float(range_um) / 2.0 + xcm * float(range_um) / nx, 3)
    y = round(float(cy) - float(range_um) / 2.0 + ycm * float(range_um) / ny, 3)
    return x, y, float(xcm), float(ycm)


def legacy_col_np(index: int, group_size: int) -> Tuple[int, int]:
    """(Col, NP) de los nombres del legado: Col = índice // n + 1, NP = índice (`Luminescence_ps.py:728-739`)."""
    return int(index) // max(1, int(group_size)) + 1, int(index)


def grid_name(rows: int, cols: int, dx_um: float, dy_um: float) -> str:
    """El rótulo de la grilla del legado: "{n}x{N}_{dn}umx{dN}um" (`Growth_ps.py:513-535`)."""
    return f"{int(rows)}x{int(cols)}_{float(dx_um):g}umx{float(dy_um):g}um"


# ── escritura ───────────────────────────────────────────────────────────────────

class LuminescenceRunWriter:
    """Los archivos de una corrida: la carpeta `<ts>_Luminescence_<grilla>/` del legado y un `.h5` con todo."""

    def __init__(self, save_dir: str, params: LuminescenceGridParams, wave, axis_source: str,
                 dark=None, dark_header: str = "", stamp: Optional[str] = None, correction: Optional[dict] = None):
        stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
        self.params = params
        self.wave = np.asarray(wave, dtype=np.float64)
        self.axis_source = axis_source
        self.run_dir = os.path.join(save_dir, f"{stamp}_Luminescence_{params.grid_name}")
        os.makedirs(self.run_dir, exist_ok=True)
        self.h5_path = os.path.join(self.run_dir, f"{stamp}_Luminescence_{params.grid_name}.h5")
        self._dark = dark
        self._dark_header = dark_header
        self._correction = correction
        self._init_h5()
        self.write_info([])

    def _init_h5(self):
        import h5py
        with h5py.File(self.h5_path, "w") as f:
            f.create_dataset("wavelength_nm", data=self.wave)
            f.attrs["wavelength_source"] = self.axis_source
            f.attrs["read_mode"] = "Single-Track"
            f.attrs["fiber_rows"] = list(self.params.roi.rows)
            f.attrs["params_json"] = json.dumps(self.params.summary(), default=str)
            f.attrs["dark_header"] = self._dark_header
            f.attrs["note"] = "Datos crudos: el fondo (dark) va aparte y no está restado."
            if self._correction is not None:                   # la corrección fina vigente (R3-gui §4.6)
                from pyspectrum.calibration.repository import write_correction_attrs
                write_correction_attrs(f.attrs, self._correction)
            if self._dark is not None:                         # el fondo, aparte y sin restar (R4-N)
                from pyspectrum.services.procedure_background import write_dark_h5
                write_dark_h5(f, self._dark)

    def set_dark_header(self, header: str) -> None:
        """La referencia al fondo guardado aparte (`<prefijo>_background_<id>.npz`), una vez conocida."""
        import h5py
        self._dark_header = header or ""
        with h5py.File(self.h5_path, "a") as f:
            f.attrs["dark_header"] = self._dark_header

    def write_info(self, extra_rows: List[Tuple[str, object]]) -> str:
        p = self.params
        mm = p.minimap
        rows = [
            ("Laser", p.laser), ("Software", "PySpectrum 3.0 (DEC-054)"),
            ("Read_mode", "Single-Track"), ("Fiber_rows", f"{p.roi.rows[0]}-{p.roi.rows[1]}"),
            ("Axis_source", self.axis_source), ("Axis_points", self.wave.size),
            ("Exposure_s", mm.exposure_s), ("Map_range_um", mm.range_um), ("Map_Nx", mm.nx), ("Map_Ny", mm.ny),
            ("Band_nm", f"{mm.band_nm[0]:g}-{mm.band_nm[1]:g}"), ("Map_CM_threshold", mm.cm_threshold),
            ("Scattering_laser_off", mm.laser_off), ("Center_scan", p.center_enabled),
            ("Center_range_um", p.center.range_um), ("Center_pixels", p.center.pixels),
            ("Autofocus_every", p.autofocus_every), ("Refresh_reference", p.refresh_reference),
            ("Trace_BS_sampling", "una muestra del BS por pixel del mapa (el legado: traza continua)"),
            ("Dark", "aparte, sin restar (ver el .h5)"),
        ]
        return lf.write_info(self.run_dir, rows + list(extra_rows))

    def node_dir(self, index: int) -> str:
        col, npi = legacy_col_np(index, self.params.group_size)
        return os.path.join(self.run_dir, lf.node_folder_name("Slow_Confocal_Spectrum", col, npi))

    def write_center(self, index: int, image, gone, back) -> None:
        lf.write_npscan_tiffs(self.run_dir, index, image, gone, back)

    def start_map(self, index: int) -> str:
        d = self.node_dir(index)
        os.makedirs(d, exist_ok=True)
        lf.write_wavelength(d, self.wave)
        return d

    def write_pixel(self, node_dir: str, i: int, j: int, spec) -> None:
        lf.write_pixel_spectrum(node_dir, i, j, spec)

    def finish_node(self, index: int, node: "NodeRecord") -> None:
        import h5py
        if node.map_dir:
            if node.map_image is not None and node.map_image.size:
                lf.write_map_tiff(node.map_dir, node.map_image)
            lf.write_trace_bs(node.map_dir, node.bs_t, node.bs_v)
        with h5py.File(self.h5_path, "a") as f:
            name = f"node_{int(index):03d}"
            if name in f:
                del f[name]
            g = f.create_group(name)
            g.attrs["status"] = node.status
            g.attrs["nominal_um"] = list(node.nominal)
            g.attrs["target_um"] = list(node.target)
            if node.center_cm is not None:
                g.attrs["center_cm_um"] = list(node.center_cm)
            if node.map_cm is not None:
                g.attrs["map_cm_um"] = list(node.map_cm)
            g.attrs["autofocus"] = node.autofocus
            for key in ("center_image", "center_gone", "center_back", "map_image", "map_xs", "map_ys", "cube",
                        "bs_t", "bs_v", "single_spectrum"):
                val = getattr(node, key)
                if val is not None and np.size(val):
                    g.create_dataset(key, data=np.asarray(val, dtype=np.float64),
                                     compression="gzip" if key == "cube" else None)


@dataclass
class NodeRecord:
    nominal: Tuple[float, float, Optional[float]]
    target: Tuple[float, float, Optional[float]] = (0.0, 0.0, None)
    status: str = "pending"
    autofocus: str = "no"
    center_cm: Optional[Tuple[float, float]] = None
    center_image: Optional[np.ndarray] = None
    center_gone: Optional[np.ndarray] = None
    center_back: Optional[np.ndarray] = None
    map_dir: str = ""
    map_xs: Optional[np.ndarray] = None
    map_ys: Optional[np.ndarray] = None
    map_image: Optional[np.ndarray] = None
    cube: Optional[np.ndarray] = None
    map_cm: Optional[Tuple[float, float]] = None
    bs_t: list = field(default_factory=list)
    bs_v: list = field(default_factory=list)
    single_spectrum: Optional[np.ndarray] = None


@dataclass
class NodeEvents:
    """Callbacks hacia la interfaz (los conecta el backend como señales)."""
    progress: Callable[[str], None] = lambda _t: None
    center: Callable[[np.ndarray, float, float], None] = lambda *_a: None
    map_update: Callable[[np.ndarray, np.ndarray, np.ndarray], None] = lambda *_a: None
    spectrum: Callable[[np.ndarray, np.ndarray], None] = lambda *_a: None
    map_done: Callable[[np.ndarray, float, float], None] = lambda *_a: None


class LuminescenceGridEngine:
    """Un nodo por llamada a `run_node`. Guarda la referencia refrescada entre nodos."""

    def __init__(self, runner, optics, params: LuminescenceGridParams, wave, writer: LuminescenceRunWriter,
                 read_bs: Callable[[], float], events: Optional[NodeEvents] = None,
                 clock: Callable[[], float] = time.monotonic):
        self.runner = runner
        self.optics = optics
        self.p = params
        self.wave = np.asarray(wave, dtype=np.float64)
        self.writer = writer
        self.read_bs = read_bs
        self.ev = events or NodeEvents()
        self.clock = clock
        self.ref_offset = (0.0, 0.0)

    def _aborted(self) -> bool:
        return self.runner.aborted()

    def run_node(self, index: int, node: Tuple[float, float, Optional[float]]) -> NodeRecord:
        r, p = self.runner, self.p
        x0, y0, z0 = node
        rec = NodeRecord(nominal=(float(x0), float(y0), z0))
        x, y = float(x0) + self.ref_offset[0], float(y0) + self.ref_offset[1]
        rec.target = (x, y, z0)
        try:
            self.ev.progress("Moviendo platina...")
            r.move_to(x, y, z0)

            every = int(p.autofocus_every)
            if every > 0 and index % every == 0:
                self.ev.progress("Autofoco Z (lock del satélite)...")
                sx, sy = (float(v) for v in p.af_shift_um)
                if sx or sy:
                    r.move_to(x + sx, y + sy, None)
                r.set_mirror("up")
                ok = self.optics.autofocus(p.laser, self._aborted, r.tick)
                rec.autofocus = "ok" if ok else "sin convergencia"
                if sx or sy:
                    r.move_to(x, y, None)

            cx, cy = x, y
            if p.center_enabled:
                self.ev.progress("Centrado con el fotodiodo...")
                r.set_mirror("up")
                res = self.optics.center_scan(p.laser, p.center, self._aborted, r.tick, number=f"{index:03d}")
                rec.center_image, rec.center_gone, rec.center_back = res.image, res.gone, res.back
                rec.center_cm = (res.x_um, res.y_um)
                self.writer.write_center(index, res.image, res.gone, res.back)
                self.ev.center(res.image, res.x_um, res.y_um)
                cx, cy, _ = r.move_to(res.x_um, res.y_um, None)

            r.set_mirror("down")
            if p.minimap.enabled:
                self._minimap(index, rec, cx, cy)
            else:
                self._single(rec)
            r.set_mirror("up")

            if p.refresh_reference and rec.map_cm is not None:
                self.ref_offset = (rec.map_cm[0] - float(x0), rec.map_cm[1] - float(y0))
            rec.status = "done"
            return rec
        except (GridAbort, GridSafetyPause):
            rec.status = "interrupted"
            raise
        except (NodeFailed, OpticsUnavailable):
            rec.status = "failed"
            raise
        finally:
            if rec.status != "pending":
                try:
                    self.writer.finish_node(index, rec)
                except OSError as e:
                    print(f"[Luminiscencia] No se pudo guardar el nodo {index}: {e}")

    def _laser_needed(self) -> bool:
        return not self.p.minimap.laser_off

    def _single(self, rec: NodeRecord) -> None:
        r, mm = self.runner, self.p.minimap
        self.ev.progress("Espectro en el centro...")
        if self._laser_needed():
            r.laser(self.p.laser, True)
        try:
            spec = r.expose((self.wave.size,), mm.exposure_s)
        finally:
            if self._laser_needed():
                r.laser(self.p.laser, False)
        rec.single_spectrum = spec
        self.ev.spectrum(self.wave, spec)

    def _minimap(self, index: int, rec: NodeRecord, cx: float, cy: float) -> None:
        r, mm = self.runner, self.p.minimap
        xs, ys = minimap_positions(cx, cy, mm.range_um, mm.nx, mm.ny)
        rec.map_xs, rec.map_ys = xs, ys
        rec.map_image = np.full((int(mm.ny), int(mm.nx)), np.nan)
        rec.cube = np.full((int(mm.ny), int(mm.nx), self.wave.size), np.nan)
        rec.map_dir = self.writer.start_map(index)
        t0 = self.clock()
        if self._laser_needed():
            r.laser(self.p.laser, True)
        try:
            for j, yv in enumerate(ys):
                for i, xv in enumerate(xs):
                    self.ev.progress(f"Mini-mapa: píxel {j * len(xs) + i + 1} / {len(xs) * len(ys)}")
                    r.move_to(float(xv), float(yv), None)
                    spec = r.expose((self.wave.size,), mm.exposure_s)
                    try:
                        rec.bs_v.append(float(self.read_bs()))
                        rec.bs_t.append(round(self.clock() - t0, 3))
                    except Exception as e:
                        print(f"[Luminiscencia] Sin lectura del BS en el píxel ({i}, {j}): {e}")
                    rec.cube[j, i, :] = spec
                    rec.map_image[j, i] = band_value(self.wave, spec, mm.band_nm)
                    self.writer.write_pixel(rec.map_dir, i, j, spec)
                    self.ev.map_update(rec.map_image, xs, ys)
                    self.ev.spectrum(self.wave, spec)
        finally:
            if self._laser_needed():
                r.laser(self.p.laser, False)
        cm = map_center_of_mass(rec.map_image, cx, cy, mm.range_um, mm.cm_threshold)
        if cm is not None:
            rec.map_cm = (cm[0], cm[1])
            self.ev.map_done(rec.map_image, cm[0], cm[1])
        else:
            self.ev.progress("El mapa es plano: sin centro de masa.")
