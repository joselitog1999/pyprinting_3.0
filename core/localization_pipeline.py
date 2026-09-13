"""
core/localization_pipeline.py
==============================
Pipeline unificado de localización de nanopartículas y emisores fluorescentes
para redes periódicas nanofabricadas en PyPrinting 3.0.

Soporta:
- Carga de imágenes multiformato (TIFF, PNG, JPG, H5).
- Carga directa de tablas de coordenadas previas (CSV, TSV, TXT).
- Motor Picasso (GaussLQ / GaussMLE) con compensación de offset de caja y parámetros extendidos.
- Motor Trackpy (Crocker-Grier) con opción de deconvolución previa Richardson-Lucy.
- Conversión métrica transparente (px -> nm).
"""

import os
import tempfile
import numpy as np
import pandas as pd
from typing import Optional, Tuple, Dict, Any, Union

try:
    import tifffile
except ImportError:
    tifffile = None

try:
    from skimage.restoration import richardson_lucy
    from scipy.ndimage import gaussian_filter
except ImportError:
    richardson_lucy = None
    gaussian_filter = None

try:
    from picasso import localize as picasso_localize
except ImportError:
    picasso_localize = None

try:
    import trackpy as tp
except ImportError:
    tp = None


def load_image(file_path: str) -> np.ndarray:
    """
    Carga una imagen confocal o de fluorescencia desde disco y devuelve un array 2D (H, W).
    Soporta TIFF, PNG, JPG y HDF5.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de imagen: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext in ('.tiff', '.tif'):
        if tifffile is None:
            raise ImportError("tifffile no está instalado para abrir imágenes TIFF.")
        img = tifffile.imread(file_path)
    elif ext in ('.h5', '.hdf5'):
        import h5py
        with h5py.File(file_path, 'r') as hf:
            img = None
            for key in hf.keys():
                obj = hf[key]
                if isinstance(obj, h5py.Dataset) and obj.ndim in (2, 3):
                    img = obj[()]
                    break
            if img is None:
                raise ValueError(f"No se encontró dataset 2D/3D en {file_path}")
    else:
        # PNG, JPG u otros formatos raster
        from PIL import Image
        with Image.open(file_path) as pil_img:
            img = np.array(pil_img)

    # Normalizar dimensiones a 2D (H, W)
    if img.ndim == 3:
        if img.shape[0] == 1:
            img = img[0]
        elif img.shape[-1] in (3, 4):  # RGB / RGBA -> Grayscale
            img = 0.2989 * img[..., 0] + 0.5870 * img[..., 1] + 0.1140 * img[..., 2]
        else:
            # Pila z o temporal: tomar el primer frame
            img = img[0]
    elif img.ndim > 3:
        img = np.squeeze(img)
        while img.ndim > 2:
            img = img[0]

    return img.astype(np.float32)


def load_coordinates(file_path: str) -> pd.DataFrame:
    """
    Carga directamente una tabla de coordenadas (CSV, TSV, TXT, NPY).
    Normaliza los nombres de columnas a 'x' e 'y'.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No se encontró el archivo de coordenadas: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.npy':
        arr = np.load(file_path)
        if arr.ndim == 2 and arr.shape[1] >= 2:
            df = pd.DataFrame(arr[:, :2], columns=['x', 'y'])
        else:
            raise ValueError(f"Array en {file_path} no tiene forma (N, 2).")
    else:
        # Delimitador automático por coma, tab o espacio
        sep = ',' if ext == '.csv' else (r'\t' if ext == '.tsv' else None)
        df = pd.read_csv(file_path, sep=sep, engine='python')

        # Buscar columnas x, y (insensible a mayúsculas)
        cols_lower = {c: str(c).strip().lower() for c in df.columns}
        x_col = next((c for c, l in cols_lower.items() if l in ('x', 'x_px', 'x_nm', 'pos_x')), None)
        y_col = next((c for c, l in cols_lower.items() if l in ('y', 'y_px', 'y_nm', 'pos_y')), None)

        if x_col is not None and y_col is not None:
            df = df.rename(columns={x_col: 'x', y_col: 'y'})
        elif len(df.columns) >= 2:
            cols = list(df.columns)
            df = df.rename(columns={cols[0]: 'x', cols[1]: 'y'})
        else:
            raise ValueError(f"El archivo {file_path} no contiene al menos dos columnas de coordenadas (x, y).")

    # Asegurar numéricos
    df['x'] = pd.to_numeric(df['x'], errors='coerce')
    df['y'] = pd.to_numeric(df['y'], errors='coerce')
    df = df.dropna(subset=['x', 'y']).reset_index(drop=True)
    return df


def apply_richardson_lucy(
    image_2d: np.ndarray,
    psf_sigma: float = 1.5,
    num_iter: int = 15
) -> np.ndarray:
    """
    Restaura la imagen confocal mediante deconvolución iterativa Richardson-Lucy
    con una PSF gaussiana 2D simétrica.
    """
    if richardson_lucy is None:
        raise ImportError("skimage.restoration no está instalado para Richardson-Lucy.")

    # Generar núcleo PSF gaussiano centrado
    kernel_radius = int(np.ceil(3 * psf_sigma))
    y, x = np.mgrid[-kernel_radius:kernel_radius + 1, -kernel_radius:kernel_radius + 1]
    psf = np.exp(-(x**2 + y**2) / (2 * psf_sigma**2))
    psf /= psf.sum()

    # Normalizar imagen al rango [0, 1]
    img_min = float(image_2d.min())
    img_max = float(image_2d.max())
    if img_max > img_min:
        img_norm = (image_2d - img_min) / (img_max - img_min)
    else:
        return image_2d.copy()

    # Ejecutar deconvolución
    restored = richardson_lucy(img_norm, psf, num_iter=num_iter, clip=False)
    # Re-escalar a la amplitud original
    restored = np.clip(restored * (img_max - img_min) + img_min, 0, None)
    return restored.astype(np.float32)


def localize_picasso(
    image_2d: np.ndarray,
    min_net_gradient: float = 1.0,
    box_size: int = 7,
    method: str = 'gausslq',
    compensate_box_offset: bool = True,
    auto_scale_uint16: bool = True,
    invert: bool = False,
    baseline: int = 100,
    sensitivity: float = 1.0,
    gain: float = 1.0,
    extended_parameters: bool = True,
    camera_info: Optional[Dict[str, Any]] = None
) -> pd.DataFrame:
    """
    Detecta y ajusta centroides de emisores usando Picasso (GaussLQ o GaussMLE).

    Soporta:
    - Auto-escalado dinámico a uint16 [1000, 30000] para imágenes float32/normalizadas.
    - Inversión de imagen para imágenes en fondo claro (transmisión).
    - Compensación nativa del offset de caja (+box/2).
    - Parámetros extendidos de localización.
    """
    if picasso_localize is None:
        raise ImportError("picasso no está instalado en el entorno.")

    if box_size % 2 == 0:
        box_size += 1

    img_clean = np.nan_to_num(image_2d, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)

    # Inversión de intensidades si se especifica fondo claro
    if invert:
        i_min = float(np.min(img_clean))
        i_max = float(np.max(img_clean))
        img_clean = (i_max + i_min) - img_clean

    # Auto-escalado dinámico a uint16 para evitar truncamiento a 0 en imágenes float
    if auto_scale_uint16 or float(np.max(img_clean)) <= 10.0:
        i_min = float(np.min(img_clean))
        i_max = float(np.max(img_clean))
        if i_max > i_min:
            img_uint = (((img_clean - i_min) / (i_max - i_min)) * 30000.0 + 1000.0).astype(np.uint16)
        else:
            img_uint = np.zeros_like(img_clean, dtype=np.uint16)
    else:
        img_uint = np.clip(img_clean, 0, 65535).astype(np.uint16)

    img_3d = img_uint[np.newaxis, :, :]

    if camera_info is None:
        camera_info = {
            "Baseline": int(baseline),
            "Gain": float(gain),
            "Sensitivity": float(sensitivity),
            "Pixelsize": 130
        }

    with tempfile.NamedTemporaryFile(suffix='.raw', delete=False) as f:
        tmp_name = f.name
    try:
        mm = np.memmap(tmp_name, dtype=img_3d.dtype, mode='w+', shape=img_3d.shape)
        mm[:] = img_3d[:]
        mm.flush()

        # 1. Identificación de candidatos
        ident = picasso_localize.identify(mm, min_net_gradient, box_size, threaded=False)
        if ident is None or len(ident) == 0:
            return pd.DataFrame(columns=['x', 'y'])

        # 2. Ajuste 2D (fit2D)
        movie_info = [{
            'Byte Order': '<',
            'Data Type': str(img_3d.dtype),
            'Frames': 1,
            'Height': img_3d.shape[1],
            'Width': img_3d.shape[2]
        }]
        locs, _ = picasso_localize.fit2D(
            mm,
            movie_info,
            camera_info,
            ident,
            box_size,
            fitting_method=method,
            multiprocess=False
        )
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except Exception:
                pass

    if locs is None or len(locs) == 0:
        return pd.DataFrame(columns=['x', 'y'])

    df = pd.DataFrame(locs)

    # 3. Compensación de offset de caja de Picasso
    if compensate_box_offset:
        box_offset = box_size // 2
        df['x'] = df['x'] - box_offset
        df['y'] = df['y'] - box_offset

    # Filtrar columnas deseadas
    base_cols = ['x', 'y']
    ext_cols = ['photons', 'sx', 'sy', 'bg', 'lpx', 'lpy', 'ellipticity', 'net_gradient']

    if extended_parameters:
        keep_cols = [c for c in base_cols + ext_cols if c in df.columns]
    else:
        keep_cols = base_cols

    return df[keep_cols].copy()


def localize_trackpy(
    image_2d: np.ndarray,
    diameter: int = 7,
    minmass: float = 0.0,
    separation: Optional[float] = None,
    noise_size: float = 1.0,
    smoothing_size: Optional[float] = None,
    threshold: Optional[float] = None,
    percentile: float = 64,
    topn: Optional[int] = None,
    invert: bool = False,
    extended_parameters: bool = True
) -> pd.DataFrame:
    """
    Detecta y ajusta centroides de nanopartículas usando el algoritmo Crocker-Grier de Trackpy.

    Soporta:
    - Inversión de imagen (para fondo claro / transmisión).
    - Separación mínima de picos (separation).
    - Parámetros avanzados de filtrado (noise_size, smoothing_size, threshold, percentile, topn).
    - Parámetros extendidos de caracterización.
    """
    if tp is None:
        raise ImportError("trackpy no está instalado en el entorno.")

    if diameter % 2 == 0:
        diameter += 1

    img_clean = np.nan_to_num(image_2d, nan=0.0, posinf=0.0, neginf=0.0)

    locate_kwargs: Dict[str, Any] = {
        'diameter': diameter,
        'minmass': minmass if minmass > 0 else None,
        'separation': separation if (separation is not None and separation > 0) else None,
        'noise_size': noise_size,
        'smoothing_size': smoothing_size,
        'threshold': threshold,
        'percentile': percentile,
        'topn': topn,
        'invert': invert,
        'characterize': True
    }
    locate_kwargs = {k: v for k, v in locate_kwargs.items() if v is not None}

    features = tp.locate(img_clean, **locate_kwargs)

    if features is None or features.empty:
        return pd.DataFrame(columns=['x', 'y'])

    base_cols = ['x', 'y']
    ext_cols = ['mass', 'size', 'ecc', 'signal', 'raw_mass', 'ep']

    if extended_parameters:
        keep_cols = [c for c in base_cols + ext_cols if c in features.columns]
    else:
        keep_cols = base_cols

    return features[keep_cols].reset_index(drop=True)


def convert_pixels_to_nm(df: pd.DataFrame, pixel_size_nm: float) -> pd.DataFrame:
    """
    Añade o actualiza las columnas 'x_nm' e 'y_nm' en el DataFrame a partir de 'x', 'y' en px.
    """
    df_out = df.copy()
    df_out['x_nm'] = df_out['x'] * pixel_size_nm
    df_out['y_nm'] = df_out['y'] * pixel_size_nm
    return df_out
