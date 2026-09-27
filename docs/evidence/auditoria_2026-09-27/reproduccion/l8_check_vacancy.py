"""L8 audit: numerical check of the Wilson-intercept vacancy estimator (CAT-308 §4.3, code L1178-1197)."""
import sys, os
sys.dont_write_bytecode = True
REPO = r"C:\Users\josel\Documents\Obsidian_Vault\printing3"
sys.path.insert(0, REPO)
import numpy as np
from core.lattice_disorder import analyze_reciprocal_space_2d, compute_analytical_bragg_relations

a = 450.0
n = 30
rng = np.random.default_rng(1)
gx = (np.arange(n) - (n - 1) / 2) * a
X0, Y0 = np.meshgrid(gx, gx)
x0, y0 = X0.ravel(), Y0.ravel()
for p in (0.0, 0.2, 0.4):
    for sig in (10.0, 20.0):
        pe_det, pe_tot, s21, sw = [], [], [], []
        for rep in range(3):
            keep = rng.uniform(size=x0.size) >= p
            x = x0[keep] + rng.normal(0, sig, keep.sum())
            y = y0[keep] + rng.normal(0, sig, keep.sum())
            res = analyze_reciprocal_space_2d(x, y, a_nominal=a, n_bins=256)
            r_det = compute_analytical_bragg_relations(res, a_nominal=a, n_total_particles=len(x))
            r_tot = compute_analytical_bragg_relations(res, a_nominal=a, n_total_particles=x0.size)
            pe_det.append(r_det.get('p_wilson_est', np.nan))
            pe_tot.append(r_tot.get('p_wilson_est', np.nan))
            s21.append(r_det['sigma_h2h1'])
            sw.append(r_det['sigma_wilson'])
        print(f"p_true={p:.2f} sigma_in={sig:5.1f} | p_est(N_det, as GUI)={np.mean(pe_det):.3f} "
              f"| p_est(N_total)={np.mean(pe_tot):.3f} | 1-sqrt(1-p)={1-np.sqrt(1-p):.3f} "
              f"| sigma_H2H1={np.mean(s21):.2f} | sigma_wilson={np.mean(sw):.2f}")
