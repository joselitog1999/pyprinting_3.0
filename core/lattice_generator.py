"""
core/lattice_generator.py - Motor Cristalográfico y Generador de Redes 2D para PyPrinting 3.0
==============================================================================================
Proporciona el motor matemático riguroso para la síntesis, diseño, superposición, rotación,
recorte por figuras geométricas (hexágonos, círculos, rectángulos) y exportación de patrones
cristalinos 2D con cuadratura de Partícula Ancla (P0) para nanofabricación fototérmica.

Autor: Equipo PyPrinting 3.0 / INS-UNSAM
Fecha: Agosto 2026
"""

from __future__ import annotations
import math
import json
import os
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Union
import numpy as np


# ══════════════════════════════════════════════════════════════════════════════
#  ESTRUCTURAS DE DATOS CRISTALOGRÁFICAS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BasisAtom:
    """Átomo o partícula en la base de la celda unidad."""
    u: float              # Coordenada fraccional a lo largo de a1 [0, 1)
    v: float              # Coordenada fraccional a lo largo de a2 [0, 1)
    material_id: int = 1  # 1 = Material A, 2 = Material B, 3 = Material C
    label: str = "Atom"


@dataclass
class LatticeLayer:
    """Capa cristalina individual con parámetros de red, rotación y traslación."""
    name: str = "Layer 1"
    lattice_type: str = "square"  # square, rectangular, hexagonal, rhombic, oblique, graphene, kagome, lieb
    a: float = 3.0                # Parámetro de red a (µm)
    b: float = 3.0                # Parámetro de red b (µm)
    gamma_deg: float = 90.0       # Ángulo entre a1 y a2 (grados)
    atoms: List[BasisAtom] = field(default_factory=list)
    rotation_deg: float = 0.0     # Rotación global de la capa (grados)
    offset_x: float = 0.0         # Desplazamiento X respecto al origen (µm)
    offset_y: float = 0.0         # Desplazamiento Y respecto al origen (µm)
    enabled: bool = True
    color: str = "#89b4fa"        # Color representativo en la UI (hex)

    def __post_init__(self):
        if not self.atoms:
            self.atoms = self._default_basis_for_type(self.lattice_type)

    @staticmethod
    def _default_basis_for_type(ltype: str) -> List[BasisAtom]:
        """Genera la base atómica por defecto según el tipo de red."""
        ltype = ltype.lower()
        if ltype in ("square", "rectangular", "hexagonal", "rhombic", "oblique", "triangular"):
            return [BasisAtom(u=0.0, v=0.0, material_id=1, label="Base 0")]
        elif ltype in ("graphene", "honeycomb"):
            # Red Honeycomb: 2 átomos por celda unidad hexagonal
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="C1 (0,0)"),
                BasisAtom(u=1.0/3.0, v=2.0/3.0, material_id=2, label="C2 (1/3, 2/3)")
            ]
        elif ltype in ("boron_nitride", "hbn"):
            # Hexagonal BN (2 átomos de diferente material)
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="B (0,0)"),
                BasisAtom(u=1.0/3.0, v=2.0/3.0, material_id=2, label="N (1/3, 2/3)")
            ]
        elif ltype == "kagome":
            # Red Kagome: 3 átomos formando triángulos por vértices compartidos
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="K1 (0,0)"),
                BasisAtom(u=0.5, v=0.0, material_id=2, label="K2 (1/2, 0)"),
                BasisAtom(u=0.0, v=0.5, material_id=3, label="K3 (0, 1/2)")
            ]
        elif ltype == "lieb":
            # Red de Lieb: 3 átomos en vértices y centros de aristas
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="L1 (Corner)"),
                BasisAtom(u=0.5, v=0.0, material_id=2, label="L2 (Edge a₁)"),
                BasisAtom(u=0.0, v=0.5, material_id=2, label="L3 (Edge a₂)")
            ]
        elif ltype in ("dice", "t3", "dice_t3"):
            # Red de Dice / T3 (Hub central con 6 vecinos + 2 orbitales)
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="Hub D1 (0,0)"),
                BasisAtom(u=1.0/3.0, v=2.0/3.0, material_id=2, label="Rim D2 (1/3, 2/3)"),
                BasisAtom(u=2.0/3.0, v=1.0/3.0, material_id=3, label="Rim D3 (2/3, 1/3)")
            ]
        elif ltype == "centered_square":
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="Corner (0,0)"),
                BasisAtom(u=0.5, v=0.5, material_id=2, label="Center (1/2, 1/2)")
            ]
        elif ltype == "centered_rectangular":
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="Corner (0,0)"),
                BasisAtom(u=0.5, v=0.5, material_id=2, label="Center (1/2, 1/2)")
            ]
        elif ltype in ("mos2", "tmd"):
            # Monocapa TMD (MoS2 / WSe2): 1 metal de transición + 2 calcógenos
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="Mo (0,0)"),
                BasisAtom(u=1.0/3.0, v=2.0/3.0, material_id=2, label="S_top (1/3, 2/3)"),
                BasisAtom(u=2.0/3.0, v=1.0/3.0, material_id=2, label="S_bot (2/3, 1/3)")
            ]
        elif ltype == "decorated_triangular":
            return [
                BasisAtom(u=0.0, v=0.0, material_id=1, label="D1 (0,0)"),
                BasisAtom(u=0.5, v=0.5, material_id=2, label="D2 (1/2, 1/2)")
            ]
        return [BasisAtom(u=0.0, v=0.0, material_id=1, label="Base 0")]

    def get_basis_vectors(self) -> Tuple[np.ndarray, np.ndarray]:
        """Calcula los vectores de red primitivos a1 y a2 (en µm) de forma totalmente paramétrica."""
        gamma = math.radians(self.gamma_deg)
        a1 = np.array([self.a, 0.0])
        a2 = np.array([self.b * math.cos(gamma), self.b * math.sin(gamma)])
        return a1, a2


# ══════════════════════════════════════════════════════════════════════════════
#  MÁSCARAS Y FIGURAS GEOMÉTRICAS CONTENEDORAS
# ══════════════════════════════════════════════════════════════════════════════

class BoundingGeometry:
    """Evalúa si un punto cartesiano (x, y) pertenece a la figura contenedora."""

    @staticmethod
    def is_inside(x: float, y: float, shape_type: str, params: dict) -> bool:
        shape = shape_type.lower()

        if shape in ("all", "cells", "none"):
            return True

        elif shape == "rectangle":
            lx = float(params.get("lx", 10.0))
            ly = float(params.get("ly", 10.0))
            return (abs(x) <= lx / 2.0 + 1e-7) and (abs(y) <= ly / 2.0 + 1e-7)

        elif shape == "square":
            size = float(params.get("size", 10.0))
            return (abs(x) <= size / 2.0 + 1e-7) and (abs(y) <= size / 2.0 + 1e-7)

        elif shape == "circle":
            radius = float(params.get("radius", 5.0))
            return (x * x + y * y) <= (radius * radius + 1e-7)

        elif shape == "annulus":
            r_in = float(params.get("r_in", 2.0))
            r_out = float(params.get("r_out", 6.0))
            r2 = x * x + y * y
            return (r2 >= r_in * r_in - 1e-7) and (r2 <= r_out * r_out + 1e-7)

        elif shape == "hexagon":
            # Hexágono regular centrado en (0, 0)
            # Definido por apotema 'ap' (distancia del centro al punto medio del lado)
            # o radio exterior 'radius' (distancia del centro a los vértices).
            if "ap" in params:
                ap = float(params["ap"])
            else:
                r_ext = float(params.get("radius", 5.0))
                ap = r_ext * math.cos(math.radians(30.0))

            # Las 3 restricciones para un hexágono regular horizontal:
            # 1. |x| <= ap / cos(30°) = R  -> proyectado en lados:
            # |y| <= ap
            # |y*cos(60) + x*sin(60)| <= ap  => |0.5 y + sqrt(3)/2 x| <= ap
            # |y*cos(60) - x*sin(60)| <= ap  => |0.5 y - sqrt(3)/2 x| <= ap
            c30 = math.cos(math.radians(30.0))
            s30 = math.sin(math.radians(30.0))
            cond1 = abs(y) <= (ap + 1e-7)
            cond2 = abs(y * s30 + x * c30) <= (ap + 1e-7)
            cond3 = abs(y * s30 - x * c30) <= (ap + 1e-7)
            return cond1 and cond2 and cond3

        elif shape == "triangle":
            # Triángulo equilátero con lado L centrado en su baricentro
            side = float(params.get("side", 10.0))
            h = side * math.sqrt(3.0) / 2.0
            r_in = h / 3.0
            r_out = 2.0 * h / 3.0
            # Vértice superior en (0, r_out), base en y = -r_in
            if y < -r_in - 1e-7 or y > r_out + 1e-7:
                return False
            max_x = (r_out - y) / math.sqrt(3.0)
            return abs(x) <= max_x + 1e-7

        return True


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMIZADOR DE TRAYECTORIAS PARA PLATINA PI
# ══════════════════════════════════════════════════════════════════════════════

class PathOptimizer:
    """Reordena los nodos de la red para minimizar desplazamientos y deriva."""

    @staticmethod
    def sort_nodes(nodes: List[Dict], mode: str = "snake") -> List[Dict]:
        if len(nodes) <= 1:
            return nodes

        mode = mode.lower()
        if mode == "none":
            return nodes

        elif mode == "snake":
            # Ordenamiento por filas con dirección alternada (Zig-Zag / Serpiente)
            # 1. Agrupar por coordenada Y con tolerancia pequeña
            sorted_by_y = sorted(nodes, key=lambda n: n["y"])
            rows: List[List[Dict]] = []
            cur_row: List[Dict] = []
            cur_y = sorted_by_y[0]["y"]

            tol = 0.05  # 50 nm de tolerancia de fila
            for n in sorted_by_y:
                if abs(n["y"] - cur_y) <= tol:
                    cur_row.append(n)
                else:
                    rows.append(cur_row)
                    cur_row = [n]
                    cur_y = n["y"]
            if cur_row:
                rows.append(cur_row)

            # Alternar dirección X en cada fila
            result = []
            for r_idx, r in enumerate(rows):
                r_sorted = sorted(r, key=lambda n: n["x"], reverse=(r_idx % 2 == 1))
                result.extend(r_sorted)
            return result

        elif mode == "spiral":
            # Ordenamiento en espiral desde el centro hacia afuera
            cx = np.mean([n["x"] for n in nodes])
            cy = np.mean([n["y"] for n in nodes])
            # Ordenar primariamente por distancia al radio r y secundariamente por ángulo theta
            return sorted(nodes, key=lambda n: (
                math.hypot(n["x"] - cx, n["y"] - cy),
                math.atan2(n["y"] - cy, n["x"] - cx)
            ))

        elif mode == "tsp":
            # Vecino más cercano (Nearest Neighbor TSP) para trayectorias de distancia mínima
            unvisited = list(nodes)
            # Empezar por el nodo más cercano a (min_x, min_y)
            cur = min(unvisited, key=lambda n: (n["x"], n["y"]))
            tour = [cur]
            unvisited.remove(cur)

            while unvisited:
                nxt = min(unvisited, key=lambda n: (n["x"] - cur["x"])**2 + (n["y"] - cur["y"])**2)
                tour.append(nxt)
                unvisited.remove(nxt)
                cur = nxt
            return tour

        return nodes


# ══════════════════════════════════════════════════════════════════════════════
#  GESTOR DE PARTÍCULA ANCLA (P0)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class AnchorConfig:
    """Configuración de la Partícula Ancla para cuadratura y multi-paso."""
    enabled: bool = True
    mode: str = "printing_reference"  # printing_reference (P0 en (0,0), red en (startX, startY)), offset, center, first_node, custom
    start_x_um: float = 2.0           # Posición de inicio X de la red respecto a P0 en (0,0) (µm)
    start_y_um: float = 2.0           # Posición de inicio Y de la red respecto a P0 en (0,0) (µm)
    offset_x_um: float = -2.0         # Offset de seguridad exterior X respecto al borde (µm)
    offset_y_um: float = -2.0         # Offset de seguridad exterior Y respecto al borde (µm)
    custom_x_um: float = 0.0
    custom_y_um: float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  COMPOSITOR Y GENERADOR PRINCIPAL DE REDES CRISTALINAS
# ══════════════════════════════════════════════════════════════════════════════

class CrystalGridComposer:
    """Genera, recorta, combina y exporta redes cristalinas 2D complejas."""

    def __init__(self):
        self.layers: List[LatticeLayer] = [LatticeLayer(name="Layer 1", lattice_type="hexagonal", a=3.0)]
        self.bounding_shape: str = "cells"  # cells, hexagon, rectangle, square, circle, annulus, triangle
        self.bounding_params: dict = {"nx": 5, "ny": 5, "ap": 5.0, "radius": 6.0, "lx": 12.0, "ly": 12.0}
        self.anchor_config = AnchorConfig(enabled=True, mode="printing_reference", start_x_um=2.0, start_y_um=2.0)
        self.path_mode: str = "snake"
        self.collision_tolerance_um: float = 0.08  # 80 nm para detectar colisiones accidentales
        self.min_distance_um: float = 0.0  # Límite de distancia mínima de impresión física entre partículas

    def generate(self) -> Dict:
        """
        Ejecuta el pipeline completo de generación:
        1. Expande celdas unidad para cada capa habilitada.
        2. Aplica rotación afín theta y traslación delta_r.
        3. Aplica máscara de geometría contenedora.
        4. Fusión de capas, deduplicación y restricción de distancia mínima.
        5. Alineación y traslación de referencia del printing (P0 en (0,0), Red en (startX, startY)).
        6. Optimización de ruta de la platina PI.
        7. Inserción de la Partícula Ancla P0.
        """
        raw_nodes: List[Dict] = []

        # Determinar el rango de índices de celda (nx, ny)
        if self.bounding_shape == "cells":
            nx = int(self.bounding_params.get("nx", 5))
            ny = int(self.bounding_params.get("ny", 5))
            n1_range = range(nx)
            n2_range = range(ny)
        else:
            # Estimar el radio máximo de la figura para generar celdas suficientes
            r_max = max(
                float(self.bounding_params.get("ap", 8.0)) * 1.5,
                float(self.bounding_params.get("radius", 8.0)) * 1.2,
                float(self.bounding_params.get("lx", 15.0)),
                float(self.bounding_params.get("ly", 15.0)),
                float(self.bounding_params.get("size", 15.0)),
                float(self.bounding_params.get("side", 15.0))
            )
            # Calcular límites de n1 y n2
            min_a = min([l.a for l in self.layers if l.enabled] or [3.0])
            n_span = int(math.ceil(r_max / min_a)) + 2
            n1_range = range(-n_span, n_span + 1)
            n2_range = range(-n_span, n_span + 1)

        # 1 & 2. Generar nodos para cada capa
        for layer_idx, layer in enumerate(self.layers):
            if not layer.enabled:
                continue

            a1, a2 = layer.get_basis_vectors()
            rot_rad = math.radians(layer.rotation_deg)
            cos_th = math.cos(rot_rad)
            sin_th = math.sin(rot_rad)

            for n1 in n1_range:
                for n2 in n2_range:
                    r_cell = n1 * a1 + n2 * a2
                    for atom in layer.atoms:
                        r_atom = r_cell + atom.u * a1 + atom.v * a2
                        # Aplicar rotación afín
                        x_rot = r_atom[0] * cos_th - r_atom[1] * sin_th
                        y_rot = r_atom[0] * sin_th + r_atom[1] * cos_th
                        # Aplicar traslación
                        x_final = x_rot + layer.offset_x
                        y_final = y_rot + layer.offset_y

                        # 3. Aplicar máscara geométrica
                        if self.bounding_shape == "cells":
                            inside = True
                        else:
                            inside = BoundingGeometry.is_inside(
                                x_final, y_final, self.bounding_shape, self.bounding_params
                            )

                        if inside:
                            raw_nodes.append({
                                "x": round(float(x_final), 4),
                                "y": round(float(y_final), 4),
                                "layer_idx": layer_idx,
                                "layer_name": layer.name,
                                "material_id": atom.material_id,
                                "label": atom.label,
                                "color": layer.color
                            })

        if not raw_nodes:
            return {
                "nodes": [], "anchor": None, "layers": self.layers, "passes_nodes": {}, "shift": (0.0, 0.0),
                "stats": {"total": 0, "mat1": 0, "mat2": 0, "mat3": 0, "width_um": 0.0, "height_um": 0.0, "path_length_um": 0.0, "suppressed_by_min_dist": 0}
            }

        # 4. Restricción de distancia mínima (límite de impresión física) y deduplicación
        effective_min_dist = max(self.collision_tolerance_um, float(self.min_distance_um))
        dedup_nodes: List[Dict] = []
        suppressed_count = 0
        for n in raw_nodes:
            is_too_close = False
            for existing in dedup_nodes:
                d = math.hypot(n["x"] - existing["x"], n["y"] - existing["y"])
                if d < (effective_min_dist - 1e-6):
                    is_too_close = True
                    break
            if not is_too_close:
                dedup_nodes.append(n)
            else:
                suppressed_count += 1

        if not dedup_nodes:
            return {
                "nodes": [], "anchor": None, "layers": self.layers, "passes_nodes": {}, "shift": (0.0, 0.0),
                "stats": {"total": 0, "mat1": 0, "mat2": 0, "mat3": 0, "width_um": 0.0, "height_um": 0.0, "path_length_um": 0.0, "suppressed_by_min_dist": 0}
            }

        # 5. Traslación de Referencia del Printing (P0 en (0,0), Red iniciando en (startX, startY))
        shift_x, shift_y = 0.0, 0.0
        if self.anchor_config.enabled and self.anchor_config.mode == "printing_reference":
            min_x_raw = min(n["x"] for n in dedup_nodes)
            min_y_raw = min(n["y"] for n in dedup_nodes)
            shift_x = round(float(self.anchor_config.start_x_um) - min_x_raw, 4)
            shift_y = round(float(self.anchor_config.start_y_um) - min_y_raw, 4)
            for n in dedup_nodes:
                n["x"] = round(n["x"] + shift_x, 4)
                n["y"] = round(n["y"] + shift_y, 4)

        # 6. Optimización de trayectoria global y por cada material independiente
        sorted_nodes = PathOptimizer.sort_nodes(dedup_nodes, mode=self.path_mode)

        materials_present = sorted(list(set(n["material_id"] for n in dedup_nodes)))
        passes_nodes: Dict[int, List[Dict]] = {}
        for mat_id in materials_present:
            mat_raw = [n for n in dedup_nodes if n["material_id"] == mat_id]
            passes_nodes[mat_id] = PathOptimizer.sort_nodes(mat_raw, mode=self.path_mode)

        # 7. Cálculo e inserción de la Partícula Ancla P0
        anchor_node = None
        if self.anchor_config.enabled:
            all_x = [n["x"] for n in sorted_nodes]
            all_y = [n["y"] for n in sorted_nodes]
            min_x, max_x = min(all_x), max(all_x)
            min_y, max_y = min(all_y), max(all_y)

            if self.anchor_config.mode == "printing_reference":
                # Estándar de PyPrinting Measurements: Ancla capacitiva en el origen exacto (0, 0)
                p0_x = 0.0
                p0_y = 0.0
            elif self.anchor_config.mode == "offset":
                p0_x = round(min_x + self.anchor_config.offset_x_um, 4)
                p0_y = round(min_y + self.anchor_config.offset_y_um, 4)
            elif self.anchor_config.mode == "center":
                p0_x = 0.0
                p0_y = 0.0
            elif self.anchor_config.mode == "first_node":
                p0_x = sorted_nodes[0]["x"]
                p0_y = sorted_nodes[0]["y"]
            else:  # custom
                p0_x = self.anchor_config.custom_x_um
                p0_y = self.anchor_config.custom_y_um

            anchor_node = {
                "x": p0_x,
                "y": p0_y,
                "layer_idx": -1,
                "layer_name": "Anchor P0",
                "material_id": 0,  # 0 = Anchor Reference
                "label": "Anchor P0 ⭐",
                "color": "#f9e2af"  # Dorado
            }

        # Calcular métricas estadísticas globales y por pase
        all_x = [n["x"] for n in sorted_nodes]
        all_y = [n["y"] for n in sorted_nodes]
        w_um = round(max(all_x) - min(all_x), 3) if all_x else 0.0
        h_um = round(max(all_y) - min(all_y), 3) if all_y else 0.0

        # Longitud total de trayectoria global
        path_len = 0.0
        pts = ([anchor_node] if anchor_node else []) + sorted_nodes
        for i in range(1, len(pts)):
            path_len += math.hypot(pts[i]["x"] - pts[i-1]["x"], pts[i]["y"] - pts[i-1]["y"])

        # Longitud de trayectoria individual por pase
        pass_stats = {}
        for mat_id, m_nodes in passes_nodes.items():
            m_pts = ([anchor_node] if anchor_node else []) + m_nodes
            m_len = 0.0
            for i in range(1, len(m_pts)):
                m_len += math.hypot(m_pts[i]["x"] - m_pts[i-1]["x"], m_pts[i]["y"] - m_pts[i-1]["y"])
            pass_stats[mat_id] = {
                "count": len(m_nodes),
                "path_length_um": round(m_len, 2),
                "path_length_mm": round(m_len / 1000.0, 3)
            }

        stats = {
            "total": len(sorted_nodes) + (1 if anchor_node else 0),
            "grid_nodes": len(sorted_nodes),
            "mat1": sum(1 for n in sorted_nodes if n["material_id"] == 1),
            "mat2": sum(1 for n in sorted_nodes if n["material_id"] == 2),
            "mat3": sum(1 for n in sorted_nodes if n["material_id"] == 3),
            "has_anchor": anchor_node is not None,
            "width_um": w_um,
            "height_um": h_um,
            "path_length_um": round(path_len, 2),
            "path_length_mm": round(path_len / 1000.0, 3),
            "suppressed_by_min_dist": suppressed_count,
            "pass_stats": pass_stats
        }

        return {
            "nodes": sorted_nodes,
            "passes_nodes": passes_nodes,
            "anchor": anchor_node,
            "layers": self.layers,
            "shift": (shift_x, shift_y),
            "stats": stats
        }


# ══════════════════════════════════════════════════════════════════════════════
#  EXPORTADOR METROLÓGICO PARA PYPRINTING 3.0
# ══════════════════════════════════════════════════════════════════════════════

class CrystalGridExporter:
    """Exporta patrones cristalinos a formatos compatibles con PyPrinting y multi-paso."""

    @staticmethod
    def export_single_txt(filepath: str, result: Dict, include_anchor: bool = True) -> str:
        """Exporta un archivo .txt estándar de 2 columnas [X, Y] en µm."""
        nodes = result.get("nodes", [])
        anchor = result.get("anchor")
        
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            if include_anchor and anchor:
                f.write(f"{anchor['x']:.4f}\t{anchor['y']:.4f}\n")
            for n in nodes:
                f.write(f"{n['x']:.4f}\t{n['y']:.4f}\n")
        return filepath

    @staticmethod
    def export_multipass_package(output_dir: str, prefix: str, result: Dict) -> Dict[str, str]:
        """
        Genera el paquete completo de recetas para nanofabricación secuencial:
        - Layer1_MatA_con_P0.txt (Imprime P0 + Capa 1 con ruta optimizada para Mat 1)
        - Layer2_MatB_ref_P0.txt (Alinea sobre P0 + Imprime Capa 2 con ruta optimizada para Mat 2)
        - Layer3_MatC_ref_P0.txt (Alinea sobre P0 + Imprime Capa 3 con ruta optimizada para Mat 3)
        - Recipe_Summary.json
        """
        os.makedirs(output_dir, exist_ok=True)
        passes_nodes = result.get("passes_nodes", {})
        anchor = result.get("anchor")
        stats = result.get("stats", {})
        generated_files = {}

        # 1. Archivo Global Unificado (Single-Pass)
        unified_path = os.path.join(output_dir, f"{prefix}_ALL_LAYERS_con_P0.txt")
        CrystalGridExporter.export_single_txt(unified_path, result, include_anchor=True)
        generated_files["unified"] = unified_path

        # 2. Sub-archivos por cada Material / Capa con su ruta optimizada individual
        materials_present = sorted(list(passes_nodes.keys()))
        for mat_id in materials_present:
            mat_nodes = passes_nodes[mat_id]
            mat_name = f"Material_{mat_id}"
            file_name = f"{prefix}_Pass{mat_id}_{mat_name}_ref_P0.txt"
            mat_path = os.path.join(output_dir, file_name)

            with open(mat_path, "w", encoding="utf-8") as f:
                # La Partícula Ancla siempre va en la primera fila como referencia (nodo 0)
                if anchor:
                    f.write(f"{anchor['x']:.4f}\t{anchor['y']:.4f}\n")
                for n in mat_nodes:
                    f.write(f"{n['x']:.4f}\t{n['y']:.4f}\n")
            generated_files[f"material_{mat_id}"] = mat_path

        # 3. Metadatos de la Receta en JSON
        recipe_meta = {
            "prefix": prefix,
            "stats": stats,
            "anchor_particle": anchor,
            "materials_count": len(materials_present),
            "generated_files": {k: os.path.basename(v) for k, v in generated_files.items()}
        }
        json_path = os.path.join(output_dir, f"{prefix}_recipe_metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(recipe_meta, f, indent=2, ensure_ascii=False)
        generated_files["metadata"] = json_path

        return generated_files
