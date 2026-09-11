"""
core/sif_processor.py
=====================
Motor científico de procesamiento de archivos espectrales .SIF (Andor Solis).
Soporta:
- Datos 1D (Full Vertical Binning / FVB) y 2D (Multi-pixel / Slit Imaging).
- Corrección de bugs de dispersión de longitud de onda nativos de SIF.
- Extracción exhaustiva de metadatos instrumentales (Solis, Shamrock, EMCCD, slit, objetivo).
- Filtros duales pre- y post-operación (Savitzky-Golay, FFT Low-pass, Media Móvil, Despiking de rayos cósmicos).
- Álgebra espectral (Resta de fondo, Transmitancia, Absorbancia / Extinción, Residuos).
- Reducción espacial interactiva por ROI (promedio/suma, desviación estándar espacial, SEM).
- Estadísticas en 3 modos: Solo ROI, Solo Set, ROI + Set.
- Propagación rigurosa de errores con modelo fotónico/EMCCD y objetivos de microscopio.
- Exportadores a texto científico (.dat, .txt, .csv) compatibles con Origin y Python.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union, Any
import io
import os
import re
import warnings
import numpy as np
from scipy import signal, ndimage
from scipy.optimize import curve_fit

try:
    import sif_parser
except ImportError:
    sif_parser = None


# ==============================================================================
# TREN ÓPTICO RELÉ 4f Y TORRETA DE 5 OBJETIVOS REALES DEL LABORATORIO
# Lente tubo intermedia: f1 = 250 mm | Lente colimadora relé: f2 = 200 mm (Gamma = 1.25x)
# Lente de inyección a Shamrock 500i: f_spec = 250 mm
# Magnificación efectiva a la ranura: M_spec = Gamma * (f_spec / f_obj) = 312.5 mm / f_obj
# Detector Andor iXon3 DU8285: pixel pitch = 13.0 um
# ==============================================================================
F_RELE_1_MM = 250.0
F_RELE_2_MM = 200.0
GAMMA_RELE = F_RELE_1_MM / F_RELE_2_MM  # 1.25x
F_SPEC_MM = 250.0
CCD_PIXEL_PITCH_UM = 13.0

MICROSCOPE_OBJECTIVES = {
    "Olympus MPLN 10x Aire (NA 0.25)": {
        "name": "Olympus 10x",
        "nominal_mag": 10.0,
        "magnification": 10.0,
        "f_obj_mm": 18.00,
        "na": 0.25,
        "medium": "Aire (n=1.0)",
        "m_spec": (GAMMA_RELE * F_SPEC_MM) / 18.00,  # 17.361x
        "pixel_scale_um": CCD_PIXEL_PITCH_UM / ((GAMMA_RELE * F_SPEC_MM) / 18.00),  # 0.7488 um/px
        "description": "Alineación rápida y localización de campo amplio (0.749 µm/px)"
    },
    "Olympus 20x Aire (NA 0.40)": {
        "name": "Olympus 20x",
        "nominal_mag": 20.0,
        "magnification": 20.0,
        "f_obj_mm": 9.00,
        "na": 0.40,
        "medium": "Aire (n=1.0)",
        "m_spec": (GAMMA_RELE * F_SPEC_MM) / 9.00,   # 34.722x
        "pixel_scale_um": CCD_PIXEL_PITCH_UM / ((GAMMA_RELE * F_SPEC_MM) / 9.00),   # 0.3744 um/px
        "description": "Campo medio para localización de nanopartículas (0.374 µm/px)"
    },
    "Nikon CFI S Plan Fluor 40x Aire (NA 0.60)": {
        "name": "Nikon 40x",
        "nominal_mag": 40.0,
        "magnification": 40.0,
        "f_obj_mm": 5.00,
        "na": 0.60,
        "medium": "Aire (Collar 0-2 mm)",
        "m_spec": (GAMMA_RELE * F_SPEC_MM) / 5.00,   # 62.500x
        "pixel_scale_um": CCD_PIXEL_PITCH_UM / ((GAMMA_RELE * F_SPEC_MM) / 5.00),   # 0.2080 um/px
        "description": "Alta resolución aire con collar de cubreobjetos (0.208 µm/px)"
    },
    "Olympus LUMPlanFLN 60x W (NA 1.00)": {
        "name": "Olympus 60x W",
        "nominal_mag": 60.0,
        "magnification": 60.0,
        "f_obj_mm": 3.00,
        "na": 1.00,
        "medium": "Agua (n=1.333)",
        "m_spec": (GAMMA_RELE * F_SPEC_MM) / 3.00,   # 104.167x
        "pixel_scale_um": CCD_PIXEL_PITCH_UM / ((GAMMA_RELE * F_SPEC_MM) / 3.00),   # 0.1248 um/px
        "description": "Inmersión directa en agua sobre muestra (sin aberración esférica, 0.125 µm/px)"
    },
    "Nikon S Plan Fluor 100x Oil (NA 0.50-1.30)": {
        "name": "Nikon 100x Oil",
        "nominal_mag": 100.0,
        "magnification": 100.0,
        "f_obj_mm": 2.00,
        "na": 1.30,
        "medium": "Aceite (n=1.515)",
        "m_spec": (GAMMA_RELE * F_SPEC_MM) / 2.00,   # 156.250x
        "pixel_scale_um": CCD_PIXEL_PITCH_UM / ((GAMMA_RELE * F_SPEC_MM) / 2.00),   # 0.0832 um/px
        "description": "Inmersión en aceite con diafragma iris variable (0.083 µm/px)"
    }
}


@dataclass
class SifMetadata:
    """Metadatos completos extraídos del archivo SIF y del nombre del archivo."""
    filepath: str = ""
    filename: str = ""
    experiment_time: int = 0
    exposure_time: float = 0.05
    cycle_time: float = 0.0
    accumulated_cycles: int = 1
    detector_temp_c: float = -65.0
    detector_type: str = "DU8285_VP"
    detector_dims: Tuple[int, int] = (1004, 1002)
    em_gain: float = 0.0
    gate_gain: float = 0.0
    gain_dac: float = 0.0
    spectrograph: str = ""
    grating_blaze_um: float = 0.0
    slit_width_um: float = 100.0
    xbin: int = 1
    ybin: int = 1
    num_frames: int = 1
    num_subimages: int = 1
    shape: Tuple[int, ...] = (1, 1, 1024)
    data_type: str = "Counts"
    polarization_angle_deg: Optional[float] = None
    original_filename: str = ""
    extra_info: Dict = field(default_factory=dict)


@dataclass(eq=False)
class SifSpectrum:
    """Estructura de datos para un archivo o frame de espectro SIF multi-canal."""
    raw_data: np.ndarray             # (no_images, height, width)
    wavelengths: np.ndarray          # (width,) en nm
    metadata: SifMetadata
    role: str = "sample"             # 'bg', 'ref', 'sample', 'transmittance_meas', 'unassigned'
    custom_name: str = ""
    is_2d: bool = False              # True si height > 1
    channels: Dict[str, np.ndarray] = field(default_factory=dict)
    channels_count: int = 1
    is_master: bool = False
    ref_is_bg_corrected: bool = False

    @property
    def num_frames(self) -> int:
        return self.raw_data.shape[0]

    @property
    def height(self) -> int:
        return self.raw_data.shape[1]

    @property
    def width(self) -> int:
        return self.raw_data.shape[2]

    @property
    def transmittance_data(self) -> Optional[np.ndarray]:
        return self.channels.get("transmittance")

    @property
    def reference_data(self) -> Optional[np.ndarray]:
        return self.channels.get("reference")

    @property
    def dark_data(self) -> Optional[np.ndarray]:
        return self.channels.get("dark")

    @property
    def live_data(self) -> Optional[np.ndarray]:
        return self.channels.get("live")


# ==============================================================================
# LECTURA Y DESEMPAQUETADO MULTI-CANAL SIF
# ==============================================================================
def parse_all_sif_channels(filepath: str, return_details: bool = False) -> Any:
    """
    Desempaqueta todos los canales espectrales contenidos en un archivo multi-canal .SIF de Andor Solis.
    Detecta los bloques de cabecera '6556X' para extraer las matrices correspondientes a:
    - Transmitancia final (Canal 1)
    - Referencia / Lámpara corregida por fondo (Canal 2)
    - Ruido / Fondo oscuro Dark counts (Canal 3)
    - Señal en vivo / Muestra Live (Canal 4)
    
    Si el archivo contiene menos canales:
    - 3 canales: Transmitancia, Referencia, Live.
    - 2 canales: Transmitancia, Live.
    - 1 canal: Transmitancia o Live (según DataType).
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"No se encontró el archivo: {filepath}")

    with open(filepath, 'rb') as f:
        content = f.read()

    magic = b'Andor Technology Multi-Channel File\n65538 1\n'
    matches = list(re.finditer(rb'6556[0-9]\s', content))
    raw_channels = []

    try:
        from sif_parser.sif_open import _open
    except ImportError:
        _open = None

    if _open is not None and len(matches) > 0:
        for m in matches:
            idx = m.start()
            stream = io.BytesIO(magic + content[idx:])
            try:
                tile, size, no_images, info = _open(stream)
                if not tile or len(tile) == 0:
                    continue
                offset = tile[0][2]
                stream.seek(offset)
                count = size[0] * size[1]
                arr = np.frombuffer(stream.read(count * 4), dtype='<f').reshape(no_images, size[1], size[0])
                raw_channels.append((arr, info))
            except Exception:
                pass

    n = len(raw_channels)
    named: Dict[str, np.ndarray] = {}
    ref_is_bg_corrected = False

    if n >= 4:
        named['transmittance'] = raw_channels[0][0]
        named['reference'] = raw_channels[1][0]
        named['dark'] = raw_channels[2][0]
        named['live'] = raw_channels[3][0]
        ref_dtype = str(raw_channels[1][1].get('DataType', '')).lower()
        if 'bg corrected' in ref_dtype or 'background corrected' in ref_dtype:
            ref_is_bg_corrected = True
    elif n == 3:
        named['transmittance'] = raw_channels[0][0]
        named['reference'] = raw_channels[1][0]
        named['live'] = raw_channels[2][0]
        ref_dtype = str(raw_channels[1][1].get('DataType', '')).lower()
        if 'bg corrected' in ref_dtype or 'background corrected' in ref_dtype:
            ref_is_bg_corrected = True
    elif n == 2:
        named['transmittance'] = raw_channels[0][0]
        named['live'] = raw_channels[1][0]
    elif n == 1:
        dtype = str(raw_channels[0][1].get('DataType', '')).lower()
        if 'trans' in dtype:
            named['transmittance'] = raw_channels[0][0]
        else:
            named['live'] = raw_channels[0][0]

    if return_details:
        return named, n, ref_is_bg_corrected
    return named, n


def read_sif_file(filepath: str, custom_calib_coeffs: Optional[List[float]] = None) -> SifSpectrum:
    """
    Lee un archivo .sif usando sif_parser con corrección crítica de calibración
    para matrices 2D multi-pixel, desempaquetado exhaustivo de todos los canales (Ruido, Ref, Live, Transmitancia)
    y detección automática de rol de archivo maestro (👑 Maestro si tiene los 4 canales).
    """
    if sif_parser is None:
        raise ImportError("El paquete 'sif-parser' no está instalado. Ejecute: pip install sif-parser")

    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"No se encontró el archivo: {filepath}")

    data, info = sif_parser.np_open(filepath)
    # data shape: (no_images, height, width)
    no_images, height, width = data.shape

    # 1. Extracción y corrección de calibración de longitud de onda
    wavelengths = _extract_wavelength_axis(info, width, custom_calib_coeffs)

    # 2. Extracción de metadatos completos
    metadata = _parse_metadata(filepath, info, data.shape)

    is_2d = (height > 1)
    base_name = os.path.basename(filepath)

    # Detección heurística de rol inicial
    name_lower = base_name.lower()
    dtype_str = str(metadata.data_type).lower()
    if "bg" in name_lower or "background" in name_lower or "dark" in name_lower:
        role = "bg"
    elif "ref" in name_lower or "reference" in name_lower or "lampara" in name_lower:
        role = "ref"
    elif "trans" in name_lower or "transmittance" in dtype_str:
        role = "transmittance_meas"
    else:
        role = "sample"

    # 3. Desempaquetado multi-canal
    channels, channels_count = {}, 1
    ref_is_bg_corr = False
    try:
        channels, channels_count, ref_is_bg_corr = parse_all_sif_channels(filepath, return_details=True)
    except Exception:
        try:
            channels, channels_count = parse_all_sif_channels(filepath)
        except Exception:
            pass

    if not channels:
        if "trans" in role or "transmittance" in dtype_str:
            channels = {"transmittance": data}
        else:
            channels = {"live": data}
        channels_count = 1

    is_master = (channels_count == 4)

    return SifSpectrum(
        raw_data=data,
        wavelengths=wavelengths,
        metadata=metadata,
        role=role,
        custom_name=os.path.splitext(base_name)[0],
        is_2d=is_2d,
        channels=channels,
        channels_count=channels_count,
        is_master=is_master,
        ref_is_bg_corrected=ref_is_bg_corr
    )


def _extract_wavelength_axis(info: dict, width: int, custom_coeffs: Optional[List[float]] = None) -> np.ndarray:
    """
    Calcula el eje de longitudes de onda en nanómetros para un ancho dado.
    Soluciona el error donde info['ImageLength'] descalibra las matrices 2D.
    """
    if custom_coeffs is not None and len(custom_coeffs) > 0:
        # custom_coeffs: orden descendente [a, b, c, d] para poly1d
        return np.poly1d(custom_coeffs)(np.arange(1, width + 1))

    # Verificar si el info contiene coeficientes de calibración
    calib_data = info.get('Calibration_data')
    if calib_data is not None:
        try:
            # Los coeficientes de Andor Solis se guardan en orden ascendente: a0 + a1*x + a2*x^2 + a3*x^3
            # np.poly1d requiere coeficientes en orden descendente, por lo que se usa np.flipud
            coefs = np.flipud(calib_data)
            wl = np.poly1d(coefs)(np.arange(1, width + 1))
            # Verificación de rango razonable de espectroscopía óptica (ej. 200 a 2500 nm)
            if 150.0 <= wl[0] <= 3000.0 and 150.0 <= wl[-1] <= 3000.0:
                return wl
        except Exception:
            pass

    # Fallback: Revisar si hay calibración por frame
    if 'Calibration_data_for_frame_1' in info:
        try:
            coefs = np.flipud(info['Calibration_data_for_frame_1'])
            return np.poly1d(coefs)(np.arange(1, width + 1))
        except Exception:
            pass

    # Fallback predeterminado si no hay calibración en el SIF: cuadrícula de píxeles
    return np.arange(width, dtype=np.float64)


def load_external_calibration_file(filepath: str, width: int) -> np.ndarray:
    """
    Carga un archivo de calibración de longitud de onda externo (.txt, .cal, .dat, Shamrock EEPROM).
    Soporta:
    1. Archivos INI / Shamrock EEPROM (como pyspectrum_calibration_last.txt con sección [DISPERSION_CUBICA_EEPROM]
       con coeff_a, coeff_b, coeff_c, coeff_d: lambda(p) = a + b*p + c*p^2 + d*p^3, p in [0, width-1]).
    2. Coeficientes en texto plano con pares clave=valor (coeff_a = ..., coeff_b = ...).
    3. Archivos de texto ASCII con 4 números: [a, b, c, d].
    4. Archivos tabulados de 2 columnas: [pixel, wavelength] (interpola a 0..width-1).
    5. Archivos tabulados de 1 columna con eje lambda directo (interpola a width si difiere).
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Archivo de calibración no encontrado: {filepath}")

    # 1. Intentar parsear como archivo INI / Shamrock EEPROM
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(filepath, encoding='utf-8')
        for sec in cfg.sections():
            sec_lower = sec.lower()
            if any(k in sec_lower for k in ["dispersion", "calibracion", "eeprom", "spectrometer", "shamrock"]):
                if 'coeff_a' in cfg[sec] and 'coeff_b' in cfg[sec]:
                    a = float(cfg[sec]['coeff_a'])
                    b = float(cfg[sec]['coeff_b'])
                    c = float(cfg[sec].get('coeff_c', 0.0))
                    d = float(cfg[sec].get('coeff_d', 0.0))
                    p = np.arange(width, dtype=np.float64)
                    return a + b * p + c * (p ** 2) + d * (p ** 3)
    except Exception:
        pass

    # 2. Intentar buscar patrones regex de coeff_a, coeff_b en texto plano
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    match_a = re.search(r'coeff_a\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
    match_b = re.search(r'coeff_b\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
    if match_a and match_b:
        a = float(match_a.group(1))
        b = float(match_b.group(1))
        c_m = re.search(r'coeff_c\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
        d_m = re.search(r'coeff_d\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', content, re.IGNORECASE)
        c = float(c_m.group(1)) if c_m else 0.0
        d = float(d_m.group(1)) if d_m else 0.0
        p = np.arange(width, dtype=np.float64)
        return a + b * p + c * (p ** 2) + d * (p ** 3)

    # 3. Intentar cargar como tabla numérica numpy
    try:
        data = np.loadtxt(filepath, comments=['#', ';', '['])
        if data.ndim == 1:
            if len(data) == 4:
                # 4 coeficientes [a, b, c, d]
                a, b, c, d = data
                p = np.arange(width, dtype=np.float64)
                return a + b * p + c * (p ** 2) + d * (p ** 3)
            elif len(data) == width:
                return data
            else:
                x_orig = np.linspace(0, 1, len(data))
                x_new = np.linspace(0, 1, width)
                return np.interp(x_new, x_orig, data)
        elif data.ndim == 2:
            pixels = data[:, 0]
            wls = data[:, 1]
            p_target = np.arange(width, dtype=np.float64)
            return np.interp(p_target, pixels, wls)
    except Exception as e:
        raise ValueError(f"No se pudo interpretar el archivo de calibración '{os.path.basename(filepath)}': {str(e)}")

    raise ValueError(f"Formato de calibración no reconocido en: {filepath}")


def compute_wavelength_uncertainty(wavelengths: np.ndarray,
                                   slit_width_um: float = 100.0,
                                   pixel_pitch_um: float = CCD_PIXEL_PITCH_UM,
                                   calib_uncertainty_nm: float = 0.08) -> np.ndarray:
    """
    Calcula la incertidumbre estándar de longitud de onda u_c(lambda) en nanómetros
    conforme al modelo metrológico del espectrómetro Shamrock 500i:
    - u(slit): Apertura física de ranura proyectada (distribución rectangular u = Delta_lambda / sqrt(12))
    - u(pixel): Discretización de píxeles del detector CCD (u = delta_lambda_px / sqrt(12))
    - u(calib): Error de calibración polinomial residual (típico 0.05 - 0.15 nm)

    u_c(lambda) = sqrt( u(slit)^2 + u(pixel)^2 + u(calib)^2 )
    """
    wl = np.asarray(wavelengths, dtype=np.float64)
    if len(wl) <= 1:
        return np.full_like(wl, calib_uncertainty_nm)

    # Dispersión local nm/pixel
    delta_lambda_px = np.abs(np.gradient(wl))

    # Ancho espectral de la ranura de entrada en la rejilla
    n_px_slit = max(1.0, float(slit_width_um) / float(pixel_pitch_um))
    delta_lambda_slit = n_px_slit * delta_lambda_px

    u_slit = delta_lambda_slit / np.sqrt(12.0)
    u_pixel = delta_lambda_px / np.sqrt(12.0)
    u_calib = float(calib_uncertainty_nm)

    u_c = np.sqrt(u_slit ** 2 + u_pixel ** 2 + u_calib ** 2)
    return u_c


def _parse_metadata(filepath: str, info: dict, shape: Tuple[int, ...]) -> SifMetadata:
    """Extrae metadatos estructurados del diccionario info de SIF y del nombre del archivo."""
    filename = os.path.basename(filepath)
    exp_time = float(info.get('ExposureTime', 0.05))

    # Búsqueda en nombre de archivo para parámetros experimentales
    # Ej: Fbin_hex_100umslit_50ms_nopol_pos_0.sif, oblicua_100umslit_1seg_176deg.sif
    slit_um = 100.0
    slit_match = re.search(r'(\d+)\s*(?:um|µm)?\s*slit', filename, re.IGNORECASE)
    if slit_match:
        slit_um = float(slit_match.group(1))

    # Tiempo de exposición en nombre si difiere o corrobora
    time_match = re.search(r'(\d+(?:\.\d+)?)\s*(ms|seg|s|sec)', filename, re.IGNORECASE)
    if time_match:
        val = float(time_match.group(1))
        unit = time_match.group(2).lower()
        if unit == 'ms':
            val_sec = val / 1000.0
        else:
            val_sec = val
        if exp_time == 0.0 or abs(exp_time - 0.05) < 1e-4:
            exp_time = val_sec

    # Ángulo de polarización
    pol_angle = None
    deg_match = re.search(r'(\d+(?:\.\d+)?)\s*deg', filename, re.IGNORECASE)
    if deg_match:
        pol_angle = float(deg_match.group(1))
    elif "nopol" in filename.lower():
        pol_angle = None

    em_gain = float(info.get('GainDAC', 0.0))
    if em_gain == 0.0:
        em_gain = float(info.get('GateGain', 0.0))

    data_type_raw = info.get('DataType', 'Counts')
    if isinstance(data_type_raw, bytes):
        data_type = data_type_raw.decode('utf-8', errors='ignore')
    else:
        data_type = str(data_type_raw)

    orig_fn = info.get('OriginalFilename', '')
    if isinstance(orig_fn, bytes):
        orig_fn = orig_fn.decode('utf-8', errors='ignore')

    detector_type = str(info.get('DetectorType', 'DU8285_VP'))
    if isinstance(detector_type, bytes):
        detector_type = detector_type.decode('utf-8', errors='ignore')

    return SifMetadata(
        filepath=filepath,
        filename=filename,
        experiment_time=int(info.get('ExperimentTime', 0)),
        exposure_time=exp_time,
        cycle_time=float(info.get('CycleTime', 0.0)),
        accumulated_cycles=int(info.get('AccumulatedCycles', 1)),
        detector_temp_c=float(info.get('DetectorTemperature', -65.0)),
        detector_type=detector_type,
        detector_dims=info.get('DetectorDimensions', (1004, 1002)),
        em_gain=em_gain,
        gate_gain=float(info.get('GateGain', 0.0)),
        gain_dac=float(info.get('GainDAC', 0.0)),
        spectrograph=str(info.get('spectrograph', 'SR500i')),
        grating_blaze_um=float(info.get('GratingBlaze', 0.0)) * 1e6 if info.get('GratingBlaze', 0.0) < 0.1 else float(info.get('GratingBlaze', 0.0)),
        slit_width_um=slit_um,
        xbin=int(info.get('xbin', 1)),
        ybin=int(info.get('ybin', 1)),
        num_frames=int(info.get('NumberOfFrames', 1)),
        num_subimages=int(info.get('NumberOfSubImages', 1)),
        shape=shape,
        data_type=data_type,
        polarization_angle_deg=pol_angle,
        original_filename=orig_fn,
        extra_info=info
    )


# ==============================================================================
# FILTROS ESPECTRALES Y DESPIKING
# ==============================================================================
def filter_savitzky_golay(y: np.ndarray, window_length: int = 15, polyorder: int = 3, deriv: int = 0) -> np.ndarray:
    """
    Aplica filtro de Savitzky-Golay preservando momentos espectrales y áreas de picos.
    Asegura ventana impar válida y menor que la longitud del vector.
    """
    y = np.asarray(y, dtype=np.float64)
    n = len(y)
    if n <= 3:
        return y.copy()

    w = max(3, int(window_length))
    if w % 2 == 0:
        w += 1
    if w >= n:
        w = n - 1 if (n - 1) % 2 != 0 else n - 2
    if w <= polyorder:
        w = polyorder + 2 if (polyorder + 2) % 2 != 0 else polyorder + 3
    if w >= n:
        return y.copy()

    return signal.savgol_filter(y, window_length=w, polyorder=polyorder, deriv=deriv, mode='interp')


def filter_fourier_lowpass(y: np.ndarray, cutoff_ratio: float = 0.05) -> np.ndarray:
    """
    Filtro pasa-bajos por Transformada Rápida de Fourier (FFT).
    cutoff_ratio: Fracción de frecuencias a conservar (0.001 a 0.5).
    Usa ventana suave de Butterworth para evitar oscilaciones de Gibbs en bordes.
    """
    y = np.asarray(y, dtype=np.float64)
    n = len(y)
    if n < 4:
        return y.copy()

    x = np.arange(n)
    p = np.polyfit([0, n - 1], [y[0], y[-1]], deg=1)
    baseline = np.polyval(p, x)
    detrended = y - baseline

    fft_vals = np.fft.rfft(detrended)
    freqs = np.fft.rfftfreq(n)

    cutoff = max(1e-4, min(0.5, float(cutoff_ratio)))
    order = 3
    transfer = 1.0 / (1.0 + (freqs / cutoff) ** (2 * order))

    filtered_fft = fft_vals * transfer
    filtered_y = np.fft.irfft(filtered_fft, n=n) + baseline
    return filtered_y


def filter_moving_average(y: np.ndarray, window_size: int = 5) -> np.ndarray:
    """Suavizado por Media Móvil uniforme con corrección de bordes."""
    y = np.asarray(y, dtype=np.float64)
    w = max(1, int(window_size))
    if w <= 1 or len(y) < w:
        return y.copy()
    kernel = np.ones(w, dtype=np.float64) / w
    return ndimage.convolve1d(y, kernel, mode='nearest')


def filter_despike_median(y: np.ndarray, threshold_sigma: float = 5.0, kernel_size: int = 5) -> np.ndarray:
    """
    Detecta y reemplaza rayos cósmicos puntuales usando la diferencia entre
    la señal y la mediana móvil local normalizada por el desvío MAD (Median Absolute Deviation).
    """
    y = np.asarray(y, dtype=np.float64)
    k = max(3, int(kernel_size))
    if k % 2 == 0:
        k += 1
    if len(y) < k:
        return y.copy()

    med = ndimage.median_filter(y, size=k, mode='nearest')
    diff = np.abs(y - med)
    mad = np.median(diff)
    if mad < 1e-9:
        sigma = np.std(diff)
    else:
        sigma = 1.4826 * mad

    if sigma < 1e-9:
        return y.copy()

    spikes = (diff > threshold_sigma * sigma) & (y > med)
    y_clean = y.copy()
    y_clean[spikes] = med[spikes]
    return y_clean


@dataclass
class NoiseProfile:
    """Perfil cuantitativo de ruido empírico caracterizado a partir de un espectro de Fondo (BG)."""
    mean_counts: float
    std_counts: float
    noise_std_spectral: np.ndarray    # sigma_BG(lambda) en cuentas
    noise_psd: np.ndarray             # Densidad espectral de potencia P_N(f)
    psd_freqs: np.ndarray             # Frecuencias espaciales normalizadas
    num_samples: int = 1
    description: str = ""


def characterize_background_noise(bg_spectrum: Union[np.ndarray, SifSpectrum]) -> NoiseProfile:
    """
    Caracteriza cuantitativamente el ruido empírico del detector a partir de un espectro de fondo (BG).
    Extrae:
    - Offset continuo térmico/bias
    - Desvío estándar espectral sigma_BG(lambda)
    - Densidad Espectral de Potencia (PSD) del ruido mediante periodograma / FFT
    """
    if isinstance(bg_spectrum, SifSpectrum):
        if bg_spectrum.is_2d:
            mat = bg_spectrum.raw_data[0].astype(np.float64)  # (height, width)
        else:
            mat = bg_spectrum.raw_data[0, 0, :].astype(np.float64).reshape(1, -1)
    elif isinstance(bg_spectrum, np.ndarray):
        if bg_spectrum.ndim == 1:
            mat = bg_spectrum.astype(np.float64).reshape(1, -1)
        elif bg_spectrum.ndim == 2:
            mat = bg_spectrum.astype(np.float64)
        elif bg_spectrum.ndim == 3:
            mat = bg_spectrum[0].astype(np.float64)
        else:
            raise ValueError(f"Dimensión de fondo no soportada: {bg_spectrum.ndim}")
    else:
        raise TypeError(f"Tipo no soportado para caracterizar fondo: {type(bg_spectrum)}")

    height, width = mat.shape
    mean_counts = float(np.mean(mat))
    std_counts = float(np.std(mat))

    if height > 1:
        # En matrices 2D, sigma_BG(lambda) es la dispersión vertical a lo largo de la ranura
        noise_std_spectral = np.std(mat, axis=0, ddof=1)
        # Ruido fluctuante sustraído el promedio vertical:
        mean_profile = np.mean(mat, axis=0)
        fluctuations = mat - mean_profile[np.newaxis, :]
        # Promedio de periodogramas sobre las filas
        ffts = [np.abs(np.fft.rfft(fluctuations[r, :])) ** 2 for r in range(height)]
        noise_psd = np.mean(ffts, axis=0) / float(width)
        psd_freqs = np.fft.rfftfreq(width)
    else:
        # En espectros 1D, sustraer línea base suave para aislar fluctuaciones de alta frecuencia
        row = mat[0]
        smoothed = filter_savitzky_golay(row, window_length=min(51, width - 1 if (width - 1) % 2 != 0 else width - 2), polyorder=2)
        fluct = row - smoothed
        w_loc = min(31, max(3, width // 4))
        if w_loc % 2 == 0:
            w_loc += 1
        sq_diff = fluct ** 2
        local_var = ndimage.uniform_filter1d(sq_diff, size=w_loc, mode='nearest')
        noise_std_spectral = np.sqrt(np.maximum(1e-9, local_var))
        noise_psd = (np.abs(np.fft.rfft(fluct)) ** 2) / float(width)
        psd_freqs = np.fft.rfftfreq(width)

    desc = f"Fondo: {mean_counts:.1f} cuentas, sigma={std_counts:.2f} ({height}x{width})"
    return NoiseProfile(
        mean_counts=mean_counts,
        std_counts=std_counts,
        noise_std_spectral=noise_std_spectral,
        noise_psd=noise_psd,
        psd_freqs=psd_freqs,
        num_samples=height,
        description=desc
    )


def filter_wiener_adaptive(y: np.ndarray,
                           noise_profile: NoiseProfile,
                           alpha: float = 1.0) -> np.ndarray:
    """
    Filtro de Wiener adaptativo en el dominio espectral calibrado con la PSD del fondo.
    H(f) = max(0, P_Y(f) - alpha * P_N(f)) / P_Y(f).
    Atenúa el ruido de alta frecuencia adaptativamente sin ensanchar artificialmente picos plasmónicos.
    """
    y = np.asarray(y, dtype=np.float64)
    n = len(y)
    if n < 8:
        return y.copy()

    # Sustraer línea base lineal temporal para evitar fugas en extremos
    x = np.arange(n)
    p = np.polyfit([0, n - 1], [y[0], y[-1]], deg=1)
    baseline = np.polyval(p, x)
    detrended = y - baseline

    fft_y = np.fft.rfft(detrended)
    psd_y = (np.abs(fft_y) ** 2) / float(n)

    # Adaptar o interpolar la PSD del ruido al tamaño actual
    psd_noise_ref = noise_profile.noise_psd
    if len(psd_noise_ref) != len(psd_y):
        freqs_orig = np.linspace(0, 0.5, len(psd_noise_ref))
        freqs_curr = np.linspace(0, 0.5, len(psd_y))
        psd_n = np.interp(freqs_curr, freqs_orig, psd_noise_ref)
    else:
        psd_n = psd_noise_ref.copy()

    psd_noise_scaled = float(alpha) * psd_n
    psd_signal = np.maximum(0.0, psd_y - psd_noise_scaled)

    # Función de transferencia H(f)
    with np.errstate(divide='ignore', invalid='ignore'):
        H = psd_signal / np.maximum(1e-12, psd_y)
        H[psd_y < 1e-12] = 0.0
        H = np.clip(H, 0.0, 1.0)

    filtered_fft = fft_y * H
    filtered_y = np.fft.irfft(filtered_fft, n=n) + baseline
    return filtered_y


def filter_despike_adaptive(y: np.ndarray,
                            noise_profile: NoiseProfile,
                            threshold_k: float = 4.0,
                            kernel_size: int = 5) -> np.ndarray:
    """
    Detecta y reemplaza rayos cósmicos utilizando la cota empírica del fondo:
    Spike detectado si: y(lambda) - mediana_local(lambda) > k * sigma_BG(lambda).
    """
    y = np.asarray(y, dtype=np.float64)
    k_size = max(3, int(kernel_size))
    if k_size % 2 == 0:
        k_size += 1

    if len(y) < k_size:
        return y.copy()

    med = ndimage.median_filter(y, size=k_size, mode='nearest')
    diff = y - med

    sigma_bg = noise_profile.noise_std_spectral
    if len(sigma_bg) != len(y):
        sigma_bg = np.interp(np.linspace(0, 1, len(y)), np.linspace(0, 1, len(sigma_bg)), sigma_bg)

    spikes = (diff > threshold_k * np.maximum(1e-6, sigma_bg))
    y_clean = y.copy()
    y_clean[spikes] = med[spikes]
    return y_clean


def apply_spectral_filter(y: np.ndarray,
                          filter_type: str = "none",
                          params: Optional[Dict] = None,
                          despike_first: bool = True,
                          noise_profile: Optional[NoiseProfile] = None) -> np.ndarray:
    """
    Aplica una tubería de filtrado flexible sobre un espectro 1D.
    filter_type: 'none', 'savgol', 'fourier', 'moving_average', 'wiener', 'despike_only'
    """
    if params is None:
        params = {}

    y_out = np.asarray(y, dtype=np.float64).copy()

    if despike_first and filter_type != "none":
        th = params.get('despike_sigma', 5.0)
        k = params.get('despike_kernel', 5)
        if noise_profile is not None:
            y_out = filter_despike_adaptive(y_out, noise_profile, threshold_k=th, kernel_size=k)
        else:
            y_out = filter_despike_median(y_out, threshold_sigma=th, kernel_size=k)

    if filter_type == "savgol":
        w = params.get('window_length', 15)
        p = params.get('polyorder', 3)
        y_out = filter_savitzky_golay(y_out, window_length=w, polyorder=p)
    elif filter_type == "fourier":
        c = params.get('cutoff_ratio', 0.05)
        y_out = filter_fourier_lowpass(y_out, cutoff_ratio=c)
    elif filter_type == "moving_average":
        w = params.get('window_size', 5)
        y_out = filter_moving_average(y_out, window_size=w)
    elif filter_type == "wiener":
        if noise_profile is not None:
            alpha = params.get('wiener_alpha', 1.0)
            y_out = filter_wiener_adaptive(y_out, noise_profile, alpha=alpha)
        else:
            w = params.get('window_length', 15)
            y_out = filter_savitzky_golay(y_out, window_length=w, polyorder=3)
    elif filter_type == "despike_only":
        th = params.get('despike_sigma', 5.0)
        k = params.get('despike_kernel', 5)
        if noise_profile is not None:
            y_out = filter_despike_adaptive(y_out, noise_profile, threshold_k=th, kernel_size=k)
        else:
            y_out = filter_despike_median(y_out, threshold_sigma=th, kernel_size=k)

    return y_out


def apply_spectral_filters_2d(matrix_2d: np.ndarray,
                              dark_matrix: Optional[np.ndarray] = None,
                              sub_dark: bool = False,
                              ref_is_bg_subtracted: bool = False,
                              despike: bool = False,
                              despike_sigma: float = 4.0,
                              noise_profile: Optional[NoiseProfile] = None,
                              wiener_adaptive: bool = False,
                              wiener_alpha: float = 1.0,
                              filter_type: str = "none",
                              filter_params: Optional[Dict] = None) -> np.ndarray:
    """
    Aplica la cadena completa de pre-acondicionamiento físico y filtrado espectral
    fila por fila sobre una matriz 2D (height, width) correspondiente a la dispersión
    espectral del detector CCD.
    Retorna una matriz 2D procesada con la misma forma (H, W).
    """
    if matrix_2d is None:
        return None

    mat = np.asarray(matrix_2d, dtype=np.float64).copy()
    while mat.ndim > 2 and mat.shape[0] == 1:
        mat = mat[0]

    if mat.ndim == 1:
        orig_1d = True
        mat = mat.reshape(1, -1)
    else:
        orig_1d = False

    h, w = mat.shape

    # 1. Resta de Ruido / Dark en 2D
    if sub_dark and not ref_is_bg_subtracted and dark_matrix is not None:
        d = np.asarray(dark_matrix, dtype=np.float64)
        while d.ndim > 2 and d.shape[0] == 1:
            d = d[0]
        if d.shape == mat.shape:
            mat = mat - d
        elif d.ndim == 1 and d.shape[0] == w:
            mat = mat - d[np.newaxis, :]
        elif d.ndim == 2 and d.shape[1] == w:
            d_1d = np.nanmean(d, axis=0)
            mat = mat - d_1d[np.newaxis, :]

    # 2. Procesamiento espectral fila por fila
    needs_row_proc = (despike or
                      (wiener_adaptive and noise_profile is not None) or
                      (filter_type not in ("none", "wiener")))
    if needs_row_proc:
        p = filter_params if filter_params is not None else {}
        for r in range(h):
            row = mat[r, :]
            if not np.any(np.isfinite(row)):
                continue

            # Despiking
            if despike:
                if noise_profile is not None:
                    row = filter_despike_adaptive(row, noise_profile, threshold_k=despike_sigma)
                else:
                    row = filter_despike_median(row, threshold_sigma=despike_sigma)

            # Filtro Wiener adaptativo
            if (wiener_adaptive or filter_type == "wiener") and noise_profile is not None:
                row = filter_wiener_adaptive(row, noise_profile, alpha=wiener_alpha)

            # Filtro espectral tradicional
            if filter_type not in ("none", "wiener"):
                row = apply_spectral_filter(row, filter_type=filter_type, params=p, despike_first=False)

            mat[r, :] = row

    return mat[0] if orig_1d else mat


# ==============================================================================
# REDUCCIÓN ESPACIAL (ROI) Y ESTADÍSTICA
# ==============================================================================
def spatial_roi_reduce(data_2d: np.ndarray,
                       y_min: int,
                       y_max: int,
                       method: str = "mean") -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Reduce una matriz 2D (height, width) en el rango de filas [y_min, y_max].
    Retorna:
    - profile: vector 1D (media o suma)
    - std_profile: desviación estándar espacial (píxel a píxel a lo largo de la ranura)
    - sem_profile: error estándar de la media (std / sqrt(Ny))
    """
    if data_2d.ndim == 3:
        data_2d = data_2d[0]  # Frame 0

    height, width = data_2d.shape
    y0 = max(0, min(int(y_min), height - 1))
    y1 = max(0, min(int(y_max), height - 1))
    if y0 > y1:
        y0, y1 = y1, y0

    roi_slice = data_2d[y0:y1 + 1, :]
    ny = roi_slice.shape[0]

    if ny <= 1:
        profile = roi_slice[0, :].astype(np.float64)
        std_profile = np.zeros(width, dtype=np.float64)
        sem_profile = np.zeros(width, dtype=np.float64)
        return profile, std_profile, sem_profile

    if method == "sum":
        profile = np.sum(roi_slice, axis=0, dtype=np.float64)
        std_profile = np.std(roi_slice, axis=0, ddof=1, dtype=np.float64) * np.sqrt(ny)
        sem_profile = std_profile / np.sqrt(ny)
    else:  # 'mean'
        profile = np.mean(roi_slice, axis=0, dtype=np.float64)
        std_profile = np.std(roi_slice, axis=0, ddof=1, dtype=np.float64)
        sem_profile = std_profile / np.sqrt(ny)

    return profile, std_profile, sem_profile


def set_average(spectra_list: List[np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Promedia una lista de espectros 1D del set.
    Retorna: (mean, std, sem)
    """
    if not spectra_list:
        raise ValueError("La lista de espectros para promediar está vacía")

    stack = np.array(spectra_list, dtype=np.float64)
    m = stack.shape[0]
    mean_spec = np.mean(stack, axis=0)
    if m <= 1:
        std_spec = np.zeros_like(mean_spec)
        sem_spec = np.zeros_like(mean_spec)
    else:
        std_spec = np.std(stack, axis=0, ddof=1)
        sem_spec = std_spec / np.sqrt(m)

    return mean_spec, std_spec, sem_spec


def roi_and_set_average(matrices_list: List[np.ndarray],
                        y_min: int,
                        y_max: int,
                        method: str = "mean") -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Combina la reducción de ROI y el conjunto de archivos del Set.
    Propaga la varianza intra-ROI junto con la dispersión inter-medición.
    """
    roi_means = []
    roi_sems = []
    for mat in matrices_list:
        p_mean, _, p_sem = spatial_roi_reduce(mat, y_min, y_max, method=method)
        roi_means.append(p_mean)
        roi_sems.append(p_sem)

    set_mean, set_std, _ = set_average(roi_means)
    m = len(matrices_list)

    # Varianza combinada total: varianza del set + promedio de varianzas de SEM intra-ROI
    intra_roi_var = np.mean([s ** 2 for s in roi_sems], axis=0)
    total_var = (set_std ** 2) + intra_roi_var
    total_std = np.sqrt(total_var)
    total_sem = total_std / np.sqrt(max(1, m))

    return set_mean, total_std, total_sem


# ==============================================================================
# MODELO DE ERRORES INSTRUMENTALES Y PROPAGACIÓN DE TRANSMITANCIA
# ==============================================================================
def estimate_photonic_noise(intensity: np.ndarray,
                            exposure_time_s: float = 0.05,
                            em_gain: float = 0.0,
                            read_noise_e: float = 6.0,
                            gain_electrons_per_count: float = 1.0) -> np.ndarray:
    """
    Modela la incertidumbre instrumental por píxel basada en la física de detectores CCD/EMCCD:
    - Ruido de disparo Poissoniano (Shot noise)
    - Factor de exceso de ruido EM (F^2 ≈ 2.0 si EM gain > 1)
    - Ruido de lectura del preamplificador (Read noise)
    """
    I = np.maximum(0.0, np.asarray(intensity, dtype=np.float64))
    photons_e = I * gain_electrons_per_count
    excess_noise_factor = 2.0 if em_gain > 1.0 else 1.0
    var_electrons = excess_noise_factor * photons_e + (read_noise_e ** 2)
    var_counts = var_electrons / (gain_electrons_per_count ** 2)
    return np.sqrt(np.maximum(1e-9, var_counts))


def compute_transmittance(signal_spec: np.ndarray,
                          ref_spec: np.ndarray,
                          bg_spec: Optional[np.ndarray] = None,
                          noise_threshold: float = 10.0,
                          in_percentage: bool = True) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calcula la transmitancia: T = (Signal - BG) / (Ref - BG)
    Retorna: (T, valid_mask)
    Aplica un Noise Gate para enmascarar divergencias asintóticas cuando Ref - BG < noise_threshold.
    """
    S = np.asarray(signal_spec, dtype=np.float64)
    R = np.asarray(ref_spec, dtype=np.float64)

    if bg_spec is not None:
        BG = np.asarray(bg_spec, dtype=np.float64)
    else:
        BG = np.zeros_like(S)

    net_signal = S - BG
    net_ref = R - BG

    valid_mask = (net_ref > noise_threshold)
    T = np.zeros_like(S)

    with np.errstate(divide='ignore', invalid='ignore'):
        T[valid_mask] = net_signal[valid_mask] / net_ref[valid_mask]
        T[~valid_mask] = np.nan

    if in_percentage:
        T = T * 100.0

    return T, valid_mask


def compute_transmittance_with_errors(signal_spec: np.ndarray,
                                      ref_spec: np.ndarray,
                                      bg_spec: Optional[np.ndarray] = None,
                                      sigma_s: Optional[np.ndarray] = None,
                                      sigma_r: Optional[np.ndarray] = None,
                                      sigma_bg: Optional[np.ndarray] = None,
                                      noise_threshold: float = 10.0,
                                      in_percentage: bool = True,
                                      ref_is_bg_subtracted: bool = False) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calcula la transmitancia y propaga analíticamente los errores considerando
    la covarianza por el término común de fondo (BG):
    sigma_T = |T| * sqrt((sigma_s^2 + sigma_bg^2)/(S-BG)^2 + (sigma_r^2 + sigma_bg^2)/(R-BG)^2 - 2*sigma_bg^2/((S-BG)*(R-BG)))
    Si ref_is_bg_subtracted=True, R ya tiene el fondo sustraído (como en Andor Solis Counts Bg Corrected).
    """
    S = np.asarray(signal_spec, dtype=np.float64)
    R = np.asarray(ref_spec, dtype=np.float64)
    BG = np.asarray(bg_spec, dtype=np.float64) if bg_spec is not None else np.zeros_like(S)

    if sigma_s is None:
        sigma_s = estimate_photonic_noise(S)
    if sigma_r is None:
        sigma_r = estimate_photonic_noise(R)
    if sigma_bg is None:
        sigma_bg = estimate_photonic_noise(BG) if bg_spec is not None else np.zeros_like(S)

    net_s = S - BG
    net_r = R if ref_is_bg_subtracted else (R - BG)
    valid_mask = (net_r > noise_threshold)

    T = np.zeros_like(S)
    sigma_T = np.zeros_like(S)

    with np.errstate(divide='ignore', invalid='ignore'):
        t_raw = net_s / net_r
        term_s = (sigma_s ** 2 + sigma_bg ** 2) / (np.maximum(1e-9, net_s) ** 2)
        if ref_is_bg_subtracted:
            term_r = (sigma_r ** 2) / (np.maximum(1e-9, net_r) ** 2)
            term_cov = 0.0
        else:
            term_r = (sigma_r ** 2 + sigma_bg ** 2) / (np.maximum(1e-9, net_r) ** 2)
            term_cov = -2.0 * (sigma_bg ** 2) / (np.maximum(1e-9, net_s) * np.maximum(1e-9, net_r))

        rel_var = term_s + term_r + term_cov
        rel_var = np.maximum(0.0, rel_var)
        s_t = np.abs(t_raw) * np.sqrt(rel_var)

        T[valid_mask] = t_raw[valid_mask]
        sigma_T[valid_mask] = s_t[valid_mask]
        T[~valid_mask] = np.nan
        sigma_T[~valid_mask] = np.nan

    if in_percentage:
        T = T * 100.0
        sigma_T = sigma_T * 100.0

    return T, sigma_T, valid_mask


def compute_extinction(transmittance: np.ndarray, sigma_t: Optional[np.ndarray] = None) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Calcula la Extinción / Absorbancia Óptica: A = -log10(T / 100)
    Propaga la incertidumbre: sigma_A = (1 / (ln(10) * T)) * sigma_T
    """
    T = np.asarray(transmittance, dtype=np.float64).copy()
    valid_t = T[np.isfinite(T)]
    mean_val = float(np.mean(valid_t)) if len(valid_t) > 0 else 0.0
    if mean_val > 1.5:
        T_norm = T / 100.0
        s_t_norm = (sigma_t / 100.0) if sigma_t is not None else None
    else:
        T_norm = T
        s_t_norm = sigma_t

    with np.errstate(divide='ignore', invalid='ignore'):
        T_safe = np.maximum(1e-6, T_norm)
        A = -np.log10(T_safe)
        A[T_norm <= 0.0] = np.nan

        sigma_A = None
        if s_t_norm is not None:
            sigma_A = (1.0 / (np.log(10.0) * T_safe)) * s_t_norm
            sigma_A[T_norm <= 0.0] = np.nan

    return A, sigma_A


def compute_residuals(t_meas: np.ndarray, t_calc: np.ndarray) -> np.ndarray:
    """Calcula la diferencia residual: Res = T_meas - T_calc."""
    return np.asarray(t_meas, dtype=np.float64) - np.asarray(t_calc, dtype=np.float64)


# ==============================================================================
# ALGORITMOS DUALES DE TRANSMITANCIA Y AJUSTE AVANZADO DE PICOS (FANO / LSPR)
# ==============================================================================
def compute_transmittance_dual_route(
    live: np.ndarray,
    ref: np.ndarray,
    dark: Optional[np.ndarray] = None,
    roi_ymin: Optional[int] = None,
    roi_ymax: Optional[int] = None,
    noise_gate: float = 0.0,
    in_percentage: bool = True,
    ref_is_bg_subtracted: bool = False
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calcula la transmitancia utilizando dos rutas metodológicas para datos 1D y 2D:
    - Ruta A: Cálculo pixel a pixel T(y, lambda) = (Live(y, lambda) - Dark(y, lambda)) / (Ref_eff(y, lambda)),
              seguido del promedio espacial sobre el ROI vertical: mean_{y in ROI}(T(y, lambda)).
    - Ruta B: Promedio espacial previo de cada matriz en el ROI vertical:
              mean_Live(lambda), mean_Ref(lambda), mean_Dark(lambda),
              seguido del cociente: (mean_Live - mean_Dark) / (mean_Ref_eff).
    
    Si ref_is_bg_subtracted=True, la matriz Ref ya posee el fondo sustraído (como en Andor Solis Bg Corrected),
    evitando la doble resta destructiva de Dark.
    
    Retorna:
    - t_route_a: ndarray (width,)
    - t_route_b: ndarray (width,)
    - valid_mask: ndarray bool (width,)
    """
    L = np.asarray(live, dtype=np.float64)
    R = np.asarray(ref, dtype=np.float64)
    while L.ndim > 2 and L.shape[0] == 1:
        L = L[0]
    while R.ndim > 2 and R.shape[0] == 1:
        R = R[0]

    if dark is not None:
        D = np.asarray(dark, dtype=np.float64)
        while D.ndim > 2 and D.shape[0] == 1:
            D = D[0]
        if D.ndim == 1 and L.ndim == 2:
            D = np.tile(D, (L.shape[0], 1))
        elif D.ndim == 2 and L.ndim == 1:
            D = np.nanmean(D, axis=0)
    else:
        D = np.zeros_like(L)

    if R.ndim == 1 and L.ndim == 2:
        R = np.tile(R, (L.shape[0], 1))
    elif R.ndim == 2 and L.ndim == 1:
        R = np.nanmean(R, axis=0)

    scale = 100.0 if in_percentage else 1.0

    # 1. Caso 1D
    if L.ndim == 1:
        net_l = L - D
        net_r = R if ref_is_bg_subtracted else (R - D)
        valid = (net_r > noise_gate)
        t = np.full_like(L, np.nan)
        with np.errstate(divide='ignore', invalid='ignore'):
            t[valid] = (net_l[valid] / net_r[valid]) * scale
        return t, t.copy(), valid

    # 2. Caso 2D (height, width)
    h, w = L.shape
    y0 = max(0, int(roi_ymin)) if roi_ymin is not None else 0
    y1 = min(h, int(roi_ymax)) if roi_ymax is not None else h
    if y1 <= y0:
        y0, y1 = 0, h

    L_roi = L[y0:y1, :]
    R_roi = R[y0:y1, :]
    D_roi = D[y0:y1, :] if D.ndim == 2 else D

    # Ruta A: T(y, lambda) pixel a pixel, luego promedio vertical
    net_l_2d = L_roi - D_roi
    net_r_2d = R_roi if ref_is_bg_subtracted else (R_roi - D_roi)
    mask_2d = (net_r_2d > noise_gate)
    t_2d = np.full_like(net_l_2d, np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        t_2d[mask_2d] = (net_l_2d[mask_2d] / net_r_2d[mask_2d]) * scale

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        t_route_a = np.nanmean(t_2d, axis=0)
        # Ruta B: Promedios espaciales verticales previos, luego división
        mean_l = np.nanmean(L_roi, axis=0)
        mean_r = np.nanmean(R_roi, axis=0)
        mean_d = np.nanmean(D_roi, axis=0) if D_roi.ndim == 2 else D_roi

    net_mean_l = mean_l - mean_d
    net_mean_r = mean_r if ref_is_bg_subtracted else (mean_r - mean_d)
    valid_b = (net_mean_r > noise_gate)
    t_route_b = np.full(w, np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        t_route_b[valid_b] = (net_mean_l[valid_b] / net_mean_r[valid_b]) * scale

    valid_mask = valid_b & np.isfinite(t_route_a) & np.isfinite(t_route_b)
    return t_route_a, t_route_b, valid_mask


def fit_peak_advanced(
    wavelengths: np.ndarray,
    signal_data: np.ndarray,
    roi_range: Optional[Tuple[float, float]] = None,
    model_type: str = "gaussian",
    slit_width_um: float = 100.0,
    pixel_pitch_um: float = CCD_PIXEL_PITCH_UM
) -> Dict[str, Any]:
    """
    Ajusta modelos de resonancia óptica (Gaussiano, Lorentziano, Fano) sobre un espectro
    restringido a un ROI espectral [lambda_min, lambda_max].
    
    Calcula incertidumbres estándar combinadas u_c para:
    - Centro de resonancia: lambda_peak +- u_c(lambda_peak)
    - Ancho a media altura: FWHM +- u_c(FWHM)
    
    u_c^2 = u_fit^2 + u_slit^2 + u_pixel^2
    donde:
    - u_slit = (n_px_slit * dispersion_px) / sqrt(12)
    - u_pixel = dispersion_px / sqrt(12)
    """
    wl = np.asarray(wavelengths, dtype=np.float64)
    sig = np.asarray(signal_data, dtype=np.float64)

    if roi_range is not None:
        lmin, lmax = min(roi_range), max(roi_range)
        mask = (wl >= lmin) & (wl <= lmax) & np.isfinite(sig)
    else:
        mask = np.isfinite(sig)

    if np.sum(mask) < 6:
        raise ValueError(f"Puntos insuficientes en el ROI para ajuste ({np.sum(mask)} puntos). Seleccione un rango mayor.")

    x_fit = wl[mask]
    y_fit = sig[mask]

    # Dispersión instrumental
    dispersion_px = np.mean(np.abs(np.gradient(x_fit)))
    n_px_slit = max(1.0, float(slit_width_um) / float(pixel_pitch_um))
    u_slit = (n_px_slit * dispersion_px) / np.sqrt(12.0)
    u_pixel = dispersion_px / np.sqrt(12.0)

    # Estimaciones iniciales
    c0_init = float(np.percentile(y_fit, 10))
    idx_max = int(np.argmax(y_fit))
    l0_init = float(x_fit[idx_max])
    amp_init = float(y_fit[idx_max] - c0_init)
    if amp_init <= 0:
        amp_init = 1.0

    fwhm_init = float((x_fit[-1] - x_fit[0]) / 4.0)
    fwhm_init = max(fwhm_init, dispersion_px * 2.0)

    model_lower = model_type.lower().strip()

    if "lorentz" in model_lower:
        # Lorentziano: f(x) = A / (1 + ((x - l0)/gamma)^2) + C0 + C1*(x - l0)
        # FWHM = 2*gamma
        def lorentz_func(x, l0, gamma, amp, c0, c1):
            g = np.maximum(1e-6, gamma)
            return amp / (1.0 + ((x - l0) / g) ** 2) + c0 + c1 * (x - l0)

        gamma_init = fwhm_init / 2.0
        p0 = [l0_init, gamma_init, amp_init, c0_init, 0.0]
        bounds = (
            [x_fit[0], dispersion_px * 0.2, 0.0, -1e6, -1e4],
            [x_fit[-1], (x_fit[-1] - x_fit[0]) * 2.0, 1e7, 1e6, 1e4]
        )
        popt, pcov = curve_fit(lorentz_func, x_fit, y_fit, p0=p0, bounds=bounds, maxfev=15000)
        perr = np.sqrt(np.maximum(0.0, np.diag(pcov)))

        l0_fit, gamma_fit, amp_fit, c0_fit, c1_fit = popt
        u_l0_fit = perr[0]
        fwhm_fit = 2.0 * gamma_fit
        u_fwhm_fit = 2.0 * perr[1]
        fit_model_callable = lambda x: lorentz_func(x, *popt)
        q_fit, u_q_fit = None, None

    elif "fano" in model_lower:
        # Resonancia de Fano: f(x) = A * ((q + eps)^2) / (1 + eps^2) + C0 + C1*(x - l0)
        # donde eps = 2*(x - l0) / Gamma, FWHM = Gamma
        def fano_func(x, l0, Gamma, q, amp, c0, c1):
            G = np.maximum(1e-6, Gamma)
            eps = 2.0 * (x - l0) / G
            return amp * ((q + eps) ** 2) / (1.0 + eps ** 2) + c0 + c1 * (x - l0)

        p0 = [l0_init, fwhm_init, -1.0, amp_init * 0.5, c0_init, 0.0]
        bounds = (
            [x_fit[0], dispersion_px * 0.2, -50.0, 0.0, -1e6, -1e4],
            [x_fit[-1], (x_fit[-1] - x_fit[0]) * 2.0, 50.0, 1e7, 1e6, 1e4]
        )
        popt, pcov = curve_fit(fano_func, x_fit, y_fit, p0=p0, bounds=bounds, maxfev=20000)
        perr = np.sqrt(np.maximum(0.0, np.diag(pcov)))

        l0_fit, Gamma_fit, q_fit, amp_fit, c0_fit, c1_fit = popt
        u_l0_fit = perr[0]
        fwhm_fit = Gamma_fit
        u_fwhm_fit = perr[1]
        u_q_fit = perr[2]
        fit_model_callable = lambda x: fano_func(x, *popt)

    else:
        # Gaussiano (por defecto): f(x) = A * exp(- (x - l0)^2 / (2*sigma^2)) + C0 + C1*(x - l0)
        # FWHM = 2 * sqrt(2*ln(2)) * sigma = 2.35482 * sigma
        def gauss_func(x, l0, sigma, amp, c0, c1):
            s = np.maximum(1e-6, sigma)
            return amp * np.exp(-0.5 * ((x - l0) / s) ** 2) + c0 + c1 * (x - l0)

        sigma_init = fwhm_init / 2.35482
        p0 = [l0_init, sigma_init, amp_init, c0_init, 0.0]
        bounds = (
            [x_fit[0], dispersion_px * 0.1, 0.0, -1e6, -1e4],
            [x_fit[-1], (x_fit[-1] - x_fit[0]), 1e7, 1e6, 1e4]
        )
        popt, pcov = curve_fit(gauss_func, x_fit, y_fit, p0=p0, bounds=bounds, maxfev=15000)
        perr = np.sqrt(np.maximum(0.0, np.diag(pcov)))

        l0_fit, sigma_fit, amp_fit, c0_fit, c1_fit = popt
        u_l0_fit = perr[0]
        fwhm_fit = 2.35482 * sigma_fit
        u_fwhm_fit = 2.35482 * perr[1]
        fit_model_callable = lambda x: gauss_func(x, *popt)
        q_fit, u_q_fit = None, None

    # Incertidumbre combinada metrológica (GUM)
    u_c_l0 = float(np.sqrt(u_l0_fit ** 2 + u_slit ** 2 + u_pixel ** 2))
    u_c_fwhm = float(np.sqrt(u_fwhm_fit ** 2 + u_slit ** 2 + u_pixel ** 2))

    # Curvas de ajuste y residuos
    y_pred = fit_model_callable(x_fit)
    residuals = y_fit - y_pred

    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y_fit - np.mean(y_fit)) ** 2))
    r_squared = float(1.0 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0

    # Curva suave de alta resolución para graficado
    x_dense = np.linspace(x_fit[0], x_fit[-1], 600)
    y_dense = fit_model_callable(x_dense)

    return {
        "model": model_lower,
        "peak_center": float(l0_fit),
        "u_peak_center_fit": float(u_l0_fit),
        "u_peak_center_combined": u_c_l0,
        "fwhm": float(fwhm_fit),
        "u_fwhm_fit": float(u_fwhm_fit),
        "u_fwhm_combined": u_c_fwhm,
        "amplitude": float(amp_fit),
        "q_factor": float(q_fit) if q_fit is not None else None,
        "u_q_factor": float(u_q_fit) if u_q_fit is not None else None,
        "baseline_offset": float(c0_fit),
        "baseline_slope": float(c1_fit),
        "r_squared": r_squared,
        "u_slit": float(u_slit),
        "u_pixel": float(u_pixel),
        "fit_x": x_fit,
        "fit_y": y_fit,
        "y_pred": y_pred,
        "residuals": residuals,
        "x_dense": x_dense,
        "y_dense": y_dense
    }


# ==============================================================================
# EXPORTADOR DE DATOS
# ==============================================================================
def export_spectrum_txt(filepath: str,
                        wavelengths: np.ndarray,
                        columns: Dict[str, np.ndarray],
                        metadata_header: Optional[Dict[str, str]] = None,
                        delimiter: str = "\t") -> None:
    """
    Exporta datos espectrales en formato .dat / .txt / .csv con encabezados científicos comentados
    compatibles directamente con Origin, QtiPlot, pandas y np.loadtxt(..., comments='#').
    """
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    col_names = ["Wavelength_nm"] + list(columns.keys())
    data_arrays = [wavelengths] + [columns[k] for k in columns.keys()]
    matrix = np.column_stack(data_arrays)

    lines = []
    lines.append("# ==============================================================================")
    lines.append("# PyPrinting 3.0 -- EXPORTACION DE ESPECTROSCOPIA OPTICA (Andor Solis SIF)")
    lines.append("# ==============================================================================")
    if metadata_header:
        for k, v in metadata_header.items():
            lines.append(f"# {k}: {v}")
        lines.append("# ------------------------------------------------------------------------------")

    # Fila de nombres de columnas
    header_line = "# " + delimiter.join(col_names)
    lines.append(header_line)

    with open(filepath, 'w', encoding='utf-8', errors='replace') as f:
        f.write("\n".join(lines) + "\n")
        fmt = "%.4f" + (delimiter + "%.6e") * len(columns)
        np.savetxt(f, matrix, fmt=fmt, delimiter=delimiter)
