# Reporte Científico Canónico: Nanotermometría por Variaciones DLS y Fluctuaciones Brownianas 🌡️

**Biblioteca Científica Canónica — Pilar I: Nanofísica, Termoplasmónica y Control Instrumental**  
**Signatura Canónica**: `CAT-111` | **Clúster**: `[FIS]` (Física)  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Físico EPN, Becario Doctoral CONICET, INS-UNSAM*)  
**Fecha de Publicación**: Septiembre 2026 | **Estado**: Vigente y Certificado por QA  
**Módulos del Sistema Asociados**: `modules/measurements.py`, `core/nidaq.py`, `analysis/time_volt_analyzer.py`  
**Referencias Cruzadas**: `[[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]]`, `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`, `[[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]]`, `[[CAT-112_Teoria_Lente_Termica_Gradientes_Indice_y_Marangoni]]`, `[[SYS-102_Senales_Slots_PyQt6_y_Temporizacion_DAQmx]]`

---

## 1. Resumen Ejecutivo

En la nanofabricación por **Impresión Óptica Fototérmica (*Optical Printing*)**, la iluminación focalizada con un haz láser continuo ($\lambda = 532\ \text{nm}$ o $808\ \text{nm}$) excita la resonancia plasmónica de superficie (LSPR) de nanopartículas coloidales individuales de oro o plata. La relajación no radiativa de los plasmones decae en un calentamiento Joule ultralocalizado que eleva la temperatura del metal y del líquido circundante en varias decenas o cientos de Kelvin.

Este reporte formaliza el marco teórico y metrológico para la **Nanotermometría Óptica In-Situ basada en Dispersión Dinámica de Luz (DLS)**: en lugar de emplear el DLS exclusivamente para la determinación estática del radio hidrodinámico coloidal $R_h$ a temperatura ambiente ($20^\circ\text{C}$ / $293.15\ \text{K}$ según ISO 22412), se explota la sensibilidad intrínseca de la difusión browniana $D(T)$ a la temperatura local y a la viscosidad dependiente de temperatura del solvente $\eta(T)$. Se demuestra la derivación formal de la función de autocorrelación temporal $g^{(2)}(\tau)$, la inversión no lineal bajo el modelo de Vogel-Fulcher-Tammann (VFT) para agua líquida, el perfil térmico estacionario $T(r)$ y el presupuesto metrológico de incertidumbre según la guía ISO/GUM.

---

## 2. Ecuación de Langevin y Dinámica Browniana en Medios Térmicamente No Homogéneos

El movimiento browniano de una nanopartícula esférica de radio $R_h$ suspendida en un fluido viscoso a temperatura $T$ está gobernado por la ecuación estocástica de Langevin en el régimen sobreamortiguado (número de Reynolds $\text{Re} \ll 1$ y tiempo de relajación inercial $\tau_{\text{inercia}} = m / \gamma \sim 10^{-9}\ \text{s}$):

$$\gamma(T) \frac{d\mathbf{r}}{dt} = \mathbf{F}_{\text{óptica}}(\mathbf{r}) + \mathbf{F}_{\text{estocástica}}(t)$$

donde $\gamma(T) = 6 \pi \eta(T) R_h$ es el coeficiente de fricción hidrodinámica de Stokes, y la fuerza estocástica gaussiana satisface el teorema de fluctuación-disipación:

$$\langle \mathbf{F}_{\text{estocástica}}(t) \rangle = 0, \quad \langle F_i(t) F_j(t') \rangle = 2 k_B T \gamma(T) \delta_{ij} \delta(t - t')$$

```
                               PERFIL TÉRMICO Y DIFUSIÓN BROWNIANA
                 
                   Calentamiento Joule (AuNP)           Gradiente Térmico en Agua
                     ┌─────────────────┐             T(r) = T_inf + (sigma_abs * I_0) / (4*pi*kappa*r)
                     │                 │                   ▲
                     │   AuNP (LSPR)   │                   │  T_nano
                     │   T = T_nano    │                   │   ╭───────
                     │                 │                   │   │       ╰───────── T(r)
                     └────────┬────────┘                   │   │
                              │ Fluido Viscoso             └───┴────────────────► Distancia r
                              ▼                             │  ◄── R_h ──►
                     eta(T) = A exp[B / (T - T_0)]         Difusión acelerada:
                     Viscosidad drásticamente reducida     D(T) = k_B T / [6 * pi * eta(T) * R_h]
```

### 2.1 Coeficiente de Difusión Traslacional de Stokes-Einstein
Para un coloide que experimenta un entorno a temperatura constante $T$, el coeficiente de difusión viene dado por:

$$D(T) = \frac{k_B T}{6 \pi \eta(T) R_h}$$

donde $k_B = 1.380649 \times 10^{-23}\ \text{J/K}$ es la constante de Boltzmann.

---

## 3. Dependencia Térmica No Lineal de la Viscosidad del Agua (Modelo VFT)

En agua líquida, la viscosidad dinámica $\eta(T)$ disminuye fuertemente al elevarse la temperatura. Mientras que la aproximación de Arrhenius falla para intervalos térmicos superiores a $30\ \text{K}$, la ecuación empírica de **Vogel-Fulcher-Tammann (VFT)** ajusta los datos experimentales con una exactitud relativa superior al $0.3\%$ en el rango $0^\circ\text{C} \le T \le 120^\circ\text{C}$ a $1\ \text{atm}$:

$$\eta(T) = A \exp\left( \frac{B}{T - T_0} \right)$$

| Parámetro VFT | Valor Físico Canónico | Unidades | Descripción |
| :---: | :---: | :---: | :--- |
| $A$ | $0.02939$ | $\text{mPa}\cdot\text{s} = 10^{-3}\ \text{Pa}\cdot\text{s}$ | Viscosidad en el límite de alta temperatura |
| $B$ | $507.88$ | $\text{K}$ | Energía de activación efectiva normalizada |
| $T_0$ | $149.3$ | $\text{K}$ | Temperatura de divergencia vítrea aparente |

Sustituyendo $\eta(T)$ en la relación de Stokes-Einstein se obtiene la dependencia explícita del coeficiente de difusión con respecto a la temperatura absoluta $T$:

$$D(T) = \frac{k_B T}{6 \pi A R_h} \exp\left( -\frac{B}{T - T_0} \right)$$

---

## 4. Función de Autocorrelación Temporal de Intensidad y Relación de Siegert

En un experimento de DLS, el fotomultiplicador o fotodiodo de avalancha en modo conteo de fotones adquiere la intensidad esparcida $I(t)$ a un ángulo de esparcimiento $\theta = 90^\circ$ (o en retrodispersión $\theta = 173^\circ$). La función de correlación temporal de intensidad de segundo orden normalizada se define como:

$$g^{(2)}(\tau) = \frac{\langle I(t) I(t + \tau) \rangle}{\langle I(t) \rangle^2}$$

Para un ensamble de difusores brownianos independientes regidos por estadística gaussiana de campo, la **relación de Siegert** vincula $g^{(2)}(\tau)$ con la función de correlación de campo eléctrico de primer orden $g^{(1)}(\tau)$:

$$g^{(2)}(\tau) = 1 + \beta |g^{(1)}(\tau)|^2$$

donde $\beta \le 1$ es el factor de coherencia instrumental o factor de óptica espacial (determinado por el tamaño de apertura del pinhole y el número de modos de esparcimiento recolectados).

### 4.1 Tasa de Decaimiento $\Gamma$ y Vector de Dispersión $\mathbf{q}$
Para una suspensión monodispersa:

$$g^{(1)}(\tau) = \exp(-\Gamma \tau)$$

$$\Gamma = D(T) q^2$$

donde $q$ es la magnitud del vector de transferencia de onda en el solvente de índice de refracción $n$:

$$q = \frac{4 \pi n}{\lambda_0} \sin\left(\frac{\theta}{2}\right)$$

Con $\lambda_0 = 532\ \text{nm}$, $n_{\text{agua}} = 1.333$ y $\theta = 90^\circ$:
$$q = \frac{4 \pi (1.333)}{532 \times 10^{-9}\ \text{m}} \sin(45^\circ) \approx 2.227 \times 10^7\ \text{m}^{-1}$$

---

## 5. Inversión Analítica y Determinación de la Temperatura Local $T_{\text{nano}}$

Cuando se conoce de forma independiente el radio hidrodinámico nominal $R_h$ de la nanopartícula sonda (por calibración DLS previa a $20^\circ\text{C}$ o espectrometría TEM), la medición experimental de la tasa de decaimiento $\Gamma_{\text{exp}}$ permite extraer el coeficiente de difusión instantáneo:

$$D_{\text{exp}} = \frac{\Gamma_{\text{exp}}}{q^2}$$

Igualando este valor a la expresión analítica $D(T)$ se obtiene la ecuación trascendente:

$$f(T) = \frac{k_B T}{6 \pi A R_h} \exp\left( -\frac{B}{T - T_0} \right) - D_{\text{exp}} = 0$$

Dado que $f'(T) > 0$ monótonamente para todo $T > T_0$, existe una única raíz real $T = T_{\text{nano}}$ que se resuelve eficientemente mediante el método de Newton-Raphson:

$$T^{(k+1)} = T^{(k)} - \frac{f(T^{(k)})}{f'(T^{(k)})}$$

con la derivada analítica:

$$f'(T) = \frac{k_B}{6 \pi A R_h} \exp\left( -\frac{B}{T - T_0} \right) \left[ 1 + \frac{B T}{(T - T_0)^2} \right]$$

---

## 6. Perfil Estacionario de Temperatura y Transferencia de Calor Nanométrica

Bajo iluminación óptica continua, la potencia disipada por efecto Joule dentro de una partícula metálica de volumen $V = \frac{4}{3}\pi R^3$ es:

$$P_{\text{abs}} = \sigma_{\text{abs}}(\lambda) I_0$$

La ecuación de conducción de calor en estado estacionario alrededor de la nanoesfera inmersa en agua (conductividad térmica $\kappa_{\text{agua}} \approx 0.60\ \text{W}/(\text{m}\cdot\text{K})$) con simetría esférica:

$$\frac{1}{r^2} \frac{d}{dr}\left( r^2 \kappa \frac{dT}{dr} \right) = 0 \quad (r \ge R)$$

Integrando con las condiciones de contorno $T(r \to \infty) = T_\infty$ y flujo de calor en la superficie $-\kappa \left. \frac{dT}{dr}\right|_{R} = \frac{P_{\text{abs}}}{4\pi R^2}$:

$$T(r) = T_\infty + \Delta T_{\text{surf}} \left( \frac{R}{r} \right), \quad \Delta T_{\text{surf}} = \frac{\sigma_{\text{abs}}(\lambda) I_0}{4 \pi \kappa_{\text{agua}} R}$$

Para una AuNP típica de $R = 40\ \text{nm}$ ($\sigma_{\text{abs}} \approx 8.2 \times 10^{-15}\ \text{m}^2$ a $532\ \text{nm}$) bajo irradiancia focalizada $I_0 = 5 \times 10^8\ \text{W/m}^2$ ($P \approx 5\ \text{mW}$ en $w_0 = 1.0\ \mu\text{m}$):

$$\Delta T_{\text{surf}} = \frac{(8.2 \times 10^{-15}\ \text{m}^2)(5 \times 10^8\ \text{W/m}^2)}{4 \pi (0.60\ \text{W/m}\cdot\text{K})(40 \times 10^{-9}\ \text{m})} \approx 13.6\ \text{K}$$

---

## 7. Presupuesto de Incertidumbre Metrológica ISO/GUM

La incertidumbre combinada en la estimación de temperatura $u_c(T)$ se deriva aplicando la ley de propagación de varianzas según la Guía ISO/GUM:

$$u_c^2(T) = \left( \frac{\partial T}{\partial D} \right)^2 u^2(D) + \left( \frac{\partial T}{\partial R_h} \right)^2 u^2(R_h) + \left( \frac{\partial T}{\partial q} \right)^2 u^2(q)$$

| Fuente de Incertidumbre ($x_i$) | Valor Nominal | Incertidumbre Estándar $u(x_i)$ | Coeficiente de Sensibilidad $c_i = \partial T / \partial x_i$ | Contribución $u_i(T)$ |
|---|:---:|:---:|:---:|:---:|
| Difusión experimental $D$ | $5.42 \times 10^{-12}\ \text{m}^2/\text{s}$ | $0.08 \times 10^{-12}\ \text{m}^2/\text{s}$ | $+1.42 \times 10^{13}\ \text{K}\cdot\text{s}/\text{m}^2$ | $\mathbf{1.14\ \text{K}}$ |
| Radio hidrodinámico calibrado $R_h$ | $40.0\ \text{nm}$ | $0.6\ \text{nm}$ | $+1.93\ \text{K/nm}$ | $\mathbf{1.16\ \text{K}}$ |
| Magnitud del vector de onda $q$ | $2.227 \times 10^7\ \text{m}^{-1}$ | $0.015 \times 10^7\ \text{m}^{-1}$ | $-2.69 \times 10^{-5}\ \text{K}\cdot\text{m}$ | $\mathbf{0.40\ \text{K}}$ |
| **Incertidumbre Combinada ($k=1$)** | — | — | $u_c(T) = \sqrt{\sum u_i^2(T)}$ | $\mathbf{\pm 1.68\ \text{K}}$ |
| **Incertidumbre Expandida ($k=2$, 95%)** | — | — | $U_{95} = 2 \cdot u_c(T)$ | $\mathbf{\pm 3.36\ \text{K}}$ |

---

## 8. Implementación Computacional en Python

```python
"""
CAT-111: Nanotermometría por Dispersión Dinámica de Luz (DLS).
Inversión analítica de temperatura local T_nano a partir de fluctuaciones brownianas.
"""
from typing import NamedTuple
import numpy as np
from scipy.optimize import newton

class DLSMeasurement(NamedTuple):
    tau_s: np.ndarray
    g2_measured: np.ndarray
    wavelength_m: float = 532e-9
    scattering_angle_deg: float = 90.0
    refractive_index: float = 1.333
    rh_nominal_m: float = 40.0e-9

class VFTWaterModel:
    A: float = 0.02939e-3  # Pa*s
    B: float = 507.88      # K
    T0: float = 149.3      # K
    KB: float = 1.380649e-23  # J/K

    @classmethod
    def viscosity(cls, T_kelvin: float) -> float:
        return cls.A * np.exp(cls.B / (T_kelvin - cls.T0))

    @classmethod
    def diffusion_coefficient(cls, T_kelvin: float, Rh_m: float) -> float:
        eta = cls.viscosity(T_kelvin)
        return (cls.KB * T_kelvin) / (6.0 * np.pi * eta * Rh_m)

def solve_local_temperature(D_exp: float, Rh_m: float, T_guess: float = 293.15) -> float:
    """Resuelve la temperatura local T mediante Newton-Raphson sobre el modelo VFT."""
    def objective(T: float) -> float:
        return VFTWaterModel.diffusion_coefficient(T, Rh_m) - D_exp

    def derivative(T: float) -> float:
        h = 1e-5
        return (objective(T + h) - objective(T - h)) / (2.0 * h)

    T_sol = newton(objective, x0=T_guess, fprime=derivative, tol=1e-4, maxiter=50)
    return float(T_sol)

def fit_decay_rate(tau: np.ndarray, g2: np.ndarray, beta: float = 0.85) -> float:
    """Extrae la tasa de decaimiento Gamma a partir de g^(2)(tau) = 1 + beta * exp(-2*Gamma*tau)."""
    valid = (g2 > 1.0) & (g2 < 1.0 + beta)
    tau_v, g2_v = tau[valid], g2[valid]
    y = np.log((g2_v - 1.0) / beta)
    gamma_fit, _ = np.polyfit(tau_v, y, 1)
    return float(-gamma_fit / 2.0)
```

---

## 9. Conclusiones y Conexión Instrumental

1. El DLS trasciende la función de sizing pasivo y se consolida como un **termómetro nanoscópico absoluto** con una precisión típica de $\pm 1.7\ \text{K}$.
2. Al combinarse con el efecto de **Lente Térmica** (`[[CAT-112_Teoria_Lente_Termica_Gradientes_Indice_y_Marangoni]]`), proporciona la confirmación cruzada entre la respuesta mecánica browniana y la distorsión del frente de onda óptico.
