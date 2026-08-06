# -*- coding: utf-8 -*-
"""
psf.py — Funciones de análisis PSF y detección de partículas
PyPrinting — UNSAM Nanofotónica

Renombrado de PSF_pp.py. Sin cambios funcionales.
Importar: from psf import center_of_mass, center_of_gauss2D, ...
"""
import numpy as np
from scipy.optimize import curve_fit
from skimage.feature import peak_local_max
from scipy import ndimage


def center_of_mass(image: np.ndarray):
    com = ndimage.measurements.center_of_mass(image)
    yo, xo = np.around(com, 3)
    return xo, yo


def gaussian2D(grid, amplitude, x0, y0, σ_x, σ_y, offset, theta=0):
    x, y = grid
    x0, y0 = float(x0), float(y0)
    a = (np.cos(theta)**2)/(2*σ_x**2) + (np.sin(theta)**2)/(2*σ_y**2)
    b = -(np.sin(2*theta))/(4*σ_x**2) + (np.sin(2*theta))/(4*σ_y**2)
    c = (np.sin(theta)**2)/(2*σ_x**2) + (np.cos(theta)**2)/(2*σ_y**2)
    G = offset + amplitude * np.exp(
        -(a*((x-x0)**2) + 2*b*(x-x0)*(y-y0) + c*((y-y0)**2)))
    return G.ravel()


def center_of_gauss2D(image: np.ndarray, xo: float, yo: float):
    Nx, Ny = image.shape
    x = np.arange(-Nx/2 + 0.5, Nx/2)
    y = np.arange(-Ny/2 + 0.5, Ny/2)
    Mx, My = np.meshgrid(x, y)
    initial_sigma = [2, 2]
    initial_guess = [1, xo + x[0], yo + y[0],
                     initial_sigma[0], initial_sigma[1], 0]
    bounds = ([0, x[0],  y[0],  0, 0, 0],
              [1, x[-1], y[-1], 4*initial_sigma[0], 4*initial_sigma[0], 1])
    popt, _ = curve_fit(gaussian2D, (Mx, My), image.ravel(),
                        p0=initial_guess, bounds=bounds)
    popt = np.around(popt, 3)
    return popt[1] - x[0], popt[2] - y[0]


def donut2D(grid, amplitude, x0, y0, σ_x, σ_y, offset):
    x, y = grid
    x0, y0 = float(x0), float(y0)
    r2 = ((x - x0)**2) / (2 * σ_x**2) + ((y - y0)**2) / (2 * σ_y**2)
    D = offset + amplitude * r2 * np.exp(-r2)
    return D.ravel()


def center_of_donut2D(image: np.ndarray, xo: float, yo: float):
    Nx, Ny = image.shape
    x = np.arange(-Nx/2 + 0.5, Nx/2)
    y = np.arange(-Ny/2 + 0.5, Ny/2)
    Mx, My = np.meshgrid(x, y)
    initial_sigma = [2.0, 2.0]
    initial_guess = [1.0, xo + x[0], yo + y[0],
                     initial_sigma[0], initial_sigma[1], 0.0]
    bounds = ([0.0, x[0],  y[0],  0.1, 0.1, 0.0],
              [5.0, x[-1], y[-1], 10.0, 10.0, 1.0])
    try:
        popt, _ = curve_fit(donut2D, (Mx, My), image.ravel(),
                            p0=initial_guess, bounds=bounds)
        popt = np.around(popt, 3)
        return popt[1] - x[0], popt[2] - y[0]
    except Exception as e:
        print(f"[PSF] Error en fit Donut 2D: {e}, fallback a center of mass")
        return xo, yo


def two_gaussian2D(grid, amplitude, x0, y0, σ_x, σ_y, offset,
                   amplitude1, x1, y1, theta=0):
    x, y = grid
    x0, y0, x1, y1 = float(x0), float(y0), float(x1), float(y1)
    a = (np.cos(theta)**2)/(2*σ_x**2) + (np.sin(theta)**2)/(2*σ_y**2)
    b = -(np.sin(2*theta))/(4*σ_x**2) + (np.sin(2*theta))/(4*σ_y**2)
    c = (np.sin(theta)**2)/(2*σ_x**2) + (np.cos(theta)**2)/(2*σ_y**2)
    G0 = amplitude  * np.exp(-(a*((x-x0)**2) + 2*b*(x-x0)*(y-y0) + c*((y-y0)**2)))
    G1 = amplitude1 * np.exp(-(a*((x-x1)**2) + 2*b*(x-x1)*(y-y1) + c*((y-y1)**2)))
    return (offset + G0 + G1).ravel()


def two_centers_of_gauss2D(image: np.ndarray,
                            x1: float, y1: float,
                            x2: float, y2: float):
    Nx, Ny = image.shape
    x = np.arange(-Nx/2 + 0.5, Nx/2)
    y = np.arange(-Nx/2 + 0.5, Ny/2)
    Mx, My = np.meshgrid(x, y)
    s = [2, 2]
    bounds = ([0, x[0], y[0], 0, 0, 0, 0, x[0], y[0]],
              [1, x[-1], y[-1], 4*s[0], 4*s[0], 1, 1, x[-1], y[-1]])
    ig = [1, x1+x[0], y1+y[0], s[0], s[1], 0, 1, x2+x[0], y2+y[0]]
    popt, _ = curve_fit(two_gaussian2D, (Mx, My), image.ravel(),
                        p0=ig, bounds=bounds)
    popt = np.around(popt, 3)
    return (popt[1]-x[0], popt[2]-y[0],
            popt[7]-x[0], popt[8]-y[0])


def find_two_centers(image: np.ndarray):
    axe_x, prof_x, axe_y, prof_y = _curve_gauss(image)
    ix, ax, px = _find_peaks(axe_x, prof_x, 0.24, 2)
    iy, ay, py = _find_peaks(axe_y, prof_y, 0.24, 2)

    nx, ny = len(ix), len(iy)
    if   nx == 2 and ny == 1: p1=(ix[1][0],iy[0][0]); p2=(ix[0][0],iy[0][0])
    elif nx == 1 and ny == 2: p1=(ix[0][0],iy[1][0]); p2=(ix[0][0],iy[0][0])
    elif nx == 2 and ny == 2: p1=(ix[1][0],iy[0][0]); p2=(ix[0][0],iy[1][0])
    else:                      p1=(ix[0][0],iy[0][0]); p2=p1

    return p1[0], p1[1], p2[0], p2[1]


def _curve_gauss(image: np.ndarray):
    Nx, Ny = image.shape
    return (np.arange(-Nx/2 + 0.5, Nx/2), np.mean(image, axis=0),
            np.arange(-Ny/2 + 0.5, Ny/2), np.mean(image, axis=1))


def _find_peaks(x, y, threshold_rel, number):
    idx = peak_local_max(y, min_distance=1,
                         threshold_rel=threshold_rel,
                         num_peaks=number)
    return idx, x[idx], y[idx]


def extract_psf_kernel(image: np.ndarray, center_x: float, center_y: float, radius_px: int = 15) -> np.ndarray:
    """
    Extrae una sub-matriz de PSF centrada en (center_x, center_y) con radio radius_px y la normaliza a suma = 1.0.
    """
    if image.ndim == 3:
        image = np.mean(image, axis=2)
    image = image.astype(float)
    H, W = image.shape
    r = int(radius_px)
    cx, cy = int(round(center_x)), int(round(center_y))

    x0, x1 = max(0, cx - r), min(W, cx + r + 1)
    y0, y1 = max(0, cy - r), min(H, cy + r + 1)

    crop = image[y0:y1, x0:x1]
    crop = crop - np.min(crop) # Remover offset de fondo
    total = np.sum(crop)
    if total > 0:
        crop = crop / total
    else:
        crop = np.ones_like(crop) / crop.size
    return crop


def richardson_lucy_deconv(image: np.ndarray, psf_kernel: np.ndarray, num_iter: int = 10, clip: bool = True) -> np.ndarray:
    """
    Deconvolución iterativa de Richardson-Lucy en 2D acelerada por FFT.
    image: Matriz 2D o 3D (RGB)
    psf_kernel: Matriz 2D de la PSF (normalizada a suma 1)
    num_iter: Número de iteraciones (0 a 100). Si num_iter == 0, devuelve la imagen original.
    """
    if num_iter <= 0 or psf_kernel is None or psf_kernel.size == 0:
        return image

    is_rgb = (image.ndim == 3 and image.shape[2] in (3, 4))
    if is_rgb:
        channels = [image[:, :, c].astype(float) for c in range(image.shape[2])]
        deconv_channels = [_richardson_lucy_2d(c, psf_kernel, num_iter, clip) for c in range(min(3, image.shape[2]))]
        res = np.stack(deconv_channels, axis=-1)
        if image.shape[2] == 4:
            res = np.dstack([res, image[:, :, 3]])
        return res.astype(image.dtype)
    else:
        return _richardson_lucy_2d(image.astype(float), psf_kernel, num_iter, clip).astype(image.dtype)


def _richardson_lucy_2d(img2d: np.ndarray, psf: np.ndarray, num_iter: int, clip: bool = True) -> np.ndarray:
    from scipy.signal import fftconvolve

    psf_sum = np.sum(psf)
    if psf_sum > 0:
        psf = psf / psf_sum
    psf_mirror = np.flip(psf)

    img_min = float(np.min(img2d))
    img_max = float(np.max(img2d))
    if img_max == img_min:
        return img2d

    norm_img = img2d.astype(float)
    estimate = norm_img.copy()

    for _ in range(num_iter):
        relative_blur = fftconvolve(estimate, psf, mode='same')
        relative_blur = np.where(relative_blur < 1e-12, 1e-12, relative_blur)
        ratio = norm_img / relative_blur
        correction = fftconvolve(ratio, psf_mirror, mode='same')
        estimate *= correction

    if clip:
        estimate = np.clip(estimate, img_min, img_max)

    return estimate
