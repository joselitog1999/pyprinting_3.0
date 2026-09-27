import sys, time, math, os, tempfile
sys.dont_write_bytecode = True
sys.path.insert(0, r"C:\Users\josel\Documents\Obsidian_Vault\printing3")
import numpy as np
from core.raman_engine import (baseline_asls, baseline_airpls, remove_cosmic_rays,
    parse_andor_solis_file, calculate_photothermal_temperature)

# 1. AsLS timing N=2048 and N=1004
rng = np.random.default_rng(0)
for N in (1004, 2048):
    x = np.arange(N)
    y = 1000*np.exp(-x/800) + 500*np.exp(-0.5*((x-N/2)/3)**2) + rng.normal(0,5,N)
    baseline_asls(y)  # warmup
    ts=[]
    for _ in range(10):
        t0=time.perf_counter(); baseline_asls(y, lam=1e5, p=1e-3); ts.append(time.perf_counter()-t0)
    print(f"AsLS N={N}: median {1e3*np.median(ts):.1f} ms, min {1e3*min(ts):.1f} ms")

# 2. Cosmic ray filter on genuine narrow Raman bands (Gaussian FWHM in px)
print("\nCosmic-ray filter vs genuine Gaussian peaks (amp 2000, noise sigma 10, bg 500):")
for thr in (6.0, 5.5, 5.0):
    for fwhm_px in (1.5, 2.0, 2.5, 3.0, 4.0, 6.0):
        N=1004; x=np.arange(N, dtype=float)
        sig=fwhm_px/2.3548
        peak=2000*np.exp(-0.5*((x-500.3)/sig)**2)
        y = 500 + peak + rng.normal(0,10,N)
        yc, m = remove_cosmic_rays(y, threshold=thr)
        area_true = np.sum(peak)
        area_after = np.sum(yc-500)
        print(f"  thr={thr} FWHM={fwhm_px} px: flagged={int(m.sum())} px, area loss={100*(1-area_after/area_true):.1f}%")

# 3. Parser: delimiters
d = tempfile.mkdtemp()
cases = {
 "tab_dot.asc": "532.10\t100.5\n532.20\t101.5\n532.30\t102.5\n",
 "tab_commadec.asc": "532,10\t100,5\n532,20\t101,5\n532,30\t102,5\n",
 "csv_comma.csv": "532.10,100.5\n532.20,101.5\n532.30,102.5\n",
 "csv_comma_space.csv": "532.10, 100.5\n532.20, 101.5\n532.30, 102.5\n",
 "semicolon.csv": "532.10;100.5\n532.20;101.5\n532.30;102.5\n",
 "semicolon_commadec.csv": "532,10;100,5\n532,20;101,5\n532,30;102,5\n",
}
print("\nParser delimiter tests:")
for fn, txt in cases.items():
    p=os.path.join(d,fn); open(p,"w").write(txt)
    try:
        md,w,c = parse_andor_solis_file(p)
        print(f"  {fn}: OK w={w.tolist()} c={c.tolist()}")
    except Exception as e:
        print(f"  {fn}: FAIL {type(e).__name__}: {e}")

# 4. AS/S thermometry: omega^4 vs omega^3 (photon counting) bias
h=6.62607015e-34; c=2.99792458e10; kB=1.380649e-23
print("\nAS/S thermometry bias (code omega^4 applied to photon-count data obeying omega^3):")
for lam in (532.0, 808.0):
    for Om in (520.7, 1000.0):
        for T in (300.0, 400.0, 550.0):
            nuL=1e7/lam; f=(nuL+Om)/(nuL-Om)
            ratio_counts = f**3*math.exp(-h*c*Om/(kB*T))
            Tk,_ = calculate_photothermal_temperature(Om, 1.0, ratio_counts, lam)
            print(f"  lam={lam} Om={Om} Ttrue={T}: Tcode={Tk:.1f} K (err {Tk-T:+.1f} K)")
