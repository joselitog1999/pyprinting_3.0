"""Script de cálculo y verificación óptica para la arquitectura del microscopio PyPrinting 3.0."""
import numpy as np

# Definición de objetivos
objectives = {
    "Olympus 20x Air": {
        "m_nom": 20, "f_ref": 180.0, "na": 0.40, "n": 1.0, "wd": 1.3, "medium": "Aire"
    },
    "Olympus LUMPlanFLN 60x W": {
        "m_nom": 60, "f_ref": 180.0, "na": 1.00, "n": 1.333, "wd": 2.0, "medium": "Agua"
    },
    "Olympus MPLN 10x Air": {
        "m_nom": 10, "f_ref": 180.0, "na": 0.25, "n": 1.0, "wd": 10.6, "medium": "Aire"
    },
    "Nikon S Plan Fluor 100x Oil (NA 1.30)": {
        "m_nom": 100, "f_ref": 200.0, "na": 1.30, "n": 1.515, "wd": 0.20, "medium": "Aceite"
    },
    "Nikon S Plan Fluor 100x Oil (NA 0.50 iris)": {
        "m_nom": 100, "f_ref": 200.0, "na": 0.50, "n": 1.515, "wd": 0.20, "medium": "Aceite"
    },
    "Nikon CFI S Plan Fluor 40x Air": {
        "m_nom": 40, "f_ref": 200.0, "na": 0.60, "n": 1.0, "wd": 3.2, "medium": "Aire (Collar 0-2mm)"
    }
}

# Tren óptico relé
f1 = 250.0  # mm (primera lente post-objetivo)
f2 = 200.0  # mm (segunda lente pre-BS)

# Puertos finales
ports = {
    "Cámara Canon EOS 500D": {"f_final": 250.0, "det": "CMOS 4.7 um", "wavelengths": [532, 592, 637]},
    "Confocal Verde 532 nm": {"f_final": 200.0, "pinhole_um": 50.0, "wl": 532},
    "Confocal Amarillo 592 nm": {"f_final": 250.0, "pinhole_um": 50.0, "wl": 592},
    "Confocal Rojo 637 nm": {"f_final": 250.0, "pinhole_um": 100.0, "wl": 637},
    "Espectrómetro Shamrock 500i": {"f_final": 250.0, "det": "Slit 10-2500 um", "f_num_spec": 9.7}
}

print("="*80)
print("VERIFICACIÓN DE AUMENTOS Y PARÁMETROS ÓPTICOS")
print("="*80)

for name, obj in objectives.items():
    f_obj = obj["f_ref"] / obj["m_nom"]
    obj["f_obj"] = f_obj
    print(f"\n--- {name} ---")
    print(f"  f_obj: {f_obj:.2f} mm | NA: {obj['na']:.2f} | n: {obj['n']:.3f} | WD: {obj['wd']} mm")
    
    # Aumentos por puerto
    for pname, port in ports.items():
        f_final = port["f_final"]
        m_eff = (f1 / f_obj) * (f_final / f2)
        print(f"  > Puerto [{pname} (f={f_final} mm)]: M_eff = {m_eff:.2f}x")

print("\n" + "="*80)
print("RESOLUCIÓN DIFRACTIVA Y CONO NUMÉRICO")
print("="*80)

wavelengths = [532, 592, 637, 808]
for name, obj in objectives.items():
    na = obj["na"]
    n = obj["n"]
    print(f"\n--- {name} (NA = {na:.2f}, n = {n:.3f}) ---")
    for wl in wavelengths:
        r_abbe = wl / (2 * na)
        r_rayleigh = 0.61 * wl / na
        z_rayleigh = 2 * n * wl / (na**2)
        # confocal axial FWHM aprox
        z_confocal = 0.64 * wl / (n - np.sqrt(n**2 - na**2)) if na < n else 0.64 * wl / (n * 0.5)
        print(f"  wl = {wl} nm: r_Abbe = {r_abbe:.1f} nm | r_Rayleigh = {r_rayleigh:.1f} nm | z_Rayleigh = {z_rayleigh/1000:.2f} um | z_confocal = {z_confocal/1000:.2f} um")

print("\n" + "="*80)
print("DIAMETRO DE AIRY EN PLANO DE PINHOLE Y AIRY UNITS (AU)")
print("="*80)

confocal_channels = [
    ("Confocal Verde 532 nm", 532, 200.0, 50.0),
    ("Confocal Amarillo 592 nm", 592, 250.0, 50.0),
    ("Confocal Rojo 637 nm", 637, 250.0, 100.0)
]

for cname, wl, f_final, pinhole in confocal_channels:
    print(f"\n=== {cname} (wl = {wl} nm, Lente = {f_final} mm, Pinhole = {pinhole} um) ===")
    for oname, obj in objectives.items():
        f_obj = obj["f_obj"]
        na = obj["na"]
        m_eff = (f1 / f_obj) * (f_final / f2)
        
        # Diametro de disco de Airy en plano del detector
        # d_Airy = 2.44 * wl * M_eff / NA
        d_airy_um = 2.44 * (wl * 1e-3) * m_eff / na
        au = pinhole / d_airy_um
        
        print(f"  {oname:35s}: M={m_eff:6.1f}x | d_Airy = {d_airy_um:6.1f} um | AU = {au:4.2f} AU")

print("\n" + "="*80)
print("CAMARA CANON EOS 500D (Sensor 22.3 x 14.9 mm, Pixel = 4.7 um, 4752 x 3168 px)")
print("="*80)
for oname, obj in objectives.items():
    f_obj = obj["f_obj"]
    na = obj["na"]
    m_eff = (f1 / f_obj) * (250.0 / f2)
    
    fov_x_um = (22.3 * 1000) / m_eff
    fov_y_um = (14.9 * 1000) / m_eff
    pixel_proj_nm = (4.7 * 1000) / m_eff
    r_abbe_532 = 532 / (2 * na)
    nyquist_ratio = r_abbe_532 / (2 * pixel_proj_nm)
    is_nyquist = nyquist_ratio >= 1.0
    print(f"  {oname:35s}: M={m_eff:6.1f}x | FOV = {fov_x_um:6.1f} x {fov_y_um:6.1f} um | Pixel_proy = {pixel_proj_nm:5.1f} nm | Nyquist 532nm: {nyquist_ratio:4.2f} ({'CUMPLE' if is_nyquist else 'SUB-MUESTREO'})")

print("\n" + "="*80)
print("ACOPLAMIENTO AL ESPECTROMETRO SHAMROCK 500i (f/# = 9.7)")
print("="*80)
# Diametro de haz colimado de salida del objetivo: D_pupil = 2 * f_obj * NA
# Tras L1 (f1=250) y L2 (f2=200): D_beam = D_pupil * (f2/f1) = D_pupil * 0.8
# Con lente focalizadora de 250 mm al slit:
# f/#_in = f_spec / D_beam = 250 / (2 * f_obj * NA * 0.8) = 250 / (1.6 * f_obj * NA)
for oname, obj in objectives.items():
    f_obj = obj["f_obj"]
    na = obj["na"]
    d_pupil = 2 * f_obj * na
    d_beam = d_pupil * (f2 / f1)
    f_num_in = 250.0 / d_beam
    match_status = "Sub-ilumina (OK, sin vineteo)" if f_num_in >= 9.7 else "Sobre-ilumina (Vineteo/Stray light)"
    print(f"  {oname:35s}: Pupila = {d_pupil:4.1f} mm | Haz = {d_beam:4.1f} mm | Cono entrada f/#{f_num_in:4.1f} vs f/9.7 -> {match_status}")
