"""Latencia del criterio (escalón -> decisión), sin ruido, fase aleatoria.
Modelo del criterio de measurements.py modo 1 (c_rel) con hold_counter >= N_hold.
Producción (7f5d10a): tick = 47 ms, cada punto = ráfaga de 1 ms al final del tick, M = M2 = 10 puntos.
E: bloques de T_b, cada punto = media del bloque (100 % de muestras), ventanas en bloques.
"""
import numpy as np

rng = np.random.default_rng(1)


def decide(points, M, M2, u, n_hold):
    hold = 0
    for n in range(1, len(points) + 1):
        x = points[:n]
        if n < M + M2:
            continue  # arranque: la base todavía no está completa (se asume nodo largo)
        I_new = x[n - M:n].mean()
        I_old = x[n - M - M2:n - M].mean()
        cond = I_old > 0 and I_new > u * I_old
        hold = hold + 1 if cond else 0
        if hold >= n_hold:
            return n
    return None


def prod(r, u=1.5, n_hold=3, T=0.047, burst=0.001, M=10, M2=10, trials=2000):
    out = []
    for _ in range(trials):
        t_step = 3.0 + rng.uniform(0, T)
        ends = np.arange(1, 200) * T  # fin de cada tick
        # ráfaga de 1 ms justo antes del fin de tick: fracción post-escalón
        frac = np.clip((ends - t_step) / burst, 0, 1)
        pts = 1.0 + (r - 1) * frac
        n = decide(pts, M, M2, u, n_hold)
        out.append(ends[n - 1] - t_step if n else np.nan)
    return np.array(out)


def e_mode(r, u=1.5, n_hold=3, T_b=0.010, W_new=2, W_old=10, trials=2000):
    out = []
    for _ in range(trials):
        t_step = 3.0 + rng.uniform(0, T_b)
        ends = np.arange(1, 1000) * T_b
        frac = np.clip((ends - t_step) / T_b, 0, 1)  # fracción del bloque después del escalón
        pts = 1.0 + (r - 1) * frac
        n = decide(pts, W_new, W_old, u, n_hold)
        out.append(ends[n - 1] - t_step if n else np.nan)
    return np.array(out)


def stats(a):
    a = a[~np.isnan(a)] * 1e3
    if a.size == 0:
        return "nunca dispara"
    return f"mediana {np.median(a):6.1f} ms  p95 {np.percentile(a,95):6.1f}  máx {a.max():6.1f}"


for r in (2.0, 1.6, 1.4):
    print(f"r={r}")
    print("  producción 47 ms, M=M2=10, u=1.5, N_hold=3 :", stats(prod(r)))
    print("  producción 35 ms (Precise)              :", stats(prod(r, T=0.035)))
    print("  E 10 ms, W_new=20 ms, W_old=100 ms, N_hold=3:", stats(e_mode(r)))
    print("  E 10 ms, W_new=20 ms, W_old=100 ms, N_hold=1:", stats(e_mode(r, n_hold=1)))
    print("  E 10 ms, W_new=40 ms, W_old=100 ms, N_hold=3:", stats(e_mode(r, W_new=4)))
    print("  E 20 ms, W_new=20 ms, W_old=100 ms, N_hold=2:", stats(e_mode(r, T_b=0.020, W_new=1, W_old=5, n_hold=2)))
    print("  E con ventanas de hoy en ms (470/470, hold 3):", stats(e_mode(r, W_new=47, W_old=47)))
