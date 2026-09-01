"""
core/hdf5_container.py — Contenedor Científico Unificado HDF5 para PyPrinting 3.0
================================================================================
Proporciona la clase `BatchHDF5Container` para la serialización y empaquetamiento
estructurado, trazable y comprimido de lotes experimentales de impresión óptica
(Printing, Dimers, Mapeos) según el estándar jerárquico HDF5.

Estructura Jerárquica:
----------------------
/metadata        -> Atributos clave-valor: láser, umbrales, sustrato, coloide, operario
/recipe          -> Coordenadas teóricas de la grilla, Partícula Ancla P0, parámetros
/telemetry       -> Tablas de seguimiento: deriva lateral XY, axial Z, ETA y Time-Volt
/nodes/node_xxx  -> Datasets individuales por nodo:
                    - photothermal_trace: [tiempo_s, fotodiodo_V, fotodiodo_BS_V]
                    - confocal_scan: Matriz 2D [Nx, Ny] float32
                    - Atributos: status (SUCCESS/TIMEOUT), t_print, fitting gaussiano

Características:
----------------
- Compresión Lossless en tiempo real con pre-filtro `shuffle=True` y `compression="gzip"` (nivel 4).
- Modo No Bloqueante / Tolerante a Fallos: guarda nodo por nodo de forma segura.
- Desempaquetador 1-Click (`unpack_to_legacy`): exporta el lote completo a archivos `.txt` y `.tiff` sueltos.
"""

import os
import time
import numpy as np
from PIL import Image

try:
    import h5py
    H5PY_AVAILABLE = True
except ImportError:
    H5PY_AVAILABLE = False


class BatchHDF5Container:
    """
    Gestor del contenedor HDF5 para un lote estructurado de nanofabricación.
    """

    def __init__(self, filepath: str, metadata: dict = None, recipe: dict = None):
        """
        Inicializa o abre un contenedor HDF5.
        
        :param filepath: Ruta completa al archivo `.h5`.
        :param metadata: Diccionario con metadatos del experimento.
        :param recipe: Diccionario con la configuración geométrica de la grilla.
        """
        self.filepath = filepath
        self.is_closed = False
        self._file = None

        if not H5PY_AVAILABLE:
            print("[HDF5 Warning] h5py no está disponible. No se generará el contenedor binario.")
            return

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        self._file = h5py.File(self.filepath, "a")

        # 1. Crear grupos base si no existen
        if "metadata" not in self._file:
            self._file.create_group("metadata")
        if "recipe" not in self._file:
            self._file.create_group("recipe")
        if "telemetry" not in self._file:
            self._file.create_group("telemetry")
        if "nodes" not in self._file:
            self._file.create_group("nodes")

        # 2. Registrar metadatos iniciales
        if metadata:
            self.set_metadata(metadata)

        # 3. Registrar receta inicial
        if recipe:
            self.set_recipe(recipe)

        self._file.flush()

    def set_metadata(self, metadata: dict):
        """Almacena o actualiza los metadatos globales del experimento en /metadata."""
        if not self._is_open():
            return
        meta_grp = self._file["metadata"]
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, (int, float, str, bool)):
                meta_grp.attrs[k] = v
            else:
                meta_grp.attrs[k] = str(v)
        self._file.flush()

    def set_recipe(self, recipe: dict):
        """Almacena la receta geométrica y coordenadas nominales en /recipe."""
        if not self._is_open():
            return
        rec_grp = self._file["recipe"]

        # Atributos escalares
        for k in ("grid_name", "mode", "n_particles", "anchor_mode", "start_x", "start_y", "d_min"):
            if k in recipe:
                rec_grp.attrs[k] = recipe[k]

        # Coordenadas de la grilla (Matriz 2xN o 3xN)
        if "coordinates" in recipe and recipe["coordinates"] is not None:
            coords = np.asarray(recipe["coordinates"], dtype=np.float64)
            if "target_coordinates_um" in rec_grp:
                del rec_grp["target_coordinates_um"]
            rec_grp.create_dataset(
                "target_coordinates_um",
                data=coords,
                compression="gzip",
                compression_opts=4,
                shuffle=True
            )

        if "anchor_p0" in recipe and recipe["anchor_p0"] is not None:
            rec_grp.attrs["anchor_p0_x"] = float(recipe["anchor_p0"][0])
            rec_grp.attrs["anchor_p0_y"] = float(recipe["anchor_p0"][1])

        self._file.flush()

    def add_node_data(self, node_idx: int, trace: np.ndarray = None, 
                      scan: np.ndarray = None, status: str = "UNKNOWN", 
                      t_print: float = 0.0, attributes: dict = None):
        """
        Registra la traza temporal y/o imagen confocal de un nodo específico.
        
        :param node_idx: Índice del nodo (0, 1, 2...).
        :param trace: Array 2D [muestras, canales] con columnas [t, Photodiode, BS].
        :param scan: Matriz 2D [Nx, Ny] de la imagen confocal.
        :param status: Estado ('SUCCESS', 'TIMEOUT', 'RETRY_SUCCESS', etc.).
        :param t_print: Tiempo efectivo de impresión en segundos.
        :param attributes: Diccionario opcional de atributos adicionales (e.g. fit gaussiano).
        """
        if not self._is_open():
            return

        nodes_grp = self._file["nodes"]
        node_name = f"node_{int(node_idx):03d}"

        if node_name not in nodes_grp:
            node_grp = nodes_grp.create_group(node_name)
        else:
            node_grp = nodes_grp[node_name]

        # Atributos del nodo
        node_grp.attrs["status"] = str(status)
        node_grp.attrs["t_print_s"] = float(t_print)
        node_grp.attrs["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

        if attributes:
            for ak, av in attributes.items():
                if isinstance(av, (int, float, str, bool)):
                    node_grp.attrs[ak] = av

        # Dataset de Traza Fototérmica
        if trace is not None and trace.size > 0:
            tr_arr = np.asarray(trace, dtype=np.float32)
            if "photothermal_trace" in node_grp:
                del node_grp["photothermal_trace"]
            node_grp.create_dataset(
                "photothermal_trace",
                data=tr_arr,
                compression="gzip",
                compression_opts=4,
                shuffle=True
            )

        # Dataset de Imagen Confocal
        if scan is not None and scan.size > 0:
            scan_arr = np.asarray(scan, dtype=np.float32)
            if "confocal_scan" in node_grp:
                del node_grp["confocal_scan"]
            node_grp.create_dataset(
                "confocal_scan",
                data=scan_arr,
                compression="gzip",
                compression_opts=4,
                shuffle=True
            )

        self._file.flush()

    def set_telemetry(self, drift_xy: list = None, drift_z: list = None, 
                      time_volt_rows: list = None, eta_history: list = None):
        """Almacena las series temporales de deriva y estadísticas de optimización."""
        if not self._is_open():
            return

        tel_grp = self._file["telemetry"]

        # 1. Deriva Lateral XY
        if drift_xy:
            xy_data = []
            for item in drift_xy:
                xy_data.append([
                    float(item.get("node", 0)),
                    float(item.get("time", 0.0)),
                    float(item.get("dx_nm", 0.0)),
                    float(item.get("dy_nm", 0.0)),
                    float(item.get("mag_nm", 0.0)),
                    float(item.get("v_xy", 0.0))
                ])
            if "drift_xy" in tel_grp:
                del tel_grp["drift_xy"]
            ds = tel_grp.create_dataset(
                "drift_xy",
                data=np.array(xy_data, dtype=np.float32),
                compression="gzip",
                compression_opts=4,
                shuffle=True
            )
            ds.attrs["columns"] = "node, time_s, dx_nm, dy_nm, mag_nm, v_xy_nms"

        # 2. Deriva Axial Z
        if drift_z:
            z_data = []
            for item in drift_z:
                z_data.append([
                    float(item.get("node", 0)),
                    float(item.get("time", 0.0)),
                    float(item.get("dz_nm", 0.0)),
                    float(item.get("v_z", 0.0))
                ])
            if "drift_z" in tel_grp:
                del tel_grp["drift_z"]
            ds_z = tel_grp.create_dataset(
                "drift_z",
                data=np.array(z_data, dtype=np.float32),
                compression="gzip",
                compression_opts=4,
                shuffle=True
            )
            ds_z.attrs["columns"] = "node, time_s, dz_nm, v_z_nms"

        # 3. Estadísticas Time-Volt
        if time_volt_rows:
            tv_data = []
            for r in time_volt_rows:
                tv_data.append([
                    float(r.get("node", 0)),
                    float(r.get("v_low", 0.0)),
                    float(r.get("v_high", 0.0)),
                    float(r.get("delta_v", 0.0)),
                    float(r.get("t_step", 0.0)),
                    float(r.get("t_raw", 0.0)),
                    float(r.get("delta_t", 0.0))
                ])
            if "time_volt_stats" in tel_grp:
                del tel_grp["time_volt_stats"]
            ds_tv = tel_grp.create_dataset(
                "time_volt_stats",
                data=np.array(tv_data, dtype=np.float32),
                compression="gzip",
                compression_opts=4,
                shuffle=True
            )
            ds_tv.attrs["columns"] = "node, v_low_V, v_high_V, delta_v_V, t_step_s, t_raw_s, delta_t_s"

        self._file.flush()

    def close(self):
        """Cierra el archivo HDF5 de forma segura."""
        if self._file and not self.is_closed:
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                pass
            finally:
                self.is_closed = True
                self._file = None

    def _is_open(self) -> bool:
        return bool(H5PY_AVAILABLE and self._file and not self.is_closed)

    # ── Desempaquetador 1-Click a Formato Tradicional ─────────────────────────
    @staticmethod
    def unpack_to_legacy(h5_filepath: str, output_folder: str = None) -> str:
        """
        Extrae todos los datos del contenedor HDF5 a la estructura clásica
        de carpetas con archivos `.txt`, `.tiff` y `grid_info.txt`.
        
        :param h5_filepath: Ruta al archivo `.h5`.
        :param output_folder: Carpeta destino (por defecto la subcarpeta del .h5 sin extensión).
        :return: Ruta de la carpeta extraída.
        """
        if not H5PY_AVAILABLE or not os.path.exists(h5_filepath):
            raise FileNotFoundError(f"Archivo HDF5 no encontrado: {h5_filepath}")

        if not output_folder:
            base_name = os.path.splitext(os.path.basename(h5_filepath))[0]
            output_folder = os.path.join(os.path.dirname(h5_filepath), f"Unpacked_{base_name}")

        os.makedirs(output_folder, exist_ok=True)

        with h5py.File(h5_filepath, "r") as f:
            # 1. Exportar grid_info.txt desde /metadata
            if "metadata" in f:
                meta = f["metadata"].attrs
                info_path = os.path.join(output_folder, "grid_info.txt")
                with open(info_path, "w", encoding="utf-8") as inf_f:
                    for k in meta.keys():
                        inf_f.write(f"{k}\t{meta[k]}\n")

            # 2. Exportar trazas e imágenes desde /nodes
            if "nodes" in f:
                nodes_grp = f["nodes"]
                for n_name in sorted(nodes_grp.keys()):
                    ng = nodes_grp[n_name]
                    
                    # Traza .txt
                    if "photothermal_trace" in ng:
                        tr_data = ng["photothermal_trace"][:]
                        tr_path = os.path.join(output_folder, f"NP_{n_name.replace('node_', '')}.txt")
                        status_val = ng.attrs.get("status", "UNKNOWN")
                        t_print = ng.attrs.get("t_print_s", 0.0)
                        hdr = f"Status: {status_val} (t_print={t_print:.2f}s)\nTime_s\tPhotodiode_V\tPhotodiode_BS_V"
                        np.savetxt(tr_path, tr_data, fmt="%.3e", header=hdr)

                    # Confocal .tiff
                    if "confocal_scan" in ng:
                        scan_arr = ng["confocal_scan"][:]
                        tif_path = os.path.join(output_folder, f"NPscan_{n_name.replace('node_', '')}.tiff")
                        
                        arr_min = float(np.min(scan_arr))
                        arr_max = float(np.max(scan_arr))
                        rng = max(1e-9, arr_max - arr_min)
                        arr_norm = (scan_arr - arr_min) / rng
                        arr_uint16 = (arr_norm * 65535).astype(np.uint16)
                        Image.fromarray(arr_uint16).save(tif_path)

            # 3. Exportar telemetría de deriva desde /telemetry
            if "telemetry" in f:
                tel = f["telemetry"]
                if "drift_xy" in tel:
                    xy_data = tel["drift_xy"][:]
                    hdr_xy = "node\ttime_s\tdx_nm\tdy_nm\tmag_nm\tv_xy_nms"
                    np.savetxt(os.path.join(output_folder, "drift_tracking_xy.txt"), xy_data, fmt="%.3f", header=hdr_xy)
                
                if "drift_z" in tel:
                    z_data = tel["drift_z"][:]
                    hdr_z = "node\ttime_s\tdz_nm\tv_z_nms"
                    np.savetxt(os.path.join(output_folder, "drift_tracking_z.txt"), z_data, fmt="%.3f", header=hdr_z)

        print(f"[HDF5 Container] Desempaquetado completo en: {output_folder}")
        return output_folder
