"""Audit L7 (read-only): end-to-end self-consistency of the Tab2 -> Tab3 sigma inversion.

Generates synthetic square lattices with KNOWN sigma, measures Hx exactly as the GUI does
(analyze_reciprocal_space_2d with GUI defaults), builds the MC calibration exactly as the
GUI does (run_monte_carlo_calibration with band_width_nm = B * 2 fmax / n_bins) and inverts
with interpolate_disorder. Nothing in the repository is written.
"""
import sys
import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, r"C:\Users\josel\Documents\Obsidian_Vault\printing3")
from core.lattice_disorder import (analyze_reciprocal_space_2d, run_monte_carlo_calibration,
                                   interpolate_disorder)

a = 500.0
n = 30
B = 3
for n_bins in (256, 512):
    fmax = 2.5 / a
    band_nm = B * (2.0 * fmax) / n_bins
    for p in (0.0, 0.07):
        mc = run_monte_carlo_calibration(n_side=n, a=a, f_vac=p, sigma_min=0.0, sigma_max=60.0,
                                         n_sigma_steps=20, iterations_per_step=30,
                                         n_bragg_pts=81, band_width_nm=band_nm,
                                         n_transversal_pts=5, seed=1)
        s_vals = mc['sigma_values']
        for s_true in (5.0, 10.0, 15.0, 25.0, 40.0):
            rec = []
            hx = []
            for seed in range(5):
                rng = np.random.default_rng(100 + seed)
                gx, gy = np.meshgrid(np.arange(n) * a + 1234.5, np.arange(n) * a + 777.0)
                x0 = gx.ravel(); y0 = gy.ravel()
                keep = rng.uniform(0, 1, x0.size) >= p
                x = x0[keep] + rng.normal(0, s_true, keep.sum())
                y = y0[keep] + rng.normal(0, s_true, keep.sum())
                r = analyze_reciprocal_space_2d(x, y, a_nominal=a, n_bins=n_bins,
                                                band_width_bins=B, dc_cut_factor=0.35)
                hx.append(r['Hx'])
                sx, _ = interpolate_disorder(r['Hx'], s_vals, mc['H_mean'], mc['H_std'])
                rec.append(sx)
            H_mc_at_true = np.interp(s_true, s_vals, mc['H_mean'])
            print(f"bins={n_bins} p={p:.2f} sigma_true={s_true:5.1f} nm | Hx_exp={np.mean(hx):8.2f} "
                  f"H_MC(sigma_true)={H_mc_at_true:8.2f} | sigma_rec={np.mean(rec):6.2f} +/- {np.std(rec):5.2f} nm "
                  f"(bias {100*(np.mean(rec)/s_true-1):+6.1f} %)")
        print(f"  H_MC(0)={mc['H_mean'][0]:.2f}  (analytic N_occ-normalized peak = {n*n*(1-p):.1f})")
