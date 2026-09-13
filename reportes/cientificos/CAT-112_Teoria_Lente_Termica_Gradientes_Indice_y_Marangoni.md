# Reporte Científico Canónico: Teoría de Lente Térmica, Gradientes de Índice y Convección de Marangoni 🔬🌊

**Biblioteca Científica Canónica — Pilar I: Nanofísica, Termoplasmónica y Control Instrumental**  
**Signatura Canónica**: `CAT-112` | **Clúster**: `[FIS]` (Física)  
**Laboratorio de Nanofotónica — Instituto de Nanosistemas (INS-UNSAM / CONICET)**  
**Autor Principal**: José Luis González Peñafiel (*Físico EPN, Becario Doctoral CONICET, INS-UNSAM*)  
**Fecha de Publicación**: Septiembre 2026 | **Estado**: Vigente y Certificado por QA  
**Módulos del Sistema Asociados**: `modules/measurements.py`, `core/nidaq.py`, `analysis/time_volt_analyzer.py`  
**Referencias Cruzadas**: `[[CAT-107_Cinetica_Captura_Fotodiodo_Time_Volt_Filtro_Nhold]]`, `[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`, `[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`, `[[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]]`, `[[CAT-111_Nanotermometria_DLS_y_Dinamica_Fluctuaciones_Brownianas]]`, `[[SYS-102_Senales_Slots_PyQt6_y_Temporizacion_DAQmx]]`

---

## 1. Resumen Ejecutivo

En la nanofabricación fototérmica asistida por láser, la absorción óptica resonante en nanopartículas metálicas no sólo genera fuerzas de radiación (`[[CAT-109_Electrodinamica_Fuerzas_Opticas_y_Termoplasmonica_Printing]]`), sino que actúa como una fuente puntual de calor que disipa energía hacia el solvente circundante. Debido a que el índice de refracción de los líquidos depende fuertemente de la temperatura a través del coeficiente termo-óptico ($dn/dT$), el campo de temperaturas no uniforme $\nabla T(\mathbf{r})$ induce un gradiente espacial de índice de refracción $\nabla n(\mathbf{r})$ que se comporta ópticamente como una **lente térmica negativa (divergente)**.

Este reporte formaliza la electrodinámica y termodinámica de la **Espectroscopía de Lente Térmica Fototérmica (*Photothermal Lens Spectroscopy*)** en el microscopio confocal de PyPrinting 3.0: la deducción de la ecuación de conducción de calor en estado estacionario y transitorio, la difracción de Fresnel-Kirchhoff del haz transmitido, la relación de transducción en el fotodiodo confocal con apertura finita (pinhole), y el acoplamiento hidrodinámico interfacial regido por el **efecto termocapilar de Marangoni** ($\nabla_s \gamma = -\beta_T \nabla_\parallel T$), justificando cuantitativamente las condiciones límite que evitan la ebullición microscópica (*nanobubbles*) y el arrastre coloidal convectivo no deseado.

---

## 2. Ecuación de Difusión Térmica y Fuentes de Calor Joule

La generación de calor disipada en una nanopartícula metálica bajo iluminación de campo armónico monocromático $\mathbf{E}(\mathbf{r}, t) = \text{Re}[\mathbf{E}(\mathbf{r}) e^{-i\omega t}]$ proviene de la densidad de potencia disipada por pérdidas óhmicas (efecto Joule de los electrones de conducción con los fonones de la red cristalina):

$$Q(\mathbf{r}) = \frac{1}{2} \text{Re}\left( \mathbf{J}^* \cdot \mathbf{E} \right) = \frac{1}{2} \omega \epsilon_0 \text{Im}(\epsilon_m) |\mathbf{E}(\mathbf{r})|^2$$

Integrando sobre el volumen de la partícula coloidal de radio $R$:

$$P_{\text{abs}} = \int_V Q(\mathbf{r}) d^3\mathbf{r} = \sigma_{\text{abs}}(\lambda) I_0$$

La evolución espacio-temporal de la temperatura $T(\mathbf{r}, t)$ en el medio circundante (agua desionizada sobre sustrato de vidrio) obedece a la ecuación de Fourier generalizada:

$$\rho C_p \frac{\partial T(\mathbf{r}, t)}{\partial t} - \nabla \cdot \left[ \kappa(T) \nabla T(\mathbf{r}, t) \right] = Q_{\text{source}}(\mathbf{r}, t)$$

```
                                  EFECTO LENTE TÉRMICA (THERMAL LENS)
                 
               Haz Láser Incidente (TEM00)                Lente Divergente (dn/dT < 0)
                   ───────────────────────►                  \
                                            Nanopartícula     \   Frente de onda distorsionado
                   ───────────────────────►    ● (Joule)       \
                                            T_nano >> T_inf     ────────► Detector / Pinhole
                   ───────────────────────►                    /          (Señal fotométrica Delta I)
                                                              /
                 ────────────────────────────────────────────/
                            Sustrato de Vidrio (Heat Sink)
```

### 2.1 Tiempo Característico de Difusión Térmica $t_c$
Para una cintura de haz focalizada con radio en el foco $w_0$ (típicamente $w_0 \approx 0.8 - 1.2\ \mu\text{m}$ con objetivo de inmersión en agua 60xW), el tiempo característico de difusión térmica del medio es:

$$t_c = \frac{w_0^2}{4 D_{\text{th}}} = \frac{w_0^2 \rho C_p}{4 \kappa}$$

Para agua a $20^\circ\text{C}$ ($\rho = 1000\ \text{kg/m}^3$, $C_p = 4184\ \text{J/(kg}\cdot\text{K)}$, $\kappa = 0.60\ \text{W/(m}\cdot\text{K)}$):
$$D_{\text{th}} = \frac{\kappa}{\rho C_p} = \frac{0.60}{1000 \times 4184} \approx 1.43 \times 10^{-7}\ \text{m}^2/\text{s}$$
$$t_c = \frac{(1.0 \times 10^{-6}\ \text{m})^2}{4 (1.43 \times 10^{-7}\ \text{m}^2/\text{s})} \approx 1.75\ \mu\text{s}$$

Dado que $t_c \ll 1\ \text{ms}$, el régimen térmico alcanza el estado estacionario de forma casi instantánea frente a la escala de muestreo del fotodiodo en PyPrinting 3.0 ($10\ \text{kHz} \implies \Delta t_{\text{sample}} = 100\ \mu\text{s}$).

---

## 3. Gradiente Termo-Óptico y Distorsión de Fase del Frente de Onda

La dependencia del índice de refracción del solvente con respecto a la temperatura se linealiza mediante la expansión en serie de Taylor alrededor de la temperatura ambiente $T_0 = 293.15\ \text{K}$:

$$n(\mathbf{r}) = n_0 + \left( \frac{dn}{dT} \right) \left[ T(\mathbf{r}) - T_0 \right]$$

| Parámetro Termofísico | Símbolo | Valor Típico | Unidades |
|---|:---:|:---:|:---:|
| Coeficiente termo-óptico del agua ($20^\circ\text{C}$, $\lambda = 532\ \text{nm}$) | $dn/dT$ | $-9.1 \times 10^{-5}$ | $\text{K}^{-1}$ |
| Coeficiente termo-óptico del vidrio (BK7) | $(dn/dT)_{\text{vidrio}}$ | $+3.0 \times 10^{-6}$ | $\text{K}^{-1}$ |
| Conductividad térmica del agua | $\kappa_{\text{agua}}$ | $0.60$ | $\text{W}/(\text{m}\cdot\text{K})$ |
| Conductividad térmica del vidrio BK7 | $\kappa_{\text{vidrio}}$ | $1.11$ | $\text{W}/(\text{m}\cdot\text{K})$ |

Dado que $dn/dT < 0$ para el agua líquida, las regiones más calientes cercanas al centro del haz poseen un índice de refracción más bajo. La velocidad de fase de la luz $v = c/n$ es mayor en el centro que en la periferia, curvando el frente de onda hacia afuera y actuando como una **lente cóncava divergente**.

### 3.1 Corrimiento de Fase Transverso $\Delta\Phi(r)$
Al atravesar la celda de espesor $L$ a lo largo del eje óptico $z$:

$$\Delta\Phi(r) = \frac{2 \pi}{\lambda_0} \int_0^L \Delta n(r, z) dz = \frac{2 \pi}{\lambda_0} \left( \frac{dn}{dT} \right) \int_0^L \Delta T(r, z) dz$$

Aproximando la distribución radial del incremento térmico por un perfil casi-gaussiano $\Delta T(r) \approx \Delta T_0 \exp(-2r^2/w_0^2)$:

$$\Delta\Phi(r) \approx \Phi_0 \left[ 1 - \frac{2r^2}{w_0^2} \right]$$

donde el corrimiento de fase térmico en el vértice es:

$$\Phi_0 = \theta = \frac{P_{\text{abs}} (dn/dT)}{\lambda_0 \kappa}$$

---

## 4. Señal Fotométrica en Detección Confocal con Pinhole

En el canal confocal de PyPrinting 3.0 (`[[CAT-108_Teoria_Optica_Telescopio_Rele_4f_y_Canales_Confocales]]`), la luz transmitida se enfoca sobre un fotodiodo precedido por una apertura micrométrica (pinhole) en el plano imagen conjugado. La irradiancia en el centro de la pupila sufre una modulación de intensidad debida a la defocalización térmica:

$$\frac{\Delta I(t)}{I_0} = \frac{I(t) - I_0}{I_0} \approx \frac{2 \theta}{1 + (t_c / 2t)}$$

En el límite estacionario ($t \gg t_c$):

$$\left( \frac{\Delta I}{I_0} \right)_{\text{estacionario}} \approx 2 \theta = \frac{2 P_{\text{abs}} (dn/dT)}{\lambda_0 \kappa}$$

Esta relación lineal directa permite una **calibración fotométrica absoluta**: al medir la caída relativa en voltios $\Delta V / V_0$ en el fotodiodo analógico acoplado a la tarjeta NI-DAQmx, se infiere directamente la potencia disipada $P_{\text{abs}}$ sin necesidad de recolectar la luz esparcida en todo el ángulo sólido.

```
                    MODULACIÓN TRANSITORIA DE LA SEÑAL FOTODÍODO
          
        Voltaje V(t)
             ▲
          V0 ┼─────────╮
             │         ╰─────────────────────────────── Nivel base estacionario
             │          ◄──── tc ~ 1.75 µs ────►        Delta V = 2 * theta * V0
             │
             └─────────────────────────────────────────► Tiempo t
```

---

## 5. Micro-Convección Termocapilar de Marangoni

En la vecindad de la interfase líquido-aire o líquido-sustrato de la celda de impresión, el gradiente de temperatura genera un gradiente en la tensión superficial $\gamma(T)$. Como la tensión superficial del agua decrece con la temperatura:

$$\gamma(T) = \gamma_0 - \beta_T \left( T - T_0 \right), \quad \beta_T = -\frac{d\gamma}{dT} \approx 0.16 \times 10^{-3}\ \text{N/(m}\cdot\text{K)}$$

Este gradiente de tensión superficial induce un esfuerzo cortante tangencial $\mathbf{\tau}_M$ sobre la superficie libre del fluido (condición de contorno de Marangoni):

$$\mathbf{\tau}_M = \nabla_s \gamma = -\beta_T \nabla_\parallel T$$

El líquido es arrastrado desde las regiones calientes (menor $\gamma$) hacia las regiones frías (mayor $\gamma$), estableciendo celdas de recirculación hidrodinámica toroidales alrededor del punto de impresión:

```
                            CELDA DE CONVECCIÓN DE MARANGONI
                                   
                                      Hacia zonas frías (Alta gamma)
                               ◄─────────────────────────────
                                 ╭────────────────────────╮
                                 │       Líquido          │
                                 │   ▲        AuNP    ▲   │
                                 │   │         ●      │   │
                                 ╰───┴─────────┬──────┴───╯
                                               ▼
                                      Zona caliente (Baja gamma)
```

### 5.1 Velocidad Convectiva y Fuerza de Arrastre de Stokes sobre Nanopartículas Adyacentes
La velocidad característica de convección termocapilar en una película de espesor $h \approx 100\ \mu\text{m}$ es:

$$v_M \approx \frac{\beta_T \Delta T_{\text{surf}} h}{4 \eta}$$

Con $\Delta T_{\text{surf}} \approx 15\ \text{K}$, $\eta \approx 1.0 \times 10^{-3}\ \text{Pa}\cdot\text{s}$:
$$v_M \approx \frac{(0.16 \times 10^{-3}\ \text{N/m}\cdot\text{K})(15\ \text{K})(100 \times 10^{-6}\ \text{m})}{4 (1.0 \times 10^{-3}\ \text{Pa}\cdot\text{s})} \approx 60\ \mu\text{m/s}$$

Esta corriente induce una fuerza de arrastre hidrodinámico de Stokes sobre coloides libres adyacentes de radio $R$:

$$\mathbf{F}_{\text{drag}} = 6 \pi \eta R \mathbf{v}_M \sim 4.5 \times 10^{-14}\ \text{N} = 0.045\ \text{pN}$$

En la celda confinada de PyPrinting 3.0, el uso de cubreobjetos sellados previene la interfase libre líquido-aire, suprimiendo la convección de Marangoni superficial y limitando el transporte exclusivamente a la termoforesis natural (fuerza de Ludwig-Soret: $\mathbf{v}_{\text{th}} = -D_T \nabla T$), garantizando la estabilidad posicional de la red cristalina.

---

## 6. Límite Crítico de Ebullición Microscópica (*Nanobubbles*)

Para asegurar la integridad estructural de la red 2D y la inmovilización sin desprendimiento, la temperatura superficial $T_{\text{surf}}$ debe mantenerse estrictamente por debajo del umbral de nucleación espinodal de vapor en agua sobrecalentada:

$$T_{\text{surf}} < T_{\text{espinodal}} \approx 280^\circ\text{C} - 300^\circ\text{C} \quad (553\ \text{K} - 573\ \text{K})$$

Si la potencia supera este umbral, se genera una nanoburbuja de vapor que colapsa violentamente (cavitación acústica), expulsando la partícula inmovilizada y destruyendo la funcionalización de APTES (`[[CAT-110_Fisicoquimica_Coloides_DLVO_y_Funcionalizacion_Superficies]]`). El sistema de software impone en `config.py` un límite duro de potencia de corte $P_{\text{laser}} \le 12.0\ \text{mW}$ para coloides de oro de $80\ \text{nm}$, asegurando $\Delta T_{\text{surf}} < 45\ \text{K}$ con un margen de seguridad de $> 200\ \text{K}$.

---

## 7. Implementación Computacional en Python

```python
"""
CAT-112: Modelo de Lente Térmica Fototérmica y Convección de Marangoni.
Simulación del perfil térmico, distorsión de fase y modulación de pinhole confocal.
"""
from typing import Tuple
import numpy as np

class ThermalLensModel:
    def __init__(
        self,
        wavelength_m: float = 532e-9,
        beam_waist_m: float = 1.0e-6,
        kappa_solvent: float = 0.60,      # W/(m*K) - Agua
        dndT_solvent: float = -9.1e-5,    # 1/K - Agua
        sigma_abs_m2: float = 8.2e-15,    # AuNP 80nm a 532nm
    ):
        self.wl = wavelength_m
        self.w0 = beam_waist_m
        self.kappa = kappa_solvent
        self.dndT = dndT_solvent
        self.sigma_abs = sigma_abs_m2

    def steady_state_temperature_rise(self, power_w: float, r_m: np.ndarray) -> np.ndarray:
        """Calcula el incremento de temperatura radial Delta T(r) en estado estacionario."""
        i0 = (2.0 * power_w) / (np.pi * self.w0**2)
        p_abs = self.sigma_abs * i0
        r_safe = np.maximum(r_m, 40e-9)
        return p_abs / (4.0 * np.pi * self.kappa * r_safe)

    def phase_shift_parameter_theta(self, power_w: float) -> float:
        """Calcula el parámetro de corrimiento de fase theta de la lente térmica."""
        i0 = (2.0 * power_w) / (np.pi * self.w0**2)
        p_abs = self.sigma_abs * i0
        return float((p_abs * self.dndT) / (self.wl * self.kappa))

    def confocal_photodiode_relative_signal(self, power_w: float) -> float:
        """Calcula la variación relativa de irradiancia Delta I / I0 en el pinhole confocal."""
        theta = self.phase_shift_parameter_theta(power_w)
        return float(2.0 * theta)

    def marangoni_stress_n_per_m2(self, grad_t_k_per_m: float, beta_t: float = 0.16e-3) -> float:
        """Calcula el esfuerzo tangencial de Marangoni en la interfase libre."""
        return float(-beta_t * grad_t_k_per_m)
```

---

## 8. Conclusiones y Conexión Instrumental

1. El efecto de Lente Térmica actúa como un transductor optofísico directo de la absorción individual de nanopartículas, detectado en tiempo real en la rutina de printing (`modules/measurements.py`).
2. El confinamiento de la celda fluídica previene las corrientes de Marangoni, asegurando que el acoplamiento óptico no altere las coordenadas de las partículas previamente depositadas en la grilla 2D.
