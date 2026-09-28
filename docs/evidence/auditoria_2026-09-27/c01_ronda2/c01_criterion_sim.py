"""C-01 Ronda 2 (metrología): modelo del criterio de parada, actual (ticks) y en ms (bloques continuos).

Unidad base: bins de 1 ms. Un bin = promedio de 10 muestras a 10 kS/s (lo mismo que una ráfaga de la
lectura finita actual). Ruido blanco por bin: sigma_1ms (relativo a la base b = 1).
Ruido correlacionado opcional: Ornstein-Uhlenbeck de tiempo tau_c y sigma_c (no se promedia).

Modelos
- "tick": criterio actual. Ticks a intervalos ~ N(47.05, 2.5) ms recortados a [31, 63] (medido, Ronda 1).
  Cada tick lee UNA ráfaga de 1 ms. Ventanas M, M2 en ticks, hold N consecutivos, u estricto.
- "block": adquisición continua; evaluación cada T_b ms; I_new = media de los últimos W_new ms,
  I_old = media de los W_old ms anteriores (o congelada al primer 'true' si freeze=True);
  hold = condición verdadera en todas las evaluaciones de los últimos tau_hold ms.
"""
import numpy as np

RNG = np.random.default_rng(20260927)
FS_BIN_MS = 1.0


def make_level(n_trials, n_bins, t_s, r, D=None):
    """Nivel determinista por bin (b=1). Escalón en t_s (ms, float por trial) con razón r.
    Si D no es None: pulso rectangular de duración D (ms). Se integra la fracción de bin cubierta."""
    edges0 = np.arange(n_bins)[None, :]            # inicio de bin (ms)
    edges1 = edges0 + 1.0
    ts = t_s[:, None]
    te = ts + (D if D is not None else 1e12)
    cover = np.clip(np.minimum(edges1, te) - np.maximum(edges0, ts), 0.0, 1.0)
    return 1.0 + (r - 1.0) * cover


def add_noise(level, sigma_1ms, sigma_c=0.0, tau_c=100.0):
    x = level * (1.0 + sigma_1ms * RNG.standard_normal(level.shape))
    if sigma_c > 0:
        a = np.exp(-1.0 / tau_c)
        e = RNG.standard_normal(level.shape) * sigma_c * np.sqrt(1 - a * a)
        ou = np.zeros_like(level)
        ou[:, 0] = sigma_c * RNG.standard_normal(level.shape[0])
        for k in range(1, level.shape[1]):
            ou[:, k] = a * ou[:, k - 1] + e[:, k]
        x = x * (1.0 + ou)
    return x


def run_tick(x, t_s, M=10, M2=10, u=1.5, n_hold=3, mode=1, T_mean=47.05, T_sd=2.5):
    """Criterio actual sobre los bins x (1 ms). Devuelve latencia (ms) o nan si no detecta."""
    n_trials, n_bins = x.shape
    lat = np.full(n_trials, np.nan)
    for i in range(n_trials):
        dts = np.clip(RNG.normal(T_mean, T_sd, size=int(n_bins / 25)), 31, 63)
        tt = np.cumsum(dts)
        tt = tt[tt < n_bins - 1]
        idx = tt.astype(int)                  # la ráfaga de 1 ms cae en el bin que arranca en tt
        v = x[i, idx]
        hold = 0
        for n in range(M + M2, len(v) + 1):
            I_new = v[n - M:n].mean()
            I_old = v[n - M - M2:n - M].mean()
            c = I_new > u * I_old
            if mode == 0:
                stop = c
            else:
                hold = hold + 1 if c else 0
                stop = hold >= n_hold
            if stop:
                t_avail = tt[n - 1] + 1.0     # la ráfaga termina 1 ms después del tick
                if t_avail >= t_s[i]:
                    lat[i] = t_avail - t_s[i]
                else:
                    lat[i] = -1.0             # parada antes del evento: falsa alarma de ruido
                break
    return lat


def run_block(x, t_s, T_b=10, W_new=20, W_old=200, u=1.2, tau_hold=20, freeze=True, sign=+1):
    """Criterio en ms sobre bins de 1 ms. Evaluación al final de cada bloque de T_b ms."""
    n_trials, n_bins = x.shape
    cs = np.concatenate([np.zeros((n_trials, 1)), np.cumsum(x, axis=1)], axis=1)
    ends = np.arange(W_new + W_old, n_bins + 1, T_b)          # instante de evaluación (ms)
    I_new = (cs[:, ends] - cs[:, ends - W_new]) / W_new
    I_old_live = (cs[:, ends - W_new] - cs[:, ends - W_new - W_old]) / W_old
    n_h = int(round(tau_hold / T_b)) + 1
    lat = np.full(n_trials, np.nan)
    for i in range(n_trials):
        hold = 0
        base = None
        for k in range(len(ends)):
            I_o = base if (freeze and base is not None) else I_old_live[i, k]
            R = I_new[i, k] / I_o
            c = (R > u) if sign > 0 else (R < 1.0 / u)
            if c:
                if hold == 0:
                    base = I_old_live[i, k]
                hold += 1
            else:
                hold = 0
                base = None
            if hold >= n_h:
                t_avail = ends[k]
                lat[i] = (t_avail - t_s[i]) if t_avail >= t_s[i] else -1.0
                break
    return lat


def summarize(lat):
    det = np.isfinite(lat) & (lat >= 0)
    fa = np.isfinite(lat) & (lat < 0)
    if det.sum() == 0:
        return dict(P=0.0, med=np.nan, p95=np.nan, fa=fa.mean())
    L = lat[det]
    return dict(P=det.mean(), med=float(np.median(L)), p95=float(np.percentile(L, 95)), fa=fa.mean())


def step_experiment(model, r, sigma=0.02, n=600, pre=1500, post=2500, sigma_c=0.0, **kw):
    n_bins = pre + post
    t_s = RNG.uniform(pre - 200, pre, size=n)
    lvl = make_level(n, n_bins, t_s, r)
    x = add_noise(lvl, sigma, sigma_c=sigma_c)
    lat = run_tick(x, t_s, **kw) if model == "tick" else run_block(x, t_s, **kw)
    return summarize(lat)


def pulse_experiment(model, r_p, D, sigma=0.02, n=400, pre=1500, post=2500, **kw):
    n_bins = pre + post
    t_s = RNG.uniform(pre - 200, pre, size=n)
    lvl = make_level(n, n_bins, t_s, r_p, D=D)
    x = add_noise(lvl, sigma)
    lat = run_tick(x, t_s, **kw) if model == "tick" else run_block(x, t_s, **kw)
    s = summarize(lat)
    return s["P"]


PROPOSALS = {
    "ACTUAL (ticks 47 ms, M=M2=10, u=1.5, N_hold=3)": ("tick", dict(M=10, M2=10, u=1.5, n_hold=3)),
    "P0 equivalente (480/480 ms, u=1.5, hold 100 ms, vivo)": ("block", dict(T_b=10, W_new=480, W_old=480, u=1.5, tau_hold=100, freeze=False)),
    "P1 latencia (20/200 ms, u=1.2, hold 20 ms, base congelada)": ("block", dict(T_b=10, W_new=20, W_old=200, u=1.2, tau_hold=20, freeze=True)),
    "P2 compromiso (40/400 ms, u=1.25, hold 60 ms, base congelada)": ("block", dict(T_b=10, W_new=40, W_old=400, u=1.25, tau_hold=60, freeze=True)),
    "P0' (480/480, u=1.5, hold 100, base congelada)": ("block", dict(T_b=10, W_new=480, W_old=480, u=1.5, tau_hold=100, freeze=True)),
}

if __name__ == "__main__":
    import sys
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    if part in ("step", "all"):
        print("== Escalón: P_det, latencia mediana y p95 (ms), sigma_1ms = 2 % blanco ==")
        for name, (model, kw) in PROPOSALS.items():
            row = []
            for r in (1.4, 1.5, 1.55, 1.6, 1.8, 2.0):
                s = step_experiment(model, r, sigma=0.02, n=300 if model == "tick" else 600, **kw)
                row.append(f"r={r}: P={s['P']:.2f} med={s['med']:.0f} p95={s['p95']:.0f}")
            print(name); print("   " + " | ".join(row))
    if part in ("pulse", "all"):
        print("== Pulso rectangular (transitorio): P(falso positivo) vs D (ms), sigma 2 % ==")
        for name, (model, kw) in PROPOSALS.items():
            for r_p in (1.2, 1.5, 2.0):
                row = []
                for D in (2, 5, 10, 20, 50, 100, 200, 300, 500):
                    p = pulse_experiment(model, r_p, D, n=150 if model == "tick" else 400, **kw)
                    row.append(f"{D}:{p:.2f}")
                print(f"{name} | r_p={r_p} | " + " ".join(row))
