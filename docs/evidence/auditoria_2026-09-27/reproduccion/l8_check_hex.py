"""L8 audit: honeycomb xi, Friedel symmetry, axis1/axis2 blindness to sigma_x != sigma_y."""
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, r"C:\Users\josel\Documents\Obsidian_Vault\printing3")
import numpy as np
from core.lattice_disorder import (compute_structure_factor_2d, extract_angular_profile,
                                   extract_honeycomb_peak_profile_metrics, compute_hexagonal_bragg_indexing,
                                   find_hexagonal_reciprocal_rotation, analyze_reciprocal_space_2d)

a = 500.0
nc = 20
a1 = np.array([a, 0.0]); a2 = np.array([a / 2, a * np.sqrt(3) / 2])
I, J = np.meshgrid(np.arange(nc), np.arange(nc))
R = I.ravel()[:, None] * a1 + J.ravel()[:, None] * a2
tau = (a1 + a2) / 3
pts = np.vstack([R, R + tau])
L_x = np.ptp(pts[:, 0]); L_y = np.ptp(pts[:, 1])
print(f"honeycomb {nc}x{nc} cells, N={len(pts)}, extent x={L_x/1000:.2f} um, y={L_y/1000:.2f} um")
fx, fy, S = compute_structure_factor_2d(pts[:, 0], pts[:, 1], a_nominal=a, n_bins=512, f_max_factor=2.5)
f1 = 2 / (np.sqrt(3) * a)
r_vals, prof = extract_angular_profile(S, fx, fy, -30.0)
m = extract_honeycomb_peak_profile_metrics(r_vals, prof, f1)
print(f"1st shell @-30deg: FWHM_f={m['FWHM']:.3e} nm^-1 -> code xi_um={m['xi_um']:.2f} um; "
      f"1/FWHM_f={1/m['FWHM']/1000:.2f} um; 1/(pi FWHM_f)={1/(np.pi*m['FWHM'])/1000:.2f} um; "
      f"square-pipeline convention 1/(2pi FWHM_f)={1/(2*np.pi*m['FWHM'])/1000:.3f} um")

# Friedel: S(q) vs S(-q) on the symmetric grid
print("max |S - S[::-1,::-1]| / max S =", float(np.max(np.abs(S - S[::-1, ::-1])) / S.max()))

# honeycomb with basis shift: pairs G/-G still equal
pts2 = np.vstack([R, R + tau + 0.03 * a1])
_, _, S2 = compute_structure_factor_2d(pts2[:, 0], pts2[:, 1], a_nominal=a, n_bins=256)
print("shifted-basis honeycomb: max |S - S(-q)|/max =", float(np.max(np.abs(S2 - S2[::-1, ::-1])) / S2.max()))

# Anisotropic disorder sigma_x=25, sigma_y=5 on hexagonal lattice: axis1 vs axis2 vs axis3
rng = np.random.default_rng(3)
Rh = R.copy()
h1, h2, h3 = [], [], []
for rep in range(4):
    P = Rh + np.column_stack([rng.normal(0, 25, len(Rh)), rng.normal(0, 5, len(Rh))])
    fxh, fyh, Sh = compute_structure_factor_2d(P[:, 0], P[:, 1], a_nominal=a, n_bins=384)
    rot = find_hexagonal_reciprocal_rotation(Sh, fxh, fyh, a)['theta_peak_deg']
    idx = compute_hexagonal_bragg_indexing(Sh, fxh, fyh, a, rotation_deg=rot)
    h1.append(idx['H_axis1']); h2.append(idx['H_axis2']); h3.append(idx['H_axis3'])
print(f"sigma_x=25, sigma_y=5, rot={rot:.1f}: H_axis1={np.mean(h1):.1f} H_axis2={np.mean(h2):.1f} H_axis3={np.mean(h3):.1f}")
