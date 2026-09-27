"""L8 audit: what lattice does the Grid Generator actually produce for honeycomb/hexagonal presets?
Headless (offscreen) instantiation of the real GridGeneratorWindow; no hardware, no file writes in repo."""
import os, sys
sys.dont_write_bytecode = True
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = r"C:\Users\josel\Documents\Obsidian_Vault\printing3"
sys.path.insert(0, REPO)
os.chdir(os.environ.get("TMP", "."))
import numpy as np
from scipy.spatial import cKDTree
from core.lattice_generator import CrystalGridComposer, LatticeLayer


def nn_stats(nodes, label):
    P = np.array([[n["x"], n["y"]] for n in nodes])
    if len(P) < 4:
        print(label, "too few nodes", len(P)); return
    t = cKDTree(P)
    d, _ = t.query(P, k=4)
    d1 = d[:, 1]
    dmin = d1.min()
    # coordination at 1.05*dmin
    cnt = np.array([len(t.query_ball_point(p, 1.05 * dmin)) - 1 for p in P])
    c = P.mean(axis=0)
    inner = np.linalg.norm(P - c, axis=1) < 0.4 * np.ptp(P[:, 0])
    vals, counts = np.unique(cnt[inner], return_counts=True)
    print(f"{label}: N={len(P)} d_nn(min)={dmin:.4f} um  d_nn median={np.median(d1):.4f}  "
          f"inner coordination histogram={dict(zip(vals.tolist(), counts.tolist()))}")


# 1) Headless: dataclass defaults used by presets
l = LatticeLayer(name="Graphene Layer", lattice_type="graphene", a=2.5)
print("LatticeLayer(graphene) defaults: a=%.2f b=%.2f gamma=%.1f basis=%s" % (l.a, l.b, l.gamma_deg, [(x.u, round(x.v, 4)) for x in l.atoms]))

for gamma in (60.0, 120.0):
    comp = CrystalGridComposer()
    lay = LatticeLayer(name="g", lattice_type="graphene", a=2.5, b=2.5, gamma_deg=gamma)
    comp.layers = [lay]; comp.bounding_shape = "circle"; comp.bounding_params = {"radius": 8.0}
    comp.anchor_config.enabled = False
    nn_stats(comp.generate()["nodes"], f"composer graphene a=b=2.5 gamma={gamma:.0f} basis (0,0),(1/3,2/3)")

# 2) Real GUI presets
try:
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import grid_generator as gg
    w = gg.GridGeneratorWindow()
    for idx, name in ((1, "preset1 Hexagonal/hexagon"), (3, "preset3 Grafeno disco R=5")):
        w._apply_preset(idx)
        L0 = w.composer.layers[0]
        print(f"{name}: layer type={L0.lattice_type} a={L0.a} b={L0.b} gamma={L0.gamma_deg}")
        w.composer.anchor_config.enabled = False
        nn_stats(w.composer.generate()["nodes"], f"  {name} generated")
    # combo path: select graphene in the lattice-type combo
    w._on_lattice_type_changed(2)
    L0 = w.composer.layers[0]
    print(f"combo 'graphene': a={L0.a} b={L0.b} gamma={L0.gamma_deg} basis={[(x.u, round(x.v,4)) for x in L0.atoms]}")
    w.composer.anchor_config.enabled = False
    nn_stats(w.composer.generate()["nodes"], "  combo graphene generated")
except Exception as e:
    import traceback; traceback.print_exc()
