"""Latencia escalón -> decisión, sin ruido, fase aleatoria (400 ensayos por caso).
Criterio modo 1 (c_rel) de measurements.py con hold_counter >= N_hold.
I_new = media de los últimos M puntos; I_old = media de M2 puntos que terminan G puntos antes de I_new.
Producción (7f5d10a): punto = ráfaga de 1 ms al final de un tick de T; G = 0.
E: punto = media de un bloque de T_b (100 % de las muestras).
"""
import numpy as np

rng = np.random.default_rng(1)


def decide(pts, M, M2, G, u, n_hold):
    c = np.concatenate([[0.0], np.cumsum(pts)])
    hold = 0
    for n in range(M + G + M2, len(pts) + 1):
        I_new = (c[n] - c[n - M]) / M
        I_old = (c[n - M - G] - c[n - M - G - M2]) / M2
        if I_new > u * I_old:
            hold += 1
            if hold >= n_hold:
                return n
        else:
            hold = 0
    return None


def run(r, T, M, M2, G=0, u=1.5, n_hold=3, burst=None, trials=400, span=2.0):
    out = []
    npts = int(span / T) + M + M2 + G + 5
    for _ in range(trials):
        t0 = (M + M2 + G + 2) * T + rng.uniform(0, T)
        ends = np.arange(1, npts + 1) * T
        w = burst if burst else T
        frac = np.clip((ends - t0) / w, 0, 1)
        n = decide(1.0 + (r - 1) * frac, M, M2, G, u, n_hold)
        out.append(ends[n - 1] - t0 if n else np.nan)
    a = np.array(out)
    if np.all(np.isnan(a)):
        return "nunca dispara"
    a = a[~np.isnan(a)] * 1e3
    return f"mediana {np.median(a):5.0f} ms · p95 {np.percentile(a, 95):5.0f} · máx {a.max():5.0f}"


cases = [
    ("producción, tick 47 ms, M=M2=10, N_hold 3", dict(T=0.047, M=10, M2=10, burst=0.001)),
    ("E 10 ms, Wn 20, Wo 100, G 0, N_hold 3", dict(T=0.010, M=2, M2=10, G=0)),
    ("E 10 ms, Wn 20, Wo 100, G 40, N_hold 3", dict(T=0.010, M=2, M2=10, G=4)),
    ("E 10 ms, Wn 20, Wo 100, G 40, N_hold 1", dict(T=0.010, M=2, M2=10, G=4, n_hold=1)),
    ("E 10 ms, Wn 40, Wo 100, G 40, N_hold 3", dict(T=0.010, M=4, M2=10, G=4)),
    ("E 20 ms, Wn 20, Wo 100, G 40, N_hold 2", dict(T=0.020, M=1, M2=5, G=2, n_hold=2)),
]
for r in (2.0, 1.6, 1.4):
    print(f"r = {r}")
    for name, kw in cases:
        print(f"  {name:45s}: {run(r, **kw)}")
print("umbral 1.3 (r = 1.4):")
for name, kw in cases:
    print(f"  {name:45s}: {run(1.4, u=1.3, **kw)}")
