"""Complementos: curvas finas de detección, falsas alarmas de ruido en nodos de 40 s, T_b = 20 ms, escalón negativo."""
import numpy as np
import c01_criterion_sim as S

S.RNG = np.random.default_rng(7)

P1 = dict(T_b=10, W_new=20, W_old=200, u=1.2, tau_hold=20, freeze=True)
P1_20 = dict(T_b=20, W_new=20, W_old=200, u=1.2, tau_hold=20, freeze=True)
P2 = dict(T_b=10, W_new=40, W_old=400, u=1.25, tau_hold=60, freeze=True)
P0 = dict(T_b=10, W_new=470, W_old=470, u=1.5, tau_hold=90, freeze=False)
CUR = dict(M=10, M2=10, u=1.5, n_hold=3)

import sys
part = sys.argv[1] if len(sys.argv) > 1 else "all"

if part in ("curve", "all"):
    print("== Curva de detección P_det(r), sigma 1 % y 2 % ==")
    for sig in (0.01, 0.02):
        row = []
        for r in (1.56, 1.57, 1.58, 1.59, 1.60, 1.62, 1.65):
            row.append(f"{r}:{S.step_experiment('tick', r, sigma=sig, n=400, **CUR)['P']:.2f}")
        print(f"ACTUAL  sigma={sig}: " + " ".join(row))
        row = []
        for r in (1.54, 1.55, 1.56, 1.57, 1.58, 1.60):
            row.append(f"{r}:{S.step_experiment('block', r, sigma=sig, n=400, **P0)['P']:.2f}")
        print(f"P0(470/470/90) sigma={sig}: " + " ".join(row))
        row = []
        for r in (1.18, 1.19, 1.20, 1.21, 1.22, 1.23, 1.25):
            row.append(f"{r}:{S.step_experiment('block', r, sigma=sig, n=400, **P1)['P']:.2f}")
        print(f"P1 sigma={sig}: " + " ".join(row))
    print("== P0 (470/470/90) latencias, para comparar con ACTUAL ==")
    for r in (1.6, 1.8, 2.0):
        s = S.step_experiment('block', r, sigma=0.02, n=600, **P0)
        print(f"r={r}: P={s['P']:.2f} med={s['med']:.0f} p95={s['p95']:.0f}")
    print("== P1 con T_b = 20 ms (rechazo de 50 Hz en el bloque) ==")
    for r in (1.4, 1.5, 2.0):
        s = S.step_experiment('block', r, sigma=0.02, n=600, **P1_20)
        print(f"r={r}: P={s['P']:.2f} med={s['med']:.0f} p95={s['p95']:.0f}")

if part in ("fa", "all"):
    print("== Falsas alarmas por ruido en un nodo de 40 s sin evento (fracción de nodos que paran) ==")
    n_bins = 40000
    for label, sig, sc in (("blanco 2 %", 0.02, 0.0), ("blanco 2 % + OU 2 % (tau 100 ms)", 0.02, 0.02),
                           ("blanco 2 % + OU 5 % (tau 100 ms)", 0.02, 0.05)):
        n = 100
        lvl = np.ones((n, n_bins))
        x = S.add_noise(lvl, sig, sigma_c=sc, tau_c=100.0)
        t_s = np.full(n, 1e9)                       # evento que nunca llega: toda parada es falsa alarma
        out = []
        for nm, model, kw in (("ACTUAL", "tick", CUR), ("P0", "block", P0), ("P1", "block", P1), ("P2", "block", P2)):
            lat = S.run_tick(x, t_s, **kw) if model == "tick" else S.run_block(x, t_s, **kw)
            out.append(f"{nm}: {np.isfinite(lat).mean():.2f}")
        print(f"{label}: " + " | ".join(out))

if part in ("neg", "all"):
    print("== Escalón negativo, criterio con signo s = -1 (R < 1/u) ==")
    for nm, kw in (("P1(-)", dict(P1, sign=-1)), ("P2(-)", dict(P2, sign=-1))):
        row = []
        for r in (0.9, 0.8, 0.76, 0.7, 0.6):
            s = S.step_experiment('block', r, sigma=0.02, n=400, **kw)
            row.append(f"r={r}: P={s['P']:.2f} med={s['med']:.0f}")
        print(nm + ": " + " | ".join(row))
    print("== Caída transitoria tipo Martínez Fig. 3.6b (r_p = 0.76) vs D, criterio negativo ==")
    for nm, kw in (("P1(-)", dict(P1, sign=-1)), ("P2(-)", dict(P2, sign=-1)),
                   ("P0(-) 470/470 u=1/0.667 hold 90", dict(P0, sign=-1))):
        row = []
        for D in (10, 50, 100, 300, 500):
            row.append(f"{D}:{S.pulse_experiment('block', 0.76, D, n=300, **kw):.2f}")
        print(nm + ": " + " ".join(row))
