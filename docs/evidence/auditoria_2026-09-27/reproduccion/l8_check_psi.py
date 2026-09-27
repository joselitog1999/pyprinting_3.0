"""L8 audit: CAT-313 psi_n checks with the real code (compute_bond_orientational_order)."""
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, r"C:\Users\josel\Documents\Obsidian_Vault\printing3")
import numpy as np
from core.lattice_disorder import compute_bond_orientational_order

rng = np.random.default_rng(7)
a = 500.0
n = 40
a1 = np.array([a, 0.0]); a2 = np.array([a / 2, a * np.sqrt(3) / 2])
I, J = np.meshgrid(np.arange(n), np.arange(n))
R = I.ravel()[:, None] * a1 + J.ravel()[:, None] * a2
# keep interior to avoid edge effects in the average
c = R.mean(axis=0)
inner = np.linalg.norm(R - c, axis=1) < 0.35 * n * a

for s in (6.55, 15.0, 30.0):
    P = R + rng.normal(0, s, R.shape)
    r = compute_bond_orientational_order(P[:, 0], P[:, 1], k_neighbors=6, lattice_type='hexagonal', n_fold=6)
    m = float(np.mean(r['psi_n_local'][inner]))
    print(f"hex a=500 sigma={s:5.2f}: <|psi6|>={m:.5f}  1-mean={1-m:.5f}  doc 36s^2/(2a^2)={36*s*s/(2*a*a):.5f}  36s^2/a^2={36*s*s/a/a:.5f}")

# random (ideal gas) points: code metric <|psi6|> with kNN k=6
L = 40 * a
Pr = rng.uniform(0, L, size=(4000, 2))
rr = compute_bond_orientational_order(Pr[:, 0], Pr[:, 1], k_neighbors=6, lattice_type='hexagonal', n_fold=6)
inner_r = np.all((Pr > 0.1 * L) & (Pr < 0.9 * L), axis=1)
print(f"random points: <|psi6|> (code metric) = {np.mean(rr['psi_n_local'][inner_r]):.3f}; "
      f"|<psi6>| (global complex) = {abs(np.mean(rr['psi_n_local_complex'][inner_r])):.3f}")

# honeycomb: global complex Psi3 vs mean of moduli
tau = (a1 + a2) / 3
Ph = np.vstack([R, R + tau])
rh = compute_bond_orientational_order(Ph[:, 0], Ph[:, 1], k_neighbors=3, lattice_type='honeycomb', n_fold=3)
cz = Ph.mean(axis=0)
inh = np.linalg.norm(Ph - cz, axis=1) < 0.3 * n * a
print(f"honeycomb ideal: <|psi3|>={np.mean(rh['psi_n_local'][inh]):.4f}; |<psi3>| global complex={abs(np.mean(rh['psi_n_local_complex'][inh])):.4f}")
