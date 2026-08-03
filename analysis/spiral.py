# -*- coding: utf-8 -*-
"""
spiral.py — Utilidades de matrices en espiral
PyPrinting — UNSAM Nanofotónica

Renombrado de matrix_spiral_pp.py. Sin cambios funcionales.
Importar: from spiral import to_spiral, from_spiral, matrix_xy
"""
import numpy as np


def _spiral_cw(A: np.ndarray) -> np.ndarray:
    A = np.array(A)
    out = []
    while A.size:
        out.append(A[0])
        A = A[1:].T[::-1]
    return np.concatenate(out)


def _spiral_ccw(A: np.ndarray) -> np.ndarray:
    A = np.array(A)
    out = []
    while A.size:
        out.append(A[0][::-1])
        A = A[1:][::-1].T
    return np.concatenate(out)


def _base_spiral(nrow: int, ncol: int, clock_type: str) -> np.ndarray:
    base = np.arange(nrow * ncol).reshape(nrow, ncol)
    if clock_type == "cw":
        return _spiral_cw(base)[::-1]
    return _spiral_ccw(base)[::-1]


def to_spiral(A, clock_type: str = "cw") -> np.ndarray:
    A = np.array(A)
    B = np.empty_like(A)
    B.flat[_base_spiral(*A.shape, clock_type)] = A.flat
    return B


def from_spiral(A, clock_type: str = "cw") -> np.ndarray:
    A = np.array(A)
    return A.flat[_base_spiral(*A.shape, clock_type)].reshape(A.shape)


def matrix_xy(xo: float, yo: float, rango: float, n: int):
    x = np.linspace(xo - rango/2, xo + rango/2, n)
    y = np.linspace(yo - rango/2, yo + rango/2, n)
    return [x, y]
